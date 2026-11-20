package com.eyedetect.ai

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.ApiService
import com.eyedetect.ai.data.PredictPolling
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.data.PredictTimeoutException
import com.eyedetect.ai.data.predictAndAwait
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.data.history.ScreeningHistoryStore
import com.eyedetect.ai.data.upload.PendingUploadRepository
import com.eyedetect.ai.data.upload.PendingUploadStore
import com.eyedetect.ai.ui.components.QualityLevel
import com.eyedetect.ai.upload.UploadScheduler
import com.eyedetect.ai.vision.BitmapLoader
import com.eyedetect.ai.vision.EyeSymmetryAnalyzer
import com.eyedetect.ai.vision.EyeSymmetryResult
import com.eyedetect.ai.vision.EyeSymmetrySample
import com.eyedetect.ai.vision.PupilHeuristicResult
import com.eyedetect.ai.vision.PupilHeuristics
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.ResponseException
import io.ktor.client.statement.bodyAsText
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import androidx.compose.runtime.Immutable
import java.net.ConnectException
import java.net.UnknownHostException

/** UI holati (ekranlar shu holatga qarab chiziladi). */
@Immutable
sealed interface UiState {
    data object Idle : UiState
    data object Loading : UiState
    data class Success(val result: PredictResponse) : UiState
    data class OfflineSuccess(val result: PredictResponse) : UiState
    /** [canRetry] true bo'lsa, so'nggi so'rov manbai (fayl/URI) hali mavjud — foydalanuvchi
     * qaytadan suratga olmasdan xuddi shu rasmni qayta yuborishi mumkin ([retry]). */
    data class Error(val message: String, val canRetry: Boolean = false) : UiState
    /** Internet yo'qligi sababli so'rov navbatga qo'yildi ([WorkManager][com.eyedetect.ai.upload.UploadWorker]
     * ulanish tiklangach avtomatik yuboradi) — qayta suratga olish shart emas. */
    data object Queued : UiState
}

/** Ikki ko'z simmetriyasini solishtirish natijasi + qaysi ko'z/qachon bilan solishtirilgani. */
@Immutable
data class EyeSymmetryUiState(
    val comparison: EyeSymmetryResult,
    val comparedEye: String?,
    val comparedAtMs: Long,
)

/**
 * Skrining oqimi ViewModel'i: bemor ID, rasm yuborish va natija holatini boshqaradi.
 * [api], [healthCheck], [historyStore], [pendingUploadStore] va [scheduleUpload] standart
 * holatda haqiqiy implementatsiyalarga bog'lanadi — testlarda soxta implementatsiya berish
 * uchun almashtiriladi (`@JvmOverloads` androidx `viewModel()` factory'si `Application`dan
 * qurish uchun konstruktorni topa olishi kerak). [historyStore]/[pendingUploadStore] alohida
 * in'eksiya qilinadi, chunki haqiqiy [ScreeningHistoryRepository]/[PendingUploadRepository]
 * bir xil SQLCipher orqali shifrlangan Room bazasini ochadi — uning native kutubxonasi
 * Robolectric (JVM) birlik testlarida yuklanmaydi. [scheduleUpload] ham xuddi shu sababdan
 * (birlik testlarida haqiqiy WorkManager infratuzilmasi kerak emas) inject qilinadi.
 */
