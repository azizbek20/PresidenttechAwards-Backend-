package com.eyedetect.ai.vision

import com.eyedetect.ai.ui.components.QualityLevel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class EyeSymmetryAnalyzerTest {

    private fun sample(
        opacity: QualityLevel = QualityLevel.GOOD,
        redReflex: QualityLevel = QualityLevel.GOOD,
        hueDeg: Float = 10f,
        saturation: Float = 0.5f,
        value: Float = 0.5f,
    ) = EyeSymmetrySample(opacity, redReflex, hueDeg, saturation, value)

    @Test
    fun `identical samples are GOOD with zero hue diff`() {
        val a = sample(hueDeg = 12f)
        val b = sample(hueDeg = 12f)

        val result = EyeSymmetryAnalyzer.compare(a, b)

        assertEquals(QualityLevel.GOOD, result.level)
        assertEquals(0f, result.hueDiffDeg)
        assertFalse(result.opacityMismatch)
        assertFalse(result.redReflexMismatch)
    }

    @Test
    fun `one eye BAD and the other not is a severe mismatch`() {
        val current = sample(opacity = QualityLevel.BAD, hueDeg = 10f)
        val other = sample(opacity = QualityLevel.GOOD, hueDeg = 10f)

        val result = EyeSymmetryAnalyzer.compare(current, other)

        assertEquals(QualityLevel.BAD, result.level)
        assertTrue(result.opacityMismatch)
    }

    @Test
    fun `WARN grade opacity mismatch that is not BAD vs GOOD stays WARN`() {
        val current = sample(opacity = QualityLevel.WARN, hueDeg = 10f)
        val other = sample(opacity = QualityLevel.GOOD, hueDeg = 10f)

        val result = EyeSymmetryAnalyzer.compare(current, other)

        assertEquals(QualityLevel.WARN, result.level)
        assertTrue(result.opacityMismatch)
    }

    @Test
    fun `large hue difference alone escalates to BAD`() {
        val current = sample(hueDeg = 0f)
        val other = sample(hueDeg = 45f)

        val result = EyeSymmetryAnalyzer.compare(current, other)

        assertEquals(QualityLevel.BAD, result.level)
        assertEquals(45f, result.hueDiffDeg)
    }

    @Test
    fun `moderate hue difference escalates to WARN not BAD`() {
        val current = sample(hueDeg = 0f)
        val other = sample(hueDeg = 20f)

        val result = EyeSymmetryAnalyzer.compare(current, other)

        assertEquals(QualityLevel.WARN, result.level)
        assertEquals(20f, result.hueDiffDeg)
    }

    @Test
    fun `hue difference wraps around the 360 degree circle`() {
        val current = sample(hueDeg = 355f)
        val other = sample(hueDeg = 5f)

        val result = EyeSymmetryAnalyzer.compare(current, other)

        // 355 -> 5 is a 10 degree gap the short way round, not 350.
        assertEquals(10f, result.hueDiffDeg)
        assertEquals(QualityLevel.GOOD, result.level)
    }
}
