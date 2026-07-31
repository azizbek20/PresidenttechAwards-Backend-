package com.eyedetect.ai.data

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

/** Backend endpointlari (Retrofit interfeysi). */
interface ApiService {

    /**
     * Fundus rasmni multipart/form-data bilan yuboradi.
     * @param file rasm qismi ("file" nomi backend bilan mos bo'lishi shart)
     * @param patientId ixtiyoriy bemor ID
     * @param eye ixtiyoriy: "right" | "left"
     */
    @Multipart
    @POST("api/v1/predict")
    suspend fun predict(
        @Part file: MultipartBody.Part,
        @Part("patient_id") patientId: RequestBody?,
        @Part("eye") eye: RequestBody?,
    ): PredictResponse
}
