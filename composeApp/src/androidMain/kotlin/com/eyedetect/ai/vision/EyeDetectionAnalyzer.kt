package com.eyedetect.ai.vision

import androidx.annotation.MainThread
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import com.eyedetect.ai.ui.components.QualityLevel
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.Face
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetector
import com.google.mlkit.vision.face.FaceDetectorOptions
import com.google.mlkit.vision.face.FaceLandmark
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/** Ko'z/yuz aniqlash natijasi — "joylashuv" sifat ko'rsatkichi shundan chiqariladi. */
data class EyePosition(
    val level: QualityLevel,
    val faceDetected: Boolean,
    /** Tanlangan ko'z (yoki yuz) markazining kadr markazidan normallashtirilgan
     * masofasi: 0 = to'liq markazda, ~1.4 = burchakda. */
    val offset: Float,
)

/**
 * CameraX `ImageAnalysis` uchun kombinatsiyalangan analizator:
 * 1) [FrameQualityAnalyzer.compute] orqali fokus/yorug'lik (piksel darajasida, sinxron),
 * 2) ML Kit `FaceDetector` orqali ko'z/yuz aniqlash va uning kadr markaziga nisbatan
 *    joylashuvi (asinxron, PLAN.md'dagi "joylashuv" bandi uchun poydevor).
 *
 * Ikkalasi bitta [ImageProxy]dan foydalanadi, shuning uchun bitta `ImageAnalysis`
 * use case'ga ulanadi — CameraX bir vaqtda faqat bitta `ImageAnalysis` oqimini
 * ishonchli qo'llab-quvvatlagani uchun bu muhim.
 *
 * ESLATMA: `vm.eye` ("left"/"right") ML Kit'ning `LEFT_EYE`/`RIGHT_EYE` landmarklariga
 * to'g'ridan-to'g'ri moslashtiriladi — bular suratga tushayotgan odamning o'zidagi
 * chap/o'ng ko'zi (ko'zguga aks etgan emas). Agar orqa kamera bilan boshqa odam
 * suratga olinsa, bu odatda to'g'ri; old kamera bilan o'z-o'zini suratga olishda
 * ekrandagi ko'rinish oynadek teskari bo'lishi mumkin — aniq kalibrlash keyingi bosqich.
 */
class EyeDetectionAnalyzer(
    private val eye: String,
    private val qualityIntervalMs: Long = 200L,
    private val faceIntervalMs: Long = 350L,
    private val onQuality: (FrameQuality) -> Unit,
    private val onEyePosition: (EyePosition) -> Unit,
) : ImageAnalysis.Analyzer {

    private val detector: FaceDetector = FaceDetection.getClient(
        FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setLandmarkMode(FaceDetectorOptions.LANDMARK_MODE_ALL)
            .build()
    )

    private var lastQualityRunAt = 0L
    private var lastFaceRunAt = 0L
    private val faceDetectionBusy = AtomicBoolean(false)

    override fun analyze(image: ImageProxy) {
        val now = System.currentTimeMillis()

        if (now - lastQualityRunAt >= qualityIntervalMs) {
            lastQualityRunAt = now
            FrameQualityAnalyzer.compute(image)?.let(onQuality)
        }

        val shouldRunFaceDetection = now - lastFaceRunAt >= faceIntervalMs && faceDetectionBusy.compareAndSet(false, true)
        if (!shouldRunFaceDetection) {
            image.close()
            return
        }
        lastFaceRunAt = now

        val mediaImage = image.image
        if (mediaImage == null) {
            faceDetectionBusy.set(false)
            image.close()
            return
        }

        val rotation = image.imageInfo.rotationDegrees
        val input = InputImage.fromMediaImage(mediaImage, rotation)
        val effWidth = if (rotation == 90 || rotation == 270) image.height else image.width
        val effHeight = if (rotation == 90 || rotation == 270) image.width else image.height

        detector.process(input)
            .addOnSuccessListener { faces -> onEyePosition(classify(faces, effWidth, effHeight)) }
            .addOnCompleteListener {
                faceDetectionBusy.set(false)
                image.close()
            }
    }

    private fun classify(faces: List<Face>, width: Int, height: Int): EyePosition {
        if (faces.isEmpty()) return EyePosition(QualityLevel.WARN, faceDetected = false, offset = Float.NaN)

        // Eng katta (kadrga eng yaqin) yuzni tanlaymiz.
        val face = faces.maxBy { it.boundingBox.width().toLong() * it.boundingBox.height().toLong() }

        val landmarkType = if (eye == "left") FaceLandmark.LEFT_EYE else FaceLandmark.RIGHT_EYE
        val point = face.getLandmark(landmarkType)?.position
        val centerX = point?.x ?: face.boundingBox.exactCenterX()
        val centerY = point?.y ?: face.boundingBox.exactCenterY()

        val offsetX = (centerX - width / 2f) / (width / 2f)
        val offsetY = (centerY - height / 2f) / (height / 2f)
        val offset = sqrt(offsetX * offsetX + offsetY * offsetY)

        val level = when {
            offset < 0.28f -> QualityLevel.GOOD
            offset < 0.55f -> QualityLevel.WARN
            else -> QualityLevel.BAD
        }
        return EyePosition(level, faceDetected = true, offset = offset)
    }

    @MainThread
    fun close() {
        detector.close()
    }
}
