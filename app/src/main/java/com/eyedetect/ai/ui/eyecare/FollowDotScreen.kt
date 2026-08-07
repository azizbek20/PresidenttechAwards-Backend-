package com.eyedetect.ai.ui.eyecare

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.eyecare.FollowDotUiState
import com.eyedetect.ai.eyecare.FollowDotViewModel
import com.eyedetect.ai.ui.components.DotTrackerCanvas
import com.eyedetect.ai.ui.components.ExerciseCompletionCard
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.theme.Spacing

/** Nuqtani kuzatish o'yini — ko'z mushaklarini mashq qildiruvchi animatsion mashq. */
@Composable
fun FollowDotScreen(onBack: () -> Unit, vm: FollowDotViewModel = viewModel()) {
    val state by vm.uiState.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Text(stringResource(R.string.exercise_followdot_title), style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
        Text(
            stringResource(R.string.followdot_instructions),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when (val s = state) {
            is FollowDotUiState.Idle -> {
                Column(modifier = Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.Center) {
                    PrimaryButton(stringResource(R.string.common_start), onClick = vm::start)
                }
            }
            is FollowDotUiState.Running -> {
                LinearProgressIndicator(progress = { s.progress }, modifier = Modifier.fillMaxWidth())
                Text(stringResource(R.string.followdot_seconds_left, s.remainingSeconds), style = MaterialTheme.typography.bodyMedium)
                DotTrackerCanvas(dotPosition = s.dot, modifier = Modifier.weight(1f).fillMaxWidth())
            }
            is FollowDotUiState.Completed -> {
                ExerciseCompletionCard(
                    title = stringResource(R.string.common_exercise_done_title),
                    message = stringResource(R.string.followdot_done_message),
                    onRepeat = vm::start,
                    onBack = onBack,
                )
            }
        }
    }
}
