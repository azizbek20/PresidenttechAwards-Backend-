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
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.eyedetect.ai.R
import com.eyedetect.ai.eyecare.ReminderSettingsViewModel
import com.eyedetect.ai.ui.components.InfoBanner
import com.eyedetect.ai.ui.components.IntervalChipRow
import com.eyedetect.ai.ui.components.SecondaryButton
import com.eyedetect.ai.ui.components.TextActionButton
import com.eyedetect.ai.ui.components.WarningBanner
import com.eyedetect.ai.ui.theme.Spacing

private val INTERVAL_OPTIONS = listOf(15, 20, 30, 45, 60)

/** 20-20-20 eslatmasi sozlamalari — yoqish/o'chirish, interval, ruxsat oqimi, statistika. */
@Composable
fun ReminderSettingsScreen(onBack: () -> Unit, vm: ReminderSettingsViewModel = viewModel()) {
    val context = LocalContext.current
    val settings by vm.settings.collectAsState()
    val stats by vm.stats.collectAsState()
    var permissionPermanentlyDenied by remember { mutableStateOf(false) }

    fun hasNotificationPermission(): Boolean =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            permissionPermanentlyDenied = false
            vm.enableReminder(settings.intervalMinutes)
        } else {
            val activity = context as? Activity
            val canAskAgain = activity != null &&
                ActivityCompat.shouldShowRequestPermissionRationale(activity, Manifest.permission.POST_NOTIFICATIONS)
            permissionPermanentlyDenied = !canAskAgain
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        TextActionButton(stringResource(R.string.common_back), onBack)
        Text(stringResource(R.string.reminder_settings_title), style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.primary)
        Text(
            stringResource(R.string.reminder_settings_description),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(stringResource(R.string.reminder_settings_toggle), style = MaterialTheme.typography.titleMedium)
            Switch(
                checked = settings.enabled,
                onCheckedChange = { checked ->
                    if (checked) {
                        if (hasNotificationPermission()) {
                            permissionPermanentlyDenied = false
                            vm.enableReminder(settings.intervalMinutes)
                        } else {
                            permissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                        }
                    } else {
                        vm.disableReminder()
                    }
                },
            )
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

        Text(stringResource(R.string.reminder_settings_interval_label), style = MaterialTheme.typography.titleMedium)
        IntervalChipRow(
            options = INTERVAL_OPTIONS,
            selected = settings.intervalMinutes,
            onSelect = { vm.changeInterval(it) },
        )

        if (settings.enabled && !permissionPermanentlyDenied) {
            InfoBanner(stringResource(R.string.reminder_settings_background_info, settings.intervalMinutes))
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Text(
                stringResource(
                    R.string.reminder_settings_total_exercises,
                    stats.followDotCount + stats.focusShiftCount + stats.blinkPalmCount,
                ),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                stringResource(R.string.reminder_settings_streak_days, stats.streakDays),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
