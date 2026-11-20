package com.eyedetect.ai.data

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.MockRequestHandleScope
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.ClientRequestException
import io.ktor.client.plugins.ServerResponseException
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.HttpResponseData
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * [KtorApiService]ni haqiqiy Ktor qatlami bilan, lekin tarmoqsiz (`MockEngine`) sinaydi —
 * ishlab chiqarishdagi bilan bir xil [configureApi] sozlamasi ishlatiladi.
 */
class ApiServiceTest {

    private val requests = mutableListOf<HttpRequestData>()

    private fun service(
        handler: suspend MockRequestHandleScope.(HttpRequestData) -> HttpResponseData,
    ): ApiService {
        val engine = MockEngine { request ->
            requests += request
            handler(request)
        }
        val client = HttpClient(engine) { configureApi(apiKey = "test-key") }
        return KtorApiService(client) { "http://backend.test/" }
    }

    private fun MockRequestHandleScope.json(body: String, status: HttpStatusCode = HttpStatusCode.OK) =
        respond(body, status, headersOf(HttpHeaders.ContentType, "application/json"))

    private val resultJson = """
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
          "quality": "good",
          "heatmap_url": "/static/heatmap.png",
          "image_url": "/static/image.png",
          "model_version": "v1.0",
          "processed_at": "2026-08-09T10:00:00Z",
          "disclaimer": "Not a diagnosis",
          "request_id": "r-1",
          "mode": "demo"
        }
    """.trimIndent()

    private val noWait = PredictPolling(intervalMs = 0, timeoutMs = 5_000)

    @Test
    fun `predict posts to the async endpoint with the api key and parses the task`() = runBlocking {
        val api = service { json("""{"task_id":"t-1","status":"PENDING","message":"ok"}""") }

        val task = api.predict("bytes".toByteArray(), "fundus.jpg", "p-1", "left")

        assertEquals("t-1", task.taskId)
        assertEquals("PENDING", task.status)
        val request = requests.single()
        assertEquals("http://backend.test/api/v1/predict/async", request.url.toString())
        assertEquals("test-key", request.headers["X-API-Key"])
    }

    @Test
    fun `predictAndAwait polls the status endpoint until SUCCESS`() = runBlocking {
        var statusCalls = 0
        val api = service { request ->
            if (request.url.encodedPath.endsWith("/predict/async")) {
                json("""{"task_id":"t-1","status":"PENDING","message":"ok"}""")
            } else {
                statusCalls++
                if (statusCalls < 3) json("""{"task_id":"t-1","status":"PROCESSING"}""")
                else json("""{"task_id":"t-1","status":"SUCCESS","result":$resultJson}""")
            }
        }

        val result = api.predictAndAwait("bytes".toByteArray(), "fundus.jpg", null, null, polling = noWait)

        assertEquals("exam-123", result.examId)
        assertEquals("REFER", result.decision)
        assertEquals(3, result.icdrGrade)
        assertEquals(0.87, result.probability, 0.0001)
        assertTrue(result.referable)
        assertEquals(3, statusCalls)
        assertEquals("http://backend.test/api/v1/predict/status/t-1", requests.last().url.toString())
    }

    @Test
    fun `predictAndAwait surfaces a FAILURE status as PredictFailedException`() = runBlocking {
        val api = service { request ->
            if (request.url.encodedPath.endsWith("/predict/async")) {
                json("""{"task_id":"t-1","status":"PENDING","message":"ok"}""")
            } else {
                json("""{"task_id":"t-1","status":"FAILURE","error":"Inference error"}""")
            }
        }

        try {
            api.predictAndAwait("bytes".toByteArray(), "fundus.jpg", null, null, polling = noWait)
            fail("expected PredictFailedException")
        } catch (e: PredictFailedException) {
            assertTrue(e.message!!.contains("Inference error"))
        }
    }

    @Test
    fun `predictAndAwait gives up after the polling timeout`() = runBlocking {
        val api = service { request ->
            if (request.url.encodedPath.endsWith("/predict/async")) {
                json("""{"task_id":"t-1","status":"PENDING","message":"ok"}""")
            } else {
                json("""{"task_id":"t-1","status":"PROCESSING"}""")
            }
        }

        try {
            api.predictAndAwait(
                "bytes".toByteArray(), "fundus.jpg", null, null,
                polling = PredictPolling(intervalMs = 10, timeoutMs = 50),
            )
            fail("expected PredictTimeoutException")
        } catch (_: PredictTimeoutException) {
        }
    }

    @Test(expected = ClientRequestException::class)
    fun `predict throws ClientRequestException on 4xx`() = runBlocking {
        val api = service { json("""{"detail":"bad image"}""", HttpStatusCode.UnprocessableEntity) }

        api.predict("bytes".toByteArray(), "fundus.jpg", null, null)
        Unit
    }

    @Test(expected = ServerResponseException::class)
    fun `predict throws ServerResponseException on 5xx`() = runBlocking {
        val api = service { json("""{"detail":"server error"}""", HttpStatusCode.InternalServerError) }

        api.predict("bytes".toByteArray(), "fundus.jpg", null, null)
        Unit
    }
}
