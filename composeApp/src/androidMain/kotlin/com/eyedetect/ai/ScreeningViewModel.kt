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
import com.eyedetect.ai.ui.components.QualityLevel
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
 * [api] va [healthCheck] standart holatda [ApiClient]ga bog'lanadi — testlarda soxta
 * implementatsiya berish uchun almashtiriladi (`@JvmOverloads` androidx `viewModel()`
 * factory'si `Application`dan qurish uchun konstruktorni topa olishi kerak).
 */
class ScreeningViewModel @JvmOverloads constructor(
    application: Application,
    private val api: ApiService = ApiClient.service,
    private val healthCheck: suspend () -> Boolean = { ApiClient.ping() },
    private val polling: PredictPolling = PredictPolling(),
) : AndroidViewModel(application) {

    private val historyRepo = ScreeningHistoryRepository(application)
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

    private suspend fun handleOfflineSync(e: Exception, bytes: ByteArray): Boolean {
        if (e is java.net.UnknownHostException || e is java.net.ConnectException ||
            e is java.net.SocketTimeoutException || e is HttpRequestTimeoutException
        ) {
            val app = getApplication<Application>()
            
            // Faylni diskka saqlash
            val pendingDir = File(app.filesDir, "pending_uploads").apply { mkdirs() }
            val fileName = "pending_${System.currentTimeMillis()}.jpg"
            val pendingFile = File(pendingDir, fileName)
            
            withContext(Dispatchers.IO) { pendingFile.writeBytes(bytes) }
            
            // Bazaga saqlash
            historyRepo.savePending(
                patientId = patientId.ifBlank { null },
                eye = eye,
                heuristic = _localHeuristic.value,
                filePath = pendingFile.absolutePath
            )
            
            // WorkManager'ga topshirish
            val constraints = androidx.work.Constraints.Builder()
                .setRequiredNetworkType(androidx.work.NetworkType.CONNECTED)
                .build()
                
            val workRequest = androidx.work.OneTimeWorkRequestBuilder<com.eyedetect.ai.worker.SyncWorker>()
                .setConstraints(constraints)
                .build()
                
            androidx.work.WorkManager.getInstance(app).enqueue(workRequest)
            
            return true
        }
        return false
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
            try {
                // Fayl o'chirilishidan oldin baytlarini o'qib olamiz (evristika uchun),
                // keyin tahlilni fonda, yuklashni bloklamay ishga tushiramiz.
                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeFileScaled(file.absolutePath) }
                if (bitmap != null) {
                    runHeuristicAsync(bitmap, rowId)
                    // TFLite orqali oflayn tahlil
                    val offlineResult = withContext(Dispatchers.Default) { offlineClassifier.predict(bitmap, eye) }
                    if (offlineResult != null) {
                        _uiState.value = UiState.OfflineSuccess(offlineResult)
                    }
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
                if (uploadBytes != null && handleOfflineSync(e, uploadBytes)) {
                    if (_uiState.value !is UiState.OfflineSuccess) {
                        _uiState.value = UiState.Error("Internet yo'q. Rasm saqlandi, tarmoq kelganda avtomatik yuboriladi.", canRetry = false)
                    }
                } else {
                    if (_uiState.value !is UiState.OfflineSuccess) {
                        _uiState.value = UiState.Error(friendly(e), canRetry = true)
                    }
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
            try {
                uploadBytes = withContext(Dispatchers.IO) {
                    appContext.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException(appContext.getString(R.string.error_cannot_read_image))

                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeBytesScaled(uploadBytes) }
                if (bitmap != null) {
                    runHeuristicAsync(bitmap, rowId)
                    // TFLite orqali oflayn tahlil
                    val offlineResult = withContext(Dispatchers.Default) { offlineClassifier.predict(bitmap, eye) }
                    if (offlineResult != null) {
                        _uiState.value = UiState.OfflineSuccess(offlineResult)
                    }
                } else {
                    rowId.complete(null)
                }

                val finalBytes = compressUploadBytes(uploadBytes)
                doRequest(finalBytes, "gallery.jpg", rowId)

                currentSource = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (uploadBytes != null && handleOfflineSync(e, uploadBytes)) {
                    if (_uiState.value !is UiState.OfflineSuccess) {
                        _uiState.value = UiState.Error("Internet yo'q. Rasm saqlandi, tarmoq kelganda avtomatik yuboriladi.", canRetry = false)
                    }
                } else {
                    if (_uiState.value !is UiState.OfflineSuccess) {
                        _uiState.value = UiState.Error(friendly(e), canRetry = true)
                    }
                }
                if (!rowId.isCompleted) rowId.complete(null)
            } finally {
                _uploadProgress.value = null
            }
        }
    }

    /**
     * Qorachiq evristikasini (ML Kit ACCURATE rejimi tufayli sekinroq) alohida, backend
     * so'rovini bloklamaydigan koroutinada ishga tushiradi. Natija tayyor bo'lgach:
     * (1) tarix yozuviga ([rowId] tayyor bo'lishini kutib) qo'shiladi,
     * (2) qarshi ko'zning oldingi natijasi bilan simmetriya solishtiriladi.
     * Xato bo'lsa jim o'tkazib yuboriladi — bu ixtiyoriy qo'shimcha ko'rsatkich.
     */
    private fun runHeuristicAsync(bitmap: Bitmap, rowId: CompletableDeferred<Long?>) {
        viewModelScope.launch(Dispatchers.Default) {
            val result = runCatching { PupilHeuristics.analyze(bitmap, eye) }.getOrNull()
            bitmap.recycle()
            if (result == null) return@launch
            _localHeuristic.value = result

            val id = withTimeoutOrNull(15_000) { rowId.await() }
            if (id != null) {
                runCatching { historyRepo.updateHeuristic(id, result) }
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
        val previous = runCatching { historyRepo.latestFor(pid, otherEye) }.getOrNull() ?: return
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
        // Tarixga saqlash
        val id = runCatching { historyRepo.saveResult(result, _localHeuristic.value) }.getOrNull()
        if (!rowId.isCompleted) rowId.complete(id)
    }

    /** Texnik xatoni foydalanuvchiga tushunarli, joriy tildagi xabarga aylantiradi. */
    private suspend fun friendly(e: Exception): String {
        val app = getApplication<Application>()
        return when (e) {
            is java.net.UnknownHostException,
            is java.net.ConnectException ->
                app.getString(R.string.error_no_connection)
            is java.net.SocketTimeoutException,
            is HttpRequestTimeoutException,
            is PredictTimeoutException ->
                app.getString(R.string.error_timeout)
            is java.net.UnknownServiceException ->
                app.getString(R.string.error_https_required)
            is ResponseException -> httpErrorMessage(e)
            else -> e.message ?: app.getString(R.string.error_unknown)
        }
    }

    private suspend fun httpErrorMessage(e: ResponseException): String {
        val app = getApplication<Application>()
        val detail = runCatching {
            val body = e.response.bodyAsText()
            Json.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.content?.ifBlank { null }
        }.getOrNull()
        if (!detail.isNullOrBlank()) return detail

        val code = e.response.status.value
        return when (code) {
            400, 422 -> app.getString(R.string.error_bad_request)
            401, 403 -> app.getString(R.string.error_unauthorized)
            404 -> app.getString(R.string.error_not_found)
            429 -> app.getString(R.string.error_too_many_requests)
            in 500..599 -> app.getString(R.string.error_server)
            else -> app.getString(R.string.error_http_generic, code)
        }
    }
}
