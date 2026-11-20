package com.eyedetect.ai.vision

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import com.eyedetect.ai.data.PredictResponse
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.support.common.FileUtil
import org.tensorflow.lite.support.image.ImageProcessor
import org.tensorflow.lite.support.image.TensorImage
import org.tensorflow.lite.support.image.ops.ResizeOp
import org.tensorflow.lite.support.tensorbuffer.TensorBuffer
import java.io.FileNotFoundException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * Internet yo'q bo'lgan vaqtda (Offline) ishlaydigan TFLite modeli.
 * Bu klass "dr_model.tflite" faylini assets papkasidan qidiradi.
 * Agar model topilmasa, shunchaki ishlamaydi va xato tashlamaydi.
 */
class OfflineDrClassifier(context: Context) {
    private var interpreter: Interpreter? = null
    private var isAvailable = false
    private val inputImageWidth = 224
    private val inputImageHeight = 224

    init {
        try {
            val modelBuffer = FileUtil.loadMappedFile(context, "dr_model.tflite")
            val options = Interpreter.Options()
            options.setNumThreads(4)
            interpreter = Interpreter(modelBuffer, options)
            isAvailable = true
            Log.d("OfflineDrClassifier", "Offline TFLite model successfully loaded.")
        } catch (e: Exception) {
            if (e is FileNotFoundException || e.message?.contains("not found") == true) {
                Log.w("OfflineDrClassifier", "dr_model.tflite not found in assets. Offline mode disabled.")
            } else {
                Log.e("OfflineDrClassifier", "Error loading TFLite model", e)
            }
        } catch (e: UnsatisfiedLinkError) {
            // TFLite native kutubxonasi yo'q (masalan, qo'llab-quvvatlanmagan ABI yoki JVM
            // testlari) — oflayn rejimsiz davom etamiz, ViewModel yaratilishini buzmaymiz.
            Log.w("OfflineDrClassifier", "TFLite native library unavailable. Offline mode disabled.", e)
        }
    }

    /**
     * Agar TFLite model o'rnatilgan bo'lsa, rasmni tahlil qiladi va PredictResponse
     * formatidagi soxta (lekin modeldan olingan aniq ma'lumotli) javob qaytaradi.
     */
    fun predict(bitmap: Bitmap, eye: String? = null): PredictResponse? {
        val tflite = interpreter
        if (!isAvailable || tflite == null) return null

        try {
            // Rasmni TFLite uchun 224x224 qilib tayyorlaymiz
            val inputTensor = tflite.getInputTensor(0)
            val inputDataType = inputTensor.dataType()

            val imageProcessor = ImageProcessor.Builder()
                .add(ResizeOp(inputImageHeight, inputImageWidth, ResizeOp.ResizeMethod.BILINEAR))
                .build()

            var tensorImage = TensorImage(inputDataType)
            tensorImage.load(bitmap)
            tensorImage = imageProcessor.process(tensorImage)

            // Natija uchun buferni modelning o'zidan qarab moslaymiz (masalan test model 1x1000 bo'lishi ham mumkin)
            val outputTensor = tflite.getOutputTensor(0)
            val outputShape = outputTensor.shape()
            val outputDataType = outputTensor.dataType()
            val outputBuffer = TensorBuffer.createFixedSize(outputShape, outputDataType)

            // Inference
            tflite.run(tensorImage.buffer, outputBuffer.buffer.rewind())

            val logits = if (outputDataType == org.tensorflow.lite.DataType.FLOAT32) {
                outputBuffer.floatArray
            } else {
                val intArray = outputBuffer.intArray
                FloatArray(intArray.size) { intArray[it].toFloat() }
            }

            val (grade, maxProb) = computeSoftmaxAndArgmax(logits)

            val isReferable = grade > 0 // 1 va undan yuqori kasallik bo'lsa "REFER"
            
            val df = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)

            return PredictResponse(
                examId = "offline_${UUID.randomUUID().toString().take(8)}",
                patientId = null,
                eye = eye ?: "unknown",
                referable = isReferable,
                probability = maxProb.toDouble(),
                icdrGrade = grade,
                gradeLabel = "Grade $grade (Offline)",
                decision = if (isReferable) "REFER" else "NO_REFER",
                decisionText = if (isReferable) "Oflayn: Shifokor ko'rigi tavsiya etiladi." else "Oflayn: Kasallik alomati topilmadi.",
                quality = "UNKNOWN", // Offline model hozircha sifatni baholamaydi
                heatmapUrl = null, // Oflayn modelda heatmap yo'q
                imageUrl = null,
                modelVersion = "tflite_offline_v1",
                processedAt = df.format(Date()),
                disclaimer = "DIQQAT: Bu natija internet yo'qligida, cheklangan oflayn sun'iy intellekt orqali chiqarildi. " +
                             "Imkon bo'lishi bilan internetga ulanib, asosiy server tekshiruvidan o'ting."
            )
        } catch (e: Exception) {
            Log.e("OfflineDrClassifier", "Error during offline prediction", e)
            return null
        }
    }

    private fun computeSoftmaxAndArgmax(logits: FloatArray): Pair<Int, Float> {
        var maxLogit = Float.NEGATIVE_INFINITY
        for (l in logits) {
            if (l > maxLogit) maxLogit = l
        }
        var sumExp = 0f
        for (l in logits) {
            sumExp += kotlin.math.exp(l - maxLogit)
        }
        
        var maxProb = -1f
        var maxIndex = 0
        for (i in logits.indices) {
            val prob = kotlin.math.exp(logits[i] - maxLogit) / sumExp
            if (prob > maxProb) {
                maxProb = prob
                maxIndex = i
            }
        }
        return Pair(maxIndex, maxProb)
    }
    
    fun close() {
        interpreter?.close()
        interpreter = null
        isAvailable = false
    }
}