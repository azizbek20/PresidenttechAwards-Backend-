package com.eyedetect.ai.eyecare

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ExerciseType
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface BlinkPalmUiState {
    data object Idle : BlinkPalmUiState
    data class BlinkingRunning(val cycleIndex: Int, val totalCycles: Int, val eyesClosed: Boolean, val phaseProgress: Float) : BlinkPalmUiState
    data class PalmingRunning(val progress: Float, val secondsLeft: Int) : BlinkPalmUiState
    data object Completed : BlinkPalmUiState
}

/** Ongli miltillash sanog'ichi + palming (ko'zni yumib dam olish) taymeri. */
class BlinkPalmViewModel(application: Application) : AndroidViewModel(application) {
    private val repo = EyeCarePreferencesRepository(application)
    private val _uiState = MutableStateFlow<BlinkPalmUiState>(BlinkPalmUiState.Idle)
    val uiState: StateFlow<BlinkPalmUiState> = _uiState.asStateFlow()
    private var job: Job? = null

    fun start() {
        job?.cancel()
        job = viewModelScope.launch {
            for (cycle in 0 until BLINK_CYCLES) {
                for (closed in listOf(true, false)) {
                    runPhase(BLINK_STEP_MS) { elapsed ->
                        _uiState.value = BlinkPalmUiState.BlinkingRunning(
                            cycleIndex = cycle,
                            totalCycles = BLINK_CYCLES,
                            eyesClosed = closed,
                            phaseProgress = elapsed / BLINK_STEP_MS.toFloat(),
                        )
                    }
                }
            }

            runPhase(PALM_MS) { elapsed ->
                _uiState.value = BlinkPalmUiState.PalmingRunning(
                    progress = elapsed / PALM_MS.toFloat(),
                    secondsLeft = ((PALM_MS - elapsed) / 1000L).toInt() + 1,
                )
            }

            _uiState.value = BlinkPalmUiState.Completed
            repo.recordCompletion(ExerciseType.BlinkPalm)
        }
    }

    override fun onCleared() {
        job?.cancel()
    }

    companion object {
        private const val BLINK_CYCLES = 10
        private const val BLINK_STEP_MS = 1_200L
        private const val PALM_MS = 60_000L
    }
}
