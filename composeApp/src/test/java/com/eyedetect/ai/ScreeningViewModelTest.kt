package com.eyedetect.ai

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import com.eyedetect.ai.data.ApiService
import com.eyedetect.ai.data.PredictPolling
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.data.TaskResponse
import com.eyedetect.ai.data.TaskStatusResponse
import com.eyedetect.ai.data.configureApi
import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.ResponseException
import io.ktor.client.request.get
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.headersOf
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryStore
import com.eyedetect.ai.data.upload.PendingUploadStore
import com.eyedetect.ai.vision.PupilHeuristicResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.io.File
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException

/**
 * `ScreeningViewModel`ning holat o'tishlarini (Idle -> Loading -> Success/Error) va
 * `friendly()` xato xabarlarini xaritalashni sinaydi. Backend `ApiService` soxta
 * implementatsiya bilan almashtiriladi ([ScreeningViewModel]dagi `@JvmOverloads`
 * konstruktor parametri orqali) — haqiqiy tarmoq yoki `ApiClient` singletoni kerak emas.
 * Xuddi shu sababdan tarix ombori ham [FakeHistoryStore], navbat ombori esa [FakePendingUploadStore]
 * bilan almashtiriladi: haqiqiy `ScreeningHistoryRepository`/`PendingUploadRepository` bir xil
 * SQLCipher orqali shifrlangan Room bazasini ochadi, va uning native kutubxonasi Robolectric
 * (JVM, qurilmasiz) muhitida yuklanmaydi.
 *
 * Rasm dekodlash (`BitmapLoader`) va mahalliy evristika `viewModelScope.launch`
 * ichida haqiqiy `Dispatchers.Default`da ishlaydi (SUT'da qattiq kodlangan) — shu
 * sababli yakuniy holatni tekshirishda [awaitTerminalState] bilan pollinguqilinadi,
 * faqat "Loading" holati (birinchi suspend nuqtasidan oldin sinxron o'rnatiladi)
 * darhol tekshiriladi.
 */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
class ScreeningViewModelTest {

    @get:Rule
    val tempFolder = TemporaryFolder()

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun app(): Application = ApplicationProvider.getApplicationContext()

    private fun newFile(): File =
        tempFolder.newFile("fundus_${System.nanoTime()}.jpg").apply {
            // Haqiqiy rasm emas -- BitmapFactory buni dekodlay olmaydi (bitmap == null),
            // shu bilan ML Kit/evristika yo'lini chetlab o'tamiz (bu birlik testi doirasidan tashqarida).
            writeBytes("not-a-real-image".toByteArray())
        }

    private fun sampleResponse() = PredictResponse(
        examId = "exam-1",
        patientId = "p-1",
        eye = "right",
        referable = false,
        probability = 0.1,
        icdrGrade = 0,
        gradeLabel = "No DR",
        decision = "NO_REFER",
        decisionText = "No referral needed",
        quality = "GOOD",
        heatmapUrl = null,
        imageUrl = null,
        modelVersion = "v1",
        processedAt = "2026-08-09T10:00:00Z",
        disclaimer = "Not a diagnosis",
    )

    /** Backend'ning asinxron oqimini soxtalashtiradi: `predict` vazifa qaytaradi,
     * `getPredictStatus` esa [respond] natijasini darhol `SUCCESS` sifatida beradi. */
    private class FakeApiService(private val respond: suspend () -> PredictResponse) : ApiService {
        override suspend fun predict(
            fileBytes: ByteArray,
            fileName: String,
            patientId: String?,
            eye: String?,
            onProgress: ((Float) -> Unit)?,
        ): TaskResponse = TaskResponse(taskId = "t-1", status = "PENDING", message = "ok")

        override suspend fun getPredictStatus(taskId: String): TaskStatusResponse =
            TaskStatusResponse(taskId = taskId, status = "SUCCESS", result = respond())
    }

    /** Har chaqiruvda ro'yxatdagi keyingi xatti-harakatni qaytaradi ([retry] testlari
     * uchun — masalan, birinchi urinish xato, ikkinchisi muvaffaqiyatli). */
    private class SequencedFakeApiService(private vararg val behaviors: suspend () -> PredictResponse) : ApiService {
        var callCount = 0
            private set

        override suspend fun predict(
            fileBytes: ByteArray,
            fileName: String,
            patientId: String?,
            eye: String?,
            onProgress: ((Float) -> Unit)?,
        ): TaskResponse = TaskResponse(taskId = "t-1", status = "PENDING", message = "ok")

        override suspend fun getPredictStatus(taskId: String): TaskStatusResponse {
            val behavior = behaviors[callCount.coerceAtMost(behaviors.size - 1)]
            callCount++
            return TaskStatusResponse(taskId = taskId, status = "SUCCESS", result = behavior())
        }
    }

