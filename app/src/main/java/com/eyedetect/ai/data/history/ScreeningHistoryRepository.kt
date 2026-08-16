package com.eyedetect.ai.data.history

import android.content.Context
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.vision.PupilHeuristicResult
import kotlinx.coroutines.flow.Flow

/** [ScreeningViewModel][com.eyedetect.ai.ScreeningViewModel] tarix uchun tayanadigan
 * torroq interfeys — SQLCipher'ning native kutubxonasi Robolectric (JVM) test
 * muhitida yuklanmaydi, shu sababli birlik testlari haqiqiy [ScreeningHistoryRepository]
 * o'rniga soxta implementatsiya berishi kerak ([ApiService][com.eyedetect.ai.data.ApiService]
 * uchun ishlatilgan `@JvmOverloads` in'eksiya naqshiga o'xshash). */
interface ScreeningHistoryStore {
    suspend fun latestFor(patientId: String, eye: String): ScreeningHistoryEntity?
    suspend fun saveResult(result: PredictResponse, heuristic: PupilHeuristicResult?): Long
    suspend fun updateHeuristic(id: Long, heuristic: PupilHeuristicResult)
}

/** O'tgan skrininglar tarixi uchun Room ombori — [EyeCarePreferencesRepository]dagi
 * kabi to'g'ridan-to'g'ri (DI'siz) instansiyalanadi. */
class ScreeningHistoryRepository(context: Context) : ScreeningHistoryStore {

    private val dao = ScreeningHistoryDatabase.getInstance(context).screeningHistoryDao()

    val history: Flow<List<ScreeningHistoryEntity>> = dao.observeAll()

    fun historyForPatient(patientId: String): Flow<List<ScreeningHistoryEntity>> =
        dao.observeForPatient(patientId)

    override suspend fun latestFor(patientId: String, eye: String): ScreeningHistoryEntity? =
        dao.latestFor(patientId, eye)

    /** Backend natijasini (+ mavjud bo'lsa mahalliy evristika natijasini) tarixga saqlaydi.
     * @return saqlangan yozuvning ID'si — evristika keyinroq tayyor bo'lsa, shu ID orqali
     * [updateHeuristic] bilan to'ldiriladi. */
    override suspend fun saveResult(result: PredictResponse, heuristic: PupilHeuristicResult?): Long =
        dao.insert(
            ScreeningHistoryEntity(
                examId = result.examId,
                patientId = result.patientId,
                eye = result.eye,
                decision = result.decision,
                decisionText = result.decisionText,
                gradeLabel = result.gradeLabel,
                icdrGrade = result.icdrGrade,
                probability = result.probability,
                quality = result.quality,
                modelVersion = result.modelVersion,
                imageUrl = result.imageUrl,
                heatmapUrl = result.heatmapUrl,
                localOpacity = heuristic?.opacity?.name,
                localRedReflex = heuristic?.redReflex?.name,
                localHueDeg = heuristic?.darkMeanHueDeg,
                localSaturation = heuristic?.darkMeanSaturation,
                localValue = heuristic?.darkMeanValue,
                processedAt = result.processedAt,
            )
        )

    /** Yozuv saqlangandan keyin tayyor bo'lgan mahalliy evristika natijasi bilan to'ldiradi. */
    override suspend fun updateHeuristic(id: Long, heuristic: PupilHeuristicResult) {
        dao.updateHeuristic(
            id = id,
            opacity = heuristic.opacity.name,
            redReflex = heuristic.redReflex.name,
            hueDeg = heuristic.darkMeanHueDeg,
            saturation = heuristic.darkMeanSaturation,
            value = heuristic.darkMeanValue,
        )
    }

    suspend fun delete(entry: ScreeningHistoryEntity) = dao.delete(entry)

    suspend fun clearAll() = dao.clearAll()
}
