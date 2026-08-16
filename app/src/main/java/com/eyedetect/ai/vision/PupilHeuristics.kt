package com.eyedetect.ai.vision

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Rect
import com.eyedetect.ai.ui.components.QualityLevel
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.google.mlkit.vision.face.FaceLandmark
import java.util.concurrent.TimeUnit

/**
 * Olingan surat ustida ishlaydigan KLASSIK CV EVRISTIKASI — trenirovka qilingan
 * ML modeli EMAS. Backendning haqiqiy klinik natijasini (ICDR/Grad-CAM) almashtirmaydi,
 * faqat qo'shimcha, mahalliy, tezkor skrining ko'rsatkichi beradi.
 *
 * G'oya: normal qorachiq (pupil) deyarli qop-qora bo'ladi.
 * - Xiralik (opacity/leukocoria): eng qorong'i piksellar ham och/oq bo'lsa — bu
 *   kataraktaga xos "oq qorachiq" belgisi bo'lishi mumkin.
 * - Qizil refleks: flash yorug'ligi sog'lom to'r pardadan qizg'ish aks etadi (normal).
 *   Aks holda kulrang/oq ko'rinish xuddi shu leukocoria belgisi bilan bog'liq bo'lishi mumkin.
 *
 * Chegaralar (pastda) taxminiy — haqiqiy qurilma/flash sharoitida sinovdan so'ng
 * sozlash tavsiya etiladi ([FrameQualityAnalyzer]dagi kabi).
 */
data class PupilHeuristicResult(
    val regionFound: Boolean,
    val usedFaceLandmark: Boolean,
    val darkMeanHueDeg: Float,
    val darkMeanSaturation: Float,
    val darkMeanValue: Float,
    val opacity: QualityLevel,
    val redReflex: QualityLevel,
)

object PupilHeuristics {

    private const val DARK_PERCENTILE = 0.12 // eng qorong'i ~12% piksel = qorachiqqa yaqin taxmin

    /** [bitmap]ning [eye] ("left"/"right") mos hududini tahlil qiladi. Sekin (MediaPipe/ML Kit
     * ACCURATE rejimi) — chaqiruvchi fon ipida (Dispatchers.IO/Default) ishga tushirishi shart. */
    fun analyze(context: Context, bitmap: Bitmap, eye: String): PupilHeuristicResult {
        val region = findEyeRegion(context, bitmap, eye)
        if (com.eyedetect.ai.BuildConfig.DEBUG) {
            runCatching { saveDebugCrop(context, bitmap, region.rect, eye) }
        }
        val samples = sampleHsv(bitmap, region.rect)
        if (samples.size < 12) {
            return PupilHeuristicResult(
                regionFound = false,
                usedFaceLandmark = region.usedLandmark,
                darkMeanHueDeg = 0f,
                darkMeanSaturation = 0f,
                darkMeanValue = 0f,
                opacity = QualityLevel.WARN,
                redReflex = QualityLevel.WARN,
            )
        }

        val darkCount = (samples.size * DARK_PERCENTILE).toInt().coerceIn(12, samples.size)
        val darkest = samples.sortedBy { it.third }.take(darkCount) // value (yorqinlik) bo'yicha eng qorong'ilari

        val meanHue = darkest.map { it.first }.average().toFloat()
        val meanSat = darkest.map { it.second }.average().toFloat()
        val meanVal = darkest.map { it.third }.average().toFloat()

        return PupilHeuristicResult(
            regionFound = true,
            usedFaceLandmark = region.usedLandmark,
            darkMeanHueDeg = meanHue,
            darkMeanSaturation = meanSat,
            darkMeanValue = meanVal,
            opacity = classifyOpacity(meanVal, meanSat),
            redReflex = classifyRedReflex(meanHue, meanSat, meanVal),
        )
    }

    private fun classifyOpacity(value: Float, saturation: Float): QualityLevel {
        // "Oqlik" ko'rsatkichi: yorqin + to'yinmagan (kulrang/oq) = normal qora qorachiqdan chetlanish.
        val whiteness = value * (1f - saturation)
        return when {
            whiteness < 0.18f -> QualityLevel.GOOD
            whiteness < 0.35f -> QualityLevel.WARN
            else -> QualityLevel.BAD
        }
    }

    private fun classifyRedReflex(hueDeg: Float, saturation: Float, value: Float): QualityLevel {
        val isReddish = hueDeg <= 25f || hueDeg >= 335f
        return when {
            // Juda qorong'i — flash aks etmagan, refleksni baholab bo'lmaydi (flash yoqilganini tekshiring).
            value < 0.12f -> QualityLevel.WARN
            isReddish && saturation > 0.25f -> QualityLevel.GOOD
            saturation < 0.15f && value > 0.35f -> QualityLevel.BAD
            else -> QualityLevel.WARN
        }
    }

