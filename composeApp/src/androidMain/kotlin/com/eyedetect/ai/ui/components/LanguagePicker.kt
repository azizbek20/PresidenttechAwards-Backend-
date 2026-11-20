package com.eyedetect.ai.ui.components

import android.app.Activity
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.eyedetect.ai.LocalePrefs
import com.eyedetect.ai.ui.theme.Spacing

private val LANGUAGES = listOf("uz", "ru", "en")

/** Ilova tilini almashtiruvchi kichik chip qator — Bosh sahifada joylashadi. */
@Composable
fun LanguagePicker(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    // Foydalanuvchi tanlagan til bo'lmasa, tizim tilidan foydalaniladi — chip
    // ko'rsatkichi har doim ekrandagi haqiqiy til bilan mos keladi.
    val resolvedTag = LocalePrefs.getLanguageTag(context) ?: LocalConfiguration.current.locales[0].language
    val currentTag = if (resolvedTag in LANGUAGES) resolvedTag else "uz"

    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        LANGUAGES.forEach { tag ->
            val isSelected = tag == currentTag
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(50))
                    .background(if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface)
                    .border(
                        BorderStroke(1.dp, if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant),
                        RoundedCornerShape(50),
                    )
                    .selectable(selected = isSelected, onClick = {
                        if (!isSelected) {
                            LocalePrefs.setLanguageTag(context, tag)
                            (context as? Activity)?.recreate()
                        }
                    })
                    .padding(horizontal = Spacing.sm, vertical = 6.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    tag.uppercase(),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                    color = if (isSelected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
