package com.eyedetect.ai.ui.eyecare

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.data.eyecare.PomodoroPhase
import com.eyedetect.ai.eyecare.PomodoroViewModel
import com.eyedetect.ai.ui.components.InfoBanner
import com.eyedetect.ai.ui.components.IntervalChipRow
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.TimerRing
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing
import com.eyedetect.ai.ui.theme.TrafficRed

private val FOCUS_OPTIONS = listOf(15, 20, 25, 30, 45)
private val BREAK_OPTIONS = listOf(5, 10, 15)

/**
 * Pomodoro — ekran vaqtini kuzatib, fokus/tanaffus davrlari almashganda ogohlantiradigan
 * mini-vosita. Taymer fon rejimida ([PomodoroWorker]) ishlaydi, shuning uchun bu ekrandan
 * chiqib ketilsa (yoki qurilma qulflansa) ham bosqich tugaganda bildirishnoma chiqadi.
 */
@Composable
fun PomodoroScreen(onBack: () -> Unit, vm: PomodoroViewModel = viewModel()) {
    val context = LocalContext.current
    val state by vm.state.collectAsState()
    val remainingSeconds by vm.remainingSeconds.collectAsState()
    var permissionPermanentlyDenied by remember { mutableStateOf(false) }

    fun hasNotificationPermission(): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            permissionPermanentlyDenied = false
            vm.start()
        } else {
            val activity = context as? Activity
            val canAskAgain = activity != null &&
                ActivityCompat.shouldShowRequestPermissionRationale(activity, Manifest.permission.POST_NOTIFICATIONS)
            permissionPermanentlyDenied = !canAskAgain
        }
    }

    val phaseMinutes = if (state.phase == PomodoroPhase.FOCUS) state.focusMinutes else state.breakMinutes
    val totalSeconds = phaseMinutes * 60
    val progress = if (state.running && totalSeconds > 0) {
        1f - remainingSeconds.toFloat() / totalSeconds
    } else 0f

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Column {
            Text(
                stringResource(R.string.pomodoro_title),
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                stringResource(R.string.pomodoro_description),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        Column(
            modifier = Modifier.fillMaxWidth().padding(vertical = Spacing.md),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            TimerRing(progress = progress, sizeDp = 220.dp) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        if (state.phase == PomodoroPhase.FOCUS) stringResource(R.string.pomodoro_phase_focus) else stringResource(R.string.pomodoro_phase_break),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        formatClock(if (state.running) remainingSeconds else phaseMinutes * 60),
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }

        if (!state.running) {
            Text(stringResource(R.string.pomodoro_focus_label), style = MaterialTheme.typography.titleMedium)
            IntervalChipRow(options = FOCUS_OPTIONS, selected = state.focusMinutes, onSelect = vm::changeFocusMinutes)
            Text(stringResource(R.string.pomodoro_break_label), style = MaterialTheme.typography.titleMedium)
            IntervalChipRow(options = BREAK_OPTIONS, selected = state.breakMinutes, onSelect = vm::changeBreakMinutes)
        }

        if (permissionPermanentlyDenied) {
            WarningBanner(stringResource(R.string.reminder_settings_permission_denied))
            SecondaryButton(
                stringResource(R.string.reminder_settings_open_settings),
                onClick = {
                    val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                    context.startActivity(intent)
                },
            )
        }

        if (state.running) {
            InfoBanner(stringResource(R.string.pomodoro_background_info))
            PrimaryButton(stringResource(R.string.pomodoro_stop), onClick = vm::stop, containerColor = TrafficRed)
        } else {
            PrimaryButton(
                stringResource(R.string.pomodoro_start),
                onClick = {
                    if (hasNotificationPermission()) {
                        permissionPermanentlyDenied = false
                        vm.start()
                    } else {
                        permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                },
            )
        }
    }
}

/** Soniyani "mm:ss" ko'rinishiga o'tkazadi. */
private fun formatClock(totalSeconds: Int): String {
    val m = totalSeconds / 60
    val s = totalSeconds % 60
    return "%02d:%02d".format(m, s)
}
