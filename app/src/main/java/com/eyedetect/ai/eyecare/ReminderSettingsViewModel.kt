package com.eyedetect.ai.eyecare

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ExerciseStats
import com.eyedetect.ai.data.eyecare.ReminderSettings
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/** ReminderSettingsScreen uchun — sozlamalarni DataStore'ga yozadi va WorkManager rejasini yangilaydi. */
class ReminderSettingsViewModel(application: Application) : AndroidViewModel(application) {
    private val repo = EyeCarePreferencesRepository(application)

    val settings: StateFlow<ReminderSettings> = repo.settings.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5_000), ReminderSettings(),
    )
    val stats: StateFlow<ExerciseStats> = repo.stats.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5_000), ExerciseStats(),
    )

    /** Ruxsat allaqachon berilgan (yoki kerak bo'lmagan) holatda chaqiriladi. */
    fun enableReminder(intervalMinutes: Int) {
        viewModelScope.launch {
            repo.setReminderEnabled(true)
            repo.setIntervalMinutes(intervalMinutes)
            ReminderScheduler.schedule(getApplication(), intervalMinutes)
        }
    }

    fun disableReminder() {
        viewModelScope.launch { repo.setReminderEnabled(false) }
        ReminderScheduler.cancel(getApplication())
    }

    fun changeInterval(minutes: Int) {
        viewModelScope.launch {
            repo.setIntervalMinutes(minutes)
            if (settings.value.enabled) {
                ReminderScheduler.schedule(getApplication(), minutes)
            }
        }
    }

    fun setQuietHours(enabled: Boolean, startHour: Int, endHour: Int) {
        viewModelScope.launch { repo.setQuietHours(enabled, startHour, endHour) }
    }
}
