package com.eyedetect.ai.eyecare

import androidx.test.core.app.ApplicationProvider
import androidx.work.Configuration
import androidx.work.testing.SynchronousExecutor
import androidx.work.testing.TestListenableWorkerBuilder
import androidx.work.testing.WorkManagerTestInitHelper
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import com.eyedetect.ai.data.eyecare.PomodoroPhase
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * `PomodoroWorker`/`ReminderWorker` had zero tests despite depending only on
 * `EyeCarePreferencesRepository` (DataStore) — unlike `UploadWorker`, they
 * never touch the SQLCipher-encrypted Room database, so they need no fake
 * seam to run under Robolectric.
 */
@RunWith(RobolectricTestRunner::class)
class PomodoroWorkerTest {

    private val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    @Before
    fun setUp() {
        val config = Configuration.Builder()
            .setExecutor(SynchronousExecutor())
            .build()
        WorkManagerTestInitHelper.initializeTestWorkManager(context, config)
    }

    @Test
    fun `doWork is a no-op when the timer was already stopped`() = runBlocking {
        val repo = EyeCarePreferencesRepository(context)
        repo.startPomodoroPhase(PomodoroPhase.FOCUS, System.currentTimeMillis() + 60_000)
        repo.stopPomodoro()

        val worker = TestListenableWorkerBuilder<PomodoroWorker>(context).build()
        val result = worker.doWork()

        assertEquals(androidx.work.ListenableWorker.Result.success(), result)
        assertEquals(PomodoroPhase.FOCUS, repo.pomodoroSnapshot().phase)
    }

    @Test
    fun `doWork advances FOCUS to BREAK and reschedules`() = runBlocking {
        val repo = EyeCarePreferencesRepository(context)
        repo.setPomodoroMinutes(focusMinutes = 25, breakMinutes = 5)
        repo.startPomodoroPhase(PomodoroPhase.FOCUS, System.currentTimeMillis() + 60_000)

        val worker = TestListenableWorkerBuilder<PomodoroWorker>(context).build()
        val result = worker.doWork()

        assertEquals(androidx.work.ListenableWorker.Result.success(), result)
        val state = repo.pomodoroSnapshot()
        assertTrue("still running after the phase flips", state.running)
        assertEquals(PomodoroPhase.BREAK, state.phase)
    }

    @Test
    fun `doWork advances BREAK back to FOCUS`() = runBlocking {
        val repo = EyeCarePreferencesRepository(context)
        repo.setPomodoroMinutes(focusMinutes = 25, breakMinutes = 5)
        repo.startPomodoroPhase(PomodoroPhase.BREAK, System.currentTimeMillis() + 60_000)

        val worker = TestListenableWorkerBuilder<PomodoroWorker>(context).build()
        worker.doWork()

        assertEquals(PomodoroPhase.FOCUS, repo.pomodoroSnapshot().phase)
    }
}
