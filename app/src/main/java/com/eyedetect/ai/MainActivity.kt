package com.eyedetect.ai

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.ui.CameraScreen
import com.eyedetect.ai.ui.HistoryScreen
import com.eyedetect.ai.ui.HomeScreen
import com.eyedetect.ai.ui.PatientScreen
import com.eyedetect.ai.ui.ResultScreen
import com.eyedetect.ai.ui.eyecare.BlinkPalmScreen
import com.eyedetect.ai.ui.eyecare.EyeCareMenuScreen
import com.eyedetect.ai.ui.eyecare.FocusShiftScreen
import com.eyedetect.ai.ui.eyecare.FollowDotScreen
import com.eyedetect.ai.ui.eyecare.ReminderSettingsScreen
import com.eyedetect.ai.ui.theme.EyeDetectTheme

/** Ilova ichidagi ekranlar (reja 2.1 + ko'z mashqlari bo'limi). */
enum class Screen {
    Home,
    Patient, Camera, Result,
    EyeCareMenu, ReminderSettings,
    FollowDot, FocusShift, BlinkPalm,
    History,
}

private val ScreenListSaver: Saver<SnapshotStateList<Screen>, List<String>> = Saver(
    save = { list -> list.map { it.name } },
    restore = { saved -> mutableStateListOf(*saved.map { Screen.valueOf(it) }.toTypedArray()) },
)

/** Ilova ishga tushganda cacheDir'da qolib ketgan eski fundus rasm fayllarini (masalan, oldingi
 * ilova to'satdan yopilishi qoldiqlari) tozalaydi. */
private fun cleanupStaleCaptures(context: Context) {
    context.cacheDir.listFiles { f -> f.name.startsWith("fundus_") && f.name.endsWith(".jpg") }
        ?.forEach { it.delete() }
}

class MainActivity : ComponentActivity() {
    companion object {
        /** Bildirishnoma tap qilinganda ko'z mashqlari bo'limiga to'g'ridan-to'g'ri o'tish uchun. */
        const val EXTRA_OPEN_EYECARE = "open_eyecare"
    }

    override fun attachBaseContext(newBase: Context) {
        super.attachBaseContext(LocalePrefs.wrap(newBase))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            cleanupStaleCaptures(applicationContext)
        }
        setContent {
            EyeDetectTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) { AppRoot() }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }
}

@Composable
fun AppRoot(vm: ScreeningViewModel = viewModel()) {
    val activity = LocalContext.current as? Activity
    val openEyeCareOnStart = activity?.intent?.getBooleanExtra(MainActivity.EXTRA_OPEN_EYECARE, false) ?: false

    val backStack = rememberSaveable(saver = ScreenListSaver) {
        mutableStateListOf(Screen.Home).apply {
            if (openEyeCareOnStart) add(Screen.EyeCareMenu)
        }
    }
    val current = backStack.last()

    val uiState by vm.uiState.collectAsState()
    val localHeuristic by vm.localHeuristic.collectAsState()
    val symmetry by vm.symmetry.collectAsState()
    val uploadProgress by vm.uploadProgress.collectAsState()

    fun push(s: Screen) { backStack.add(s) }
    // Natija ekranida so'rov hali ketayotgan bo'lsa (Loading), orqaga qaytishdan oldin
    // uni bekor qiladi — aks holda foydalanuvchi chiqib ketsa ham so'rov fonda davom etardi.
    fun pop(): Boolean {
        if (current == Screen.Result && uiState is UiState.Loading) vm.cancelUpload()
        return if (backStack.size > 1) { backStack.removeAt(backStack.lastIndex); true } else false
    }
    fun resetTo(vararg s: Screen) { backStack.clear(); backStack.addAll(s) }

    BackHandler(enabled = backStack.size > 1) { pop() }

    when (current) {
        Screen.Home -> HomeScreen(
            onScreening = { push(Screen.Patient) },
            onEyeCare = { push(Screen.EyeCareMenu) },
            onHistory = { push(Screen.History) },
        )
        Screen.Patient -> PatientScreen(
            vm = vm,
            onNext = { push(Screen.Camera) },
        )
        Screen.Camera -> CameraScreen(
            vm = vm,
            onResult = { push(Screen.Result) },
            onBack = { pop() },
        )
        Screen.Result -> ResultScreen(
            uiState = uiState,
            localHeuristic = localHeuristic,
            symmetry = symmetry,
            uploadProgress = uploadProgress,
            onRetry = {
                // Tarmoq/server xatosi va rasm hali saqlangan bo'lsa — qayta suratga
                // olmasdan xuddi shu rasmni qaytadan yuboradi. Aks holda (masalan,
                // UNGRADABLE natija) kameraga qaytib qayta suratga olish so'raladi.
                val s = uiState
                if (s is UiState.Error && s.canRetry) {
                    vm.retry()
                } else {
                    vm.reset()
                    pop()
                }
            },
            onCancelUpload = { pop() },
            onNewPatient = {
                vm.reset()
                resetTo(Screen.Home, Screen.Patient)
            },
        )
        Screen.EyeCareMenu -> EyeCareMenuScreen(
            onFollowDot = { push(Screen.FollowDot) },
            onFocusShift = { push(Screen.FocusShift) },
            onBlinkPalm = { push(Screen.BlinkPalm) },
            onReminderSettings = { push(Screen.ReminderSettings) },
            onBack = { pop() },
        )
        Screen.FollowDot -> FollowDotScreen(onBack = { pop() })
        Screen.FocusShift -> FocusShiftScreen(onBack = { pop() })
        Screen.BlinkPalm -> BlinkPalmScreen(onBack = { pop() })
        Screen.ReminderSettings -> ReminderSettingsScreen(onBack = { pop() })
        Screen.History -> HistoryScreen(onBack = { pop() })
    }
}
