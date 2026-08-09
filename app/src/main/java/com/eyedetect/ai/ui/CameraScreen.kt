package com.eyedetect.ai.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.OpenableColumns
import android.provider.Settings
import android.util.Size
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FlashAuto
import androidx.compose.material.icons.filled.FlashOff
import androidx.compose.material.icons.filled.FlashOn
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import coil.compose.AsyncImage
import com.eyedetect.ai.R
import com.eyedetect.ai.ScreeningViewModel
import com.eyedetect.ai.ui.components.InfoBanner
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.QualityLevel
import com.eyedetect.ai.ui.components.QualityPanel
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.ShutterButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficGreen
import com.eyedetect.ai.vision.EyeDetectionAnalyzer
import java.io.File
import java.util.concurrent.Executors

/**
 * 2-ekran (6-hujjat, 6.B): CameraX preview + jonli sifat yo'l-yo'riqchisi,
 * doiraviy markazlash overlay, tezkor ko'rib chiqish, va galereya zaxira rejimi.
 *
 * Fokus va yorug'lik piksel darajasida (Laplasian variansi + histogram o'rtacha
 * yorqinligi, 3-hujjat 2.3), "joylashuv" esa ML Kit `FaceDetector` orqali —
 * tanlangan ko'z (`vm.eye`) landmarki kadr markaziga qanchalik yaqinligidan —
 * real-vaqtda hisoblanadi ([EyeDetectionAnalyzer], PLAN.md 2-band).
 */
