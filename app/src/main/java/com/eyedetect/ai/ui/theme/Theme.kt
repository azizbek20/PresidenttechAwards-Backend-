package com.eyedetect.ai.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

/**
 * EYE DETECT AI mavzusi (6-hujjat, 9-bo'lim).
 *
 * - Dynamic color (Material You) O'CHIRILGAN: brend/svetofor ranglari doimiy
 *   va bashoratli bo'lishi kerak (klinik ilova).
 * - Qorong'i rejim qo'llab-quvvatlanadi (poliklinika xira yorug'ligi uchun).
 */
private val LightColors = lightColorScheme(
    primary = Primary,
    onPrimary = OnPrimary,
    primaryContainer = PrimaryContainer,
    onPrimaryContainer = OnPrimaryContainer,
    surface = SurfaceLight,
    onSurface = OnSurfaceLight,
    surfaceVariant = SurfaceVariantLight,
    onSurfaceVariant = OnSurfaceVarLight,
    background = SurfaceLight,
    onBackground = OnSurfaceLight,
    outline = OutlineLight,
    outlineVariant = OutlineVarLight,
    error = ErrorLight,
)

private val DarkColors = darkColorScheme(
    primary = PrimaryDark,
    onPrimary = OnPrimaryDark,
    primaryContainer = PrimaryContainerDark,
    onPrimaryContainer = PrimaryContainer,
    surface = SurfaceDark,
    onSurface = OnSurfaceDark,
    surfaceVariant = SurfaceVariantDark,
    onSurfaceVariant = OnSurfaceVarDark,
    background = SurfaceDark,
    onBackground = OnSurfaceDark,
    outline = OutlineDark,
    outlineVariant = OutlineDark,
    error = ErrorDark,
)

@Composable
fun EyeDetectTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = AppTypography,
        content = content,
    )
}
