package com.eyedetect.ai.data.history

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import com.eyedetect.ai.data.upload.PendingUploadDao
import com.eyedetect.ai.data.upload.PendingUploadEntity
import java.io.File
import net.sqlcipher.database.SQLiteDatabase
import net.sqlcipher.database.SupportFactory

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
                instance ?: run {
                    // PHI (bemor ID, skrining natijalari) diskda ochiq matn
                    // holida yotmasligi uchun SQLCipher orqali shifrlanadi.
                    // Parol har safar Keystore-himoyalangan qiymatdan
                    // qayta tiklanadi (DatabaseKeyProvider) — kodda hech
                    // qayerda literal parol yo'q.
                    SQLiteDatabase.loadLibs(context.applicationContext)
                    val passphrase = DatabaseKeyProvider.getOrCreatePassphrase(context)
                    deleteUnreadableLegacyDatabase(context, passphrase)
                    Room.databaseBuilder(
                        context.applicationContext,
                        ScreeningHistoryDatabase::class.java,
                        "screening_history.db",
                    )
                        .openHelperFactory(SupportFactory(passphrase))
                        // v1 -> v2: localHueDeg/localSaturation/localValue qo'shildi (simmetriya
                        // solishtiruvi uchun). v2 -> v3: pending_uploads jadvali qo'shildi (offline
                        // navbat, WorkManager). Loyiha hali relizga chiqmagan — eski keshni
                        // migratsiya qilish o'rniga oddiy tozalab qayta yaratamiz.
                        .fallbackToDestructiveMigration(true)
                        .build().also { instance = it }
                }
            }

        /**
         * Shifrlashdan oldingi (oddiy matn) bazadan qolgan fayl bo'lsa,
         * SQLCipher uni yangi parol bilan ocholmaydi va ilova ishga
         * tushishda qulaydi — versiya raqami mos bo'lsa ham,
         * `fallbackToDestructiveMigration` bu holatni ushlamaydi (u faqat
         * sxema versiyasi to'qnashuvi uchun). Fayl haqiqatan ham eski
         * (shifrlanmagan) yoki noto'g'ri kalit bilan yozilganini bir marta
         * tekshirib, shunday bo'lsa, o'chirib tashlaymiz — Room uni bo'sh
         * joydan qayta yaratadi. Loyiha hali relizga chiqmagani uchun
         * (PLAN.md) bu yo'qotish qabul qilinadi.
         */
        private fun deleteUnreadableLegacyDatabase(context: Context, passphrase: ByteArray) {
            val dbFile = context.getDatabasePath("screening_history.db")
            if (!dbFile.exists()) return
            // SQLCipher's raw-key PRAGMA format ("x'<hex>'") — the same
            // encoding `SupportFactory(byte[])` uses internally, so this
            // probe opens with exactly the key Room will use.
            val hexKey = "x'" + passphrase.joinToString("") { "%02x".format(it) } + "'"
            try {
                SQLiteDatabase.openDatabase(
                    dbFile.absolutePath,
                    hexKey,
                    null,
                    SQLiteDatabase.OPEN_READONLY,
                ).close()
            } catch (_: Exception) {
                dbFile.delete()
                File(dbFile.path + "-wal").delete()
                File(dbFile.path + "-shm").delete()
                File(dbFile.path + "-journal").delete()
            }
        }
    }
}