@Composable
fun CameraScreen(
    vm: ScreeningViewModel,
    onResult: () -> Unit,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val executor = remember { Executors.newSingleThreadExecutor() }

    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
                == PackageManager.PERMISSION_GRANTED
        )
    }
    // Flash: qizil refleks testi uchun muhim (5-hujjat) — sog'lom to'r pardadan qizg'ish
    // aks yaqindan turib flash bilan yoritilganda ancha ishonchli ko'rinadi. Standart
    // holat YOQILGAN qilib belgilangan, foydalanuvchi pastdagi tugma bilan almashtira oladi.
    var flashMode by remember { mutableIntStateOf(ImageCapture.FLASH_MODE_ON) }
    val imageCapture = remember { ImageCapture.Builder().setFlashMode(flashMode).build() }
    LaunchedEffect(flashMode) { imageCapture.flashMode = flashMode }

    // Real-vaqt sifat tahlili: fokus, yorug'lik (piksel darajasida) + joylashuv (ML Kit)
    var focusQuality by remember { mutableStateOf(QualityLevel.WARN) }
    var lightQuality by remember { mutableStateOf(QualityLevel.WARN) }
    var positionQuality by remember { mutableStateOf(QualityLevel.WARN) }
    val imageAnalysis = remember {
        ImageAnalysis.Builder()
            .setResolutionSelector(
                ResolutionSelector.Builder()
                    .setResolutionStrategy(
                        ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
                    )
                    .build()
            )
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
    }
    val eyeDetectionAnalyzer = remember(vm.eye) {
        EyeDetectionAnalyzer(
            eye = vm.eye,
            onQuality = { result ->
                ContextCompat.getMainExecutor(context).execute {
                    focusQuality = result.focus
                    lightQuality = result.light
                }
            },
            onEyePosition = { result ->
                ContextCompat.getMainExecutor(context).execute {
                    positionQuality = result.level
                }
            },
        )
    }
    DisposableEffect(eyeDetectionAnalyzer) {
        imageAnalysis.setAnalyzer(executor, eyeDetectionAnalyzer)
        onDispose { eyeDetectionAnalyzer.close() }
    }

    // Olingan, ammo hali yuborilmagan rasm (tezkor ko'rib chiqish uchun)
    var pendingFile by remember { mutableStateOf<File?>(null) }

    // Suratga olingan payt sifat past bo'lsa, ko'rib chiqish varag'ida ogohlantirish ko'rsatiladi
    var captureQualityWarning by remember { mutableStateOf(false) }

    // Galereyadan tanlangan, ammo hali tasdiqlanmagan rasmlar (grid ko'rib chiqish uchun)
    var pendingGalleryUris by remember { mutableStateOf<List<Uri>>(emptyList()) }

    // Suratga olishning o'zi (fayl yozish) muvaffaqiyatsiz bo'lsa — natija ekraniga
    // o'tmasdan, shu yerda ogohlantirib, qayta urinishga taklif qilinadi.
    var captureError by remember { mutableStateOf(false) }

    val eyeLabel = if (vm.eye == "left") stringResource(R.string.common_eye_left) else stringResource(R.string.common_eye_right)

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> hasCameraPermission = granted }

    LaunchedEffect(Unit) {
        if (!hasCameraPermission) permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    // Galereyadan bir nechta rasm tanlash (zaxira rejim — reja 3.3, 6-hujjat 6.E)
    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.PickMultipleVisualMedia(maxItems = 4)
    ) { uris ->
        if (uris.isNotEmpty()) {
            // Ikkita ko'rib chiqish varag'i bir vaqtda ustma-ust chiqmasligi uchun
            // qarama-qarshi holatni tozalaymiz (6-hujjat, 6.B/6.E o'zaro eksklyuziv).
            pendingFile = null
            pendingGalleryUris = uris
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // ---- Jonli preview + overlaylar ----
        Box(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .background(Color.Black),
        ) {
            if (hasCameraPermission) {
                AndroidView(
                    modifier = Modifier.fillMaxSize(),
                    factory = { ctx ->
                        val previewView = PreviewView(ctx)
                        val providerFuture = ProcessCameraProvider.getInstance(ctx)
                        providerFuture.addListener({
                            val provider = providerFuture.get()
                            val preview = Preview.Builder().build().also {
                                it.setSurfaceProvider(previewView.surfaceProvider)
                            }
                            val selector = CameraSelector.DEFAULT_BACK_CAMERA
                            try {
                                provider.unbindAll()
                                provider.bindToLifecycle(lifecycleOwner, selector, preview, imageCapture, imageAnalysis)
                            } catch (_: Exception) { /* demo: e'tiborsiz */ }
                        }, ContextCompat.getMainExecutor(ctx))
                        previewView
                    },
                )
            } else {
                Column(
                    modifier = Modifier.fillMaxSize().padding(Spacing.xl),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md, Alignment.CenterVertically),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        stringResource(R.string.camera_no_permission),
                        color = Color.White,
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    SecondaryButton(
                        stringResource(R.string.camera_request_permission),
                        onClick = { permissionLauncher.launch(Manifest.permission.CAMERA) },
                    )
                    SecondaryButton(
                        stringResource(R.string.camera_open_settings),
                        onClick = {
                            context.startActivity(
                                Intent(
                                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                    Uri.fromParts("package", context.packageName, null),
                                )
                            )
                        },
                    )
                }
            }

            // Ko'z tegi + flash boshqaruvi (yuqori chap)
            Column(
                modifier = Modifier.align(Alignment.TopStart).padding(Spacing.md),
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color.Black.copy(alpha = 0.55f))
                        .padding(horizontal = Spacing.md, vertical = 6.dp),
                ) {
                    Text(stringResource(R.string.camera_eye_tag, eyeLabel), color = Color.White, style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold)
                }
                FlashModeChip(
                    flashMode = flashMode,
                    onToggle = {
                        flashMode = when (flashMode) {
                            ImageCapture.FLASH_MODE_ON -> ImageCapture.FLASH_MODE_AUTO
                            ImageCapture.FLASH_MODE_AUTO -> ImageCapture.FLASH_MODE_OFF
                            else -> ImageCapture.FLASH_MODE_ON
                        }
                    },
                )
            }

            // Sifat paneli (yuqori o'ng) — uchalasi ham real-vaqtda hisoblanadi
            QualityPanel(
                focus = focusQuality,
                light = lightQuality,
                position = positionQuality,
                modifier = Modifier.align(Alignment.TopEnd).padding(Spacing.md),
            )

            // Doiraviy markazlash overlay (fundus doirasi)
            Box(
                modifier = Modifier
                    .align(Alignment.Center)
                    .size(230.dp)
                    .clip(CircleShape)
                    .border(3.dp, TrafficGreen, CircleShape),
            )

            // Yo'riqnoma (pastda)
            Text(
                stringResource(R.string.camera_center_guide),
                color = Color.White,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
                style = MaterialTheme.typography.bodyLarge,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(Spacing.lg),
            )
        }

        // ---- Boshqaruvlar ----
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            if (captureError) {
                WarningBanner(stringResource(R.string.camera_capture_error))
            }
            ShutterButton(
                enabled = hasCameraPermission,
                onClick = {
                    captureError = false
                    val photoFile = File(context.cacheDir, "fundus_${System.currentTimeMillis()}.jpg")
                    val output = ImageCapture.OutputFileOptions.Builder(photoFile).build()
                    imageCapture.takePicture(
                        output, executor,
                        object : ImageCapture.OnImageSavedCallback {
                            override fun onImageSaved(results: ImageCapture.OutputFileResults) {
                                ContextCompat.getMainExecutor(context).execute {
                                    pendingGalleryUris = emptyList()
                                    captureQualityWarning = focusQuality == QualityLevel.BAD ||
                                        lightQuality == QualityLevel.BAD || positionQuality == QualityLevel.BAD
                                    pendingFile = photoFile
                                }
                            }
                            override fun onError(exc: ImageCaptureException) {
                                // Suratga olish muvaffaqiyatsiz bo'lsa, natija ekraniga
                                // o'tmaymiz (fayl to'liq/yaroqli emas) — shu yerda
                                // ogohlantirib, foydalanuvchi qayta bosishini kutamiz.
                                ContextCompat.getMainExecutor(context).execute {
                                    photoFile.delete()
                                    captureError = true
                                }
                            }
                        },
                    )
                },
            )
            SecondaryButton(
                stringResource(R.string.camera_pick_gallery),
                onClick = {
                    galleryLauncher.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
            )
            TextActionButton(stringResource(R.string.common_back), onClick = onBack)
        }
    }

    // ---- Tezkor ko'rib chiqish (6-hujjat, 6.B) ----
    val fileToReview = pendingFile
    if (fileToReview != null) {
        CaptureReviewSheet(
            qualityWarning = captureQualityWarning,
            onRetake = { fileToReview.delete(); pendingFile = null },
            onConfirm = {
                pendingFile = null
                vm.uploadFile(fileToReview)
                onResult()
            },
        )
    }

    // ---- Galereya grid ko'rib chiqish (6-hujjat, 6.E) ----
    if (pendingGalleryUris.isNotEmpty()) {
        GalleryPickSheet(
            uris = pendingGalleryUris,
            onCancel = { pendingGalleryUris = emptyList() },
            onConfirm = { uri ->
                pendingGalleryUris = emptyList()
                vm.uploadUri(context, uri)
                onResult()
            },
        )
    }
}

