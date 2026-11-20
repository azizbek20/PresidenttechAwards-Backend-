package com.eyedetect.ai

import android.content.Context
import com.eyedetect.ai.data.PredictTimeoutException
import io.ktor.client.plugins.HttpRequestTimeoutException
import io.ktor.client.plugins.ResponseException
import io.ktor.client.statement.bodyAsText
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * Tarmoq/server xatosini foydalanuvchiga ko'rsatiladigan matnga aylantiradi. Backend
 * `detail` maydoni (o'zbekcha, foydalanuvchi uchun yozilgan) bo'lsa, o'shani qaytaradi.
 * Skrining va boshqa tahlillar oqimi ikkalasi shu funksiyani ishlatadi.
 */
internal suspend fun friendlyErrorMessage(context: Context, e: Exception): String = when (e) {
    is java.net.UnknownHostException,
    is java.net.ConnectException ->
        context.getString(R.string.error_no_connection)
    is java.net.SocketTimeoutException,
    is HttpRequestTimeoutException,
    is PredictTimeoutException ->
        context.getString(R.string.error_timeout)
    is java.net.UnknownServiceException ->
        context.getString(R.string.error_https_required)
    is ResponseException -> httpErrorMessage(context, e)
    else -> e.message ?: context.getString(R.string.error_unknown)
}

private suspend fun httpErrorMessage(context: Context, e: ResponseException): String {
    val detail = runCatching {
        val body = e.response.bodyAsText()
        Json.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.content?.ifBlank { null }
    }.getOrNull()
    if (!detail.isNullOrBlank()) return detail

    val code = e.response.status.value
    return when (code) {
        400, 422 -> context.getString(R.string.error_bad_request)
        401, 403 -> context.getString(R.string.error_unauthorized)
        404 -> context.getString(R.string.error_not_found)
        429 -> context.getString(R.string.error_too_many_requests)
        in 500..599 -> context.getString(R.string.error_server)
        else -> context.getString(R.string.error_http_generic, code)
    }
}
