package com.eyedetect.ai.upload

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.data.upload.PendingUploadEntity
import com.eyedetect.ai.data.upload.PendingUploadRepository
import com.eyedetect.ai.eyecare.NotificationHelper
import com.eyedetect.ai.vision.BitmapLoader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
import java.io.File
import java.io.IOException

/**
 * [UploadScheduler]dan `NetworkType.CONNECTED` cheklovi bilan rejalashtiriladi — shu sababli
 * faqat internet bor paytda ishga tushadi. Navbatdagi rasmni [ApiClient.service.predict]ga
 * yuboradi (`ScreeningViewModel.doRequest()` bilan bir xil mantiq, faqat progress kuzatuvisiz —
 * fon vazifasida ko'rsatiladigan UI yo'q).
 *
 * Qayta urinish siyosati: tarmoq xatosi ([IOException] — ulanish yo'q/timeout) yoki 5xx server
 * xatosi bo'lsa [androidx.work.ListenableWorker.Result.retry] (WorkManager eksponensial orqaga
 * chekinish bilan avtomatik qayta chaqiradi). Boshqa xatolar (masalan 4xx — noto'g'ri rasm
 * formati) qayta urinish bilan tuzalmaydi, shu sababli yozuv `failed = true` bilan belgilanadi
 * (o'chirilmaydi — foydalanuvchi Tarix ekranidan qo'lda qayta urinishi yoki bekor qilishi mumkin).
 */
class UploadWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val id = inputData.getLong(KEY_PENDING_ID, -1L)
        if (id < 0) return Result.failure()

        val pendingRepo = PendingUploadRepository(applicationContext)
        val entry = pendingRepo.get(id) ?: return Result.success() // allaqachon bekor qilingan/o'chirilgan

        val file = File(entry.filePath)
        if (!file.exists()) {
            pendingRepo.delete(entry)
            return Result.failure()
        }

        return try {
            val result = withContext(Dispatchers.IO) {
                val rawBytes = file.readBytes()
                val compressed = BitmapLoader.compressForUpload(rawBytes)
                val (bodyBytes, mediaType) =
                    if (compressed != null) compressed to "image/jpeg" else rawBytes to entry.fallbackMediaType
                val body = bodyBytes.toRequestBody(mediaType.toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("file", file.name, body)
                val pidPart = entry.patientId?.toRequestBody("text/plain".toMediaTypeOrNull())
                val eyePart = entry.eye.toRequestBody("text/plain".toMediaTypeOrNull())
                ApiClient.service.predict(part, pidPart, eyePart)
            }

            runCatching { ScreeningHistoryRepository(applicationContext).saveResult(result, heuristic = null) }
            pendingRepo.delete(entry)
            NotificationHelper.showUploadSuccess(applicationContext, entry.patientId)
            Result.success()
        } catch (e: Exception) {
            if (isRetryable(e) && runAttemptCount < MAX_ATTEMPTS) {
                Result.retry()
            } else {
                onPermanentFailure(pendingRepo, entry)
                Result.failure()
            }
        }
    }

    private suspend fun onPermanentFailure(pendingRepo: PendingUploadRepository, entry: PendingUploadEntity) {
        pendingRepo.markFailed(entry.id)
        NotificationHelper.showUploadFailed(applicationContext)
    }

    private fun isRetryable(e: Exception): Boolean =
        e is IOException || (e is HttpException && e.code() in 500..599)

    companion object {
        const val KEY_PENDING_ID = "pending_upload_id"
        private const val MAX_ATTEMPTS = 8
    }
}
