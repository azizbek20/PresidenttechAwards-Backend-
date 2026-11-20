package com.eyedetect.ai.vision

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.GraphicsMode
import java.io.ByteArrayOutputStream

@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class BitmapLoaderTest {

    @Test
    fun `compressForUpload returns null for bytes that are not a decodable image`() {
        val result = BitmapLoader.compressForUpload("not-a-real-image".toByteArray())
        assertNull(result)
    }

    @Test
    fun `compressForUpload shrinks a large image to at most maxDim on the long side`() {
        val original = Bitmap.createBitmap(3000, 2000, Bitmap.Config.ARGB_8888)
        val inputBytes = ByteArrayOutputStream().use { out ->
            original.compress(Bitmap.CompressFormat.PNG, 100, out)
            out.toByteArray()
        }

        val compressed = BitmapLoader.compressForUpload(inputBytes, maxDim = 1500, quality = 85)

        assertTrue("compression should succeed for a valid PNG", compressed != null && compressed.isNotEmpty())
        val decoded = BitmapFactory.decodeByteArray(compressed, 0, compressed!!.size)
        assertTrue("compressed bytes should decode back to a bitmap", decoded != null)
        assertTrue(
            "long side should be capped at maxDim, was ${maxOf(decoded!!.width, decoded.height)}",
            maxOf(decoded!!.width, decoded.height) <= 1500,
        )
    }

    @Test
    fun `compressForUpload leaves a small image roughly as-is`() {
        val original = Bitmap.createBitmap(400, 300, Bitmap.Config.ARGB_8888)
        val inputBytes = ByteArrayOutputStream().use { out ->
            original.compress(Bitmap.CompressFormat.PNG, 100, out)
            out.toByteArray()
        }

        val compressed = BitmapLoader.compressForUpload(inputBytes, maxDim = 1500, quality = 85)

        assertTrue(compressed != null && compressed.isNotEmpty())
        val decoded = BitmapFactory.decodeByteArray(compressed, 0, compressed!!.size)
        assertTrue(decoded!!.width == 400 && decoded.height == 300)
    }
}
