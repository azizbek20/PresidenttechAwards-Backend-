package com.eyedetect.ai.vision

import android.content.Context
import android.graphics.Bitmap
import com.google.mediapipe.framework.image.BitmapImageBuilder
import com.google.mediapipe.tasks.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarker
import com.google.mediapipe.tasks.vision.facelandmarker.FaceLandmarkerResult
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import kotlin.math.sqrt

/**
 * MediaPipe Face Landmarker orqali haqiqiy iris (qorachiq atrofi) markazi va radiusini
 * topadi — [PupilHeuristics]dagi ML Kit'ning bitta ko'z-landmark nuqtasi + taxminiy
 * (yuz kengligining 9%i) radius o'rniga. Model 478 nuqtali yuz to'ri qaytaradi, shu
 * jumladan iris halqalari (Tasks API'da qo'shimcha bayroqsiz doim yoqilgan): o'ng ko'z
 * markazi=468 (halqa 469-472), chap ko'z markazi=473 (halqa 474-477).
 *
 * ESLATMA: MediaPipe'da "left"/"right" — [EyeDetectionAnalyzer]dagi ML Kit
 * LEFT_EYE/RIGHT_EYE'ga o'xshab — suratga tushayotgan odamning O'ZIDAGI chap/o'ng
 * ko'zi (anatomik), ekrandagi ko'rinish emas.
 *
 * Yuz/iris topilmasa yoki model yuklanmasa `null` qaytaradi — [PupilHeuristics] bunday
 * holda ML Kit zaxira yo'liga o'tadi.
 */
object IrisLandmarker {

    private const val MODEL_ASSET = "face_landmarker.task"

    private const val RIGHT_IRIS_CENTER = 468
    private val RIGHT_IRIS_RING = intArrayOf(469, 470, 471, 472)
    private const val LEFT_IRIS_CENTER = 473
    private val LEFT_IRIS_RING = intArrayOf(474, 475, 476, 477)

    private const val DETECT_TIMEOUT_SECONDS = 3L

    @Volatile
    private var landmarker: FaceLandmarker? = null

    // detect() past kutilmagan holatlarda (masalan, xotira bosimi ostida) uzoq bloklanib
    // qolishi mumkin — chegaralangan kutish uchun alohida ip. `@Volatile var` (val emas):
    // timeout'da bu ip qayta yaratiladi, quyidagi izohga qarang.
    @Volatile
    private var detectExecutor: ExecutorService = newDetectExecutor()

    private fun newDetectExecutor(): ExecutorService =
        Executors.newSingleThreadExecutor { r -> Thread(r, "IrisLandmarkerDetect") }

    private fun getOrCreate(context: Context): FaceLandmarker =
        landmarker ?: synchronized(this) {
            landmarker ?: buildLandmarker(context).also { landmarker = it }
        }

    private fun buildLandmarker(context: Context): FaceLandmarker {
        val baseOptions = BaseOptions.builder()
            .setModelAssetPath(MODEL_ASSET)
            .build()
        val options = FaceLandmarker.FaceLandmarkerOptions.builder()
            .setBaseOptions(baseOptions)
            .setRunningMode(RunningMode.IMAGE)
            .setNumFaces(1)
            .setOutputFaceBlendshapes(false)
            .setOutputFacialTransformationMatrixes(false)
            .build()
        return FaceLandmarker.createFromOptions(context.applicationContext, options)
    }

