package com.eyedetect.ai.eyecare

import android.content.Context
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/** Joriy Pomodoro bosqichi tugaydigan vaqtga bitta martalik WorkManager vazifasini rejalashtiradi. */
object PomodoroScheduler {
    private const val UNIQUE_WORK_NAME = "pomodoro_phase_end"

    fun schedulePhaseEnd(context: Context, minutes: Int) {
        val request = OneTimeWorkRequestBuilder<PomodoroWorker>()
            .setInitialDelay(minutes.toLong().coerceAtLeast(1), TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            UNIQUE_WORK_NAME,
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context).cancelUniqueWork(UNIQUE_WORK_NAME)
    }
}
