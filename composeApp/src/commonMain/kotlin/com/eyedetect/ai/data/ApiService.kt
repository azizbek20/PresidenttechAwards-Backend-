package com.eyedetect.ai.data

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
