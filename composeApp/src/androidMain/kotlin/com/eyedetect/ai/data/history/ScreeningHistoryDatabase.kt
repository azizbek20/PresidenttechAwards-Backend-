package com.eyedetect.ai.data.history

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase

@Database(entities = [ScreeningHistoryEntity::class], version = 3, exportSchema = false)
abstract class ScreeningHistoryDatabase : RoomDatabase() {
    abstract fun screeningHistoryDao(): ScreeningHistoryDao

    companion object {
        @Volatile private var instance: ScreeningHistoryDatabase? = null

        /**
         * Faqat JVM (Robolectric) testlari uchun: SQLCipher'ning native kutubxonasi
         * JVM'da yuklanmaydi, shu sabab testlar shifrlanmagan in-memory bazani beradi.
         * `null` berilsa keyingi [getInstance] yana haqiqiy bazani quradi.
         */
        @androidx.annotation.VisibleForTesting
        fun overrideForTests(db: ScreeningHistoryDatabase?) {
            synchronized(this) {
                instance?.takeIf { it !== db }?.close()
                instance = db
            }
        }

        fun getInstance(context: Context): ScreeningHistoryDatabase =
            instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    ScreeningHistoryDatabase::class.java,
                    "screening_history.db",
                )
                    // SQLCipher factory bilan bazani shifrlaymiz
                    .openHelperFactory(
                        net.sqlcipher.database.SupportFactory(
                            DbKeyProvider.getPassphrase(context)
                        )
                    )
                    // v1 -> v2: localHueDeg/localSaturation/localValue qo'shildi (simmetriya
                    // solishtiruvi uchun). Loyiha hali relizga chiqmagan — eski keshni
                    // migratsiya qilish o'rniga oddiy tozalab qayta yaratamiz.
                    .fallbackToDestructiveMigration(true)
                    .build().also { instance = it }
            }
    }
}
