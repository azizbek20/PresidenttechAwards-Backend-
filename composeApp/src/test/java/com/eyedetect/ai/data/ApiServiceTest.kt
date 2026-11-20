package com.eyedetect.ai.data

import kotlinx.coroutines.runBlocking
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.net.SocketTimeoutException
import java.util.concurrent.TimeUnit

/**
 * `ApiService`ni haqiqiy Retrofit/OkHttp qatlami bilan, lekin haqiqiy tarmoqsiz
 * (`MockWebServer`) sinaydi — `ApiClient` singletoni (BuildConfig'ga bog'liq)
 * chetlab o'tiladi, bevosita mock server manziliga ulanadigan klient quriladi.
 */
class ApiServiceTest {

    private lateinit var server: MockWebServer
    private lateinit var service: ApiService

    private fun buildService(readTimeoutMs: Long = 5_000): ApiService {
        val client = OkHttpClient.Builder()
            .readTimeout(readTimeoutMs, TimeUnit.MILLISECONDS)
            .build()
        return Retrofit.Builder()
            .baseUrl(server.url("/"))
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    private fun samplePart() = MultipartBody.Part.createFormData(
        "file", "fundus.jpg",
        "fake-bytes".toRequestBody("image/jpeg".toMediaTypeOrNull()),
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        service = buildService()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private val successJson = """
        {
          "exam_id": "exam-123",
          "patient_id": "p-1",
          "eye": "right",
          "referable": true,
          "probability": 0.87,
          "icdr_grade": 3,
          "grade_label": "Severe NPDR",
          "decision": "REFER",
          "decision_text": "Refer to specialist",
          "quality": "GOOD",
          "heatmap_url": "/static/heatmap.png",
          "image_url": "/static/image.png",
          "model_version": "v1.0",
          "processed_at": "2026-08-09T10:00:00Z",
          "disclaimer": "Not a diagnosis"
        }
    """.trimIndent()

    @Test
    fun `predict parses a successful response`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody(successJson))

        val result = service.predict(samplePart(), null, null)

        assertEquals("exam-123", result.examId)
        assertEquals("REFER", result.decision)
        assertEquals(3, result.icdrGrade)
        assertEquals(0.87, result.probability, 0.0001)
        assertTrue(result.referable)
    }

    @Test(expected = HttpException::class)
    fun `predict throws HttpException on 4xx`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(422).setBody("""{"detail":"bad image"}"""))

        service.predict(samplePart(), null, null)
        Unit
    }

    @Test(expected = HttpException::class)
    fun `predict throws HttpException on 5xx`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"server error"}"""))

        service.predict(samplePart(), null, null)
        Unit
    }

    @Test(expected = SocketTimeoutException::class)
    fun `predict times out when the server never responds`() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
        service = buildService(readTimeoutMs = 200)

        service.predict(samplePart(), null, null)
        Unit
    }
}
