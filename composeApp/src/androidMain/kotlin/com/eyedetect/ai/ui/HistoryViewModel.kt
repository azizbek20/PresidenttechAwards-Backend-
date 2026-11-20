package com.eyedetect.ai.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.eyedetect.ai.data.history.ScreeningHistoryEntity
import com.eyedetect.ai.data.history.ScreeningHistoryRepository
import com.eyedetect.ai.data.upload.PendingUploadEntity
import com.eyedetect.ai.data.upload.PendingUploadRepository
import com.eyedetect.ai.upload.UploadScheduler
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.launch

/**
 * [HistoryScreen] uchun ViewModel — repository'larni to'g'ridan-to'g'ri Composable ichida
 * chaqirish o'rniga (ilovadagi boshqa barcha ekranlar bilan izchil MVVM), tarix/navbat
 * oqimlarini va ular ustidagi amallarni (o'chirish, qayta urinish, bekor qilish) shu yerga
 * jamlaydi.
 */
class HistoryViewModel(application: Application) : AndroidViewModel(application) {
    private val historyRepo = ScreeningHistoryRepository(application)
    private val pendingRepo = PendingUploadRepository(application)

    val history: Flow<List<ScreeningHistoryEntity>> = historyRepo.history
    val pending: Flow<List<PendingUploadEntity>> = pendingRepo.pending

    fun deleteEntry(entry: ScreeningHistoryEntity) {
        viewModelScope.launch { historyRepo.delete(entry) }
    }

    fun deleteEntries(entries: List<ScreeningHistoryEntity>) {
        viewModelScope.launch { entries.forEach { historyRepo.delete(it) } }
    }

    /** Navbatdagi yozuvni butunlay bekor qiladi — rejalashtirilgan WorkManager vazifasi ham,
     * Room yozuvi ham o'chiriladi. */
    fun cancelPending(entry: PendingUploadEntity) {
        viewModelScope.launch {
            UploadScheduler.cancel(getApplication(), entry.id)
            pendingRepo.delete(entry)
        }
    }

    /** Doimiy xato bilan yakunlangan ([PendingUploadEntity.failed]) yozuvni qo'lda qayta
     * navbatga qo'yadi. */
    fun retryPendingNow(entry: PendingUploadEntity) {
        viewModelScope.launch {
            pendingRepo.resetFailed(entry.id)
            UploadScheduler.enqueue(getApplication(), entry.id)
        }
    }
}
