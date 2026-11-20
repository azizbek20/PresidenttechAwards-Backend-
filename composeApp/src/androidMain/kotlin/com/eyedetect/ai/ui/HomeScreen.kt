package com.eyedetect.ai.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import com.eyedetect.ai.R
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.ExerciseStats
import com.eyedetect.ai.ui.components.LanguagePicker
import com.eyedetect.ai.ui.components.MenuCard
import com.eyedetect.ai.ui.theme.Spacing

/**
 * Ilova kirish ekrani — foydalanuvchi Skrining oqimi yoki Ko'z mashqlari
 * bo'limiga o'tishni tanlaydi.
 */
import androidx.compose.material3.windowsizeclass.WindowWidthSizeClass
import androidx.compose.material3.windowsizeclass.WindowWidthSizeClass.Companion.Expanded

@Composable
fun HomeScreen(
    widthSizeClass: WindowWidthSizeClass = WindowWidthSizeClass.Compact,
    onScreening: () -> Unit,
    onEyeCare: () -> Unit,
    onHistory: () -> Unit,
    onAnalysis: () -> Unit = {},
) {
    val context = LocalContext.current
    val eyeCareRepo = remember { EyeCarePreferencesRepository(context) }
    val stats by eyeCareRepo.stats.collectAsState(initial = ExerciseStats())

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(
                    stringResource(R.string.app_name),
                    style = MaterialTheme.typography.headlineMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    stringResource(R.string.home_subtitle),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            LanguagePicker()
        }

        if (widthSizeClass == Expanded) {
            Row(horizontalArrangement = Arrangement.spacedBy(Spacing.lg)) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
                    MenuCard(
                        title = stringResource(R.string.home_screening_title),
                        subtitle = stringResource(R.string.home_screening_subtitle),
                        emoji = "🩺",
                        onClick = onScreening,
                    )
                    MenuCard(
                        title = stringResource(R.string.home_analysis_title),
                        subtitle = stringResource(R.string.home_analysis_subtitle),
                        emoji = "🔬",
                        onClick = onAnalysis,
                    )
                }
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
                    MenuCard(
                        title = stringResource(R.string.home_eyecare_title),
                        subtitle = stringResource(R.string.home_eyecare_subtitle),
                        emoji = "🧘",
                        onClick = onEyeCare,
                        badge = if (stats.streakDays > 0) "🔥 ${stats.streakDays}" else null,
                    )
                    MenuCard(
                        title = stringResource(R.string.home_history_title),
                        subtitle = stringResource(R.string.home_history_subtitle),
                        emoji = "🗂️",
                        onClick = onHistory,
                    )
                }
            }
        } else {
            MenuCard(
                title = stringResource(R.string.home_screening_title),
                subtitle = stringResource(R.string.home_screening_subtitle),
                emoji = "🩺",
                onClick = onScreening,
            )
            MenuCard(
                title = stringResource(R.string.home_analysis_title),
                subtitle = stringResource(R.string.home_analysis_subtitle),
                emoji = "🔬",
                onClick = onAnalysis,
            )
            MenuCard(
                title = stringResource(R.string.home_eyecare_title),
                subtitle = stringResource(R.string.home_eyecare_subtitle),
                emoji = "🧘",
                onClick = onEyeCare,
                badge = if (stats.streakDays > 0) "🔥 ${stats.streakDays}" else null,
            )
            MenuCard(
                title = stringResource(R.string.home_history_title),
                subtitle = stringResource(R.string.home_history_subtitle),
                emoji = "🗂️",
                onClick = onHistory,
            )
        }
    }
}
