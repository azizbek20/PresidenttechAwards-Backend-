package com.eyedetect.ai

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import com.eyedetect.ai.data.ApiService
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryStore
import com.eyedetect.ai.vision.PupilHeuristicResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody.Companion.toResponseBody
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
import retrofit2.HttpException
import retrofit2.Response
import java.io.File
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.net.UnknownServiceException

/**
 * `ScreeningViewModel`ning holat o'tishlarini (Idle -> Loading -> Success/Error) va
 * `friendly()` xato xabarlarini xaritalashni sinaydi. Backend `ApiService` soxta
 * implementatsiya bilan almashtiriladi ([ScreeningViewModel]dagi `@JvmOverloads`
 * konstruktor parametri orqali) — haqiqiy tarmoq yoki `ApiClient` singletoni kerak emas.
 * Xuddi shu sababdan tarix ombori ham [FakeHistoryStore] bilan almashtiriladi: haqiqiy
 * `ScreeningHistoryRepository` SQLCipher orqali shifrlangan Room bazasini ochadi, va
 * uning native kutubxonasi Robolectric (JVM, qurilmasiz) muhitida yuklanmaydi.
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

    private class FakeApiService(private val respond: suspend () -> PredictResponse) : ApiService {
        override suspend fun predict(
            file: MultipartBody.Part,
            patientId: RequestBody?,
            eye: RequestBody?,
        ): PredictResponse = respond()
    }

    /** Har chaqiruvda ro'yxatdagi keyingi xatti-harakatni qaytaradi ([retry] testlari
     * uchun — masalan, birinchi urinish xato, ikkinchisi muvaffaqiyatli). */
    private class SequencedFakeApiService(private vararg val behaviors: suspend () -> PredictResponse) : ApiService {
        var callCount = 0
            private set

        override suspend fun predict(
            file: MultipartBody.Part,
            patientId: RequestBody?,
            eye: RequestBody?,
        ): PredictResponse {
            val behavior = behaviors[callCount.coerceAtMost(behaviors.size - 1)]
            callCount++
            return behavior()
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

    private fun httpException(code: Int, body: String? = null): HttpException {
        val responseBody = (body ?: "").toResponseBody("application/json".toMediaTypeOrNull())
        return HttpException(Response.error<Any>(code, responseBody))
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
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() }, historyStore = FakeHistoryStore())
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `uploadFile sets Loading synchronously, then Success once the backend replies`() {
        val gate = CompletableDeferred<Unit>()
        val vm = ScreeningViewModel(app(), FakeApiService { gate.await(); sampleResponse() }, historyStore = FakeHistoryStore())
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
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException("boom") }, historyStore = FakeHistoryStore())
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
            { throw java.net.SocketTimeoutException("first attempt times out") },
            { sampleResponse() },
        )
        val vm = ScreeningViewModel(app(), api, historyStore = FakeHistoryStore())
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
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() }, historyStore = FakeHistoryStore())

        vm.retry()

        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `cancelUpload deletes the pending file and returns to Idle`() {
        val gate = CompletableDeferred<Unit>()
        val vm = ScreeningViewModel(app(), FakeApiService { gate.await(); sampleResponse() }, historyStore = FakeHistoryStore())
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
        val vm = ScreeningViewModel(
            app(),
            FakeApiService { throw httpException(422, """{"detail":"Rasm juda xira"}""") },
            historyStore = FakeHistoryStore(),
        )

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals("Rasm juda xira", (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps a 404 HttpException without a detail body to the not-found message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw httpException(404) }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_not_found), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps a 5xx HttpException to the server error message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw httpException(503) }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_server), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps an unmapped HttpException code to the generic http message with the code`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw httpException(418) }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_http_generic, 418), (state as UiState.Error).message)
    }

    @Test
    fun `checkBackendHealth reflects the injected health check result`() {
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() }, healthCheck = { true }, historyStore = FakeHistoryStore())

        vm.checkBackendHealth()

        assertEquals(true, vm.backendOnline.value)
    }

    @Test
    fun `checkBackendHealth reports offline when the health check fails`() {
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() }, healthCheck = { throw java.io.IOException("down") }, historyStore = FakeHistoryStore())

        vm.checkBackendHealth()

        assertEquals(false, vm.backendOnline.value)
    }

    @Test
    fun `uploadFile queues the photo instead of showing an error when there is no connection`() {
        // `scheduleUpload` va `enqueuePendingUpload` inject qilinadi — birlik testida haqiqiy
        // WorkManager/tarmoq va haqiqiy (SQLCipher bilan shifrlangan, Robolectric ostida
        // yuklanmaydigan) Room bazasi kerak emas (`healthCheck`dagi kabi sabab). Navbatga
        // qo'yilgan baytlar/bemor ID/ko'z va qaytarilgan ID orqali chaqirilishini tekshiramiz.
        var scheduledId: Long? = null
        var enqueuedPatientId: String? = null
        var enqueuedEye: String? = null
        var enqueuedByteCount = -1
        val vm = ScreeningViewModel(
            app(),
            FakeApiService { throw UnknownHostException("no dns") },
            scheduleUpload = { id -> scheduledId = id },
            historyStore = FakeHistoryStore(),
            enqueuePendingUpload = { bytes, patientId, eye, _ ->
                enqueuedByteCount = bytes.size
                enqueuedPatientId = patientId
                enqueuedEye = eye
                42L
            },
        )
        vm.patientId = "p-42"
        vm.eye = "left"
        val file = newFile()

        vm.uploadFile(file)
        val state = awaitTerminalState(vm)

        assertEquals(UiState.Queued, state)
        awaitFileDeleted(file)

        assertEquals(42L, scheduledId)
        assertTrue(enqueuedByteCount > 0)
        assertEquals("p-42", enqueuedPatientId)
        assertEquals("left", enqueuedEye)
    }

    @Test
    fun `uploadFile maps SocketTimeoutException to the timeout message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw SocketTimeoutException("timed out") }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_timeout), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps UnknownServiceException to the https-required message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw UnknownServiceException("cleartext blocked") }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_https_required), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the raw exception message for unmapped errors`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException("backend exploded") }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals("backend exploded", (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the unknown-error message when the exception has no message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException() }, historyStore = FakeHistoryStore())

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_unknown), (state as UiState.Error).message)
    }

    @Test
    fun `reset returns to Idle and clears local heuristic and symmetry`() {
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() }, historyStore = FakeHistoryStore())
        vm.uploadFile(newFile())
        awaitTerminalState(vm)

        vm.reset()

        assertEquals(UiState.Idle, vm.uiState.value)
        assertNull(vm.localHeuristic.value)
        assertNull(vm.symmetry.value)
    }
}
