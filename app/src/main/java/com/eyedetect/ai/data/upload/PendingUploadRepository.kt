package com.eyedetect.ai.data.upload

import android.content.Context
import com.eyedetect.ai.data.history.ScreeningHistoryDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import java.io.File

/** [PendingUploadRepository]dan `ScreeningViewModel`ga kerak bo'lgan qismi — testlarda
 * SQLCipher'ning native kutubxonasisiz (Robolectric/JVM) soxta implementatsiya bilan
 * almashtirish uchun, [com.eyedetect.ai.data.history.ScreeningHistoryStore] bilan bir xil sabab. */
interface PendingUploadStore {
    suspend fun enqueue(bytes: ByteArray, patientId: String?, eye: String, fallbackMediaType: String): Long
}

/** Internet yo'q paytda navbatga qo'yilgan rasmlar uchun Room ombori — [ScreeningHistoryRepository]
 * kabi to'g'ridan-to'g'ri (DI'siz) instansiyalanadi, xuddi shu Room bazasidan ([ScreeningHistoryDatabase]). */
class PendingUploadRepository(private val context: Context) : PendingUploadStore {

    private val appContext = context.applicationContext
    private val dao = ScreeningHistoryDatabase.getInstance(appContext).pendingUploadDao()

    private val pendingDir: File
        get() = File(appContext.filesDir, "pending_uploads").apply { mkdirs() }

    val pending: Flow<List<PendingUploadEntity>> = dao.observeAll()

    /** Baytlarni doimiy saqlash joyiga (cacheDir emas — jarayon o'chib qayta tiklanishida
     * ham saqlanib qolishi kerak) yozadi va navbat yozuvini yaratadi.
     * @return yaratilgan yozuv ID'si — [UploadScheduler.enqueue][com.eyedetect.ai.upload.UploadScheduler.enqueue]
     * shu ID bilan chaqirilishi kerak.
     */
    override suspend fun enqueue(bytes: ByteArray, patientId: String?, eye: String, fallbackMediaType: String): Long =
        withContext(Dispatchers.IO) {
            val file = File(pendingDir, "pending_${System.currentTimeMillis()}_${(0..9999).random()}.jpg")
            file.writeBytes(bytes)
            dao.insert(
                PendingUploadEntity(
                    filePath = file.absolutePath,
                    patientId = patientId,
                    eye = eye,
                    fallbackMediaType = fallbackMediaType,
                )
            )
        }

    suspend fun get(id: Long): PendingUploadEntity? = dao.getById(id)

    suspend fun markFailed(id: Long) = dao.markFailed(id)

    suspend fun resetFailed(id: Long) = dao.resetFailed(id)

    /** Yozuvni ham, unga tegishli faylni ham o'chiradi — muvaffaqiyatli yuklangandan keyin
     * yoki foydalanuvchi navbatdan bekor qilganda chaqiriladi. */
    suspend fun delete(entry: PendingUploadEntity) = withContext(Dispatchers.IO) {
        runCatching { File(entry.filePath).delete() }
        dao.delete(entry)
    }
}
