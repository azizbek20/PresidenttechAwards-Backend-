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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.eyecare.BlinkPalmUiState
import com.eyedetect.ai.eyecare.BlinkPalmViewModel
import com.eyedetect.ai.ui.components.ExerciseCompletionCard
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.TimerRing
import com.eyedetect.ai.ui.theme.Spacing

/** Ongli miltillash sanog'ichi, so'ng palming (ko'zni yumib dam olish) taymeri. */
@Composable
fun BlinkPalmScreen(onBack: () -> Unit, vm: BlinkPalmViewModel = viewModel()) {
    val state by vm.uiState.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Text(stringResource(R.string.exercise_blinkpalm_title), style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
        Text(
            stringResource(R.string.blinkpalm_instructions),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (val s = state) {
            is BlinkPalmUiState.Idle -> {
                Column(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.Center) {
                    PrimaryButton(stringResource(R.string.common_start), onClick = vm::start)
                }
            }
            is BlinkPalmUiState.BlinkingRunning -> {
                Column(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text(
                        stringResource(R.string.blinkpalm_cycle, s.cycleIndex + 1, s.totalCycles),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(Spacing.lg))
                    TimerRing(progress = s.phaseProgress) {
                        Text(if (s.eyesClosed) "😌" else "👁️", fontSize = 44.sp)
                    }
                    Spacer(Modifier.height(Spacing.lg))
                    Text(
                        if (s.eyesClosed) stringResource(R.string.blinkpalm_close) else stringResource(R.string.blinkpalm_open),
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
            is BlinkPalmUiState.PalmingRunning -> {
                Column(
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    TimerRing(progress = s.progress, sizeDp = 200.dp) {
                        Text("${s.secondsLeft}", style = MaterialTheme.typography.displaySmall)
                    }
                    Spacer(Modifier.height(Spacing.lg))
                    Text(
                        stringResource(R.string.blinkpalm_palming_instruction),
                        style = MaterialTheme.typography.titleMedium,
                        textAlign = TextAlign.Center,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            is BlinkPalmUiState.Completed -> {
                ExerciseCompletionCard(
                    title = stringResource(R.string.common_exercise_done_title),
                    message = stringResource(R.string.blinkpalm_done_message),
                    onRepeat = vm::start,
                    onBack = onBack,
                )
            }
        }
    }
}
