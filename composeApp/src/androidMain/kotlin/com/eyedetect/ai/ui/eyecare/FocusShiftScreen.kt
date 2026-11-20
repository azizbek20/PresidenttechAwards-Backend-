package com.eyedetect.ai.ui.eyecare

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.eyecare.FocusPhase
import com.eyedetect.ai.eyecare.FocusShiftUiState
import com.eyedetect.ai.eyecare.FocusShiftViewModel
import com.eyedetect.ai.ui.components.ExerciseCompletionCard
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.TimerRing
import com.eyedetect.ai.ui.theme.Spacing

/** Yaqin-uzoq fokus mashqi — navbatlashuvchi yaqin/uzoq nishonlar bilan akkomodatsiya mashqi. */
@Composable
fun FocusShiftScreen(onBack: () -> Unit, vm: FocusShiftViewModel = viewModel()) {
    val state by vm.uiState.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Text(stringResource(R.string.exercise_focusshift_title), style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
        Text(
            stringResource(R.string.focusshift_instructions),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (val s = state) {
            is FocusShiftUiState.Idle -> {
                Column(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.Center) {
                    PrimaryButton(stringResource(R.string.common_start), onClick = vm::start)
                }
            }
            is FocusShiftUiState.Running -> {
                Column(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        stringResource(R.string.focusshift_phase, s.cycleIndex + 1, s.totalCycles),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(Spacing.lg))
                    TimerRing(progress = s.phaseProgress) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(if (s.phase == FocusPhase.Near) "🔎" else "🌄", fontSize = 40.sp)
                            Text("${s.secondsLeftInPhase}", style = MaterialTheme.typography.headlineMedium)
                        }
                    }
                    Spacer(Modifier.height(Spacing.lg))
                    Text(
                        if (s.phase == FocusPhase.Near) stringResource(R.string.focusshift_look_near) else stringResource(R.string.focusshift_look_far),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            is FocusShiftUiState.Completed -> {
                ExerciseCompletionCard(
                    title = stringResource(R.string.common_exercise_done_title),
                    message = stringResource(R.string.focusshift_done_message),
                    onRepeat = vm::start,
                    onBack = onBack,
                )
            }
        }
    }
}