    private data class EyeRegion(val rect: Rect, val usedLandmark: Boolean)

    private fun findEyeRegion(context: Context, bitmap: Bitmap, eye: String): EyeRegion {
        // 1) Afzal: MediaPipe haqiqiy iris landmarklari (aniq markaz+radius, ML Kit'ning
        // taxminiy fixed-radius'idan farqli o'laroq ko'z ochiqligi/burchagiga moslashadi).
        val fromIris = runCatching { IrisLandmarker.detectIris(context, bitmap, eye) }.getOrNull()
        if (fromIris != null) {
            return EyeRegion(squareRect(bitmap, fromIris.first, fromIris.second, fromIris.third), usedLandmark = true)
        }
        // 2) Zaxira: MediaPipe muvaffaqiyatsiz (model yuklanmadi, yuz topilmadi) — ML Kit.
        val fromFace = runCatching { detectEyeCenterViaFace(bitmap, eye) }.getOrNull()
        if (fromFace != null) {
            return EyeRegion(squareRect(bitmap, fromFace.first, fromFace.second, fromFace.third), usedLandmark = true)
        }
        // 3) Oxirgi zaxira: yuz ham aniqlanmadi (masalan, juda yaqin makro surat — faqat ko'z
        // kadrni to'ldirgan) — kadr markazini ishlatamiz (FrameQualityAnalyzer'dagi markaziy
        // ROI mantig'iga o'xshash).
        val minDim = minOf(bitmap.width, bitmap.height)
        return EyeRegion(
            squareRect(bitmap, bitmap.width / 2f, bitmap.height / 2f, minDim * 0.18f),
            usedLandmark = false,
        )
    }

    /** @return (markazX, markazY, radius) yoki yuz/ko'z topilmasa `null`. */
    private fun detectEyeCenterViaFace(bitmap: Bitmap, eye: String): Triple<Float, Float, Float>? {
        val detector = FaceDetection.getClient(
            FaceDetectorOptions.Builder()
                .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_ACCURATE)
                .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
                .build()
        )
        try {
            val input = InputImage.fromBitmap(bitmap, 0)
            val faces = Tasks.await(detector.process(input), 3, TimeUnit.SECONDS)
            val face = faces.maxByOrNull { it.boundingBox.width().toLong() * it.boundingBox.height().toLong() }
                ?: return null

            val landmarkType = if (eye == "left") FaceLandmark.LEFT_EYE else FaceLandmark.RIGHT_EYE
            val point = face.getLandmark(landmarkType)?.position
            val cx = point?.x ?: face.boundingBox.exactCenterX()
            val cy = point?.y ?: face.boundingBox.exactCenterY()
            val radius = (face.boundingBox.width() * 0.09f).coerceAtLeast(8f)
            return Triple(cx, cy, radius)
        } finally {
            detector.close()
        }
    }

    // VAQTINCHALIQ: chap/o'ng xaritalanishini real qurilmada tasdiqlash uchun — tekshiruv
    // tugagach olib tashlanadi. Faqat DEBUG buildda ishlaydi.
    private fun saveDebugCrop(context: Context, bitmap: Bitmap, rect: Rect, eye: String) {
        val crop = Bitmap.createBitmap(bitmap, rect.left, rect.top, rect.width(), rect.height())
        val dir = context.getExternalFilesDir(null) ?: return
        val out = java.io.File(dir, "debug_eye_crop_$eye.jpg")
        java.io.FileOutputStream(out).use { crop.compress(Bitmap.CompressFormat.JPEG, 95, it) }
    }

    private fun squareRect(bitmap: Bitmap, cx: Float, cy: Float, radius: Float): Rect {
        val left = (cx - radius).toInt().coerceIn(0, bitmap.width - 1)
        val top = (cy - radius).toInt().coerceIn(0, bitmap.height - 1)
        val right = (cx + radius).toInt().coerceIn(left + 1, bitmap.width)
        val bottom = (cy + radius).toInt().coerceIn(top + 1, bitmap.height)
        return Rect(left, top, right, bottom)
    }

    /** @return (hue 0-360, saturation 0-1, value 0-1) ro'yxati, ROI ichida siyrak namunalangan. */
    private fun sampleHsv(bitmap: Bitmap, rect: Rect): List<Triple<Float, Float, Float>> {
        val w = rect.width()
        val h = rect.height()
        if (w <= 0 || h <= 0) return emptyList()
        val stride = (maxOf(w, h) / 50).coerceAtLeast(1)
        val hsv = FloatArray(3)
        val out = ArrayList<Triple<Float, Float, Float>>()
        var y = rect.top
        while (y < rect.bottom) {
            var x = rect.left
            while (x < rect.right) {
                Color.colorToHSV(bitmap.getPixel(x, y), hsv)
                out.add(Triple(hsv[0], hsv[1], hsv[2]))
                x += stride
            }
            y += stride
        }
        return out
    }
}
