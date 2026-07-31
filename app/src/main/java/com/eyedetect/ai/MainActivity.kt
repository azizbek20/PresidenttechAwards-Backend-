package com.eyedetect.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.ui.CameraScreen
import com.eyedetect.ai.ui.PatientScreen
import com.eyedetect.ai.ui.ResultScreen
import com.eyedetect.ai.ui.theme.EyeDetectTheme

/** Ilova ichidagi 3 ekran (reja 2.1): Bemor -> Kamera -> Natija. */
enum class Screen { Patient, Camera, Result }

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            EyeDetectTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) { AppRoot() }
            }
        }
    }
}

@Composable
fun AppRoot(vm: ScreeningViewModel = viewModel()) {
    // Oddiy, kutubxonasiz navigatsiya (demo skelet uchun yetarli).
    var screen by remember { mutableStateOf(Screen.Patient) }
    val uiState by vm.uiState.collectAsState()

    when (screen) {
        Screen.Patient -> PatientScreen(
            vm = vm,
            onNext = { screen = Screen.Camera },
        )
        Screen.Camera -> CameraScreen(
            vm = vm,
            onResult = { screen = Screen.Result },
            onBack = { screen = Screen.Patient },
        )
        Screen.Result -> ResultScreen(
            uiState = uiState,
            onRetry = {
                vm.reset()
                screen = Screen.Camera
            },
            onNewPatient = {
                vm.reset()
                screen = Screen.Patient
            },
        )
    }
}
