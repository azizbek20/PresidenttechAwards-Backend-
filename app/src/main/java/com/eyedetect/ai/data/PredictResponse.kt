package com.eyedetect.ai.data

import com.google.gson.annotations.SerializedName

/**
 * Backend POST /api/v1/predict javobi (reja 5.1 API kontrakti).
 * Maydonlar backend JSON kalitlariga aynan mos.
 */
data class PredictResponse(
    @SerializedName("exam_id") val examId: String,
    @SerializedName("patient_id") val patientId: String?,
    val eye: String?,
    val referable: Boolean,
    val probability: Double,
    @SerializedName("icdr_grade") val icdrGrade: Int,
    @SerializedName("grade_label") val gradeLabel: String,
    val decision: String,                 // REFER | NO_REFER | UNGRADABLE
    @SerializedName("decision_text") val decisionText: String,
    val quality: String,
    @SerializedName("heatmap_url") val heatmapUrl: String?,
    @SerializedName("image_url") val imageUrl: String?,
    @SerializedName("model_version") val modelVersion: String,
    @SerializedName("processed_at") val processedAt: String,
    val disclaimer: String,
)