class ScreeningViewModel @JvmOverloads constructor(
    application: Application,
    private val api: ApiService = ApiClient.service,
    private val healthCheck: suspend () -> Boolean = { ApiClient.ping() },
    private val historyStore: ScreeningHistoryStore = ScreeningHistoryRepository(application),
    private val pendingUploadStore: PendingUploadStore = PendingUploadRepository(application),
    private val scheduleUpload: (Long) -> Unit = { id -> UploadScheduler.enqueue(application, id) },
    private val polling: PredictPolling = PredictPolling(),
) : AndroidViewModel(application) {

    private val offlineClassifier = com.eyedetect.ai.vision.OfflineDrClassifier(application)

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    // Mahalliy CV evristikasi (opacity/red-reflex) — backend natijasidan mustaqil,
    // tayyor bo'lishi bilanoq (odatda biroz kechroq) yangilanadi. Diagnostika emas.
    private val _localHeuristic = MutableStateFlow<PupilHeuristicResult?>(null)
    val localHeuristic: StateFlow<PupilHeuristicResult?> = _localHeuristic.asStateFlow()

    // Ikki ko'z simmetriyasi — faqat bemor ID kiritilgan va qarshi ko'z uchun avvalgi
    // yozuv (evristika bilan) topilganda hisoblanadi.
    private val _symmetry = MutableStateFlow<EyeSymmetryUiState?>(null)
    val symmetry: StateFlow<EyeSymmetryUiState?> = _symmetry.asStateFlow()

    // Multipart so'rovning haqiqiy yuklash progressi (0f..1f) — faqat baytlar jo'natilayotgan
    // paytda; tugagach (muvaffaqiyat/xato/bekor) null'ga qaytadi.
    private val _uploadProgress = MutableStateFlow<Float?>(null)
    val uploadProgress: StateFlow<Float?> = _uploadProgress.asStateFlow()

    // Backend bilan tezkor ulanish holati — null = hali tekshirilmagan/tekshirilmoqda.
    private val _backendOnline = MutableStateFlow<Boolean?>(null)
    val backendOnline: StateFlow<Boolean?> = _backendOnline.asStateFlow()

    var patientId: String = ""
    var eye: String = "right"   // "right" | "left"

    /** So'nggi yuborilgan (yoki yuborilmoqchi bo'lgan) rasm manbai — xato bo'lsa [retry] shu
     * orqali xuddi shu rasmni qaytadan yuboradi (foydalanuvchi qayta suratga olmasdan). */
    private sealed interface UploadSource {
        data class FromFile(val file: File) : UploadSource
        data class FromGalleryUri(val appContext: Context, val uri: Uri) : UploadSource
    }
    private var currentSource: UploadSource? = null
    private var activeJob: Job? = null

    fun checkBackendHealth() {
        viewModelScope.launch {
            _backendOnline.value = runCatching { healthCheck() }.getOrDefault(false)
        }
    }

    /** Joriy so'rovni bekor qiladi (masalan, foydalanuvchi natija kutayotganda orqaga
     * qaytsa) va tozalaydi — qayta suratga olish talab qilinadi (fayl o'chiriladi). */
    fun cancelUpload() {
        val fileToDelete = (currentSource as? UploadSource.FromFile)?.file
        cancelActiveJobAndDeleteAfter(fileToDelete)
        _uploadProgress.value = null
        _localHeuristic.value = null
        _symmetry.value = null
        currentSource = null
        _uiState.value = UiState.Idle
    }

    fun reset() {
        val fileToDelete = (currentSource as? UploadSource.FromFile)?.file
        cancelActiveJobAndDeleteAfter(fileToDelete)
        _uploadProgress.value = null
        currentSource = null
        _uiState.value = UiState.Idle
        _localHeuristic.value = null
        _symmetry.value = null
    }

    /** [file]ni darhol o'chirishga urinish xavfli — [activeJob] hali fon threadida (masalan,
     * `BitmapLoader`da) faylni o'qiyotgan bo'lishi mumkin, va Windows'da ochiq fayl
     * o'chirilmaydi. Shu sababli avval joyni ega bo'lgan job to'liq to'xtashini kutamiz
     * (`join`), keyingina o'chiramiz — alohida, bekor qilinmagan koroutinada. */
    private fun cancelActiveJobAndDeleteAfter(file: File?) {
        val jobToJoin = activeJob
        activeJob?.cancel()
        activeJob = null
        if (file != null) {
            viewModelScope.launch {
                jobToJoin?.join()
                if (file.exists()) file.delete()
            }
        }
    }

    /** Oxirgi xato holatidagi rasmni (fayl yoki galereya URI'si) qaytadan, o'sha holicha
     * yuboradi — foydalanuvchi qayta suratga olishga majbur bo'lmaydi. */
    fun retry() {
        when (val src = currentSource) {
            is UploadSource.FromFile ->
                if (src.file.exists()) uploadFile(src.file)
                else _uiState.value = UiState.Error(
                    getApplication<Application>().getString(R.string.error_retry_unavailable),
                )
            is UploadSource.FromGalleryUri -> uploadUri(src.appContext, src.uri)
            null -> Unit
        }
    }

    /** Yuklashdan oldin rasmni siqadi (uzun tomoni ~1500px, JPEG ~85%) — to'liq o'lchamdagi
     * kamera surati sekin/qimmat mobil internetga mos emas. Siqish muvaffaqiyatsiz bo'lsa
     * (masalan, kutilmagan format) asl baytlar o'zgarishsiz yuboriladi. */
    private suspend fun compressUploadBytes(bytes: ByteArray): ByteArray {
        val compressed = withContext(Dispatchers.Default) { BitmapLoader.compressForUpload(bytes) }
        return compressed ?: bytes
    }

    /** Faylni (kameradan) yuboradi; faqat muvaffaqiyatda o'chiriladi — xato bo'lsa [retry]
     * uchun saqlanadi. */
    fun uploadFile(file: File) {
        currentSource = UploadSource.FromFile(file)
        activeJob = viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uploadProgress.value = 0f
            _localHeuristic.value = null
            _symmetry.value = null
            val rowId = CompletableDeferred<Long?>()
            var uploadBytes: ByteArray? = null
            var offlineResult: PredictResponse? = null
            try {
                // Fayl o'chirilishidan oldin baytlarini o'qib olamiz (evristika uchun),
                // keyin tahlilni fonda, yuklashni bloklamay ishga tushiramiz.
                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeFileScaled(file.absolutePath) }
                if (bitmap != null) {
                    runHeuristicAsync(bitmap, rowId)
                    // TFLite orqali oflayn tahlil — faqat tayyorlab qo'yiladi; ekranda
                    // server javobi kelmasa (internet yo'q, rasm navbatga qo'yilganda)
                    // ko'rsatiladi, aks holda yuklanish holati server javobigacha turadi.
                    offlineResult = withContext(Dispatchers.Default) { offlineClassifier.predict(bitmap, eye) }
                } else {
                    rowId.complete(null)
                }

                uploadBytes = withContext(Dispatchers.IO) { file.readBytes() }
                val finalBytes = compressUploadBytes(uploadBytes)
                doRequest(finalBytes, file.name, rowId)

                file.delete()
                currentSource = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val bytesForQueue = uploadBytes
                    ?: if (file.exists()) withContext(Dispatchers.IO) { file.readBytes() } else null
                if (isOfflineError(e) && bytesForQueue != null) {
                    queueForOffline(bytesForQueue, "image/jpeg")
                    file.delete()
                    currentSource = null
                    // Qurilmadagi TFLite natijasi bo'lsa, shuni ko'rsatamiz (rasm baribir navbatda).
                    _uiState.value = offlineResult?.let { UiState.OfflineSuccess(it) } ?: UiState.Queued
                } else {
                    _uiState.value = UiState.Error(friendly(e), canRetry = true)
                }
                if (!rowId.isCompleted) rowId.complete(null)
            } finally {
                _uploadProgress.value = null
            }
        }
    }

    /** Galereyadan tanlangan Uri'ni yuboradi (zaxira rejim, reja 3.3). Doimiy fayl
     * yaratilmagani uchun xato bo'lsa ham [retry] uchun URI o'zi saqlanib qoladi. */
    fun uploadUri(context: Context, uri: Uri) {
        val appContext = context.applicationContext
        currentSource = UploadSource.FromGalleryUri(appContext, uri)
        activeJob = viewModelScope.launch {
            _uiState.value = UiState.Loading
            _uploadProgress.value = 0f
            _localHeuristic.value = null
            _symmetry.value = null
            val rowId = CompletableDeferred<Long?>()
            var uploadBytes: ByteArray? = null
            var offlineResult: PredictResponse? = null
            try {
                uploadBytes = withContext(Dispatchers.IO) {
                    appContext.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException(appContext.getString(R.string.error_cannot_read_image))

                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeBytesScaled(uploadBytes) }
                if (bitmap != null) {
                    runHeuristicAsync(bitmap, rowId)
                    // TFLite orqali oflayn tahlil — faqat tayyorlab qo'yiladi; ekranda
                    // server javobi kelmasa (internet yo'q, rasm navbatga qo'yilganda)
                    // ko'rsatiladi, aks holda yuklanish holati server javobigacha turadi.
                    offlineResult = withContext(Dispatchers.Default) { offlineClassifier.predict(bitmap, eye) }
                } else {
                    rowId.complete(null)
                }

                val finalBytes = compressUploadBytes(uploadBytes)
                doRequest(finalBytes, "gallery.jpg", rowId)

                currentSource = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                val bytesForQueue = uploadBytes
                if (isOfflineError(e) && bytesForQueue != null) {
                    queueForOffline(bytesForQueue, "image/*")
                    currentSource = null
                    _uiState.value = offlineResult?.let { UiState.OfflineSuccess(it) } ?: UiState.Queued
                } else {
                    _uiState.value = UiState.Error(friendly(e), canRetry = true)
                }
                if (!rowId.isCompleted) rowId.complete(null)
            } finally {
                _uploadProgress.value = null
            }
        }
    }

    /** Ulanish umuman yo'qligi (DNS topilmadi / ulanib bo'lmadi) — bunday holatlarda so'rovni
     * xato sifatida ko'rsatib qayta urinishni foydalanuvchiga qoldirish o'rniga darhol
     * navbatga qo'yish ma'noliroq (ulanish tiklanmaguncha qayta urinish baribir
     * muvaffaqiyatsiz bo'ladi). [SocketTimeoutException] atayin bunga kirmaydi — bu server
     * sekin javob berayotganini ham bildirishi mumkin (tarmoq mavjud), shu sababli oddiy
     * "Qayta urinish" xato holati saqlanib qoladi. HTTPS/sertifikat xatosi
     * ([java.net.UnknownServiceException]) ham kirmaydi — bu konfiguratsiya muammosi, qayta
     * urinish (yoki navbatga qo'yish) yordam bermaydi. */
    private fun isOfflineError(e: Exception): Boolean =
        e is UnknownHostException || e is ConnectException

    /** Rasmni doimiy saqlash joyiga yozadi va [UploadScheduler] orqali WorkManager vazifasini
     * rejalashtiradi — ulanish tiklangach [com.eyedetect.ai.upload.UploadWorker] avtomatik yuboradi. */
    private suspend fun queueForOffline(bytes: ByteArray, fallbackMediaType: String) {
        val id = pendingUploadStore.enqueue(bytes, patientId.ifBlank { null }, eye, fallbackMediaType)
        scheduleUpload(id)
    }

    /**
     * Qorachiq evristikasini (ML Kit ACCURATE rejimi tufayli sekinroq) alohida, backend
     * so'rovini bloklamaydigan koroutinada ishga tushiradi. Natija tayyor bo'lgach:
     * (1) tarix yozuviga ([rowId] tayyor bo'lishini kutib) qo'shiladi,
     * (2) qarshi ko'zning oldingi natijasi bilan simmetriya solishtiriladi.
     * Xato bo'lsa jim o'tkazib yuboriladi — bu ixtiyoriy qo'shimcha ko'rsatkich.
     */
    private fun runHeuristicAsync(bitmap: Bitmap, rowId: CompletableDeferred<Long?>) {
        val appContext = getApplication<Application>()
        viewModelScope.launch(Dispatchers.Default) {
            val result = runCatching { PupilHeuristics.analyze(appContext, bitmap, eye) }.getOrNull()
            bitmap.recycle()
            if (result == null) return@launch
            _localHeuristic.value = result

            val id = withTimeoutOrNull(15_000) { rowId.await() }
            if (id != null) {
                runCatching { historyStore.updateHeuristic(id, result) }
            }
            computeSymmetry(result)
        }
    }

    /** Joriy ko'z natijasini, bemorning qarshi ko'zi uchun saqlangan oxirgi yozuv bilan
     * solishtiradi (agar bemor ID kiritilgan va qarshi ko'zda evristika ma'lumoti bo'lsa). */
    private suspend fun computeSymmetry(current: PupilHeuristicResult) {
        val pid = patientId.trim()
        if (pid.isBlank() || !current.regionFound) return
        val otherEye = if (eye == "left") "right" else "left"
        val previous = runCatching { historyStore.latestFor(pid, otherEye) }.getOrNull() ?: return
        val previousSample = previous.toSymmetrySample() ?: return

        val currentSample = EyeSymmetrySample(
            opacity = current.opacity,
            redReflex = current.redReflex,
            hueDeg = current.darkMeanHueDeg,
            saturation = current.darkMeanSaturation,
            value = current.darkMeanValue,
        )
        val comparison = EyeSymmetryAnalyzer.compare(currentSample, previousSample)
        _symmetry.value = EyeSymmetryUiState(comparison, previous.eye, previous.savedAtMs)
    }

    private fun ScreeningHistoryEntity.toSymmetrySample(): EyeSymmetrySample? {
        val opacityLevel = localOpacity?.let { runCatching { QualityLevel.valueOf(it) }.getOrNull() }
        val redReflexLevel = localRedReflex?.let { runCatching { QualityLevel.valueOf(it) }.getOrNull() }
        if (opacityLevel == null || redReflexLevel == null || localHueDeg == null || localSaturation == null || localValue == null) {
            return null
        }
        return EyeSymmetrySample(opacityLevel, redReflexLevel, localHueDeg, localSaturation, localValue)
    }

    private suspend fun doRequest(uploadBytes: ByteArray, fileName: String, rowId: CompletableDeferred<Long?>) {
        val pid = patientId.ifBlank { null }
        
        val result = api.predictAndAwait(
            fileBytes = uploadBytes,
            fileName = fileName,
            patientId = pid,
            eye = eye,
            onProgress = { _uploadProgress.value = it },
            polling = polling,
        )

        _uiState.value = UiState.Success(result)
        // Tarixga saqlash — shu payt mahalliy evristika hali tayyor bo'lmasa (odatda
        // sekinroq, backend javobidan keyin ham kelishi mumkin), holsiz saqlanadi;
        // tayyor bo'lgach `runHeuristicAsync` shu ID orqali to'ldiradi.
        val id = runCatching { historyStore.saveResult(result, _localHeuristic.value) }.getOrNull()
        if (!rowId.isCompleted) rowId.complete(id)
    }

    /** Texnik xatoni foydalanuvchiga tushunarli, joriy tildagi xabarga aylantiradi. */
    private suspend fun friendly(e: Exception): String =
        friendlyErrorMessage(getApplication<Application>(), e)
}
