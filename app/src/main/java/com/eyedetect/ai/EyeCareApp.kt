package com.eyedetect.ai

import android.app.Application
import android.content.Context
import com.eyedetect.ai.eyecare.NotificationHelper

/**
 * Ilova darajasidagi kirish nuqtasi — ko'z mashqlari bildirishnoma kanalini o'rnatadi.
 * attachBaseContext orqali tanlangan til fon jarayonlariga (Worker/Notification) ham tarqaladi.
 */
class EyeCareApp : Application() {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(LocalePrefs.wrap(base))
    }

    override fun onCreate() {
        super.onCreate()
        NotificationHelper.ensureChannel(this)
    }
}
