package com.eyedetect.ai.vision

import android.graphics.Bitmap
import com.eyedetect.ai.ui.components.QualityLevel
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.GraphicsMode

/**
 * `classifyOpacity`/`classifyRedReflex`/`squareRect` are pure math with no
 * MediaPipe/ML Kit dependency — unlike `analyze()`/`findEyeRegion()`, which
 * need a running IrisLandmarker/FaceDetection pipeline, these were left
 * `private` and untested despite being directly testable (opened up to
 * `internal` + `@VisibleForTesting` for this file).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class PupilHeuristicsTest {

    // ------------------------------------------------------------------
    // classifyOpacity: whiteness = value * (1 - saturation)
    // ------------------------------------------------------------------
    @Test
    fun `classifyOpacity is GOOD for a dark saturated pupil`() {
        assertEquals(QualityLevel.GOOD, PupilHeuristics.classifyOpacity(value = 0f, saturation = 1f))
    }

    @Test
    fun `classifyOpacity is BAD for a bright unsaturated (white) pupil`() {
        assertEquals(QualityLevel.BAD, PupilHeuristics.classifyOpacity(value = 1f, saturation = 0f))
    }

    @Test
    fun `classifyOpacity whiteness just under 0_18 is GOOD`() {
        assertEquals(QualityLevel.GOOD, PupilHeuristics.classifyOpacity(value = 0.17f, saturation = 0f))
    }

    @Test
    fun `classifyOpacity whiteness at exactly 0_18 is WARN, not GOOD`() {
        assertEquals(QualityLevel.WARN, PupilHeuristics.classifyOpacity(value = 0.18f, saturation = 0f))
    }

    @Test
    fun `classifyOpacity whiteness at exactly 0_35 is BAD, not WARN`() {
        assertEquals(QualityLevel.BAD, PupilHeuristics.classifyOpacity(value = 0.35f, saturation = 0f))
    }

    @Test
    fun `classifyOpacity whiteness just under 0_35 is WARN`() {
        assertEquals(QualityLevel.WARN, PupilHeuristics.classifyOpacity(value = 0.34f, saturation = 0f))
    }

    // ------------------------------------------------------------------
    // classifyRedReflex
    // ------------------------------------------------------------------
    @Test
    fun `classifyRedReflex is WARN when too dark to judge, regardless of hue`() {
        assertEquals(
            QualityLevel.WARN,
            PupilHeuristics.classifyRedReflex(hueDeg = 10f, saturation = 0.9f, value = 0.11f),
        )
    }

    @Test
    fun `classifyRedReflex dark-value check wins even over a reddish healthy-looking sample`() {
        // Would be GOOD by the reddish+saturated rule alone, but value < 0.12 short-circuits first.
        assertEquals(
            QualityLevel.WARN,
            PupilHeuristics.classifyRedReflex(hueDeg = 5f, saturation = 0.5f, value = 0.05f),
        )
    }

    @Test
    fun `classifyRedReflex is GOOD for a reddish, saturated reflex (low hue end)`() {
        assertEquals(
            QualityLevel.GOOD,
            PupilHeuristics.classifyRedReflex(hueDeg = 10f, saturation = 0.3f, value = 0.5f),
        )
    }

    @Test
    fun `classifyRedReflex is GOOD for a reddish, saturated reflex (high hue end)`() {
        assertEquals(
            QualityLevel.GOOD,
            PupilHeuristics.classifyRedReflex(hueDeg = 340f, saturation = 0.3f, value = 0.5f),
        )
    }

    @Test
    fun `classifyRedReflex hue boundary at 25deg is still reddish`() {
        assertEquals(
            QualityLevel.GOOD,
            PupilHeuristics.classifyRedReflex(hueDeg = 25f, saturation = 0.3f, value = 0.5f),
        )
    }

    @Test
    fun `classifyRedReflex hue just past 25deg is no longer reddish`() {
        assertEquals(
            QualityLevel.WARN,
            PupilHeuristics.classifyRedReflex(hueDeg = 26f, saturation = 0.3f, value = 0.5f),
        )
    }

    @Test
    fun `classifyRedReflex is BAD for an unsaturated bright (leukocoria-like) reflex`() {
        assertEquals(
            QualityLevel.BAD,
            PupilHeuristics.classifyRedReflex(hueDeg = 90f, saturation = 0.1f, value = 0.5f),
        )
    }

    @Test
    fun `classifyRedReflex falls back to WARN for an ambiguous non-reddish sample`() {
        assertEquals(
            QualityLevel.WARN,
            PupilHeuristics.classifyRedReflex(hueDeg = 90f, saturation = 0.2f, value = 0.5f),
        )
    }

    // ------------------------------------------------------------------
    // squareRect
    // ------------------------------------------------------------------
    @Test
    fun `squareRect centers a square of the given radius`() {
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        val rect = PupilHeuristics.squareRect(bitmap, cx = 50f, cy = 50f, radius = 10f)
        assertEquals(40, rect.left)
        assertEquals(40, rect.top)
        assertEquals(60, rect.right)
        assertEquals(60, rect.bottom)
    }

    @Test
    fun `squareRect clamps to the bitmap bounds near the top-left corner`() {
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        val rect = PupilHeuristics.squareRect(bitmap, cx = 5f, cy = 5f, radius = 10f)
        assertEquals(0, rect.left)
        assertEquals(0, rect.top)
        assertEquals(15, rect.right)
        assertEquals(15, rect.bottom)
    }

    @Test
    fun `squareRect clamps to the bitmap bounds near the bottom-right corner`() {
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        val rect = PupilHeuristics.squareRect(bitmap, cx = 95f, cy = 95f, radius = 10f)
        assertEquals(85, rect.left)
        assertEquals(85, rect.top)
        assertEquals(100, rect.right)
        assertEquals(100, rect.bottom)
    }

    @Test
    fun `squareRect never collapses to a zero-size rect even with radius 0`() {
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        val rect = PupilHeuristics.squareRect(bitmap, cx = 50f, cy = 50f, radius = 0f)
        assertEquals(true, rect.width() >= 1)
        assertEquals(true, rect.height() >= 1)
    }
}
