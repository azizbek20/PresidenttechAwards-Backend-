package com.eyedetect.ai.data.history

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface ScreeningHistoryDao {

    @Insert
    suspend fun insert(entry: ScreeningHistoryEntity): Long

    @Query("SELECT * FROM screening_history ORDER BY savedAtMs DESC")
    fun observeAll(): Flow<List<ScreeningHistoryEntity>>

    @Query("SELECT * FROM screening_history WHERE patientId = :patientId ORDER BY savedAtMs DESC")
    fun observeForPatient(patientId: String): Flow<List<ScreeningHistoryEntity>>

    /** Berilgan bemor/ko'z uchun oxirgi yozuv — kelajakda ikki ko'z simmetriyasini
     * solishtirish (PLAN.md 2-band) shu metodga tayanadi. */
    @Query(
        "SELECT * FROM screening_history WHERE patientId = :patientId AND eye = :eye " +
            "ORDER BY savedAtMs DESC LIMIT 1"
    )
    suspend fun latestFor(patientId: String, eye: String): ScreeningHistoryEntity?

    /** Yozuv saqlangandan keyin tayyor bo'lgan mahalliy evristika natijasini qo'shadi
     * (birinchi saqlashda hali hisoblanmagan bo'lishi mumkin). */
    @Query(
        "UPDATE screening_history SET localOpacity = :opacity, localRedReflex = :redReflex, " +
            "localHueDeg = :hueDeg, localSaturation = :saturation, localValue = :value WHERE id = :id"
    )
    suspend fun updateHeuristic(
        id: Long,
        opacity: String?,
        redReflex: String?,
        hueDeg: Float?,
        saturation: Float?,
        value: Float?,
    )

    @Delete
    suspend fun delete(entry: ScreeningHistoryEntity)

    @Query("DELETE FROM screening_history")
    suspend fun clearAll()
}