    /**
     * @return (markazX, markazY, radius) bitmap piksel koordinatalarida, yoki yuz/iris
     * topilmasa, model muvaffaqiyatsiz yuklansa, yoki `detect()` [DETECT_TIMEOUT_SECONDS]
     * ichida qaytmasa `null`. Sinxron — chaqiruvchi fon ipida (Dispatchers.Default) ishga
     * tushirishi shart. Bir vaqtda faqat bitta chaqiruv ishlaydi (`@Synchronized`) —
     * [FaceLandmarker] ko'p ipli parallel `detect()` chaqiruvini kafolatlamaydi, hozircha
     * esa yagona chaqiruvchi ([com.eyedetect.ai.ScreeningViewModel]) baribir ketma-ket
     * ishlaydi, shuning uchun bu amalda bloklashga olib kelmaydi.
     *
     * `detect()` chegaralangan kutish bilan ([detectExecutor] + timeout) chaqiriladi —
     * ML Kit zaxira yo'lidagi `Tasks.await(..., 3, TimeUnit.SECONDS)`ga o'xshab: xotira
     * bosimi yoki boshqa kutilmagan holat ostida native chaqiruv cheksiz bloklanib qolsa
     * ham, chaqiruvchi ip abadiy osilib qolmaydi (past ip esa fon rejimida davom etadi).
     * Timeout yuz bersa, [detectExecutor] va [landmarker] ikkalasi ham tashlab, qaytadan
     * yaratiladi — aks holda band (osilib qolgan) yagona ip barcha keyingi chaqiruvlarni
     * navbatga tizib, funksiya butun jarayon davomida jimgina ishlamay qolar edi.
     */
    @Synchronized
    fun detectIris(context: Context, bitmap: Bitmap, eye: String): Triple<Float, Float, Float>? {
        val result = runCatching {
            val faceLandmarker = getOrCreate(context)
            val future = detectExecutor.submit<FaceLandmarkerResult> {
                faceLandmarker.detect(BitmapImageBuilder(bitmap).build())
            }
            try {
                future.get(DETECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            } catch (e: TimeoutException) {
                // `cancel(true)` faqat interrupt bayrog'ini qo'yadi — MediaPipe'ning native
                // `detect()` chaqiruvi buni e'tiborsiz qoldirishi mumkin, ya'ni bitta ip'li
                // executor'ning yagona ipi haligacha band bo'lib qolishi mumkin. Shu ipni
                // (va navbatga tizilgan bitmap'ni) tashlab, yangi executor bilan
                // almashtiramiz — aks holda barcha keyingi chaqiruvlar shu band ip ortida
                // navbatga tizilib, har biri ham vaqt tugashi bilan yakunlanadi va bu
                // funksiya butun jarayon davomida jimgina (hech qanday signal'siz) ishlamay
                // qoladi.
                future.cancel(true)
                detectExecutor = newDetectExecutor()
                // `faceLandmarker.detect()` ko'p ipli parallel chaqiruvni kafolatlamaydi
                // (yuqoridagi eslatmaga qarang). Osilib qolgan eski ip hali shu obyekt
                // ustida ishlab turgan bo'lishi mumkin — agar `landmarker`ni shu holicha
                // qoldirsak, keyingi chaqiruv (yangi executor ipida) xuddi shu obyektda
                // eski chaqiruv bilan bir vaqtda ishlab, aniqlanishi qiyin xatolarga
                // (yoki native crash'ga) olib kelishi mumkin. Shu sababli obyektni ham
                // tashlab yuboramiz — keyingi chaqiruv o'z sof nusxasini yaratadi, eski
                // (hali tugamagan) chaqiruv esa eski nusxa bilan yakunlanadi/xotiradan
                // chiqadi, ikkalasi bir-biriga aralashmaydi.
                landmarker = null
                null
            }
        }.getOrNull() ?: return null

        if (result.faceLandmarks().isEmpty()) return null
        val landmarks = result.faceLandmarks()[0]

        val centerIdx = if (eye == "left") LEFT_IRIS_CENTER else RIGHT_IRIS_CENTER
        val ringIdx = if (eye == "left") LEFT_IRIS_RING else RIGHT_IRIS_RING
        if (centerIdx >= landmarks.size || ringIdx.any { it >= landmarks.size }) return null

        val center = landmarks[centerIdx]
        val cx = center.x() * bitmap.width
        val cy = center.y() * bitmap.height

        val radius = ringIdx.map { idx ->
            val p = landmarks[idx]
            val dx = p.x() * bitmap.width - cx
            val dy = p.y() * bitmap.height - cy
            sqrt(dx * dx + dy * dy)
        }.average().toFloat()

        if (radius < 1f) return null
        return Triple(cx, cy, radius)
    }
}
