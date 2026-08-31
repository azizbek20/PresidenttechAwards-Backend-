package com.eyedetect.ai.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.vision.BitmapLoader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

class SyncWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val repo = ScreeningHistoryRepository(applicationContext)
        val pendingUploads = repo.getPendingUploads()

        if (pendingUploads.isEmpty()) {
            return Result.success()
        }

        var hasFailures = false

        for (pending in pendingUploads) {
            val filePath = pending.pendingFilePath ?: continue
            val file = File(filePath)

            if (!file.exists()) {
                // Rasm topilmadi, xato sifatida belgilaymiz
                repo.update(pending.copy(syncStatus = "ERROR"))
                continue
            }

            try {
                val fileBytes = withContext(Dispatchers.IO) { file.readBytes() }
                
                // Siqish (compress) ViewModel'dagi kabi
                val compressed = withContext(Dispatchers.Default) { BitmapLoader.compressForUpload(fileBytes) }
                val (finalBytes, mediaType) =
                    if (compressed != null) compressed to "image/jpeg" else fileBytes to "image/jpeg"
                    
                val body = finalBytes.toRequestBody(mediaType.toMediaTypeOrNull())
                val part = MultipartBody.Part.createFormData("file", file.name, body)
                
                val pid = pending.patientId?.takeIf { it.isNotBlank() }?.toRequestBody("text/plain".toMediaTypeOrNull())
                val eyePart = pending.eye?.toRequestBody("text/plain".toMediaTypeOrNull())
                
                // API so'rovi
                val taskResponse = ApiClient.service.predict(part, pid, eyePart)
                var status = taskResponse.status
                var result: com.eyedetect.ai.data.PredictResponse? = null
                
                // Natijani kutish (Polling)
                while (status == "PENDING" || status == "PROCESSING") {
                    kotlinx.coroutines.delay(2000)
                    val statusResponse = ApiClient.service.getPredictStatus(taskResponse.taskId)
                    status = statusResponse.status
                    if (status == "SUCCESS" && statusResponse.result != null) {
                        result = statusResponse.result
                    } else if (status == "FAILURE") {
                        throw Exception("Backend xatosi: ${statusResponse.error ?: "Noma'lum"}")
                    }
                }
                
                if (result == null) {
                    throw Exception("Natija kelmadi!")
                }
                
                // Bazani muvaffaqiyatli natija bilan yangilash
                repo.update(
                    pending.copy(
                        examId = result.examId,
                        patientId = result.patientId, // server qaytargan ID (P-XXXX) bo'lishi mumkin
                        decision = result.decision,
                        decisionText = result.decisionText,
                        gradeLabel = result.gradeLabel,
                        icdrGrade = result.icdrGrade,
                        probability = result.probability,
                        quality = result.quality,
                        modelVersion = result.modelVersion,
                        imageUrl = result.imageUrl,
                        heatmapUrl = result.heatmapUrl,
                        processedAt = result.processedAt,
                        syncStatus = "SYNCED",
                        pendingFilePath = null
                    )
                )
                
                // Yuborilgan rasmni o'chirish
                file.delete()
                
            } catch (e: Exception) {
                e.printStackTrace()
                // Tarmoq yoki server xatosi — keyinroq yana urinib ko'rish uchun retry
                hasFailures = true
            }
        }

        return if (hasFailures) Result.retry() else Result.success()
    }
}
