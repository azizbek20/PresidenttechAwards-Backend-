package com.eyedetect.ai.data.upload

import androidx.room.Entity
import androidx.room.PrimaryKey

/**
 * Internet yo'q paytda yuborilmay qolgan rasmning navbatga qo'yilgan nusxasi (Room). [filePath]
 * — doimiy saqlash joyidagi (`filesDir/pending_uploads/`, cacheDir emas — jarayon o'chib
 * qayta tiklanishida ham saqlanib qolishi kerak) fayl, [UploadWorker][com.eyedetect.ai.upload.UploadWorker]
 * ulanish tiklangach shu faylni o'qib yuboradi.
 *
 * [fallbackMediaType] — yuklashdan oldingi siqish (`BitmapLoader.compressForUpload`) muvaffaqiyatsiz
 * bo'lsa ishlatiladigan asl MIME turi (`ScreeningViewModel`dagi kabi: kameradan "image/jpeg",
 * galereyadan umumiy "image" MIME turkumi).
 *
 * [failed] — bir necha marta qayta urinishdan keyin ham doimiy xato (masalan 4xx) bilan
 * yakunlangan urinish; bunday yozuv avtomatik o'chirilmaydi, foydalanuvchi
 * [com.eyedetect.ai.ui.HistoryScreen]dan qo'lda qayta urinishi yoki bekor qilishi mumkin.
 */
@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val filePath: String,
    val patientId: String?,
    val eye: String,
    val fallbackMediaType: String,
    val queuedAtMs: Long = System.currentTimeMillis(),
    val failed: Boolean = false,
)
