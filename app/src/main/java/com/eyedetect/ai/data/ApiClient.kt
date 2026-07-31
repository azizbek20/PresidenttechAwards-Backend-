package com.eyedetect.ai.data

import com.eyedetect.ai.BuildConfig
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Retrofit klienti. baseUrl = BuildConfig.API_BASE_URL
 * (app/build.gradle.kts ichida sozlanadi — o'sha yerni o'zgartiring).
 */
object ApiClient {

    val baseUrl: String get() = BuildConfig.API_BASE_URL

    private val logging = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val okHttp = OkHttpClient.Builder()
        .addInterceptor(logging)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)   // CPU inference 1-3s, ehtiyot uchun 30s
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    val service: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttp)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    /** Nisbiy URL (masalan "/static/...") ni to'liq URL'ga aylantiradi. */
    fun absoluteUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http")) return path
        return baseUrl.trimEnd('/') + path
    }
}