    /** SQLCipher'ga tegmaydigan xotiradagi soxta tarix ombori — bu test to'plami tarixning
     * o'zini emas, faqat `ScreeningViewModel`ning tarixga bog'liq bo'lmagan holat o'tishlarini
     * tekshiradi, shu sababli hech narsani haqiqatan saqlash shart emas. */
    private class FakeHistoryStore : ScreeningHistoryStore {
        private var nextId = 1L
        override suspend fun latestFor(patientId: String, eye: String): ScreeningHistoryEntity? = null
        override suspend fun saveResult(result: PredictResponse, heuristic: PupilHeuristicResult?): Long = nextId++
        override suspend fun updateHeuristic(id: Long, heuristic: PupilHeuristicResult) {}
    }

    /** SQLCipher'ga tegmaydigan soxta navbat ombori (`FakeHistoryStore` bilan bir xil sabab) —
     * [enqueue]ga uzatilgan argumentlarni keyinchalik tekshirish uchun eslab qoladi. */
    private class FakePendingUploadStore : PendingUploadStore {
        private var nextId = 1L
        var lastPatientId: String? = null
            private set
        var lastEye: String? = null
            private set

        override suspend fun enqueue(bytes: ByteArray, patientId: String?, eye: String, fallbackMediaType: String): Long {
            lastPatientId = patientId
            lastEye = eye
            return nextId++
        }
    }

    private val noWait = PredictPolling(intervalMs = 0, timeoutMs = 5_000)

    private fun newVm(
        api: ApiService,
        healthCheck: suspend () -> Boolean = { true },
        pendingUploadStore: PendingUploadStore = FakePendingUploadStore(),
        scheduleUpload: (Long) -> Unit = {},
        polling: PredictPolling = noWait,
    ) = ScreeningViewModel(app(), api, healthCheck, FakeHistoryStore(), pendingUploadStore, scheduleUpload, polling)

    /** Haqiqiy Ktor `ResponseException`ni (ishlab chiqarishdagi [configureApi] bilan)
     * `MockEngine` orqali hosil qiladi — javob tanasi `bodyAsText()` uchun saqlangan bo'ladi. */
    private suspend fun httpException(code: Int, body: String? = null): ResponseException {
        val client = HttpClient(MockEngine {
            respond(body ?: "", HttpStatusCode.fromValue(code), headersOf(HttpHeaders.ContentType, "application/json"))
        }) { configureApi(apiKey = "k") }
        return try {
            client.get("http://backend.test/")
            error("expected an HTTP $code failure")
        } catch (e: ResponseException) {
            e
        }
    }

    /** `uiState` hali `Loading`ligicha qolsa, alohida (real) threadda ishlayotgan
     * `Dispatchers.Default` ishi tugashini kutib, qisqa muddat so'rovlar bilan tekshiradi. */
    private fun awaitTerminalState(vm: ScreeningViewModel, timeoutMs: Long = 3_000): UiState {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (vm.uiState.value is UiState.Loading) {
            if (System.currentTimeMillis() > deadline) fail("Timed out waiting for a terminal UiState")
            Thread.sleep(5)
        }
        return vm.uiState.value
    }

