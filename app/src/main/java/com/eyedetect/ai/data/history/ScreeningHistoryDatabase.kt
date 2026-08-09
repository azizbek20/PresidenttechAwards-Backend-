package com.eyedetect.ai.data.history

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [ScreeningHistoryEntity::class], version = 2, exportSchema = false)
abstract class ScreeningHistoryDatabase : RoomDatabase() {
    abstract fun screeningHistoryDao(): ScreeningHistoryDao

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
                    // solishtiruvi uchun). Loyiha hali relizga chiqmagan — eski keshni
                    // migratsiya qilish o'rniga oddiy tozalab qayta yaratamiz.
                    .fallbackToDestructiveMigration(true)
                    .build().also { instance = it }
            }
    }
}
