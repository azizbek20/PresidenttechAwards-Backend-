# Room, WorkManager, Ktor va kotlinx.serialization releaseda o'zlarining
# consumer-rules qoidalarini AAR/jar orqali olib keladi. Quyida faqat qo'lda
# kerak bo'lganlar.

-keepattributes Signature
-keepattributes *Annotation*
-keepattributes InnerClasses,EnclosingMethod

# Backend bilan almashinadigan DTO'lar (PredictResponse, TaskResponse ...) hamda
# Room entity/DAO'lar shu paket ostida — maydon nomlari (JSON kalitlari/ustun
# nomlari) o'zgarmasligi/olib tashlanmasligi shart.
-keep class com.eyedetect.ai.data.** { *; }

# --- kotlinx.serialization: @Serializable klasslarning generatsiya qilingan
# serializer'lari companion orqali topiladi ---
-keepclassmembers @kotlinx.serialization.Serializable class ** {
    static ** Companion;
    *** Companion;
    kotlinx.serialization.KSerializer serializer(...);
}
-if @kotlinx.serialization.Serializable class **
-keepclassmembers class <1>$Companion {
    kotlinx.serialization.KSerializer serializer(...);
}

# --- Ktor / OkHttp / Okio: platformaga xos ixtiyoriy klasslar ---
-dontwarn io.ktor.**
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
-dontwarn org.slf4j.**
-dontwarn java.lang.management.**

# --- Kotlin coroutines: debug metadata klasslari ixtiyoriy ---
-dontwarn kotlinx.coroutines.debug.**

# --- SQLCipher (Room bazasini shifrlash — JNI/native ko'prik klasslari
# reflektsiya orqali chaqiriladi, saqlanishi shart) ---
-keep,includedescriptorclasses class net.sqlcipher.** { *; }
-keep,includedescriptorclasses interface net.sqlcipher.** { *; }
-dontwarn net.sqlcipher.**

# --- ML Kit, MediaPipe Tasks va TensorFlow Lite: native kod Java klasslarini
# nomi bo'yicha chaqiradi ---
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**
-keep class com.google.mediapipe.** { *; }
-dontwarn com.google.mediapipe.**
-keep class org.tensorflow.lite.** { *; }
-dontwarn org.tensorflow.lite.**
-dontwarn javax.annotation.**
