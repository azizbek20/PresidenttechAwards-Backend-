package com.eyedetect.ai.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.upload.PendingUploadEntity
import com.eyedetect.ai.ui.components.QualityLevel
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.theme.Sizing
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficRed
import com.eyedetect.ai.ui.theme.TrafficRedContainer
import com.eyedetect.ai.ui.theme.TrafficYellow
import com.eyedetect.ai.ui.theme.TrafficYellowContainer
import com.eyedetect.ai.ui.theme.decisionColor
import com.eyedetect.ai.ui.theme.decisionIcon
import com.eyedetect.ai.ui.theme.isUngradableDecision
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
fun HistoryScreen(onBack: () -> Unit, vm: HistoryViewModel = viewModel()) {
    val entries by vm.history.collectAsState(initial = null)
    val pending by vm.pending.collectAsState(initial = emptyList())

    var searchQuery by rememberSaveable { mutableStateOf("") }
    var selectionMode by rememberSaveable { mutableStateOf(false) }
    var selectedIds by remember { mutableStateOf(emptySet<Long>()) }
    var showDeleteConfirm by rememberSaveable { mutableStateOf(false) }

    val filteredList = entries?.filter { entry ->
        searchQuery.isBlank() || entry.patientId?.contains(searchQuery, ignoreCase = true) == true
    }

    fun exitSelectionMode() {
        selectionMode = false
        selectedIds = emptySet()
    }

    Column(modifier = Modifier.fillMaxSize().padding(Spacing.xl)) {
        if (selectionMode) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                    IconButton(onClick = { exitSelectionMode() }) {
                        Icon(Icons.Filled.Close, contentDescription = stringResource(R.string.history_select_cancel_content_desc))
                    }
                    Text(stringResource(R.string.history_selected_count, selectedIds.size), style = MaterialTheme.typography.titleMedium)
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextActionButton(stringResource(R.string.history_select_all), onClick = {
                        selectedIds = filteredList.orEmpty().map { it.id }.toSet()
                    })
                    IconButton(onClick = { showDeleteConfirm = true }, enabled = selectedIds.isNotEmpty()) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = stringResource(R.string.history_delete_selected_content_desc),
                            tint = if (selectedIds.isNotEmpty()) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        } else {
            TextActionButton(stringResource(R.string.common_back), onBack)
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = Spacing.sm, bottom = Spacing.lg),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                stringResource(R.string.history_title),
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            if (!selectionMode && !entries.isNullOrEmpty()) {
                TextActionButton(stringResource(R.string.history_select_button), onClick = { selectionMode = true })
            }
        }

        if (!entries.isNullOrEmpty()) {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text(stringResource(R.string.history_search_placeholder)) },
                leadingIcon = { Icon(Icons.Filled.Search, contentDescription = null) },
                singleLine = true,
                shape = RoundedCornerShape(Sizing.fieldRadius),
                modifier = Modifier.fillMaxWidth().padding(bottom = Spacing.lg),
            )
        }

        if (showDeleteConfirm) {
            AlertDialog(
                onDismissRequest = { showDeleteConfirm = false },
                title = { Text(stringResource(R.string.history_delete_selected_dialog_title)) },
                text = { Text(stringResource(R.string.history_delete_selected_dialog_message, selectedIds.size)) },
                confirmButton = {
                    TextButton(onClick = {
                        val toDelete = entries.orEmpty().filter { it.id in selectedIds }
                        vm.deleteEntries(toDelete)
                        exitSelectionMode()
                        showDeleteConfirm = false
                    }) { Text(stringResource(R.string.history_delete_confirm), color = MaterialTheme.colorScheme.error) }
                },
                dismissButton = {
                    TextButton(onClick = { showDeleteConfirm = false }) { Text(stringResource(R.string.common_cancel)) }
                },
            )
        }

        if (pending.isNotEmpty() && !selectionMode) {
            Text(
                stringResource(R.string.history_pending_section_title),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(bottom = Spacing.sm),
            )
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                pending.forEach { entry ->
                    PendingUploadCard(
                        entry = entry,
                        onCancel = { vm.cancelPending(entry) },
                        onRetryNow = { vm.retryPendingNow(entry) },
                    )
                }
            }
            Spacer(Modifier.height(Spacing.lg))
        }

        val list = filteredList
        val savedEntries = entries
        when {
            savedEntries == null -> Unit // hali yuklanmoqda — hech narsa ko'rsatmaymiz (yaltirash yo'q)
            savedEntries.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    stringResource(R.string.history_empty),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            list.isNullOrEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text(
                    stringResource(R.string.history_search_empty),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            else -> LazyColumn(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                items(list, key = { it.id }) { entry ->
                    HistoryEntryCard(
                        entry = entry,
                        selectionMode = selectionMode,
                        selected = entry.id in selectedIds,
                        onToggleSelect = {
                            selectedIds = if (entry.id in selectedIds) selectedIds - entry.id else selectedIds + entry.id
                        },
                        onDelete = { vm.deleteEntry(entry) },
                    )
                }
            }
        }
    }
}

@Composable
private fun HistoryEntryCard(
    entry: ScreeningHistoryEntity,
    onDelete: () -> Unit,
    selectionMode: Boolean = false,
    selected: Boolean = false,
    onToggleSelect: () -> Unit = {},
) {
    val ungradable = isUngradableDecision(entry.decision)
    val eyeLabel = eyeShortLabel(entry.eye)
    val dateLabel = remember(entry.savedAtMs) {
        SimpleDateFormat("dd MMM yyyy, HH:mm", Locale.getDefault()).format(Date(entry.savedAtMs))
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .let { if (selectionMode) it.clickable { onToggleSelect() } else it },
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surface,
        ),
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
                    Icon(
                        decisionIcon(entry.decision),
                        contentDescription = null,
                        tint = decisionColor(entry.decision),
                        modifier = Modifier.size(20.dp),
                    )
                    Text(
                        if (ungradable) stringResource(R.string.result_ungradable) else entry.decisionText,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = decisionColor(entry.decision),
                    )
                }
                if (selectionMode) {
                    val checkboxContentDesc = stringResource(R.string.history_checkbox_content_desc)
                    Checkbox(
                        checked = selected,
                        onCheckedChange = { onToggleSelect() },
                        modifier = Modifier.semantics { contentDescription = checkboxContentDesc },
                    )
                } else {
                    IconButton(onClick = onDelete) {
                        Icon(
                            Icons.Filled.Delete,
                            contentDescription = stringResource(R.string.history_delete_content_desc),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
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
    val eyeLabel = eyeShortLabel(entry.eye)
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
