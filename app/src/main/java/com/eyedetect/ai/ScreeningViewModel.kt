package com.eyedetect.ai

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
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
class ScreeningViewModel : ViewModel() {

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
                } ?: throw IllegalStateException("Rasmni o'qib bo'lmadi")
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

    /** Texnik xatoni foydalanuvchiga tushunarli o'zbekcha xabarga aylantiradi. */
    private fun friendly(e: Exception): String = when (e) {
        is java.net.UnknownHostException,
        is java.net.ConnectException ->
            "Serverga ulanib bo'lmadi. Backend ishga tushganini va manzilni tekshiring."
        is java.net.SocketTimeoutException ->
            "Server javob bermadi (timeout). Qayta urinib ko'ring."
        is java.net.UnknownServiceException ->
            "Xavfsiz ulanish (HTTPS) talab qilinadi, lekin server manzili buni qo'llab-quvvatlamaydi. Administrator bilan bog'laning."
        else -> e.message ?: "Noma'lum xato"
    }
}
