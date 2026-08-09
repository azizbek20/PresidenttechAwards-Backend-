package com.eyedetect.ai.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import com.eyedetect.ai.R
import com.eyedetect.ai.EyeSymmetryUiState
import com.eyedetect.ai.data.ApiClient
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.vision.PupilHeuristicResult
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import com.eyedetect.ai.ui.theme.Sizing
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficGreen
import com.eyedetect.ai.ui.theme.TrafficGreenContainer
import com.eyedetect.ai.ui.theme.TrafficGrey
import com.eyedetect.ai.ui.theme.TrafficRed
import com.eyedetect.ai.ui.theme.TrafficYellow
import com.eyedetect.ai.ui.theme.decisionColor
import com.eyedetect.ai.ui.theme.decisionEmoji

// =====================================================================
//  TUGMALAR — dala uchun kattalashtirilgan (6-hujjat, 4.2)
// =====================================================================

/** Asosiy (Filled) tugma — 56 dp, ekrandagi bosh harakat. */
@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    containerColor: Color = MaterialTheme.colorScheme.primary,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(Sizing.buttonHeight),
        shape = RoundedCornerShape(28.dp),
        colors = ButtonDefaults.buttonColors(containerColor = containerColor),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** Ikkilamchi (Outlined) tugma — 56 dp, muqobil harakat. */
@Composable
fun SecondaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(Sizing.buttonHeight),
        shape = RoundedCornerShape(28.dp),
    ) { Text(text, style = MaterialTheme.typography.labelLarge) }
}

/** Matn tugmasi — kam ahamiyatli harakat ("Bekor qilish", "← Orqaga"). */
@Composable
fun TextActionButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    TextButton(onClick = onClick, modifier = modifier.height(Sizing.touchMin)) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

// =====================================================================
//  STATUS / HOLAT
// =====================================================================

/** Ijobiy/axborot banneri — yashil (galereya tanlovi kabi neytral eslatmalar uchun). */
@Composable
fun InfoBanner(text: String, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(TrafficGreenContainer)
            .padding(Spacing.md),
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text("✅")
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Color(0xFF1B5E20))
    }
}

/** Yuqoridagi server ulanish indikatori (6-hujjat, 6.A). */
@Composable
fun StatusBadge(online: Boolean, modifier: Modifier = Modifier) {
    val color = if (online) TrafficGreen else TrafficRed
    val label = if (online) stringResource(R.string.status_online) else stringResource(R.string.status_offline)
    val contentDesc = stringResource(R.string.status_content_desc, label)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(color.copy(alpha = 0.12f))
            .padding(horizontal = Spacing.md, vertical = 6.dp)
            .semantics { contentDescription = contentDesc },
    ) {
        Box(Modifier.size(9.dp).clip(CircleShape).background(color))
        Text(label, color = color, style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold)
    }
}

// =====================================================================
//  BEMOR KIRISH
// =====================================================================

/** Katta bemor ID maydoni (6-hujjat, 6.A). */
@Composable
fun PatientIdField(value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(stringResource(R.string.patient_id_label)) },
        placeholder = { Text(stringResource(R.string.patient_id_placeholder)) },
        singleLine = true,
        shape = RoundedCornerShape(Sizing.fieldRadius),
        modifier = modifier.fillMaxWidth(),
    )
}

