package com.eyedetect.ai.vision

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Olingan/tanlangan suratni mahalliy CV tahlili ([PupilHeuristics], [EyeDetectionAnalyzer])
 * uchun kichraytirib va EXIF burilishini to'g'rilab dekodlaydi. To'liq o'lchamdagi rasm
 * ML Kit yoki piksel tahlili uchun kerak emas — [maxDim] shu sababli chegaralanadi.
 */
object BitmapLoader {

    fun decodeFileScaled(path: String, maxDim: Int = 1024): Bitmap? =
        runCatching { File(path).readBytes() }.getOrNull()?.let { decodeBytesScaled(it, maxDim) }

    fun decodeBytesScaled(bytes: ByteArray, maxDim: Int = 1024): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

        var sample = 1
        while (bounds.outWidth / sample > maxDim * 2 || bounds.outHeight / sample > maxDim * 2) sample *= 2
        val opts = BitmapFactory.Options().apply { inSampleSize = sample }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, opts) ?: return null

        val orientation = runCatching {
            ExifInterface(ByteArrayInputStream(bytes))
                .getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        }.getOrDefault(ExifInterface.ORIENTATION_NORMAL)

        val degrees = when (orientation) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        if (degrees == 0f) return bitmap

        val matrix = Matrix().apply { postRotate(degrees) }
        val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        if (rotated !== bitmap) bitmap.recycle()
        return rotated
    }

    /**
     * Backendga yuborishdan oldin siqadi: uzun tomoni [maxDim]dan oshmaydigan qilib aniq
     * kichraytiradi (avval [decodeBytesScaled] bilan xotira tejovchi taxminiy namunalash,
     * so'ng [Bitmap.createScaledBitmap] bilan aniq o'lchamga moslash), keyin JPEG'ga
     * [quality] sifat bilan siqadi. Dekodlab bo'lmasa (buzilgan fayl) `null` qaytaradi —
     * chaqiruvchi asl baytlarni yuborishga tushishi kerak.
     */
    fun compressForUpload(bytes: ByteArray, maxDim: Int = 1500, quality: Int = 85): ByteArray? {
        val sampled = decodeBytesScaled(bytes, maxDim) ?: return null
        val longSide = maxOf(sampled.width, sampled.height)
        val bitmap = if (longSide > maxDim) {
            val scale = maxDim.toFloat() / longSide
            val w = (sampled.width * scale).toInt().coerceAtLeast(1)
            val h = (sampled.height * scale).toInt().coerceAtLeast(1)
            Bitmap.createScaledBitmap(sampled, w, h, true).also { if (it !== sampled) sampled.recycle() }
        } else sampled

        return try {
            ByteArrayOutputStream().use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, quality, out)
                out.toByteArray()
            }
        } finally {
            bitmap.recycle()
        }
    }
}
