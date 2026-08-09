package com.eyedetect.ai.data

import com.eyedetect.ai.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Retrofit klienti. baseUrl = BuildConfig.API_BASE_URL
 * (`local.properties` ichidagi `API_BASE_URL` orqali sozlanadi — git'ga
 * kirmaydi; standart qiymat emulyator uchun `app/build.gradle.kts`da).
 */
object ApiClient {

    val baseUrl: String get() = BuildConfig.API_BASE_URL

    private val authInterceptor = Interceptor { chain ->
        val request = chain.request().newBuilder()
            .addHeader("X-API-Key", BuildConfig.API_KEY)
            .build()
        chain.proceed(request)
    }

    private val logging = HttpLoggingInterceptor().apply {
        redactHeader("X-API-Key")
        level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                else HttpLoggingInterceptor.Level.BASIC
    }

    private val okHttp = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
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

    // Asosiy `okHttp`dan alohida, qisqa muddatli klient — StatusBadge uchun tezkor
    // ulanish tekshiruvi asosiy so'rovlarning (30s) uzoq timeoutini kutmasligi kerak.
    private val pingClient = okHttp.newBuilder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    /** Backend manziliga yengil HEAD so'rovi yuboradi — istalgan HTTP javob (xato kodi
     * bo'lsa ham) server tarmoqda borligini bildiradi; istisno esa yo'qligini. */
    suspend fun ping(): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            pingClient.newCall(Request.Builder().url(baseUrl).head().build()).execute().use { true }
        }.getOrDefault(false)
    }

    /** Nisbiy URL (masalan "/static/...") ni to'liq URL'ga aylantiradi. */
    fun absoluteUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http")) return path
        return baseUrl.trimEnd('/') + path
    }
}
