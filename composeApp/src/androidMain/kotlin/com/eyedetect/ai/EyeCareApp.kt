package com.eyedetect.ai

import android.app.Application
import android.content.Context
import com.eyedetect.ai.eyecare.NotificationHelper

import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache

/**
 * Ilova darajasidagi kirish nuqtasi — ko'z mashqlari bildirishnoma kanalini o'rnatadi.
 * attachBaseContext orqali tanlangan til fon jarayonlariga (Worker/Notification) ham tarqaladi.
 */
class EyeCareApp : Application(), ImageLoaderFactory {
    override fun attachBaseContext(base: Context) {
        super.attachBaseContext(LocalePrefs.wrap(base))
    }

    override fun onCreate() {
        super.onCreate()
        NotificationHelper.ensureChannel(this)
    }

    override fun newImageLoader(): ImageLoader {
        return ImageLoader.Builder(this)
            .memoryCache {
                MemoryCache.Builder(this)
                    .maxSizePercent(0.25)
                    .build()
            }
            .diskCache {
                DiskCache.Builder()
                    .directory(cacheDir.resolve("image_cache"))
                    .maxSizePercent(0.02)
                    .build()
            }
            .crossfade(true)
            .build()
    }
}
