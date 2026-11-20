package com.eyedetect.ai.data

import io.ktor.client.HttpClient
import io.ktor.client.HttpClientConfig
import io.ktor.client.call.body
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.onUpload
import io.ktor.client.request.forms.formData
import io.ktor.client.request.forms.submitFormWithBinaryData
import io.ktor.client.request.get
import io.ktor.client.request.head
import io.ktor.client.request.header
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * Backend API klientining umumiy sozlamasi. Alohida funksiya bo'lgani uchun testlar
 * xuddi shu sozlamani `MockEngine` bilan qayta ishlatadi.
 *
 * `expectSuccess = true` — 4xx/5xx javoblar `ResponseException` sifatida tashlanadi
 * (aks holda xato tanasi `TaskResponse`ga dekodlanib, tushunarsiz xato chiqadi).
 */
fun HttpClientConfig<*>.configureApi(apiKey: String) {
    expectSuccess = true
    install(ContentNegotiation) {
        json(Json {
            ignoreUnknownKeys = true
            isLenient = true
        })
    }
    install(HttpTimeout) {
        requestTimeoutMillis = 30000
        connectTimeoutMillis = 15000
        socketTimeoutMillis = 30000
    }
    defaultRequest {
        header("X-API-Key", apiKey)
    }
}

/** `POST /api/v1/predict/async` + `GET /api/v1/predict/status/{id}` (Ktor). */
class KtorApiService(
    private val client: HttpClient,
    private val baseUrl: () -> String,
) : ApiService {
    override suspend fun predict(
        fileBytes: ByteArray,
        fileName: String,
        patientId: String?,
        eye: String?,
        onProgress: ((Float) -> Unit)?
    ): TaskResponse {
        val response = client.submitFormWithBinaryData(
            url = "${baseUrl()}api/v1/predict/async",
            formData = formData {
                append("file", fileBytes, Headers.build {
                    append(HttpHeaders.ContentType, "image/jpeg")
                    append(HttpHeaders.ContentDisposition, "filename=\"$fileName\"")
                })
                if (patientId != null) {
                    append("patient_id", patientId)
                }
                if (eye != null) {
                    append("eye", eye)
                }
            }
        ) {
            onUpload { bytesSentTotal, contentLength ->
                if (contentLength > 0) {
                    onProgress?.invoke(bytesSentTotal.toFloat() / contentLength.toFloat())
                }
            }
        }
        return response.body()
    }

    override suspend fun getPredictStatus(taskId: String): TaskStatusResponse {
        return client.get("${baseUrl()}api/v1/predict/status/$taskId").body()
    }
}

object ApiClient {
    val baseUrl: String get() = AppConfig.API_BASE_URL

    val client = HttpClient { configureApi(AppConfig.API_KEY) }

    private val pingClient = HttpClient {
        install(HttpTimeout) {
            requestTimeoutMillis = 3000
            connectTimeoutMillis = 3000
        }
    }

    val service: ApiService = KtorApiService(client) { baseUrl }

    val analysis: AnalysisApi = KtorAnalysisApi(client) { baseUrl }

    suspend fun ping(): Boolean {
        return try {
            val response = pingClient.head(baseUrl)
            response.status.value in 200..599
        } catch (e: Exception) {
            false
        }
    }

    fun absoluteUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http")) return path
        return baseUrl.trimEnd('/') + path
    }
}
