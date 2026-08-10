package com.eyedetect.ai.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.eyedetect.ai.R
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.data.upload.PendingUploadEntity
import com.eyedetect.ai.data.upload.PendingUploadRepository
import com.eyedetect.ai.ui.components.QualityLevel
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.theme.Sizing
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficRed
import com.eyedetect.ai.ui.theme.TrafficRedContainer
import com.eyedetect.ai.ui.theme.TrafficYellow
import com.eyedetect.ai.ui.theme.TrafficYellowContainer
import com.eyedetect.ai.ui.theme.decisionColor
import com.eyedetect.ai.ui.theme.decisionEmoji
import com.eyedetect.ai.upload.UploadScheduler
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Room'da saqlangan `QualityLevel.name` ("GOOD"/"WARN"/"BAD")ni joriy tildagi matnga aylantiradi. */
@Composable
private fun localizedQuality(name: String?): String {
    val level = name?.let { runCatching { QualityLevel.valueOf(it) }.getOrNull() }
    return when (level) {
        QualityLevel.GOOD -> stringResource(R.string.quality_good)
        QualityLevel.WARN -> stringResource(R.string.quality_warn)
        QualityLevel.BAD -> stringResource(R.string.quality_bad)
        null -> stringResource(R.string.common_dash)
    }
}

/** O'tgan skrininglar tarixi — Room'da saqlangan yozuvlarni ko'rsatadi (PLAN.md 4-band). */
@Composable
fun HistoryScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val repo = remember { ScreeningHistoryRepository(context) }
    val pendingRepo = remember { PendingUploadRepository(context) }
    val entries by repo.history.collectAsState(initial = null)
    val pending by pendingRepo.pending.collectAsState(initial = emptyList())
    val scope = rememberCoroutineScope()

    Column(modifier = Modifier.fillMaxSize().padding(Spacing.xl)) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Text(
            stringResource(R.string.history_title),
            style = MaterialTheme.typography.headlineMedium,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(top = Spacing.sm, bottom = Spacing.lg),
        )

        if (pending.isNotEmpty()) {
            Text(
                stringResource(R.string.history_pending_section_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = Spacing.sm),
            )
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                pending.forEach { entry ->
                    PendingUploadCard(
                        entry = entry,
                        onCancel = {
                            scope.launch {
                                UploadScheduler.cancel(context, entry.id)
                                pendingRepo.delete(entry)
                            }
                        },
                        onRetryNow = {
                            scope.launch {
                                pendingRepo.resetFailed(entry.id)
                                UploadScheduler.enqueue(context, entry.id)
                            }
                        },
                    )
                }
            }
            Spacer(Modifier.height(Spacing.lg))
        }

        val list = entries
        when {
            list == null -> Unit // hali yuklanmoqda — hech narsa ko'rsatmaymiz (yaltirash yo'q)
            list.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    stringResource(R.string.history_empty),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                items(list, key = { it.id }) { entry ->
                    HistoryEntryCard(
                        entry = entry,
                        onDelete = { scope.launch { repo.delete(entry) } },
                    )
                }
            }
        }
    }
}

@Composable
private fun HistoryEntryCard(entry: ScreeningHistoryEntity, onDelete: () -> Unit) {
    val ungradable = entry.decision != "REFER" && entry.decision != "NO_REFER"
    val eyeLabel = when (entry.eye) {
        "left" -> stringResource(R.string.common_eye_left_short)
        "right" -> stringResource(R.string.common_eye_right_short)
        else -> entry.eye ?: stringResource(R.string.common_dash)
    }
    val dateLabel = remember(entry.savedAtMs) {
        SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(entry.savedAtMs))
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text(decisionEmoji(entry.decision))
                    Text(
                        if (ungradable) stringResource(R.string.result_ungradable) else entry.decisionText,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = decisionColor(entry.decision),
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(
                        Icons.Filled.Delete,
                        contentDescription = stringResource(R.string.history_delete_content_desc),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            val pid = entry.patientId?.takeIf { it.isNotBlank() } ?: stringResource(R.string.result_unknown_patient)
            Text(
                stringResource(R.string.history_patient_eye_row, pid, eyeLabel),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (!ungradable) {
                Text(
                    stringResource(
                        R.string.history_icdr_grade_row,
                        stringResource(R.string.result_icdr_grade),
                        entry.icdrGrade,
                        entry.gradeLabel,
                        (entry.probability * 100).toInt(),
                    ),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (entry.localOpacity != null || entry.localRedReflex != null) {
                Text(
                    stringResource(
                        R.string.history_local_heuristic_row,
                        localizedQuality(entry.localOpacity),
                        localizedQuality(entry.localRedReflex),
                    ),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(dateLabel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** Navbatdagi (hali yuborilmagan) yoki doimiy xato bilan yakunlangan skrining — [onRetryNow]
 * faqat [PendingUploadEntity.failed] true bo'lganda ko'rsatiladi ([HistoryScreen], PLAN.md
 * 4-band, offline navbat). */
@Composable
private fun PendingUploadCard(entry: PendingUploadEntity, onCancel: () -> Unit, onRetryNow: () -> Unit) {
    val eyeLabel = when (entry.eye) {
        "left" -> stringResource(R.string.common_eye_left_short)
        "right" -> stringResource(R.string.common_eye_right_short)
        else -> entry.eye
    }
    val pid = entry.patientId?.takeIf { it.isNotBlank() } ?: stringResource(R.string.result_unknown_patient)
    val dateLabel = remember(entry.queuedAtMs) {
        SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(entry.queuedAtMs))
    }
    val statusColor: Color = if (entry.failed) TrafficRed else TrafficYellow
    val containerColor: Color = if (entry.failed) TrafficRedContainer else TrafficYellowContainer

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(containerColor = containerColor),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    if (entry.failed) stringResource(R.string.history_pending_status_failed)
                    else stringResource(R.string.history_pending_status_queued),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = statusColor,
                )
                Row {
                    if (entry.failed) {
                        IconButton(onClick = onRetryNow) {
                            Icon(
                                Icons.Filled.Refresh,
                                contentDescription = stringResource(R.string.history_pending_retry_content_desc),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    IconButton(onClick = onCancel) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = stringResource(R.string.history_pending_cancel_content_desc),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            Text(
                stringResource(R.string.history_patient_eye_row, pid, eyeLabel),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                stringResource(R.string.history_pending_queued_at_row, dateLabel),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
