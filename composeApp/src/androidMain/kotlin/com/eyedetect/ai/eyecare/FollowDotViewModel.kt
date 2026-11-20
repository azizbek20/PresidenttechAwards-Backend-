package com.eyedetect.ai.eyecare

import android.app.Application
import androidx.compose.ui.geometry.Offset
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
import kotlin.math.sin

sealed interface FollowDotUiState {
    data object Idle : FollowDotUiState
    data class Running(val progress: Float, val dot: Offset, val remainingSeconds: Int) : FollowDotUiState
    data object Completed : FollowDotUiState
}

/** Nuqtani kuzatish mashqi — 30 soniyalik seans, nuqta Lissajous egri chizig'i bo'ylab harakatlanadi. */
class FollowDotViewModel(application: Application) : AndroidViewModel(application) {
    private val repo = EyeCarePreferencesRepository(application)
    private val _uiState = MutableStateFlow<FollowDotUiState>(FollowDotUiState.Idle)
    val uiState: StateFlow<FollowDotUiState> = _uiState.asStateFlow()
    private var job: Job? = null

    fun start() {
        job?.cancel()
        job = viewModelScope.launch {
            val startTime = System.currentTimeMillis()
            while (true) {
                val elapsed = System.currentTimeMillis() - startTime
                if (elapsed >= SESSION_MS) break
                val t = elapsed / 1000f
                val x = 0.5f + 0.36f * sin(t * 0.9f)
                val y = 0.5f + 0.28f * sin(t * 1.4f + 1.1f)
                _uiState.value = FollowDotUiState.Running(
                    progress = elapsed / SESSION_MS.toFloat(),
                    dot = Offset(x, y),
                    remainingSeconds = ((SESSION_MS - elapsed) / 1000L).toInt() + 1,
                )
                delay(16L)
            }
            _uiState.value = FollowDotUiState.Completed
            repo.recordCompletion(ExerciseType.FollowDot)
        }
    }

    override fun onCleared() {
        job?.cancel()
    }

    companion object {
        private const val SESSION_MS = 30_000L
    }
}
