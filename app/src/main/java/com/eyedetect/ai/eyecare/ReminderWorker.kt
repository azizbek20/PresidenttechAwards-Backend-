package com.eyedetect.ai.eyecare

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ReminderSettings
import kotlinx.coroutines.flow.first
import java.util.Calendar

/** Davriy ishga tushadigan 20-20-20 eslatma vazifasi — sozlamalarni tekshirib, bildirishnoma chiqaradi. */
class ReminderWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val repo = EyeCarePreferencesRepository(applicationContext)
        val settings = repo.settings.first()

        if (!settings.enabled) return Result.success()
        if (settings.quietHoursEnabled && isWithinQuietHours(settings)) return Result.success()

        NotificationHelper.showReminder(applicationContext)
        repo.markReminderShown()
        return Result.success()
    }

    private fun isWithinQuietHours(s: ReminderSettings): Boolean {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        return if (s.quietStartHour <= s.quietEndHour) {
            hour in s.quietStartHour until s.quietEndHour
        } else {
            // Yarim tundan o'tadigan oraliq, masalan 22 -> 7
            hour >= s.quietStartHour || hour < s.quietEndHour
        }
    }
}
