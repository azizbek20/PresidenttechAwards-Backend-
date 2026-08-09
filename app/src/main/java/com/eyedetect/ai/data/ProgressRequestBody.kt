package com.eyedetect.ai.data

import okhttp3.MediaType
import okhttp3.RequestBody
import okio.Buffer
import okio.BufferedSink
import okio.ForwardingSink
import okio.buffer

/**
 * [delegate]ni o'raydi va yozilgan baytlar ulushini (0f..1f) [onProgress]ga xabar beradi.
 * Multipart fayl yuklashda foydalanuvchiga haqiqiy yuklash progressini ko'rsatish uchun
 * (`LoadingState`dagi qadam-indikator avval qattiq kodlangan edi — reja 3-bo'lim).
 */
class ProgressRequestBody(
    private val delegate: RequestBody,
    private val onProgress: (fraction: Float) -> Unit,
) : RequestBody() {

    override fun contentType(): MediaType? = delegate.contentType()
    override fun contentLength(): Long = delegate.contentLength()

    override fun writeTo(sink: BufferedSink) {
        val total = contentLength()
        var written = 0L
        val countingSink = object : ForwardingSink(sink) {
            override fun write(source: Buffer, byteCount: Long) {
                super.write(source, byteCount)
                written += byteCount
                if (total > 0) onProgress((written.toFloat() / total).coerceIn(0f, 1f))
            }
        }
        // Diqqat: bufferni yopmaymiz (`.use`/`close()` emas) — multipart so'rovda bir nechta
        // qism bitta umumiy sink orqali ketma-ket yoziladi; buni yopish OkHttp'ning qolgan
        // qismlarni yozishiga xalaqit beradi. Faqat flush qilamiz.
        val bufferedSink = countingSink.buffer()
        delegate.writeTo(bufferedSink)
        bufferedSink.flush()
    }
}
