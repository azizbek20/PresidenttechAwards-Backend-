package com.eyedetect.ai.ui.analysis

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import coil.compose.AsyncImage
import com.eyedetect.ai.AnalysisUiState
import com.eyedetect.ai.AnalysisViewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.data.AnalysisFinding
import com.eyedetect.ai.data.AnalysisTypes
import com.eyedetect.ai.data.AnalyzeResponse
import com.eyedetect.ai.ui.components.DisclaimerText
import com.eyedetect.ai.ui.components.ErrorState
import com.eyedetect.ai.ui.components.LoadingState
import com.eyedetect.ai.ui.components.MenuCard
import com.eyedetect.ai.ui.components.PatientIdField
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficGreen
import com.eyedetect.ai.ui.theme.TrafficGrey
import com.eyedetect.ai.ui.theme.TrafficRed
import com.eyedetect.ai.ui.theme.TrafficYellow
import java.io.File

/** Kamera rasmi vaqtincha saqlanadigan papka (`res/xml/file_paths.xml` bilan bir xil). */
internal const val ANALYSIS_CAPTURE_DIR = "analysis"

private data class TypeUi(val title: Int, val subtitle: Int, val emoji: String, val tip: Int)

private fun typeUi(code: String?): TypeUi = when (code) {
    AnalysisTypes.EXTERNAL_EYE -> TypeUi(R.string.analysis_type_external_eye, R.string.analysis_type_external_eye_sub, "👁️", R.string.analysis_tip_external_eye)
    AnalysisTypes.SKIN -> TypeUi(R.string.analysis_type_skin, R.string.analysis_type_skin_sub, "🩹", R.string.analysis_tip_skin)
    AnalysisTypes.ORAL -> TypeUi(R.string.analysis_type_oral, R.string.analysis_type_oral_sub, "👄", R.string.analysis_tip_oral)
    else -> TypeUi(R.string.analysis_type_nail, R.string.analysis_type_nail_sub, "💅", R.string.analysis_tip_nail)
}

@Composable
private fun ScreenTitle(title: String, subtitle: String? = null, onBack: (() -> Unit)? = null) {
    Column {
        if (onBack != null) TextActionButton(stringResource(R.string.analysis_back), onBack)
        Text(title, style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
        if (subtitle != null) {
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// =====================================================================
//  1. Tahlil turini tanlash
// =====================================================================
@Composable
fun AnalysisTypeScreen(onSelect: (String) -> Unit, onBack: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        ScreenTitle(
            stringResource(R.string.analysis_types_title),
            stringResource(R.string.analysis_types_subtitle),
            onBack,
        )
        AnalysisTypes.ALL.forEach { code ->
            val ui = typeUi(code)
            MenuCard(
                title = stringResource(ui.title),
                subtitle = stringResource(ui.subtitle),
                emoji = ui.emoji,
                onClick = { onSelect(code) },
            )
        }
        DisclaimerText(stringResource(R.string.analysis_types_note))
    }
}

// =====================================================================
//  2. Bemor ID + rasm (kamera yoki galereya)
// =====================================================================
private fun newCaptureUri(context: Context): Uri {
    val dir = File(context.cacheDir, ANALYSIS_CAPTURE_DIR).apply { mkdirs() }
    val file = File(dir, "capture_${System.currentTimeMillis()}.jpg")
    return FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
}

@Composable
fun AnalysisCaptureScreen(vm: AnalysisViewModel, onAnalyze: () -> Unit, onBack: () -> Unit) {
    val context = LocalContext.current
    val type by vm.type.collectAsState()
    val patientId by vm.patientId.collectAsState()
    val bodySite by vm.bodySite.collectAsState()
    val ui = typeUi(type)

    var pendingCapture by rememberSaveable { mutableStateOf<String?>(null) }
    var permissionDenied by remember { mutableStateOf(false) }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = pendingCapture?.let(Uri::parse)
        pendingCapture = null
        if (ok && uri != null) {
            vm.analyze(uri)
            onAnalyze()
        }
    }
    fun launchCamera() {
        val uri = newCaptureUri(context)
        pendingCapture = uri.toString()
        takePicture.launch(uri)
    }
    // Manifestda CAMERA ruxsati e'lon qilingani uchun, u berilmagan bo'lsa tizim kamerasini
    // chaqirish (ACTION_IMAGE_CAPTURE) SecurityException beradi — avval ruxsat so'raymiz.
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permissionDenied = !granted
        if (granted) launchCamera()
    }
    val gallery = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) {
            vm.analyze(uri)
            onAnalyze()
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        ScreenTitle("${ui.emoji} ${stringResource(ui.title)}", stringResource(ui.subtitle), onBack)
        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            PatientIdField(value = patientId, onChange = vm::setPatientId)
            if (type == AnalysisTypes.SKIN) {
                OutlinedTextField(
                    value = bodySite,
                    onValueChange = vm::setBodySite,
                    label = { Text(stringResource(R.string.analysis_body_site_label)) },
                    placeholder = { Text(stringResource(R.string.analysis_body_site_placeholder)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text(stringResource(R.string.analysis_tips_title), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    Text(stringResource(ui.tip), style = MaterialTheme.typography.bodyMedium)
                }
            }
            if (permissionDenied) WarningBanner(stringResource(R.string.analysis_camera_denied))
        }
        PrimaryButton(
            text = stringResource(R.string.analysis_take_photo),
            onClick = {
                val granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                    PackageManager.PERMISSION_GRANTED
                if (granted) launchCamera() else permission.launch(Manifest.permission.CAMERA)
            },
        )
        SecondaryButton(
            text = stringResource(R.string.analysis_pick_gallery),
            onClick = { gallery.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) },
        )
    }
}

// =====================================================================
//  3. Natija
// =====================================================================
private fun riskColor(risk: String): Color = when (risk) {
    "high" -> TrafficRed
    "medium" -> TrafficYellow
    "low" -> TrafficGreen
    else -> TrafficGrey
}

private fun riskIcon(risk: String): ImageVector = when (risk) {
    "high" -> Icons.Filled.ErrorOutline
    "medium" -> Icons.Filled.WarningAmber
    "low" -> Icons.Filled.CheckCircle
    else -> Icons.AutoMirrored.Filled.HelpOutline
}

@Composable
private fun riskLabel(risk: String): String = stringResource(
    when (risk) {
        "high" -> R.string.analysis_risk_high
        "medium" -> R.string.analysis_risk_medium
        "low" -> R.string.analysis_risk_low
        else -> R.string.analysis_risk_ungradable
    }
)

@Composable
fun AnalysisResultScreen(
    vm: AnalysisViewModel,
    onNewAnalysis: () -> Unit,
    onHome: () -> Unit,
) {
    val state by vm.uiState.collectAsState()
    val progress by vm.uploadProgress.collectAsState()
    val imageUri by vm.imageUri.collectAsState()

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        when (val s = state) {
            AnalysisUiState.Idle, AnalysisUiState.Loading ->
                LoadingState(progress = progress, onCancel = { vm.cancel(); onNewAnalysis() })
            is AnalysisUiState.Error ->
                ErrorState(message = s.message, onRetry = vm::retry, onNewPatient = onNewAnalysis)
            is AnalysisUiState.Success -> {
                AnalysisResultContent(s.result, imageUri)
                PrimaryButton(stringResource(R.string.analysis_new), onNewAnalysis)
                SecondaryButton(stringResource(R.string.analysis_home), onHome)
            }
        }
    }
}

