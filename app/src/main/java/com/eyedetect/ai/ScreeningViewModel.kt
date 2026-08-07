package com.eyedetect.ai

import android.app.Application
import android.content.Context
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.PredictResponse
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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

/**
 * Skrining oqimi ViewModel'i: bemor ID, rasm yuborish va natija holatini boshqaradi.
 */
class ScreeningViewModel(application: Application) : AndroidViewModel(application) {

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    var patientId: String = ""
    var eye: String = "right"   // "right" | "left"

    fun reset() {
        _uiState.value = UiState.Idle
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
            try {
                doRequest(part)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
            } finally {
                file.delete()
            }
        }
    }

    /** Galereyadan tanlangan Uri'ni yuboradi (zaxira rejim, reja 3.3). */
    fun uploadUri(context: Context, uri: Uri) {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            try {
                val bytes = withContext(Dispatchers.IO) {
                    context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                } ?: throw IllegalStateException(getApplication<Application>().getString(R.string.error_cannot_read_image))
                val body = bytes.toRequestBody("image/*".toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("file", "gallery.jpg", body)
                doRequest(part)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
            }
        }
    }

    private suspend fun doRequest(part: MultipartBody.Part) {
        val pid = patientId.ifBlank { null }?.toRequestBody("text/plain".toMediaTypeOrNull())
        val eyePart = eye.toRequestBody("text/plain".toMediaTypeOrNull())
        val result = ApiClient.service.predict(part, pid, eyePart)
        _uiState.value = UiState.Success(result)
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
