package com.eyedetect.ai.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Backend POST /api/v1/predict javobi (reja 5.1 API kontrakti).
 * Maydonlar backend JSON kalitlariga aynan mos.
 */
@Serializable
data class PredictResponse(
    @SerialName("exam_id") val examId: String,
    @SerialName("patient_id") val patientId: String? = null,
    val eye: String? = null,
    val referable: Boolean,
    val probability: Double,
    @SerialName("icdr_grade") val icdrGrade: Int,
    @SerialName("grade_label") val gradeLabel: String,
    val decision: String,                 // REFER | NO_REFER | UNGRADABLE
    @SerialName("decision_text") val decisionText: String,
    val quality: String,
    @SerialName("heatmap_url") val heatmapUrl: String? = null,
    @SerialName("image_url") val imageUrl: String? = null,
    @SerialName("model_version") val modelVersion: String,
    @SerialName("processed_at") val processedAt: String,
    val disclaimer: String,
)

@Serializable
data class TaskResponse(
    @SerialName("task_id") val taskId: String,
    val status: String,
    val message: String
)

@Serializable
data class TaskStatusResponse(
    @SerialName("task_id") val taskId: String,
    val status: String, // PENDING, PROCESSING, SUCCESS, FAILURE
    val result: PredictResponse? = null,
    val error: String? = null
)
