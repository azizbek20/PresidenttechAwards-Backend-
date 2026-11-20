package com.eyedetect.ai.data

import kotlinx.coroutines.delay
import kotlin.time.TimeSource

interface ApiService {
    suspend fun predict(
        fileBytes: ByteArray,
        fileName: String,
        patientId: String?,
        eye: String?,
        onProgress: ((Float) -> Unit)? = null
    ): TaskResponse

    suspend fun getPredictStatus(taskId: String): TaskStatusResponse
}

/** Backend vazifasi [PredictPolling.timeoutMs] ichida tugamadi (masalan, worker ishlamayapti). */
class PredictTimeoutException(message: String) : Exception(message)

/** Backend vazifani `FAILURE` bilan yakunladi. */
class PredictFailedException(message: String) : Exception(message)

data class PredictPolling(
    val intervalMs: Long = 2_000,
    val timeoutMs: Long = 120_000,
)

/**
 * Rasmni yuboradi va natija tayyor bo'lguncha `status` endpointini so'rab turadi.
 * ViewModel va SyncWorker ikkalasi shuni ishlatadi.
 */
suspend fun ApiService.predictAndAwait(
    fileBytes: ByteArray,
    fileName: String,
    patientId: String?,
    eye: String?,
    onProgress: ((Float) -> Unit)? = null,
    polling: PredictPolling = PredictPolling(),
): PredictResponse {
    val task = predict(fileBytes, fileName, patientId, eye, onProgress)
    val started = TimeSource.Monotonic.markNow()
    var status = task.status
    while (status == "PENDING" || status == "PROCESSING") {
        if (started.elapsedNow().inWholeMilliseconds >= polling.timeoutMs) {
            throw PredictTimeoutException("Natija ${polling.timeoutMs / 1000} soniyada tayyor bo'lmadi")
        }
        delay(polling.intervalMs)
        val response = getPredictStatus(task.taskId)
        status = response.status
        when (status) {
            "SUCCESS" -> return response.result
                ?: throw PredictFailedException("Backend natijasiz SUCCESS qaytardi")
            "FAILURE" -> throw PredictFailedException("Backend xatosi: ${response.error ?: "Noma'lum"}")
        }
    }
    throw PredictFailedException("Kutilmagan vazifa holati: $status")
}
