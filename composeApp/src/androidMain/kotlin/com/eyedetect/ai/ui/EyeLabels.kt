package com.eyedetect.ai.ui

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import com.eyedetect.ai.R
import com.eyedetect.ai.data.Eye

/** To'liq nom ("O'ng ko'z"/"Chap ko'z"); noma'lum qiymat uchun "—". */
@Composable
fun eyeLabel(raw: String?): String = when (Eye.from(raw)) {
    Eye.RIGHT -> stringResource(R.string.common_eye_right)
    Eye.LEFT -> stringResource(R.string.common_eye_left)
    null -> stringResource(R.string.common_dash)
}

/** [eyeLabel] ning @Composable bo'lmagan joylar (masalan ulashish matni) uchun versiyasi. */
fun eyeLabel(context: Context, raw: String?): String = when (Eye.from(raw)) {
    Eye.RIGHT -> context.getString(R.string.common_eye_right)
    Eye.LEFT -> context.getString(R.string.common_eye_left)
    null -> context.getString(R.string.common_dash)
}

/** Qisqa nom ("o'ng"/"chap"); noma'lum qiymat uchun xom qiymatning o'zi (u ham bo'lmasa "—"). */
@Composable
fun eyeShortLabel(raw: String?): String = when (Eye.from(raw)) {
    Eye.RIGHT -> stringResource(R.string.common_eye_right_short)
    Eye.LEFT -> stringResource(R.string.common_eye_left_short)
    null -> raw ?: stringResource(R.string.common_dash)
}
