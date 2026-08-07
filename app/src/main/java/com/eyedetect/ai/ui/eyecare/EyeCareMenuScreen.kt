package com.eyedetect.ai.ui.eyecare

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import com.eyedetect.ai.R
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ExerciseStats
import com.eyedetect.ai.data.eyecare.ExerciseType
import com.eyedetect.ai.data.eyecare.ReminderSettings
import com.eyedetect.ai.data.eyecare.isToday
import com.eyedetect.ai.ui.components.GameCard
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.theme.Sizing
import com.eyedetect.ai.ui.theme.Spacing

private data class ExerciseMenuItem(val type: ExerciseType, val titleRes: Int, val subtitleRes: Int, val emoji: String)

private val EXERCISES = listOf(
    ExerciseMenuItem(ExerciseType.FollowDot, R.string.exercise_followdot_title, R.string.exercise_followdot_subtitle, "🔵"),
    ExerciseMenuItem(ExerciseType.FocusShift, R.string.exercise_focusshift_title, R.string.exercise_focusshift_subtitle, "🔍"),
    ExerciseMenuItem(ExerciseType.BlinkPalm, R.string.exercise_blinkpalm_title, R.string.exercise_blinkpalm_subtitle, "😌"),
)

/** Ko'z mashqlari bo'limi — 3 ta mashq + 20-20-20 eslatma holati. */
@Composable
fun EyeCareMenuScreen(
    onFollowDot: () -> Unit,
    onFocusShift: () -> Unit,
    onBlinkPalm: () -> Unit,
    onReminderSettings: () -> Unit,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val repo = remember { EyeCarePreferencesRepository(context) }
    val stats by repo.stats.collectAsState(initial = ExerciseStats())
    val settings by repo.settings.collectAsState(initial = ReminderSettings())

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Column {
            Text(
                stringResource(R.string.eyecare_menu_title),
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                stringResource(R.string.eyecare_streak, stats.streakDays),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
            modifier = Modifier.weight(1f),
        ) {
            items(EXERCISES) { item ->
                val doneToday = isToday(stats.lastCompletedMsFor(item.type))
                GameCard(
                    title = stringResource(item.titleRes),
                    subtitle = stringResource(item.subtitleRes),
                    emoji = item.emoji,
                    statusLabel = if (doneToday) stringResource(R.string.eyecare_done_today) else stringResource(R.string.eyecare_not_done_today),
                    onClick = when (item.type) {
                        ExerciseType.FollowDot -> onFollowDot
                        ExerciseType.FocusShift -> onFocusShift
                        ExerciseType.BlinkPalm -> onBlinkPalm
                    },
                )
            }
        }

        Card(
            onClick = onReminderSettings,
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(Sizing.cardRadius),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column {
                    Text(stringResource(R.string.reminder_row_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text(
                        if (settings.enabled) stringResource(R.string.reminder_row_enabled, settings.intervalMinutes) else stringResource(R.string.reminder_row_disabled),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Box(
                    Modifier
                        .clip(RoundedCornerShape(50))
                        .background(if (settings.enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant)
                        .padding(horizontal = Spacing.md, vertical = Spacing.xs),
                ) {
                    Text(
                        if (settings.enabled) stringResource(R.string.reminder_row_configure) else stringResource(R.string.reminder_row_enable),
                        color = MaterialTheme.colorScheme.surface,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}
