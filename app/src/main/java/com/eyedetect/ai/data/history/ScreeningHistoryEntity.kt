package com.eyedetect.ai.data.history

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Backenddan qaytgan bitta skrining natijasining lokal nusxasi (Room). Bemor ID va
 * rasm — shaxsiy tibbiy ma'lumot (PHI), shuning uchun faqat qurilma ichida, faqat
 * matn/havola sifatida saqlanadi (rasmning o'zi emas — `imageUrl` backend manzili).
 *
 * `localOpacity`/`localRedReflex`/`localHueDeg`/`localSaturation`/`localValue` —
 * [com.eyedetect.ai.vision.PupilHeuristics] mahalliy evristikasining natijasi.
 * Bular yozuv birinchi saqlanganda hali tayyor bo'lmasligi mumkin (ML Kit ACCURATE
 * rejimi tufayli sekinroq) — shu holda `null` bilan saqlanadi, keyin tayyor bo'lgach
 * `ScreeningHistoryDao.updateHeuristic()` orqali to'ldiriladi. Ikki ko'z simmetriyasini
 * solishtirish ([com.eyedetect.ai.vision.EyeSymmetryAnalyzer]) shu maydonlarga tayanadi.
 */
@Entity(tableName = "screening_history")
data class ScreeningHistoryEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val examId: String,
    val patientId: String?,
    val eye: String?,
    val decision: String,
    val decisionText: String,
    val gradeLabel: String,
    val icdrGrade: Int,
    val probability: Double,
    val quality: String,
    val modelVersion: String,
    val imageUrl: String?,
    val heatmapUrl: String?,
    val localOpacity: String?,
    val localRedReflex: String?,
    val localHueDeg: Float? = null,
    val localSaturation: Float? = null,
    val localValue: Float? = null,
    val processedAt: String,
    val savedAtMs: Long = System.currentTimeMillis(),
)
