package com.eyedetect.ai.ui

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.eyedetect.ai.EyeSymmetryUiState
import com.eyedetect.ai.R
import com.eyedetect.ai.UiState
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.ui.components.ClinicalDetailCard
import com.eyedetect.ai.ui.components.DisclaimerText
import com.eyedetect.ai.ui.components.ErrorState
import com.eyedetect.ai.ui.components.EyeSymmetryCard
import com.eyedetect.ai.ui.components.HeatmapCard
import com.eyedetect.ai.ui.components.LoadingState
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.PupilHeuristicCard
import com.eyedetect.ai.ui.components.QueuedState
import com.eyedetect.ai.ui.components.RecommendationCard
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.TrafficLightCard
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.isUngradableDecision
import com.eyedetect.ai.vision.PupilHeuristicResult

/**
 * 3-ekran: yuklanish / natija (svetofor + ishonch + heatmap) / xato.
 * Barcha holatlar 6-hujjat (6.C/6.D/6.F) dizayniga mos, API kontrakti buzilmagan.
 */
@Composable
fun ResultScreen(
    uiState: UiState,
    localHeuristic: PupilHeuristicResult?,
    symmetry: EyeSymmetryUiState?,
    uploadProgress: Float? = null,
    onRetry: () -> Unit,
    onCancelUpload: (() -> Unit)? = null,
    onNewPatient: () -> Unit,
) {
    when (uiState) {
        is UiState.Loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            LoadingState(progress = uploadProgress, onCancel = onCancelUpload)
        }

        is UiState.Error -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            ErrorState(message = uiState.message, onRetry = onRetry, onNewPatient = onNewPatient)
        }

        is UiState.Success -> SuccessContent(uiState.result, localHeuristic, symmetry, onRetry, onNewPatient)

        UiState.Queued -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            QueuedState(onDone = onNewPatient)
        }

        UiState.Idle -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(stringResource(R.string.result_none), style = MaterialTheme.typography.bodyLarge)
        }
    }
}

@Composable
private fun SuccessContent(
    r: PredictResponse,
    localHeuristic: PupilHeuristicResult?,
    symmetry: EyeSymmetryUiState?,
    onRetry: () -> Unit,
    onNewPatient: () -> Unit,
) {
    val ungradable = isUngradableDecision(r.decision)
    val context = LocalContext.current

    // Harakat tugmalari (Yangi surat/Yangi bemor) skroll qatoridan tashqarida, pastda
    // qotirilgan — natija sahifasi 8+ ketma-ket kartadan iborat (svetofor, klinik
    // tafsilot, mahalliy evristika, simmetriya, heatmap, tavsiya, disklaymer), shu
    // sababli asosiy keyingi qadam har doim bir tegishda yetib bo'ladigan bo'lishi kerak
    // — pastigacha aylantirishga majbur qilmasdan.
    Column(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            // Brend + bemor
            Column {
                Text(
                    stringResource(R.string.app_name),
                    style = MaterialTheme.typography.titleLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    stringResource(R.string.result_header, r.patientId ?: stringResource(R.string.result_unknown_patient)),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            TrafficLightCard(r)

            if (ungradable) {
                WarningBanner(stringResource(R.string.result_ungradable_warning))
            }

            ClinicalDetailCard(r)

            // Mahalliy CV evristikasi (opacity/red-reflex) — mavjud bo'lsa
            PupilHeuristicCard(localHeuristic)

            // Ikki ko'z simmetriyasi — qarshi ko'z uchun oldingi natija topilgan bo'lsa
            EyeSymmetryCard(symmetry)

            HeatmapCard(r)

            RecommendationCard(r.decision)

            DisclaimerText(r.disclaimer)

            // Ulashish — foydalanuvchi tanlagan ilova orqali (Telegram, SMS, email va h.k.);
            // hech narsa avtomatik yuborilmaydi, faqat tizim ulashish oynasi ochiladi.
            TextActionButton(
                text = "🔗 " + stringResource(R.string.result_share_button),
                onClick = { shareResult(context, r) },
            )
        }

        Surface(
            color = MaterialTheme.colorScheme.surface,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                PrimaryButton(
                    text = if (ungradable) stringResource(R.string.common_retake) else stringResource(R.string.result_new_photo),
                    onClick = onRetry,
                    modifier = Modifier.weight(1f),
                )
                SecondaryButton(
                    text = stringResource(R.string.common_new_patient),
                    onClick = onNewPatient,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

/** Tizim ulashish oynasini (ACTION_SEND) ochadi — foydalanuvchi o'zi ilova va qabul qiluvchini tanlaydi. */
private fun shareResult(context: Context, r: PredictResponse) {
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/plain"
        putExtra(Intent.EXTRA_TEXT, buildShareText(context, r))
    }
    context.startActivity(Intent.createChooser(intent, context.getString(R.string.result_share_chooser_title)))
}

private fun buildShareText(context: Context, r: PredictResponse): String {
    val ungradable = isUngradableDecision(r.decision)
    val eyeLabel = eyeLabel(context, r.eye)
    val probabilityText = if (ungradable) "—" else "${(r.probability * 100).toInt()}%"
    val gradeText = if (ungradable) "—" else "${r.icdrGrade} — ${r.gradeLabel}"
    return context.getString(
        R.string.result_share_text,
        context.getString(R.string.app_name),
        r.patientId ?: context.getString(R.string.result_unknown_patient),
        eyeLabel,
        r.decisionText,
        probabilityText,
        gradeText,
        r.processedAt,
        r.disclaimer,
    )
}
