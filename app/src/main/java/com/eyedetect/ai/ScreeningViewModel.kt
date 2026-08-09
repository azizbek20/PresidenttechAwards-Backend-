package com.eyedetect.ai

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.ui.components.QualityLevel
import com.eyedetect.ai.vision.BitmapLoader
import com.eyedetect.ai.vision.EyeSymmetryAnalyzer
import com.eyedetect.ai.vision.EyeSymmetryResult
import com.eyedetect.ai.vision.EyeSymmetrySample
import com.eyedetect.ai.vision.PupilHeuristicResult
import com.eyedetect.ai.vision.PupilHeuristics
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
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
import java.io.File

/** UI holati (ekranlar shu holatga qarab chiziladi). */
sealed interface UiState {
    data object Idle : UiState
    data object Loading : UiState
    data class Success(val result: PredictResponse) : UiState
    data class Error(val message: String) : UiState
}

/** Ikki ko'z simmetriyasini solishtirish natijasi + qaysi ko'z/qachon bilan solishtirilgani. */
data class EyeSymmetryUiState(
    val comparison: EyeSymmetryResult,
    val comparedEye: String?,
    val comparedAtMs: Long,
)

/**
 * Skrining oqimi ViewModel'i: bemor ID, rasm yuborish va natija holatini boshqaradi.
 */
class ScreeningViewModel(application: Application) : AndroidViewModel(application) {

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

    var patientId: String = ""
    var eye: String = "right"   // "right" | "left"

    fun reset() {
        _uiState.value = UiState.Idle
        _localHeuristic.value = null
        _symmetry.value = null
    }

    /** Faylni (kameradan) yuboradi; yuborilgach (muvaffaqiyat yoki xato) faylni o'chiradi. */
    fun uploadFile(file: File) {
        val part = MultipartBody.Part.createFormData(
            name = "file",
            filename = file.name,
            body = file.asRequestBody("image/jpeg".toMediaTypeOrNull()),
        )
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _localHeuristic.value = null
            _symmetry.value = null
            val rowId = CompletableDeferred<Long?>()
            try {
                // Fayl o'chirilishidan oldin baytlarini o'qib olamiz (evristika uchun),
                // keyin tahlilni fonda, yuklashni bloklamay ishga tushiramiz.
                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeFileScaled(file.absolutePath) }
                if (bitmap != null) runHeuristicAsync(bitmap, rowId) else rowId.complete(null)
                doRequest(part, rowId)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
                if (!rowId.isCompleted) rowId.complete(null)
            } finally {
                file.delete()
            }
        }
    }

    /** Galereyadan tanlangan Uri'ni yuboradi (zaxira rejim, reja 3.3). */
    fun uploadUri(context: Context, uri: Uri) {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            _localHeuristic.value = null
            _symmetry.value = null
            val rowId = CompletableDeferred<Long?>()
            try {
                val bytes = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException(getApplication<Application>().getString(R.string.error_cannot_read_image))

                val bitmap = withContext(Dispatchers.Default) { BitmapLoader.decodeBytesScaled(bytes) }
                if (bitmap != null) runHeuristicAsync(bitmap, rowId) else rowId.complete(null)

                val body = bytes.toRequestBody("image/*".toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("file", "gallery.jpg", body)
                doRequest(part, rowId)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
                if (!rowId.isCompleted) rowId.complete(null)
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
        val result = ApiClient.service.predict(part, pid, eyePart)
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
            else -> e.message ?: app.getString(R.string.error_unknown)
        }
    }
}
