package com.eyedetect.ai.data.eyecare

import java.util.Calendar

/** `epochMs` bugungi kunga to'g'ri kelsa true (0 — hali bajarilmagan). */
fun isToday(epochMs: Long): Boolean {
    if (epochMs <= 0L) return false
    val now = Calendar.getInstance()
    val then = Calendar.getInstance().apply { timeInMillis = epochMs }
    return now.get(Calendar.YEAR) == then.get(Calendar.YEAR) &&
        now.get(Calendar.DAY_OF_YEAR) == then.get(Calendar.DAY_OF_YEAR)
}

/** Ko'z mashqi turlari — DataStore kalitlari va statistikada ishlatiladi. */
enum class ExerciseType { FollowDot, FocusShift, BlinkPalm }

/** 20-20-20 eslatmasi sozlamalari. */
data class ReminderSettings(
    val enabled: Boolean = false,
    val intervalMinutes: Int = 20,
    val quietHoursEnabled: Boolean = false,
    val quietStartHour: Int = 22,
    val quietEndHour: Int = 7,
)

/** Ko'z mashqlari bo'yicha bajarilish statistikasi. */
data class ExerciseStats(
    val followDotCount: Int = 0,
    val followDotLastCompletedMs: Long = 0L,
    val focusShiftCount: Int = 0,
    val focusShiftLastCompletedMs: Long = 0L,
    val blinkPalmCount: Int = 0,
    val blinkPalmLastCompletedMs: Long = 0L,
    val streakDays: Int = 0,
) {
    fun countFor(type: ExerciseType): Int = when (type) {
        ExerciseType.FollowDot -> followDotCount
        ExerciseType.FocusShift -> focusShiftCount
        ExerciseType.BlinkPalm -> blinkPalmCount
    }

    fun lastCompletedMsFor(type: ExerciseType): Long = when (type) {
        ExerciseType.FollowDot -> followDotLastCompletedMs
        ExerciseType.FocusShift -> focusShiftLastCompletedMs
        ExerciseType.BlinkPalm -> blinkPalmLastCompletedMs
    }
}
