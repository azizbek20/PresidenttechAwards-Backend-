package com.eyedetect.ai.data.upload

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface PendingUploadDao {

    @Insert
    suspend fun insert(entry: PendingUploadEntity): Long

    @Query("SELECT * FROM pending_uploads ORDER BY queuedAtMs DESC")
    fun observeAll(): Flow<List<PendingUploadEntity>>

    @Query("SELECT * FROM pending_uploads WHERE id = :id")
    suspend fun getById(id: Long): PendingUploadEntity?

    @Query("UPDATE pending_uploads SET failed = 1 WHERE id = :id")
    suspend fun markFailed(id: Long)

    /** Foydalanuvchi "Qayta urinish"ni bosganda — doimiy xato belgisi olib tashlanadi,
     * [com.eyedetect.ai.upload.UploadScheduler] yana ish rejalashtirishdan oldin. */
    @Query("UPDATE pending_uploads SET failed = 0 WHERE id = :id")
    suspend fun resetFailed(id: Long)

    @Delete
    suspend fun delete(entry: PendingUploadEntity)
}