    /** `finally { file.delete() }` `doRequest()` to'liq tugagach (masalan, Room'ga yozishdan
     * keyin) ishlaydi — `uiState` allaqachon Success/Error bo'lgandan biroz keyin kelishi
     * mumkin, shu sababli fayl yo'qolishini ham qisqa muddat so'rovlar bilan kutamiz. */
    private fun awaitFileDeleted(file: File, timeoutMs: Long = 3_000) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (file.exists()) {
            if (System.currentTimeMillis() > deadline) fail("Timed out waiting for the temp file to be deleted")
            Thread.sleep(5)
        }
    }

    @Test
    fun `initial state is Idle`() {
        val vm = newVm(FakeApiService { sampleResponse() })
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `uploadFile sets Loading synchronously, then Success once the backend replies`() {
        val gate = CompletableDeferred<Unit>()
        val vm = newVm(FakeApiService { gate.await(); sampleResponse() })
        val file = newFile()

        vm.uploadFile(file)
        assertEquals(UiState.Loading, vm.uiState.value)

        gate.complete(Unit)

        val state = awaitTerminalState(vm)
        assertTrue(state is UiState.Success)
        assertEquals("exam-1", (state as UiState.Success).result.examId)
        awaitFileDeleted(file)
    }

    @Test
    fun `uploadFile keeps the temp file when the request fails, so retry can resend it`() {
        val vm = newVm(FakeApiService { throw IllegalStateException("boom") })
        val file = newFile()

        vm.uploadFile(file)
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertTrue("Error state should allow retry when the source photo is still on disk", (state as UiState.Error).canRetry)
        assertTrue("temp file must survive a failed upload for retry to work", file.exists())
    }

    @Test
    fun `retry resends the same file without the caller retaking a photo`() {
        val api = SequencedFakeApiService(
            { throw httpException(503) },
            { sampleResponse() },
        )
        val vm = newVm(api)
        val file = newFile()

        vm.uploadFile(file)
        val failed = awaitTerminalState(vm)
        assertTrue(failed is UiState.Error)
        assertTrue(file.exists())

        vm.retry()
        val succeeded = awaitTerminalState(vm)

        assertTrue(succeeded is UiState.Success)
        assertEquals(2, api.callCount)
        awaitFileDeleted(file)
    }

    @Test
    fun `retry is a no-op when there is no pending upload source`() {
        val vm = newVm(FakeApiService { sampleResponse() })

        vm.retry()

        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `cancelUpload deletes the pending file and returns to Idle`() {
        val gate = CompletableDeferred<Unit>()
        val vm = newVm(FakeApiService { gate.await(); sampleResponse() })
        val file = newFile()

        vm.uploadFile(file)
        assertEquals(UiState.Loading, vm.uiState.value)

        vm.cancelUpload()

        assertEquals(UiState.Idle, vm.uiState.value)
        awaitFileDeleted(file)
        // Bekor qilingandan keyin so'nggi manba tozalangan -- qayta urinish endi hech narsa qilmaydi.
        vm.retry()
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `uploadFile maps a 422 HttpException body detail when present`() {
        val vm = newVm(FakeApiService {
            throw httpException(422, """{"detail":"Rasm juda xira"}""")
        })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals("Rasm juda xira", (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps a 404 HttpException without a detail body to the not-found message`() {
        val vm = newVm(FakeApiService { throw httpException(404) })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_not_found), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps a 5xx HttpException to the server error message`() {
        val vm = newVm(FakeApiService { throw httpException(503) })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_server), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps an unmapped HttpException code to the generic http message with the code`() {
        val vm = newVm(FakeApiService { throw httpException(418) })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_http_generic, 418), (state as UiState.Error).message)
    }

    @Test
    fun `checkBackendHealth reflects the injected health check result`() {
        val vm = newVm(FakeApiService { sampleResponse() }, healthCheck = { true })

        vm.checkBackendHealth()

        assertEquals(true, vm.backendOnline.value)
    }

    @Test
    fun `checkBackendHealth reports offline when the health check fails`() {
        val vm = newVm(FakeApiService { sampleResponse() }, healthCheck = { throw java.io.IOException("down") })

        vm.checkBackendHealth()

        assertEquals(false, vm.backendOnline.value)
    }

    @Test
    fun `uploadFile queues the photo instead of showing an error when there is no connection`() {
        var scheduledId: Long? = null
        val pendingStore = FakePendingUploadStore()
        val vm = newVm(
            FakeApiService { throw UnknownHostException("no dns") },
            pendingUploadStore = pendingStore,
            scheduleUpload = { id -> scheduledId = id },
        )
        vm.patientId = "p-42"
        vm.eye = "left"
        val file = newFile()

        vm.uploadFile(file)
        val state = awaitTerminalState(vm)

        assertEquals(UiState.Queued, state)
        awaitFileDeleted(file)

        assertEquals(1L, scheduledId)
        assertEquals("p-42", pendingStore.lastPatientId)
        assertEquals("left", pendingStore.lastEye)
    }

    @Test
    fun `uploadFile maps SocketTimeoutException to the timeout message`() {
        // Timeout navbatga qo'yilmaydi — server sekin bo'lishi mumkin (tarmoq bor).
        val vm = newVm(FakeApiService { throw SocketTimeoutException("timed out") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_timeout), (state as UiState.Error).message)
        assertTrue(state.canRetry)
    }

    @Test
    fun `a backend task that never finishes maps to the timeout message`() {
        val stuck = object : ApiService {
            override suspend fun predict(
                fileBytes: ByteArray,
                fileName: String,
                patientId: String?,
                eye: String?,
                onProgress: ((Float) -> Unit)?,
            ) = TaskResponse(taskId = "t-1", status = "PENDING", message = "ok")

            override suspend fun getPredictStatus(taskId: String) =
                TaskStatusResponse(taskId = taskId, status = "PROCESSING")
        }
        val vm = newVm(stuck, polling = PredictPolling(intervalMs = 0, timeoutMs = 50))

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_timeout), (state as UiState.Error).message)
        assertTrue(state.canRetry)
    }

    @Test
    fun `uploadFile maps UnknownServiceException to the https-required message`() {
        val vm = newVm(FakeApiService { throw UnknownServiceException("cleartext blocked") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_https_required), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the raw exception message for unmapped errors`() {
        val vm = newVm(FakeApiService { throw IllegalStateException("backend exploded") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals("backend exploded", (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the unknown-error message when the exception has no message`() {
        val vm = newVm(FakeApiService { throw IllegalStateException() })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_unknown), (state as UiState.Error).message)
    }

    @Test
    fun `reset returns to Idle and clears local heuristic and symmetry`() {
        val vm = newVm(FakeApiService { sampleResponse() })
        vm.uploadFile(newFile())
        awaitTerminalState(vm)

        vm.reset()

        assertEquals(UiState.Idle, vm.uiState.value)
        assertNull(vm.localHeuristic.value)
        assertNull(vm.symmetry.value)
    }
}
