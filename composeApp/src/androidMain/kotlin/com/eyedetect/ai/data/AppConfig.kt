package com.eyedetect.ai.data

import com.eyedetect.ai.BuildConfig

actual object AppConfig {
    actual val API_BASE_URL: String = BuildConfig.API_BASE_URL
    actual val API_KEY: String = BuildConfig.API_KEY
    actual val DEBUG: Boolean = BuildConfig.DEBUG
}
