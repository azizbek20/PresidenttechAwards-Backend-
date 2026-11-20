package com.eyedetect.ai.eyecare

import android.app.Application
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ExerciseType
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class FocusPhase { Near, Far }

sealed interface FocusShiftUiState {
    data object Idle : FocusShiftUiState
    data class Running(
        val phase: FocusPhase,
        val cycleIndex: Int,
        val totalCycles: Int,
        val phaseProgress: Float,
        val secondsLeftInPhase: Int,
    ) : FocusShiftUiState
    data object Completed : FocusShiftUiState
}

/** Yaqin-uzoq fokus mashqi — akkomodatsiya mushaklarini kuchaytiradigan navbatlashuvchi mashq. */
class FocusShiftViewModel(application: Application) : AndroidViewModel(application) {
    private val repo = EyeCarePreferencesRepository(application)
    private val _uiState = MutableStateFlow<FocusShiftUiState>(FocusShiftUiState.Idle)
    val uiState: StateFlow<FocusShiftUiState> = _uiState.asStateFlow()
    private var job: Job? = null

    fun start() {
        job?.cancel()
        job = viewModelScope.launch {
            for (cycle in 0 until TOTAL_CYCLES) {
                for (phase in listOf(FocusPhase.Near, FocusPhase.Far)) {
                    vibrate()
                    val phaseStart = System.currentTimeMillis()
                    while (true) {
                        val elapsed = System.currentTimeMillis() - phaseStart
                        if (elapsed >= PHASE_MS) break
                        _uiState.value = FocusShiftUiState.Running(
                            phase = phase,
                            cycleIndex = cycle,
                            totalCycles = TOTAL_CYCLES,
                            phaseProgress = elapsed / PHASE_MS.toFloat(),
                            secondsLeftInPhase = ((PHASE_MS - elapsed) / 1000L).toInt() + 1,
                        )
                        delay(16L)
                    }
                }
            }
            _uiState.value = FocusShiftUiState.Completed
            repo.recordCompletion(ExerciseType.FocusShift)
        }
    }

    override fun onCleared() {
        job?.cancel()
    }

    private fun vibrate() {
        val context = getApplication<Application>()
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Vibrator::class.java)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator?.vibrate(VibrationEffect.createOneShot(40, VibrationEffect.DEFAULT_AMPLITUDE))
        } else {
            @Suppress("DEPRECATION")
            vibrator?.vibrate(40)
        }
    }

    companion object {
        private const val TOTAL_CYCLES = 5
        private const val PHASE_MS = 5_000L
    }
}
