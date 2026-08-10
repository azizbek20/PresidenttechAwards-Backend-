package com.eyedetect.ai.eyecare

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.eyedetect.ai.MainActivity
import com.eyedetect.ai.R
import com.eyedetect.ai.data.eyecare.PomodoroPhase

/** 20-20-20 va Pomodoro eslatmalari uchun umumiy bildirishnoma kanali va tuzilishi. */
object NotificationHelper {
    const val CHANNEL_ID = "eyecare_reminder_channel"
    private const val NOTIFICATION_ID = 1001
    private const val NOTIFICATION_ID_POMODORO = 1002

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                context.getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = context.getString(R.string.notification_channel_description)
            }
            context.getSystemService(NotificationManager::class.java)
                ?.createNotificationChannel(channel)
        }
    }

    fun showReminder(context: Context) {
        notify(context, NOTIFICATION_ID, context.getString(R.string.notification_title), context.getString(R.string.notification_text))
    }

    /** [endedPhase] — hozirgina tugagan bosqich; xabar keyingi bosqichga taklif sifatida yoziladi. */
    fun showPomodoroAlert(context: Context, endedPhase: PomodoroPhase) {
        val title = if (endedPhase == PomodoroPhase.FOCUS) {
            context.getString(R.string.notification_pomodoro_focus_done_title)
        } else {
            context.getString(R.string.notification_pomodoro_break_done_title)
        }
        val text = if (endedPhase == PomodoroPhase.FOCUS) {
            context.getString(R.string.notification_pomodoro_focus_done_text)
        } else {
            context.getString(R.string.notification_pomodoro_break_done_text)
        }
        notify(context, NOTIFICATION_ID_POMODORO, title, text)
    }

    private fun notify(context: Context, notificationId: Int, title: String, text: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }

        val intent = Intent(context, MainActivity::class.java).apply {
            putExtra(MainActivity.EXTRA_OPEN_EYECARE, true)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context, 0, intent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle(title)
            .setContentText(text)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        NotificationManagerCompat.from(context).notify(notificationId, notification)
    }
}