/** "O'ng/Chap ko'z" segment tanlagichi — butun karta bosiladi (6-hujjat, 6.A). */
@Composable
fun EyeSelector(selected: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.md)) {
        listOf("right" to stringResource(R.string.common_eye_right), "left" to stringResource(R.string.common_eye_left)).forEach { (value, label) ->
            val isSel = selected == value
            val contentDesc = if (isSel) "$label ✓" else label
            Card(
                modifier = Modifier
                    .weight(1f)
                    .height(Sizing.buttonHeight)
                    .selectable(selected = isSel, onClick = { onSelect(value) })
                    .semantics { contentDescription = contentDesc },
                shape = RoundedCornerShape(Sizing.fieldRadius),
                colors = CardDefaults.cardColors(
                    containerColor = if (isSel) MaterialTheme.colorScheme.primaryContainer
                    else MaterialTheme.colorScheme.surface,
                ),
                border = BorderStroke(
                    1.5.dp,
                    if (isSel) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
                ),
            ) {
                Box(Modifier.fillMaxWidth().height(Sizing.buttonHeight), contentAlignment = Alignment.Center) {
                    Text(
                        label,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                        color = if (isSel) MaterialTheme.colorScheme.onPrimaryContainer
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

// =====================================================================
//  NATIJA KOMPONENTLARI (6-hujjat, 6.D)
// =====================================================================

/** Svetofor qaror kartasi — eng tepa, eng katta element. */
@Composable
fun TrafficLightCard(result: PredictResponse, modifier: Modifier = Modifier) {
    val bg = decisionColor(result.decision)
    val emoji = decisionEmoji(result.decision)
    val ungradable = result.decision != "REFER" && result.decision != "NO_REFER"

    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(bg)
            .padding(Spacing.xl)
            .semantics {
                contentDescription = "Natija: ${result.decisionText}" +
                    if (!ungradable) ", ishonch ${(result.probability * 100).toInt()} foiz" else ""
            },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text(emoji, fontSize = 46.sp)
        Text(
            result.decisionText,
            color = Color.White,
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
        )
        if (ungradable) {
            Text(
                stringResource(R.string.result_ungradable),
                color = Color.White.copy(alpha = 0.92f),
                style = MaterialTheme.typography.titleMedium,
            )
        } else {
            Text(
                "${(result.probability * 100).toInt()}%",
                color = Color.White,
                fontSize = 40.sp,
                fontWeight = FontWeight.ExtraBold,
            )
            Text(
                stringResource(R.string.result_confidence),
                color = Color.White.copy(alpha = 0.9f),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

/** Umumiy karta karkasi (sarlavha + tarkib). */
@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            Text(
                title.uppercase(),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            content()
        }
    }
}

@Composable
private fun KeyValueRow(key: String, value: String, valueColor: Color = MaterialTheme.colorScheme.onSurface) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(key, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = valueColor)
    }
}

/** Klinik tafsilot kartasi. */
@Composable
fun ClinicalDetailCard(result: PredictResponse) {
    SectionCard(stringResource(R.string.result_clinical_details)) {
        val ungradable = result.decision != "REFER" && result.decision != "NO_REFER"
        if (!ungradable) {
            KeyValueRow(stringResource(R.string.result_icdr_grade), "${result.icdrGrade} — ${result.gradeLabel}")
        }
        KeyValueRow(
            stringResource(R.string.result_image_quality),
            result.quality,
            valueColor = if (ungradable) TrafficGrey else MaterialTheme.colorScheme.onSurface,
        )
        val pid = result.patientId ?: stringResource(R.string.result_unknown_patient)
        val eye = when (result.eye) {
            "right" -> stringResource(R.string.common_eye_right_short)
            "left" -> stringResource(R.string.common_eye_left_short)
            else -> result.eye ?: stringResource(R.string.result_unknown_patient)
        }
        KeyValueRow(stringResource(R.string.result_patient_eye), "$pid · $eye")
        KeyValueRow(stringResource(R.string.result_model), result.modelVersion)
    }
}

/**
 * Mahalliy CV evristikasi kartasi (xiralik/opacity + qizil refleks) — backend
 * natijasidan MUSTAQIL, tashxis emas, faqat qo'shimcha skrining ko'rsatkichi.
 * `result` `null` bo'lsa (hali hisoblanmagan yoki muvaffaqiyatsiz) hech narsa chizmaydi.
 */
@Composable
fun PupilHeuristicCard(result: PupilHeuristicResult?) {
    if (result == null) return
    SectionCard(stringResource(R.string.result_local_heuristic_title)) {
        Text(
            stringResource(R.string.result_local_heuristic_disclaimer),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(2.dp))
        QualityRow(stringResource(R.string.result_local_opacity), result.opacity)
        QualityRow(stringResource(R.string.result_local_red_reflex), result.redReflex)
        if (!result.regionFound) {
            Text(
                stringResource(R.string.result_local_no_region),
                style = MaterialTheme.typography.bodySmall,
                color = TrafficGrey,
            )
        }
    }
}

/**
 * Ikki ko'z simmetriyasi kartasi — joriy ko'zning mahalliy evristika natijasini bemorning
 * qarshi ko'zi uchun oldin saqlangan natija bilan solishtiradi (klinikadagi Bruckner testi
 * g'oyasiga o'xshash: ikkala ko'z orasidagi sezilarli farq, har biri alohida "normal" ko'rinsa
 * ham, ogohlantiruvchi belgi hisoblanadi). `state` `null` bo'lsa (bemor ID yo'q yoki qarshi
 * ko'z hali skrining qilinmagan) hech narsa chizmaydi. Tashxis emas.
 */
@Composable
fun EyeSymmetryCard(state: EyeSymmetryUiState?) {
    if (state == null) return
    val comparedEyeLabel = when (state.comparedEye) {
        "left" -> stringResource(R.string.common_eye_left_short)
        "right" -> stringResource(R.string.common_eye_right_short)
        else -> "—"
    }
    val dateLabel = remember(state.comparedAtMs) {
        SimpleDateFormat("dd MMM, HH:mm", Locale.getDefault()).format(Date(state.comparedAtMs))
    }

    SectionCard(stringResource(R.string.result_symmetry_title)) {
        Text(
            stringResource(R.string.result_symmetry_disclaimer),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(2.dp))
        QualityRow(stringResource(R.string.result_symmetry_row), state.comparison.level)
        Text(
            stringResource(R.string.result_symmetry_compared_with, comparedEyeLabel, dateLabel),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

/** Heatmap kartasi — asl rasm + Grad-CAM yonma-yon (6-hujjat, 6.D.3). */
@Composable
fun HeatmapCard(result: PredictResponse) {
    val origUrl = ApiClient.absoluteUrl(result.imageUrl)
    val heatUrl = ApiClient.absoluteUrl(result.heatmapUrl)
    if (origUrl == null && heatUrl == null) return

    SectionCard(stringResource(R.string.result_heatmap_title)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            origUrl?.let { url ->
                HeatCell(
                    caption = stringResource(R.string.result_original_image),
                    url = url,
                    desc = stringResource(R.string.result_original_image_content_desc),
                    modifier = Modifier.weight(1f),
                )
            }
            heatUrl?.let { url ->
                HeatCell(
                    caption = stringResource(R.string.result_gradcam),
                    url = url,
                    desc = stringResource(R.string.result_gradcam_content_desc),
                    modifier = Modifier.weight(1f),
                )
            }
        }
        Text(
            stringResource(R.string.result_heatmap_note),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun HeatCell(caption: String, url: String, desc: String, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        Text(caption, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        AsyncImage(
            model = url,
            contentDescription = desc,
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)),
        )
    }
}

/** Keyingi qadam tavsiyasi (6-hujjat, 6.D.4). */
@Composable
fun RecommendationCard(decision: String) {
    val text = when (decision) {
        "REFER" -> stringResource(R.string.result_recommendation_refer)
        "NO_REFER" -> stringResource(R.string.result_recommendation_no_refer)
        else -> stringResource(R.string.result_recommendation_ungradable)
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f))
            .padding(Spacing.md),
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text("➜", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
        Text(text, style = MaterialTheme.typography.bodyLarge)
    }
}

/** Majburiy disklaymer (har natijada). */
@Composable
fun DisclaimerText(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

/** Ogohlantiruvchi banner (masalan UNGRADABLE "kasallik yo'q emas"). */
@Composable
fun WarningBanner(text: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(com.eyedetect.ai.ui.theme.TrafficYellowContainer)
            .padding(Spacing.md),
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text("⚠️")
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Color(0xFF7A5B00))
    }
}

// =====================================================================
//  HOLAT EKRANLARI
// =====================================================================

/** Yuklanish + progress qadamlari (6-hujjat, 6.C). */
@Composable
fun LoadingState(activeStep: Int = 2, onCancel: (() -> Unit)? = null) {
    val steps = listOf(
        stringResource(R.string.loading_step_uploaded),
        stringResource(R.string.loading_step_quality),
        stringResource(R.string.loading_step_analyzing),
        stringResource(R.string.loading_step_preparing),
    )
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
    ) {
        CircularProgressIndicator()
        Text(stringResource(R.string.loading_title), style = MaterialTheme.typography.titleMedium)
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            steps.forEachIndexed { i, label ->
                val done = i < activeStep
                val active = i == activeStep
                val dotColor = when {
                    done -> TrafficGreen
                    active -> MaterialTheme.colorScheme.primary
                    else -> MaterialTheme.colorScheme.outlineVariant
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.md)) {
                    Box(Modifier.size(16.dp).clip(CircleShape).background(dotColor), contentAlignment = Alignment.Center) {
                        if (done) Text("✓", color = Color.White, fontSize = 9.sp)
                    }
                    Text(
                        label,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal,
                        color = if (done || active) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        if (onCancel != null) {
            Spacer(Modifier.height(Spacing.xs))
            TextActionButton(stringResource(R.string.common_cancel), onCancel)
        }
    }
}

/** Xato holati — harakatga yo'naltiruvchi (6-hujjat, 6.F). */
@Composable
fun ErrorState(message: String, onRetry: () -> Unit, onNewPatient: () -> Unit) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
    ) {
        Text("⚠️", fontSize = 48.sp)
        Text(stringResource(R.string.error_title), style = MaterialTheme.typography.headlineSmall)
        Text(
            message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(Spacing.xs))
        PrimaryButton(stringResource(R.string.common_retry), onRetry)
        SecondaryButton(stringResource(R.string.common_new_patient), onNewPatient)
    }
}

// =====================================================================
//  KAMERA KOMPONENTLARI (6-hujjat, 6.B)
// =====================================================================

enum class QualityLevel { GOOD, WARN, BAD }

private fun qualityColor(level: QualityLevel): Color = when (level) {
    QualityLevel.GOOD -> TrafficGreen
    QualityLevel.WARN -> TrafficYellow
    QualityLevel.BAD -> TrafficRed
}

/** Real-vaqt kamera sifat paneli — uch svetofor nuqta + matn (6-hujjat, 6.B.3). */
@Composable
fun QualityPanel(
    focus: QualityLevel,
    light: QualityLevel,
    position: QualityLevel,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(Color.Black.copy(alpha = 0.6f))
            .padding(horizontal = Spacing.md, vertical = Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        QualityRow(stringResource(R.string.quality_focus), focus)
        QualityRow(stringResource(R.string.quality_light), light)
        QualityRow(stringResource(R.string.quality_position), position)
    }
}

@Composable
private fun QualityRow(label: String, level: QualityLevel) {
    val text = when (level) {
        QualityLevel.GOOD -> stringResource(R.string.quality_good)
        QualityLevel.WARN -> stringResource(R.string.quality_warn)
        QualityLevel.BAD -> stringResource(R.string.quality_bad)
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(qualityColor(level)))
        Text(stringResource(R.string.quality_row_format, label, text), color = Color.White, style = MaterialTheme.typography.bodyMedium)
    }
}

/** 72 dp doiraviy kamera zatvor tugmasi (6-hujjat, 4.2). */
@Composable
fun ShutterButton(enabled: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val ring = if (enabled) TrafficGreen else MaterialTheme.colorScheme.outlineVariant
    val contentDesc = stringResource(R.string.camera_shutter_content_desc)
    Box(
        modifier = modifier
            .size(Sizing.shutter)
            .clip(CircleShape)
            .background(ring)
            .padding(5.dp)
            .semantics { contentDescription = contentDesc },
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .fillMaxWidth()
                .height(Sizing.shutter)
                .clip(CircleShape)
                .background(Color.White)
                .selectable(selected = false, enabled = enabled, onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            Text("📷", fontSize = 26.sp)
        }
    }
}
