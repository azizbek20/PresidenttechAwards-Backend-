package com.eyedetect.ai.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.eyedetect.ai.R
import com.eyedetect.ai.ui.theme.Sizing
import com.eyedetect.ai.ui.theme.Spacing

// =====================================================================
//  KO'Z MASHQLARI — bosh sahifa / menyu kartalari
// =====================================================================

/** Bosh sahifadagi katta bo'lim kartasi ("Skrining" / "Ko'z mashqlari"). */
@Composable
fun MenuCard(
    title: String,
    subtitle: String,
    emoji: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val titleSubtitleDesc = stringResource(R.string.content_desc_title_subtitle, title, subtitle)
    Card(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(120.dp)
            .semantics { contentDescription = titleSubtitleDesc },
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            Box(
                Modifier
                    .size(56.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) { Text(emoji, fontSize = 26.sp) }
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** Ko'z mashqlari menyusidagi 2x2 to'r kartasi. */
@Composable
fun GameCard(
    title: String,
    subtitle: String,
    emoji: String,
    statusLabel: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val titleSubtitleDesc = if (statusLabel != null) {
        stringResource(R.string.content_desc_title_subtitle_status, title, subtitle, statusLabel)
    } else {
        stringResource(R.string.content_desc_title_subtitle, title, subtitle)
    }
    Card(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .semantics { contentDescription = titleSubtitleDesc },
        shape = RoundedCornerShape(Sizing.cardRadius),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.md),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            Text(emoji, fontSize = 30.sp)
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(
                subtitle,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (statusLabel != null) {
                Text(
                    statusLabel,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

// =====================================================================
//  TAYMER HALQASI — mashq ekranlarida umumiy foydalanish
// =====================================================================

/** Aylana progress-taymer — markazida ixtiyoriy kontent (soniya/label). */
@Composable
fun TimerRing(
    progress: Float,
    modifier: Modifier = Modifier,
    sizeDp: Dp = 160.dp,
    strokeWidth: Dp = 12.dp,
    content: @Composable () -> Unit = {},
) {
    val track = MaterialTheme.colorScheme.outlineVariant
    val active = MaterialTheme.colorScheme.primary
    Box(modifier = modifier.size(sizeDp), contentAlignment = Alignment.Center) {
        Canvas(modifier = Modifier.size(sizeDp)) {
            val stroke = strokeWidth.toPx()
            drawArc(
                color = track,
                startAngle = -90f,
                sweepAngle = 360f,
                useCenter = false,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = stroke, cap = StrokeCap.Round),
            )
            drawArc(
                color = active,
                startAngle = -90f,
                sweepAngle = 360f * progress.coerceIn(0f, 1f),
                useCenter = false,
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = stroke, cap = StrokeCap.Round),
            )
        }
        content()
    }
}

// =====================================================================
//  MASHQ YAKUNI
// =====================================================================

/** Mashq tugagach ko'rsatiladigan yakun kartasi. */
@Composable
fun ExerciseCompletionCard(
    title: String,
    message: String,
    onRepeat: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxWidth().padding(Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Text("✅", fontSize = 48.sp)
        Text(title, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
        Text(
            message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(Spacing.xs))
        PrimaryButton(stringResource(R.string.common_repeat), onRepeat)
        TextActionButton(stringResource(R.string.common_back), onBack)
    }
}

// =====================================================================
//  INTERVAL TANLAGICH — eslatma sozlamalari uchun
// =====================================================================

/** Daqiqalar ro'yxatidan bittasini tanlash uchun chip qator (EyeSelector uslubida). */
@Composable
fun IntervalChipRow(
    options: List<Int>,
    selected: Int,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier = modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        options.forEach { minutes ->
            val isSel = selected == minutes
            val chipDesc = if (isSel) {
                stringResource(R.string.interval_chip_content_desc_selected, minutes)
            } else {
                stringResource(R.string.interval_chip_content_desc, minutes)
            }
            Card(
                modifier = Modifier
                    .weight(1f)
                    .height(Sizing.touchMin)
                    .selectable(selected = isSel, onClick = { onSelect(minutes) })
                    .semantics { contentDescription = chipDesc },
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
                Box(Modifier.fillMaxWidth().height(Sizing.touchMin), contentAlignment = Alignment.Center) {
                    Text(
                        "$minutes",
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

/** FollowDotScreen uchun — nisbiy (0..1) markazga asoslangan nuqta chizmasi. */
@Composable
fun DotTrackerCanvas(dotPosition: Offset, modifier: Modifier = Modifier, dotRadiusDp: Dp = 22.dp) {
    val dotColor = MaterialTheme.colorScheme.primary
    Canvas(modifier = modifier) {
        val radiusPx = dotRadiusDp.toPx()
        val cx = dotPosition.x * size.width
        val cy = dotPosition.y * size.height
        drawCircle(color = dotColor, radius = radiusPx, center = Offset(cx, cy))
    }
}
