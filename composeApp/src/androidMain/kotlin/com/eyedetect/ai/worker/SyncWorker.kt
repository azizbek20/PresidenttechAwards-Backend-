package com.eyedetect.ai.worker

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.predictAndAwait
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.vision.BitmapLoader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
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
                val finalBytes = compressed ?: fileBytes
                val pid = pending.patientId?.takeIf { it.isNotBlank() }
                
                // API so'rovi
                val result = ApiClient.service.predictAndAwait(finalBytes, file.name, pid, pending.eye)

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
