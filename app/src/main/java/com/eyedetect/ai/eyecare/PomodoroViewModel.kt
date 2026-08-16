package com.eyedetect.ai.eyecare

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.PomodoroPhase
import com.eyedetect.ai.data.eyecare.PomodoroState
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * Pomodoro ekranini boshqaradi. Taymerning haqiqiy manbai [EyeCarePreferencesRepository]da
 * saqlangan [PomodoroState.phaseEndEpochMs] — bu ekranga [PomodoroWorker] fon rejimida
 * bosqichni almashtirsa ham (masalan, ilova yopiq bo'lganda) qolgan vaqt to'g'ri hisoblanishini
 * ta'minlaydi. [remainingSeconds] shu maqsad uchun har soniyada shu qiymatdan qayta hisoblanadi.
 */
class PomodoroViewModel(application: Application) : AndroidViewModel(application) {
    private val repo = EyeCarePreferencesRepository(application)

    val state: StateFlow<PomodoroState> = repo.pomodoroState.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5_000), PomodoroState(),
    )

    private val _remainingSeconds = MutableStateFlow(0)
    val remainingSeconds: StateFlow<Int> = _remainingSeconds.asStateFlow()

    private var tickerJob: Job? = null

    init {
        viewModelScope.launch {
            state.collect { s ->
                tickerJob?.cancel()
                tickerJob = if (s.running) startTicker(s.phaseEndEpochMs) else null
                if (!s.running) _remainingSeconds.value = 0
            }
        }
    }

    private fun startTicker(phaseEndEpochMs: Long) = viewModelScope.launch {
        while (true) {
            val remain = ((phaseEndEpochMs - System.currentTimeMillis()) / 1000L).coerceAtLeast(0)
            _remainingSeconds.value = remain.toInt()
            if (remain <= 0) break
            delay(1_000L)
        }
    }

    /** Ruxsat allaqachon berilgan (yoki kerak bo'lmagan) holatda chaqiriladi. */
    fun start() {
        viewModelScope.launch {
            val s = state.value
            val endMs = System.currentTimeMillis() + s.focusMinutes * 60_000L
            repo.startPomodoroPhase(PomodoroPhase.FOCUS, endMs)
            PomodoroScheduler.schedulePhaseEnd(getApplication(), s.focusMinutes)
        }
    }

    fun stop() {
        viewModelScope.launch { repo.stopPomodoro() }
        PomodoroScheduler.cancel(getApplication())
    }

    fun changeFocusMinutes(minutes: Int) {
        viewModelScope.launch { repo.setPomodoroMinutes(focusMinutes = minutes, breakMinutes = state.value.breakMinutes) }
    }

    fun changeBreakMinutes(minutes: Int) {
        viewModelScope.launch { repo.setPomodoroMinutes(focusMinutes = state.value.focusMinutes, breakMinutes = minutes) }
    }
}
