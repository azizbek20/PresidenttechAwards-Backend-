package com.eyedetect.ai.vision

import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.eyedetect.ai.ui.components.QualityLevel
import kotlin.math.sqrt

/** Fokus va yorug'lik uchun hisoblangan xom qiymatlar + ulardan chiqarilgan svetofor darajasi. */
data class FrameQuality(
    val sharpness: Double,
    val brightness: Double,
    val focus: QualityLevel,
    val light: QualityLevel,
)

/**
 * CameraX `ImageAnalysis` uchun analizator: har freymda YUV Y-tekisligidan (luminance)
 * markaziy hududni tanlab, fokusni Laplacian variansi orqali, yorug'likni esa
 * o'rtacha yorqinlik (histogram) orqali baholaydi (3-hujjat 2.3, PLAN.md 2-band).
 *
 * Ishlash tezligi uchun: (a) har freym emas, [minIntervalMs] oralig'ida bir marta
 * hisoblanadi, (b) faqat markaziy ROI (doiraviy overlayga mos) siyrak qadam (stride)
 * bilan namunalanadi — to'liq piksel-piksel emas.
 */
class FrameQualityAnalyzer(
    private val minIntervalMs: Long = 200L,
    private val onResult: (FrameQuality) -> Unit,
) : ImageAnalysis.Analyzer {

    private var lastRunAt = 0L

    override fun analyze(image: ImageProxy) {
        val now = System.currentTimeMillis()
        if (now - lastRunAt < minIntervalMs) {
            image.close()
            return
        }
        lastRunAt = now
        try {
            compute(image)?.let(onResult)
        } finally {
            image.close()
        }
    }

    companion object {

        /**
         * Y-tekislikning markaziy ROI'sidan fokus (Laplasian variansi) va yorug'lik
         * (o'rtacha yorqinlik) hisoblaydi. `image`ni YOPMAYDI — chaqiruvchi javobgar
         * (bir nechta analizator bitta freymni ketma-ket ishlatishi mumkinligi uchun,
         * masalan [EyeDetectionAnalyzer]).
         */
        fun compute(image: ImageProxy): FrameQuality? {
            val yPlane = image.planes[0]
            val buffer = yPlane.buffer
            val rowStride = yPlane.rowStride
            val pixelStride = yPlane.pixelStride
            val width = image.width
            val height = image.height

            // Doiraviy markazlash overlayga mos markaziy kvadrat (kadrning ~55%)
            val roiSize = (minOf(width, height) * 0.55f).toInt().coerceAtLeast(2)
            val roiLeft = (width - roiSize) / 2
            val roiTop = (height - roiSize) / 2
            val stride = (roiSize / 96).coerceAtLeast(2) // ~96x96 namuna nuqtasi

            var brightnessSum = 0L
            var sampleCount = 0
            var laplacianSqSum = 0.0
            var laplacianCount = 0

            fun yAt(x: Int, y: Int): Int {
                val index = y * rowStride + x * pixelStride
                return buffer.get(index).toInt() and 0xFF
            }

            var y = roiTop + stride
            while (y < roiTop + roiSize - stride) {
                var x = roiLeft + stride
                while (x < roiLeft + roiSize - stride) {
                    val center = yAt(x, y)
                    brightnessSum += center
                    sampleCount++

                    val laplacian = 4 * center - yAt(x - stride, y) - yAt(x + stride, y) -
                        yAt(x, y - stride) - yAt(x, y + stride)
                    laplacianSqSum += (laplacian.toDouble() * laplacian.toDouble())
                    laplacianCount++

                    x += stride
                }
                y += stride
            }

            if (sampleCount == 0 || laplacianCount == 0) return null

            val brightness = brightnessSum.toDouble() / sampleCount
            // Laplacian variansining taxminiy o'lchovi (o'rtacha ~0 deb faraz qilinadi,
            // shu sababli E[L^2] variansga yaqinlashadi) — mutlaq qiymat emas, nisbiy o'tkirlik ko'rsatkichi.
            val sharpness = sqrt(laplacianSqSum / laplacianCount)

            return FrameQuality(
                sharpness = sharpness,
                brightness = brightness,
                focus = classifyFocus(sharpness),
                light = classifyBrightness(brightness),
            )
        }
        // Bu chegaralar 640x480 atrofidagi tahlil o'lchami uchun taxminiy kalibrlangan;
        // haqiqiy qurilmalarda sinovdan so'ng sozlash tavsiya etiladi.
        private const val SHARPNESS_GOOD = 12.0
        private const val SHARPNESS_WARN = 6.0

        private const val BRIGHTNESS_LOW_BAD = 35.0
        private const val BRIGHTNESS_LOW_WARN = 65.0
        private const val BRIGHTNESS_HIGH_WARN = 195.0
        private const val BRIGHTNESS_HIGH_BAD = 225.0

        fun classifyFocus(sharpness: Double): QualityLevel = when {
            sharpness >= SHARPNESS_GOOD -> QualityLevel.GOOD
            sharpness >= SHARPNESS_WARN -> QualityLevel.WARN
            else -> QualityLevel.BAD
        }

        fun classifyBrightness(brightness: Double): QualityLevel = when {
            brightness < BRIGHTNESS_LOW_BAD || brightness > BRIGHTNESS_HIGH_BAD -> QualityLevel.BAD
            brightness < BRIGHTNESS_LOW_WARN || brightness > BRIGHTNESS_HIGH_WARN -> QualityLevel.WARN
            else -> QualityLevel.GOOD
        }
    }
}
