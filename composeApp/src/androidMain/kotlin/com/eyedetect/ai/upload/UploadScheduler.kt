package com.eyedetect.ai.upload

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

/** Navbatga qo'yilgan bitta rasm uchun WorkManager vazifasini rejalashtiradi — internetga
 * ulanish ([NetworkType.CONNECTED]) bo'lmaguncha ishga tushmaydi, ulanish tiklangach avtomatik
 * bajariladi. Har bir navbat yozuvi ([com.eyedetect.ai.data.upload.PendingUploadEntity.id])
 * o'zining nomlangan (unique) ishiga ega — bir xil yozuv uchun ikki marta enqueue qilinsa
 * ([ExistingWorkPolicy.KEEP]) eskisi davom etadi, dublikat yaratilmaydi. */
object UploadScheduler {
    private fun workName(id: Long) = "pending_upload_$id"

    fun enqueue(context: Context, id: Long) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = OneTimeWorkRequestBuilder<UploadWorker>()
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, WorkRequest.MIN_BACKOFF_MILLIS, TimeUnit.MILLISECONDS)
            .setInputData(workDataOf(UploadWorker.KEY_PENDING_ID to id))
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(workName(id), ExistingWorkPolicy.KEEP, request)
    }

    fun cancel(context: Context, id: Long) {
        WorkManager.getInstance(context).cancelUniqueWork(workName(id))
    }
}
