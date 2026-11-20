package com.eyedetect.ai.eyecare

import android.app.Application
import android.app.NotificationManager
import androidx.test.core.app.ApplicationProvider
import androidx.work.testing.TestListenableWorkerBuilder
import com.eyedetect.ai.data.eyecare.EyeCarePreferencesRepository
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

private const val REMINDER_NOTIFICATION_ID = 1001

@RunWith(RobolectricTestRunner::class)
class ReminderWorkerTest {

    private val context = ApplicationProvider.getApplicationContext<Application>()

    init {
        // `notify()` (NotificationHelper.kt) no-ops on API 33+ without POST_NOTIFICATIONS —
        // Robolectric does not auto-grant runtime permissions just because they are
        // declared in the manifest, unlike some install-time permissions.
        shadowOf(context).grantPermissions(android.Manifest.permission.POST_NOTIFICATIONS)
    }

    private fun postedReminder() =
        shadowOf(context.getSystemService(NotificationManager::class.java))
            .getNotification(REMINDER_NOTIFICATION_ID)

    @Test
    fun `doWork shows no reminder when reminders are disabled`() = runBlocking {
        val repo = EyeCarePreferencesRepository(context)
        repo.setReminderEnabled(false)

        val worker = TestListenableWorkerBuilder<ReminderWorker>(context).build()
        val result = worker.doWork()

        assertEquals(androidx.work.ListenableWorker.Result.success(), result)
        assertNull("no notification should be posted while disabled", postedReminder())
    }

    @Test
    fun `doWork shows the reminder when enabled and quiet hours are off`() = runBlocking {
        val repo = EyeCarePreferencesRepository(context)
        repo.setReminderEnabled(true)
        repo.setQuietHours(enabled = false, startHour = 22, endHour = 7)

        val worker = TestListenableWorkerBuilder<ReminderWorker>(context).build()
        val result = worker.doWork()

        assertEquals(androidx.work.ListenableWorker.Result.success(), result)
        assertNotNull("a reminder notification should be posted", postedReminder())
    }
}
