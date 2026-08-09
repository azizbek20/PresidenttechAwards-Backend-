package com.eyedetect.ai

import android.app.Application
import androidx.test.core.app.ApplicationProvider
import com.eyedetect.ai.data.ApiService
import com.eyedetect.ai.data.PredictResponse
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import okhttp3.MultipartBody
import okhttp3.RequestBody
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
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() })
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test
    fun `uploadFile sets Loading synchronously, then Success once the backend replies`() {
        val gate = CompletableDeferred<Unit>()
        val vm = ScreeningViewModel(app(), FakeApiService { gate.await(); sampleResponse() })
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
    fun `uploadFile deletes the temp file even when the request fails`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException("boom") })
        val file = newFile()

        vm.uploadFile(file)
        awaitTerminalState(vm)
        awaitFileDeleted(file)
    }

    @Test
    fun `uploadFile maps UnknownHostException to the no-connection message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw UnknownHostException("no dns") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_no_connection), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps SocketTimeoutException to the timeout message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw SocketTimeoutException("timed out") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_timeout), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile maps UnknownServiceException to the https-required message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw UnknownServiceException("cleartext blocked") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_https_required), (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the raw exception message for unmapped errors`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException("backend exploded") })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals("backend exploded", (state as UiState.Error).message)
    }

    @Test
    fun `uploadFile falls back to the unknown-error message when the exception has no message`() {
        val vm = ScreeningViewModel(app(), FakeApiService { throw IllegalStateException() })

        vm.uploadFile(newFile())
        val state = awaitTerminalState(vm)

        assertTrue(state is UiState.Error)
        assertEquals(app().getString(R.string.error_unknown), (state as UiState.Error).message)
    }

    @Test
    fun `reset returns to Idle and clears local heuristic and symmetry`() {
        val vm = ScreeningViewModel(app(), FakeApiService { sampleResponse() })
        vm.uploadFile(newFile())
        awaitTerminalState(vm)

        vm.reset()

        assertEquals(UiState.Idle, vm.uiState.value)
        assertNull(vm.localHeuristic.value)
        assertNull(vm.symmetry.value)
    }
}