/** Flash rejimini bosib almashtiradigan chip (YOQILGAN → AVTO → O'CHIQ → ...). */
@Composable
private fun FlashModeChip(flashMode: Int, onToggle: () -> Unit) {
    val (icon, label) = when (flashMode) {
        ImageCapture.FLASH_MODE_ON -> Icons.Filled.FlashOn to stringResource(R.string.camera_flash_on)
        ImageCapture.FLASH_MODE_AUTO -> Icons.Filled.FlashAuto to stringResource(R.string.camera_flash_auto)
        else -> Icons.Filled.FlashOff to stringResource(R.string.camera_flash_off)
    }
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(Color.Black.copy(alpha = 0.55f))
            .clickable(onClick = onToggle)
            .padding(horizontal = Spacing.md, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(16.dp))
        Text(label, color = Color.White, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
    }
}

/**
 * Galereyadan tanlangan bir nechta rasmni katakchali (grid) ko'rinishda ko'rsatib,
 * foydalanuvchi ulardan bittasini tanlab tahlilga yuborishiga imkon beradi (6-hujjat, 6.E).
 */
@Composable
private fun GalleryPickSheet(uris: List<Uri>, onCancel: () -> Unit, onConfirm: (Uri) -> Unit) {
    val context = LocalContext.current
    var selected by remember(uris) { mutableStateOf(uris.first()) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.55f)),
        contentAlignment = Alignment.BottomCenter,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.lg)
                .clip(RoundedCornerShape(20.dp))
                .background(MaterialTheme.colorScheme.surface)
                .padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Text(stringResource(R.string.gallery_pick_title), style = MaterialTheme.typography.titleLarge)
            InfoBanner(stringResource(R.string.gallery_pick_info, uris.size))

            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                verticalArrangement = Arrangement.spacedBy(Spacing.md),
                modifier = Modifier.heightIn(max = 320.dp),
            ) {
                items(uris) { uri ->
                    val isSelected = uri == selected
                    Box(
                        modifier = Modifier
                            .aspectRatio(1f)
                            .clip(RoundedCornerShape(14.dp))
                            .border(
                                width = if (isSelected) 3.dp else 1.dp,
                                color = if (isSelected) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.outlineVariant,
                                shape = RoundedCornerShape(14.dp),
                            )
                            .selectable(selected = isSelected, onClick = { selected = uri }),
                    ) {
                        AsyncImage(
                            model = uri,
                            contentDescription = stringResource(R.string.gallery_image_content_desc),
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Crop,
                        )
                        if (isSelected) {
                            Box(
                                modifier = Modifier
                                    .align(Alignment.TopEnd)
                                    .padding(6.dp)
                                    .size(22.dp)
                                    .clip(CircleShape)
                                    .background(MaterialTheme.colorScheme.primary),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text("✓", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }

            Text(
                fileLabel(context, selected),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                SecondaryButton(stringResource(R.string.common_cancel), onClick = onCancel, modifier = Modifier.weight(1f))
                PrimaryButton(
                    stringResource(R.string.gallery_pick_confirm),
                    onClick = { onConfirm(selected) },
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

/** Rasmning nomi va hajmini ContentResolver orqali o'qiydi ("nomi.jpg · 1.2 MB"). */
private fun fileLabel(context: android.content.Context, uri: Uri): String {
    var name = "rasm.jpg"
    var size = -1L
    context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        val nameIdx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        val sizeIdx = cursor.getColumnIndex(OpenableColumns.SIZE)
        if (cursor.moveToFirst()) {
            if (nameIdx >= 0) name = cursor.getString(nameIdx) ?: name
            if (sizeIdx >= 0) size = cursor.getLong(sizeIdx)
        }
    }
    val sizeLabel = if (size > 0) " · %.1f MB".format(size / 1024f / 1024f) else ""
    return "$name$sizeLabel"
}

/** Rasm olingach chiqadigan "Rasm yaxshimi?" tasdiq oynasi. */
@Composable
private fun CaptureReviewSheet(qualityWarning: Boolean, onRetake: () -> Unit, onConfirm: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.55f)),
        contentAlignment = Alignment.BottomCenter,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.lg)
                .clip(RoundedCornerShape(20.dp))
                .background(MaterialTheme.colorScheme.surface)
                .padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(stringResource(R.string.capture_review_title), style = MaterialTheme.typography.titleLarge)
            Text(
                stringResource(R.string.capture_review_body),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
            if (qualityWarning) {
                WarningBanner(stringResource(R.string.capture_review_quality_warning))
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                SecondaryButton(stringResource(R.string.common_retake), onClick = onRetake, modifier = Modifier.weight(1f))
                PrimaryButton(stringResource(R.string.capture_review_confirm), onClick = onConfirm, modifier = Modifier.weight(1f))
            }
        }
    }
}
