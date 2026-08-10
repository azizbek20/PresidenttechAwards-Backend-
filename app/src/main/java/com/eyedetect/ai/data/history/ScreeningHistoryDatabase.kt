package com.eyedetect.ai.data.history

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import com.eyedetect.ai.data.upload.PendingUploadDao
import com.eyedetect.ai.data.upload.PendingUploadEntity

@Database(
    entities = [ScreeningHistoryEntity::class, PendingUploadEntity::class],
    version = 3,
    exportSchema = false,
)
abstract class ScreeningHistoryDatabase : RoomDatabase() {
    abstract fun screeningHistoryDao(): ScreeningHistoryDao
    abstract fun pendingUploadDao(): PendingUploadDao

    companion object {
        @Volatile private var instance: ScreeningHistoryDatabase? = null

        fun getInstance(context: Context): ScreeningHistoryDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    ScreeningHistoryDatabase::class.java,
                    "screening_history.db",
                )
                    // v1 -> v2: localHueDeg/localSaturation/localValue qo'shildi (simmetriya
                    // solishtiruvi uchun). v2 -> v3: pending_uploads jadvali qo'shildi (offline
                    // navbat, WorkManager). Loyiha hali relizga chiqmagan — eski keshni
                    // migratsiya qilish o'rniga oddiy tozalab qayta yaratamiz.
                    .fallbackToDestructiveMigration(true)
                    .build().also { instance = it }
            }
    }
}
