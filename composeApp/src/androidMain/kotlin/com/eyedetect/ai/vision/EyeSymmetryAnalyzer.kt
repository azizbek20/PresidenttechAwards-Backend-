package com.eyedetect.ai.vision

import com.eyedetect.ai.ui.components.QualityLevel
import kotlin.math.abs

/** Bitta ko'zning solishtirish uchun ishlatiladigan xulosaviy CV ko'rsatkichlari. */
data class EyeSymmetrySample(
    val opacity: QualityLevel,
    val redReflex: QualityLevel,
    val hueDeg: Float,
    val saturation: Float,
    val value: Float,
)

data class EyeSymmetryResult(
    val level: QualityLevel,
    val hueDiffDeg: Float,
    val opacityMismatch: Boolean,
    val redReflexMismatch: Boolean,
)

/**
 * Ikki ko'zning [PupilHeuristics] natijalarini solishtiradi — klinikadagi "Bruckner testi"
 * g'oyasiga o'xshash: ikkala ko'z qizil refleksi/rangi bir-biriga qanchalik o'xshash bo'lishi
 * kerak, va sezilarli assimmetriya (bir ko'z normal, ikkinchisi emas) har ikkala ko'z alohida
 * "normal" chegarada bo'lsa ham, o'zi alohida ogohlantiruvchi belgi hisoblanadi.
 *
 * KLASSIK EVRISTIKA — trenirovka qilingan model emas, tashxis emas.
 */
object EyeSymmetryAnalyzer {

    fun compare(current: EyeSymmetrySample, other: EyeSymmetrySample): EyeSymmetryResult {
        val opacityMismatch = current.opacity != other.opacity
        val redReflexMismatch = current.redReflex != other.redReflex
        val hueDiff = circularHueDiff(current.hueDeg, other.hueDeg)

        // Bir ko'z BAD, ikkinchisi emas — bu eng sezilarli assimetriya turi.
        val severeMismatch = (current.opacity == QualityLevel.BAD) != (other.opacity == QualityLevel.BAD) ||
            (current.redReflex == QualityLevel.BAD) != (other.redReflex == QualityLevel.BAD)

        val level = when {
            severeMismatch || hueDiff > 40f -> QualityLevel.BAD
            opacityMismatch || redReflexMismatch || hueDiff > 18f -> QualityLevel.WARN
            else -> QualityLevel.GOOD
        }
        return EyeSymmetryResult(level, hueDiff, opacityMismatch, redReflexMismatch)
    }

    /** Rang doirasidagi eng qisqa masofa (masalan, 355° va 5° orasidagi farq 10°, 350° emas). */
    private fun circularHueDiff(a: Float, b: Float): Float {
        val diff = abs(a - b) % 360f
        return if (diff > 180f) 360f - diff else diff
    }
}
