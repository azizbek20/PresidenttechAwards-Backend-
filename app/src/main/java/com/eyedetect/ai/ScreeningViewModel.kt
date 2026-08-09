package com.eyedetect.ai

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.ApiService
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.data.ProgressRequestBody
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
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
import java.io.File

/** UI holati (ekranlar shu holatga qarab chiziladi). */
sealed interface UiState {
    data object Idle : UiState
    data object Loading : UiState
    data class Success(val result: PredictResponse) : UiState
    /** [canRetry] true bo'lsa, so'nggi so'rov manbai (fayl/URI) hali mavjud — foydalanuvchi
     * qaytadan suratga olmasdan xuddi shu rasmni qayta yuborishi mumkin ([retry]). */
    data class Error(val message: String, val canRetry: Boolean = false) : UiState
}

/** Ikki ko'z simmetriyasini solishtirish natijasi + qaysi ko'z/qachon bilan solishtirilgani. */
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
) : AndroidViewModel(application) {

    private val historyRepo = ScreeningHistoryRepository(application)

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
            try {
                // Fayl o'chirilishidan oldin baytlarini o'qib olamiz (evristika uchun),
                // keyin tahlilni fonda, yuklashni bloklamay ishga tushiramiz.
                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeFileScaled(file.absolutePath) }
                if (bitmap != null) runHeuristicAsync(bitmap, rowId) else rowId.complete(null)

                val body = ProgressRequestBody(file.asRequestBody("image/jpeg".toMediaTypeOrNull())) {
                    _uploadProgress.value = it
                }
                val part = MultipartBody.Part.createFormData("file", file.name, body)
                doRequest(part, rowId)

                file.delete()
                currentSource = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e), canRetry = true)
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
            try {
                val bytes = withContext(Dispatchers.IO) {
                    appContext.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException(appContext.getString(R.string.error_cannot_read_image))

                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeBytesScaled(bytes) }
                if (bitmap != null) runHeuristicAsync(bitmap, rowId) else rowId.complete(null)

                val body = ProgressRequestBody(bytes.toRequestBody("image/*".toMediaTypeOrNull())) {
                    _uploadProgress.value = it
                }
                val part = MultipartBody.Part.createFormData("file", "gallery.jpg", body)
                doRequest(part, rowId)

                currentSource = null
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e), canRetry = true)
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

    private suspend fun doRequest(part: MultipartBody.Part, rowId: CompletableDeferred<Long?>) {
        val pid = patientId.ifBlank { null }?.toRequestBody("text/plain".toMediaTypeOrNull())
        val eyePart = eye.toRequestBody("text/plain".toMediaTypeOrNull())
        val result = api.predict(part, pid, eyePart)
        _uiState.value = UiState.Success(result)
        // Tarixga saqlash — shu payt mahalliy evristika hali tayyor bo'lmasa (odatda
        // sekinroq, backend javobidan keyin ham kelishi mumkin), holsiz saqlanadi;
        // tayyor bo'lgach `runHeuristicAsync` shu ID orqali to'ldiradi.
        val id = runCatching { historyRepo.saveResult(result, _localHeuristic.value) }.getOrNull()
        if (!rowId.isCompleted) rowId.complete(id)
    }

    /** Texnik xatoni foydalanuvchiga tushunarli, joriy tildagi xabarga aylantiradi. */
    private fun friendly(e: Exception): String {
        val app = getApplication<Application>()
        return when (e) {
            is java.net.UnknownHostException,
            is java.net.ConnectException ->
                app.getString(R.string.error_no_connection)
            is java.net.SocketTimeoutException ->
                app.getString(R.string.error_timeout)
            is java.net.UnknownServiceException ->
                app.getString(R.string.error_https_required)
            is HttpException -> httpErrorMessage(e)
            else -> e.message ?: app.getString(R.string.error_unknown)
        }
    }

    /** 4xx/5xx javoblarni kod oralig'iga qarab tushunarli xabarga aylantiradi. Backend
     * xato tanasida (`{"detail": "..."}`, odatiy FastAPI validatsiya formati) aniqroq
     * xabar bo'lsa, o'shani ishlatadi. */
    private fun httpErrorMessage(e: HttpException): String {
        val app = getApplication<Application>()
        val detail = runCatching {
            e.response()?.errorBody()?.string()?.let { body ->
                org.json.JSONObject(body).optString("detail").ifBlank { null }
            }
        }.getOrNull()
        if (!detail.isNullOrBlank()) return detail

        return when (e.code()) {
            400, 422 -> app.getString(R.string.error_bad_request)
            401, 403 -> app.getString(R.string.error_unauthorized)
            404 -> app.getString(R.string.error_not_found)
            429 -> app.getString(R.string.error_too_many_requests)
            in 500..599 -> app.getString(R.string.error_server)
            else -> app.getString(R.string.error_http_generic, e.code())
        }
    }
}
