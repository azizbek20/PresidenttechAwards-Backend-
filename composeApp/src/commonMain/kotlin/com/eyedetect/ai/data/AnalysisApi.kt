package com.eyedetect.ai.data

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.plugins.onUpload
import io.ktor.client.request.forms.formData
import io.ktor.client.request.forms.submitFormWithBinaryData
import io.ktor.client.request.get
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Ko'z tubidan tashqari tahlil turlari (backend `app/analysis/catalog.py` bilan bir xil kodlar). */
object AnalysisTypes {
    const val EXTERNAL_EYE = "external_eye"
    const val SKIN = "skin"
    const val ORAL = "oral"
    const val NAIL = "nail"
    val ALL = listOf(EXTERNAL_EYE, SKIN, ORAL, NAIL)
}

@Serializable
data class AnalysisFinding(
    val code: String,
    val label: String,
    val probability: Double,
    val risk: String, // low | medium | high
)

/** `POST /api/v1/analyze` javobi. Backendda hech bir maydon null bo'lmaydi. */
@Serializable
data class AnalyzeResponse(
    @SerialName("analysis_id") val analysisId: String,
    @SerialName("analysis_type") val analysisType: String,
    @SerialName("analysis_label") val analysisLabel: String,
    @SerialName("patient_id") val patientId: String = "",
    @SerialName("body_site") val bodySite: String = "",
    @SerialName("risk_level") val riskLevel: String, // low | medium | high | ungradable
    @SerialName("top_finding") val topFinding: String = "",
    @SerialName("top_label") val topLabel: String = "",
    val probability: Double = 0.0,
    val findings: List<AnalysisFinding> = emptyList(),
    val recommendation: String = "",
    val quality: String = "good",
    @SerialName("image_url") val imageUrl: String = "",
    @SerialName("model_version") val modelVersion: String = "",
    @SerialName("processed_at") val processedAt: String = "",
    val disclaimer: String = "",
    @SerialName("is_demo") val isDemo: Boolean = false,
)

interface AnalysisApi {
    suspend fun analyze(
        fileBytes: ByteArray,
        fileName: String,
        analysisType: String,
        patientId: String?,
        bodySite: String?,
        onProgress: ((Float) -> Unit)? = null,
    ): AnalyzeResponse

    suspend fun history(patientId: String? = null, limit: Int = 50): List<AnalyzeResponse>
}

class KtorAnalysisApi(
    private val client: HttpClient,
    private val baseUrl: () -> String,
) : AnalysisApi {
    override suspend fun analyze(
        fileBytes: ByteArray,
        fileName: String,
        analysisType: String,
        patientId: String?,
        bodySite: String?,
        onProgress: ((Float) -> Unit)?,
    ): AnalyzeResponse {
        val response = client.submitFormWithBinaryData(
            url = "${baseUrl()}api/v1/analyze",
            formData = formData {
                append("file", fileBytes, Headers.build {
                    append(HttpHeaders.ContentType, "image/jpeg")
                    append(HttpHeaders.ContentDisposition, "filename=\"$fileName\"")
                })
                append("analysis_type", analysisType)
                patientId?.takeIf { it.isNotBlank() }?.let { append("patient_id", it) }
                bodySite?.takeIf { it.isNotBlank() }?.let { append("body_site", it) }
            }
        ) {
            onUpload { sent, total ->
                if (total > 0) onProgress?.invoke(sent.toFloat() / total.toFloat())
            }
        }
        return response.body()
    }

    override suspend fun history(patientId: String?, limit: Int): List<AnalyzeResponse> {
        return client.get("${baseUrl()}api/v1/analyses") {
            url {
                parameters.append("limit", limit.toString())
                patientId?.takeIf { it.isNotBlank() }?.let { parameters.append("patient_id", it) }
            }
        }.body()
    }
}