@Composable
private fun AnalysisResultContent(result: AnalyzeResponse, imageUri: Uri?) {
    val color = riskColor(result.riskLevel)
    val label = riskLabel(result.riskLevel)
    val ungradable = result.riskLevel == "ungradable"
    val headline = if (ungradable) stringResource(R.string.analysis_ungradable_title) else result.topLabel
    val desc = stringResource(R.string.analysis_result_content_desc, label, headline)

    Text(
        stringResource(R.string.analysis_result_title, result.analysisLabel),
        style = MaterialTheme.typography.titleLarge,
        color = MaterialTheme.colorScheme.primary,
    )

    // Svetofor kartasi
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(18.dp))
            .background(color)
            .padding(Spacing.xl)
            .semantics { contentDescription = desc },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Icon(riskIcon(result.riskLevel), contentDescription = null, tint = Color.White, modifier = Modifier.size(48.dp))
        Text(label.uppercase(), color = Color.White, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
        Text(headline, color = Color.White, style = MaterialTheme.typography.headlineSmall, textAlign = TextAlign.Center)
        if (!ungradable) {
            Text("${(result.probability * 100).toInt()}%", color = Color.White, fontSize = 36.sp, fontWeight = FontWeight.ExtraBold)
        }
    }

    if (result.isDemo) WarningBanner(stringResource(R.string.analysis_demo_warning))

    // Tavsiya
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Text(stringResource(R.string.analysis_recommendation), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Text(result.recommendation, style = MaterialTheme.typography.bodyLarge)
        }
    }

    if (imageUri != null) {
        AsyncImage(
            model = imageUri,
            contentDescription = stringResource(R.string.analysis_image_desc),
            contentScale = ContentScale.Crop,
            modifier = Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(14.dp)),
        )
    }

    if (result.findings.isNotEmpty()) {
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                Text(stringResource(R.string.analysis_findings), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                result.findings.forEach { FindingRow(it) }
            }
        }
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(Spacing.lg), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            DetailRow(stringResource(R.string.analysis_detail_patient), result.patientId)
            if (result.bodySite.isNotBlank()) DetailRow(stringResource(R.string.analysis_body_site_label), result.bodySite)
            DetailRow(stringResource(R.string.analysis_detail_quality), result.quality)
            DetailRow(stringResource(R.string.analysis_detail_model), result.modelVersion)
        }
    }
    DisclaimerText(result.disclaimer)
}

@Composable
private fun FindingRow(f: AnalysisFinding) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(f.label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
            Text("${(f.probability * 100).toInt()}%", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        }
        LinearProgressIndicator(
            progress = { f.probability.toFloat().coerceIn(0f, 1f) },
            color = riskColor(f.risk),
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun DetailRow(key: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(key, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}
