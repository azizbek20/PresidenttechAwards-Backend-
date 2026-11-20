package com.eyedetect.ai

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.Immutable
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.AnalysisApi
import com.eyedetect.ai.data.AnalyzeResponse
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.vision.BitmapLoader
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Immutable
sealed interface AnalysisUiState {
    data object Idle : AnalysisUiState
    data object Loading : AnalysisUiState
    data class Success(val result: AnalyzeResponse) : AnalysisUiState
    data class Error(val message: String) : AnalysisUiState
}

/**
 * Ko'z tubidan tashqari tahlillar (tashqi ko'z, teri, og'iz, tirnoq) oqimi:
 * tur tanlash → bemor ID / tana qismi → rasm → natija.
 *
 * Rasm yuborishdan oldin [BitmapLoader.compressForUpload] bilan kichraytirilib JPEG qilinadi —
 * telefon kamerasining 10+ MB rasmini to'g'ridan-to'g'ri yuborish sekin va backend
 * hajm chegarasiga urilishi mumkin.
 */
class AnalysisViewModel @JvmOverloads constructor(
    application: Application,
    private val api: AnalysisApi = ApiClient.analysis,
) : AndroidViewModel(application) {

    private val _type = MutableStateFlow<String?>(null)
    val type: StateFlow<String?> = _type.asStateFlow()

    private val _patientId = MutableStateFlow("")
    val patientId: StateFlow<String> = _patientId.asStateFlow()

    private val _bodySite = MutableStateFlow("")
    val bodySite: StateFlow<String> = _bodySite.asStateFlow()

    /** Natija ekranida ko'rsatish uchun yuborilgan rasm (lokal URI). */
    private val _imageUri = MutableStateFlow<Uri?>(null)
    val imageUri: StateFlow<Uri?> = _imageUri.asStateFlow()

    private val _uiState = MutableStateFlow<AnalysisUiState>(AnalysisUiState.Idle)
    val uiState: StateFlow<AnalysisUiState> = _uiState.asStateFlow()

    private val _uploadProgress = MutableStateFlow<Float?>(null)
    val uploadProgress: StateFlow<Float?> = _uploadProgress.asStateFlow()

    private var job: Job? = null

    fun selectType(code: String) {
        _type.value = code
        _uiState.value = AnalysisUiState.Idle
    }

    fun setPatientId(value: String) { _patientId.value = value.take(64) }
    fun setBodySite(value: String) { _bodySite.value = value.take(64) }

    fun analyze(uri: Uri) {
        val type = _type.value ?: return
        _imageUri.value = uri
        job?.cancel()
        job = viewModelScope.launch {
            _uiState.value = AnalysisUiState.Loading
            try {
                val bytes = withContext(Dispatchers.IO) { readAsJpeg(uri) }
                    ?: throw IllegalStateException(
                        getApplication<Application>().getString(R.string.analysis_error_read_image)
                    )
                val result = api.analyze(
                    fileBytes = bytes,
                    fileName = "analysis_$type.jpg",
                    analysisType = type,
                    patientId = _patientId.value.trim().ifBlank { null },
                    bodySite = _bodySite.value.trim().ifBlank { null },
                    onProgress = { _uploadProgress.value = it },
                )
                _uiState.value = AnalysisUiState.Success(result)
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                _uiState.value = AnalysisUiState.Error(
                    friendlyErrorMessage(getApplication<Application>(), e)
                )
            } finally {
                _uploadProgress.value = null
            }
        }
    }

    fun retry() { _imageUri.value?.let { analyze(it) } }

    fun cancel() {
        job?.cancel()
        _uiState.value = AnalysisUiState.Idle
    }

    /** Yangi tahlil: tur va bemor saqlanadi, natija va rasm tozalanadi. */
    fun resetResult() {
        job?.cancel()
        _uiState.value = AnalysisUiState.Idle
        _imageUri.value = null
    }

    private fun readAsJpeg(uri: Uri): ByteArray? {
        val raw = getApplication<Application>().contentResolver
            .openInputStream(uri)?.use { it.readBytes() } ?: return null
        return BitmapLoader.compressForUpload(raw)
    }
}
