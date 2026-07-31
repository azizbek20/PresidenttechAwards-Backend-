package com.eyedetect.ai.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import com.eyedetect.ai.ScreeningViewModel
import com.eyedetect.ai.ui.components.EyeSelector
import com.eyedetect.ai.ui.components.PatientIdField
import com.eyedetect.ai.ui.components.PrimaryButton
import com.eyedetect.ai.ui.components.StatusBadge
import com.eyedetect.ai.ui.theme.Spacing

/**
 * 1-ekran: bemor ID + ko'z tanlash (6-hujjat, 6.A).
 * Bir vazifa — bir ekran: minimal, tez, xatosiz. Asosiy tugma pastda.
 */
@Composable
fun PatientScreen(vm: ScreeningViewModel, onNext: () -> Unit) {
    var pid by remember { mutableStateOf(vm.patientId) }
    var eye by remember { mutableStateOf(vm.eye) }

    Column(
        modifier = Modifier.fillMaxSize().padding(Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        // Brend sarlavhasi + ulanish holati
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Column {
                Text(
                    "EYE DETECT AI",
                    style = MaterialTheme.typography.headlineMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Text(
                    "DR skrining · yangi tekshiruv",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            StatusBadge(online = true)
        }

        Column(
            modifier = Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            PatientIdField(value = pid, onChange = { pid = it })
            Text(
                "ID kiritilmasa avtomatik raqam beriladi.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Text("Qaysi ko'z?", style = MaterialTheme.typography.titleMedium)
            EyeSelector(selected = eye, onSelect = { eye = it })
        }

        Spacer(Modifier.padding(top = Spacing.xs))
        PrimaryButton(
            text = "Davom etish → Kamera",
            onClick = {
                vm.patientId = pid
                vm.eye = eye
                onNext()
            },
        )
    }
}
