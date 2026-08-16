package com.eyedetect.ai.eyecare

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.PomodoroPhase
import kotlinx.coroutines.flow.first

/**
 * Pomodoro bosqichi (fokus yoki tanaffus) tugaganda ishga tushadi: ogohlantirish ko'rsatadi,
 * keyingi bosqichga o'tadi va uni ham rejalashtiradi — foydalanuvchi "To'xtatish"ni bosmaguncha
 * fokus/tanaffus davri cheksiz aylanadi (ilova yopiq bo'lsa ham, chunki WorkManager fon vazifasi).
 */
class PomodoroWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val repo = EyeCarePreferencesRepository(applicationContext)
        val state = repo.pomodoroState.first()

        // Foydalanuvchi shu bosqich davomida "To'xtatish"ni bosgan bo'lishi mumkin —
        // schedulePhaseEnd bekor qilinadi, lekin ehtiyot uchun holatni ham tekshiramiz.
        if (!state.running) return Result.success()

        val endedPhase = state.phase
        NotificationHelper.showPomodoroAlert(applicationContext, endedPhase)

        val nextPhase = if (endedPhase == PomodoroPhase.FOCUS) PomodoroPhase.BREAK else PomodoroPhase.FOCUS
        val nextMinutes = if (nextPhase == PomodoroPhase.FOCUS) state.focusMinutes else state.breakMinutes
        val nextEndMs = System.currentTimeMillis() + nextMinutes * 60_000L

        repo.startPomodoroPhase(nextPhase, nextEndMs)
        PomodoroScheduler.schedulePhaseEnd(applicationContext, nextMinutes)

        return Result.success()
    }
}
