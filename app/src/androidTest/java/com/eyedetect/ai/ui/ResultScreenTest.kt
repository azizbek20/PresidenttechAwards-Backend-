package com.eyedetect.ai.ui

import androidx.activity.ComponentActivity
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import com.eyedetect.ai.UiState
import com.eyedetect.ai.data.PredictResponse
import com.eyedetect.ai.ui.theme.EyeDetectTheme
import org.junit.Rule
import org.junit.Test

/** Backend natijasi kelgach `ResultScreen` kutilgan qaror/ICDR matnini ko'rsatishini
 * sinaydi — kamera/tarmoqni chetlab o'tib, to'g'ridan-to'g'ri holat beriladi. */
class ResultScreenTest {

    @get:Rule
    val composeRule = createAndroidComposeRule<ComponentActivity>()

    private val sampleResult = PredictResponse(
        examId = "exam-1",
        patientId = "P-0001",
        eye = "right",
        referable = true,
        probability = 0.87,
        icdrGrade = 3,
        gradeLabel = "Severe NPDR",
        decision = "REFER",
        decisionText = "Mutaxassisga yuboring",
        quality = "GOOD",
        heatmapUrl = null,
        imageUrl = null,
        modelVersion = "v1",
        processedAt = "2026-08-09T10:00:00Z",
        disclaimer = "Bu tashxis emas",
    )

    @Test
    fun successStateShowsDecisionAndGrade() {
        composeRule.setContent {
            EyeDetectTheme {
                ResultScreen(
                    uiState = UiState.Success(sampleResult),
                    localHeuristic = null,
                    symmetry = null,
                    onRetry = {},
                    onNewPatient = {},
                )
            }
        }

        composeRule.onNodeWithText(sampleResult.decisionText).assertExists()
        composeRule.onNodeWithText(sampleResult.gradeLabel, substring = true).assertExists()
    }

    @Test
    fun errorStateShowsMessage() {
        composeRule.setContent {
            EyeDetectTheme {
                ResultScreen(
                    uiState = UiState.Error("Serverga ulanib bo'lmadi"),
                    localHeuristic = null,
                    symmetry = null,
                    onRetry = {},
                    onNewPatient = {},
                )
            }
        }

        composeRule.onNodeWithText("Serverga ulanib bo'lmadi").assertExists()
    }
}
