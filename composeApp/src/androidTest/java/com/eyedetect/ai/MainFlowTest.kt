package com.eyedetect.ai

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.eyedetect.ai.ui.theme.EyeDetectTheme
import org.junit.Rule
import org.junit.Test

/**
 * Asosiy skrining oqimining navigatsiya qismini sinaydi: Bosh ekran -> "Skrining" ->
 * Bemor ID kiritish -> "Davom etish" -> Kamera ekrani. Haqiqiy kamera surati olish
 * qurilma/emulyator kamerasiga bog'liq bo'lgani uchun bu yerda sinalmaydi (CAMERA
 * ruxsati ataylab berilmagan — shu sababli Kamera ekrani ruxsat so'rash holatini
 * ko'rsatadi, bu ham "kamera ekraniga yetib kelindi"ni tasdiqlaydi).
 * Natija ko'rsatilishi alohida — [com.eyedetect.ai.ui.ResultScreenTest] da,
 * to'g'ridan-to'g'ri `ResultScreen`ni fake holat bilan tekshiradi.
 */
class MainFlowTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<ComponentActivity>()

    @Test
    fun patientEntryLeadsToCameraScreen() {
        composeRule.setContent {
            EyeDetectTheme { AppRoot() }
        }

        composeRule.onNodeWithText(composeRule.activity.getString(R.string.home_screening_title)).performClick()

        composeRule.onNodeWithText(composeRule.activity.getString(R.string.patient_id_placeholder))
            .performTextInput("P-0001")

        composeRule.onNodeWithText(composeRule.activity.getString(R.string.patient_continue)).performClick()

        // CAMERA ruxsati berilmagan -> kamera ekrani ruxsat so'rash matnini ko'rsatadi.
        composeRule.onNodeWithText(composeRule.activity.getString(R.string.camera_no_permission)).assertExists()
    }
}
