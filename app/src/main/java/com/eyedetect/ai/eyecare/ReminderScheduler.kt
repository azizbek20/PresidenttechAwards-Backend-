package com.eyedetect.ai.eyecare

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/** 20-20-20 eslatmasini WorkManager orqali davriy rejalashtiradi/bekor qiladi. */
object ReminderScheduler {
    private const val UNIQUE_WORK_NAME = "eyecare_20_20_20_reminder"

    /** WorkManager'ning davriy vazifa uchun minimal oralig'i 15 daqiqa. */
    fun schedule(context: Context, intervalMinutes: Int) {
        val interval = intervalMinutes.coerceAtLeast(15)
        val request = PeriodicWorkRequestBuilder<ReminderWorker>(interval.toLong(), TimeUnit.MINUTES).build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            UNIQUE_WORK_NAME,
            ExistingPeriodicWorkPolicy.UPDATE,
            request,
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK_NAME)
    }
}
