package com.eyedetect.ai.data.eyecare

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.util.Calendar

private val Context.eyeCareDataStore by preferencesDataStore(name = "eyecare_prefs")

private object Keys {
    val REMINDER_ENABLED = booleanPreferencesKey("reminder_enabled")
    val REMINDER_INTERVAL_MIN = intPreferencesKey("reminder_interval_minutes")
    val QUIET_HOURS_ENABLED = booleanPreferencesKey("quiet_hours_enabled")
    val QUIET_HOURS_START_HOUR = intPreferencesKey("quiet_hours_start_hour")
    val QUIET_HOURS_END_HOUR = intPreferencesKey("quiet_hours_end_hour")

    val FOLLOW_DOT_COUNT = intPreferencesKey("follow_dot_completion_count")
    val FOLLOW_DOT_LAST_MS = longPreferencesKey("follow_dot_last_completed_epoch")
    val FOCUS_SHIFT_COUNT = intPreferencesKey("focus_shift_completion_count")
    val FOCUS_SHIFT_LAST_MS = longPreferencesKey("focus_shift_last_completed_epoch")
    val BLINK_PALM_COUNT = intPreferencesKey("blink_palm_completion_count")
    val BLINK_PALM_LAST_MS = longPreferencesKey("blink_palm_last_completed_epoch")

    val STREAK_DAYS = intPreferencesKey("eyecare_streak_days")
    val STREAK_LAST_ACTIVE_DAY = stringPreferencesKey("eyecare_streak_last_active_day")
}

/** Ko'z mashqlari sozlamalari va statistikasi uchun DataStore ombori (ilovadagi birinchi persistensiya). */
class EyeCarePreferencesRepository(private val context: Context) {

    val settings: Flow<ReminderSettings> = context.eyeCareDataStore.data.map { p ->
        ReminderSettings(
            enabled = p[Keys.REMINDER_ENABLED] ?: false,
            intervalMinutes = p[Keys.REMINDER_INTERVAL_MIN] ?: 20,
            quietHoursEnabled = p[Keys.QUIET_HOURS_ENABLED] ?: false,
            quietStartHour = p[Keys.QUIET_HOURS_START_HOUR] ?: 22,
            quietEndHour = p[Keys.QUIET_HOURS_END_HOUR] ?: 7,
        )
    }

    val stats: Flow<ExerciseStats> = context.eyeCareDataStore.data.map { p ->
        ExerciseStats(
            followDotCount = p[Keys.FOLLOW_DOT_COUNT] ?: 0,
            followDotLastCompletedMs = p[Keys.FOLLOW_DOT_LAST_MS] ?: 0L,
            focusShiftCount = p[Keys.FOCUS_SHIFT_COUNT] ?: 0,
            focusShiftLastCompletedMs = p[Keys.FOCUS_SHIFT_LAST_MS] ?: 0L,
            blinkPalmCount = p[Keys.BLINK_PALM_COUNT] ?: 0,
            blinkPalmLastCompletedMs = p[Keys.BLINK_PALM_LAST_MS] ?: 0L,
            streakDays = p[Keys.STREAK_DAYS] ?: 0,
        )
    }

    suspend fun setReminderEnabled(enabled: Boolean) {
        context.eyeCareDataStore.edit { it[Keys.REMINDER_ENABLED] = enabled }
    }

    suspend fun setIntervalMinutes(minutes: Int) {
        context.eyeCareDataStore.edit { it[Keys.REMINDER_INTERVAL_MIN] = minutes }
    }

    suspend fun setQuietHours(enabled: Boolean, startHour: Int, endHour: Int) {
        context.eyeCareDataStore.edit {
            it[Keys.QUIET_HOURS_ENABLED] = enabled
            it[Keys.QUIET_HOURS_START_HOUR] = startHour
            it[Keys.QUIET_HOURS_END_HOUR] = endHour
        }
    }

    suspend fun recordCompletion(type: ExerciseType) {
        val nowMs = System.currentTimeMillis()
        val today = dayKey(nowMs)
        context.eyeCareDataStore.edit { p ->
            when (type) {
                ExerciseType.FollowDot -> {
                    p[Keys.FOLLOW_DOT_COUNT] = (p[Keys.FOLLOW_DOT_COUNT] ?: 0) + 1
                    p[Keys.FOLLOW_DOT_LAST_MS] = nowMs
                }
                ExerciseType.FocusShift -> {
                    p[Keys.FOCUS_SHIFT_COUNT] = (p[Keys.FOCUS_SHIFT_COUNT] ?: 0) + 1
                    p[Keys.FOCUS_SHIFT_LAST_MS] = nowMs
                }
                ExerciseType.BlinkPalm -> {
                    p[Keys.BLINK_PALM_COUNT] = (p[Keys.BLINK_PALM_COUNT] ?: 0) + 1
                    p[Keys.BLINK_PALM_LAST_MS] = nowMs
                }
            }

            val lastActiveDay = p[Keys.STREAK_LAST_ACTIVE_DAY]
            if (lastActiveDay != today) {
                val yesterday = dayKey(nowMs - 24L * 60 * 60 * 1000)
                val currentStreak = p[Keys.STREAK_DAYS] ?: 0
                p[Keys.STREAK_DAYS] = if (lastActiveDay == yesterday) currentStreak + 1 else 1
                p[Keys.STREAK_LAST_ACTIVE_DAY] = today
            }
        }
    }

    suspend fun markReminderShown() {
        context.eyeCareDataStore.edit { it[longPreferencesKey("reminder_last_shown_epoch")] = System.currentTimeMillis() }
    }

    suspend fun settingsSnapshot(): ReminderSettings = settings.first()

    /** "yyyy-DDD" ko'rinishidagi kun kaliti — java.time o'rniga (minSdk 24, desugaring yo'q). */
    private fun dayKey(epochMs: Long): String {
        val cal = Calendar.getInstance().apply { timeInMillis = epochMs }
        return "${cal.get(Calendar.YEAR)}-${cal.get(Calendar.DAY_OF_YEAR)}"
    }
}
