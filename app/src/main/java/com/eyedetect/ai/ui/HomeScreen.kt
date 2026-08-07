package com.eyedetect.ai.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import com.eyedetect.ai.R
import com.eyedetect.ai.ui.components.LanguagePicker
import com.eyedetect.ai.ui.components.MenuCard
import com.eyedetect.ai.ui.theme.Spacing

/**
 * Ilova kirish ekrani — foydalanuvchi Skrining oqimi yoki Ko'z mashqlari
 * bo'limiga o'tishni tanlaydi.
 */
@Composable
fun HomeScreen(onScreening: () -> Unit, onEyeCare: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
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

        MenuCard(
            title = stringResource(R.string.home_screening_title),
            subtitle = stringResource(R.string.home_screening_subtitle),
            emoji = "🩺",
            onClick = onScreening,
        )
        MenuCard(
            title = stringResource(R.string.home_eyecare_title),
            subtitle = stringResource(R.string.home_eyecare_subtitle),
            emoji = "🧘",
            onClick = onEyeCare,
        )
    }
}
