package com.eyedetect.ai.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.eyedetect.ai.UiState
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.ui.components.ClinicalDetailCard
import com.eyedetect.ai.ui.components.DisclaimerText
import com.eyedetect.ai.ui.components.ErrorState
import com.eyedetect.ai.ui.components.HeatmapCard
import com.eyedetect.ai.ui.components.LoadingState
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.RecommendationCard
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.TrafficLightCard
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing

/**
 * 3-ekran: yuklanish / natija (svetofor + ishonch + heatmap) / xato.
 * Barcha holatlar 6-hujjat (6.C/6.D/6.F) dizayniga mos, API kontrakti buzilmagan.
 */
@Composable
fun ResultScreen(
    uiState: UiState,
    onRetry: () -> Unit,
    onNewPatient: () -> Unit,
) {
    when (uiState) {
        is UiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            LoadingState()
        }

        is UiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            ErrorState(message = uiState.message, onRetry = onRetry, onNewPatient = onNewPatient)
        }

        is UiState.Success -> SuccessContent(uiState.result, onRetry, onNewPatient)

        UiState.Idle -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Natija yo'q.", style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun SuccessContent(r: PredictResponse, onRetry: () -> Unit, onNewPatient: () -> Unit) {
    val ungradable = r.decision != "REFER" && r.decision != "NO_REFER"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        // Brend + bemor
        Column {
            Text(
                "EYE DETECT AI",
                style = MaterialTheme.typography.titleLarge,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                "Natija · ${r.patientId ?: "—"}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // 1) Svetofor qaror kartasi
        TrafficLightCard(r)

        // UNGRADABLE uchun ogohlantirish
        if (ungradable) {
            WarningBanner("Bu \"kasallik yo'q\" degani EMAS. Rasm sifati past — qayta oling yoki mutaxassisga yo'llang.")
        }

        // 2) Klinik tafsilot
        ClinicalDetailCard(r)

        // 3) Heatmap (asl + Grad-CAM)
        HeatmapCard(r)

        // 4) Tavsiya
        RecommendationCard(r.decision)

        // 5) Disklaymer
        DisclaimerText(r.disclaimer)

        // 6) Harakat tugmalari
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            PrimaryButton(
                text = if (ungradable) "Qayta olish" else "Yana bir rasm",
                onClick = onRetry,
                modifier = Modifier.weight(1f),
            )
            SecondaryButton(
                text = "Yangi bemor",
                onClick = onNewPatient,
                modifier = Modifier.weight(1f),
            )
        }
    }
}
