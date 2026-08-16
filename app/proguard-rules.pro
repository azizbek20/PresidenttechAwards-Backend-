# Retrofit, OkHttp, Room va WorkManager releaseda o'zlarining consumer-rules.txt/
# META-INF/proguard qoidalarini AAR/jar orqali avtomatik olib keladi (tekshirildi:
# app\build\...\merged consumer rules yoki kutubxona artifaktlari ichida mavjud) —
# ular uchun qo'lda qoida shart emas. Gson esa (converter-gson ham) hech qanday
# consumer-rules olib kelmaydi, shu sababli quyidagilar qo'lda kerak:

# Gson maydon nomlarini reflection orqali o'qiydi/annotatsiyalarga (@SerializedName)
# qaraydi — Signature/Annotation atributlari saqlanishi shart, aks holda generic
# turlar va @SerializedName ma'lumoti yo'qoladi.
-keepattributes Signature
-keepattributes *Annotation*
-dontwarn sun.misc.**

# Backend bilan almashinadigan DTO'lar (PredictResponse va h.k.) hamda Room
# entity/DAO'lar shu paket ostida — maydon nomlari (JSON kalitlari/ustun nomlari)
# o'zgarmasligi/olib tashlanmasligi shart.
-keep class com.eyedetect.ai.data.** { *; }

# Gson generic TypeAdapter/TypeToken mexanizmi uchun (hozir to'g'ridan-to'g'ri
# ishlatilmasa ham, kelajakda List<T>/generic javob qo'shilsa xavfsiz bo'lishi
# uchun himoyaviy qoida — Gson'ning rasmiy tavsiyasi).
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer
-keep,allowobfuscation,allowoptimization class com.google.gson.reflect.TypeToken
-keep,allowobfuscation,allowoptimization class * extends com.google.gson.reflect.TypeToken

# --- Retrofit (https://square.github.io/retrofit/ , rasmiy ProGuard tavsiyasi) ---
# Retrofit AAR o'zining consumer-rules.txt'ini olib keladi, lekin loyihaning
# o'z `ApiService` interfeysi dinamik proksi (java.lang.reflect.Proxy) orqali
# implementatsiya qilingani uchun bu interfeysning o'zi qo'shimcha ravishda
# aniq saqlanadi — bitta noto'g'ri qatnashuvchi qoida butun tarmoq qatlamini
# jim ravishda sindirishi mumkin.
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}
-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface <1>
-keep,allowobfuscation interface com.eyedetect.ai.data.ApiService
-dontwarn org.codehaus.mojo.animal_sniffer.*
-dontwarn javax.annotation.**
-dontwarn kotlin.Unit
-dontwarn retrofit2.KotlinExtensions
-dontwarn retrofit2.KotlinExtensions$*

# --- OkHttp / Okio: platformaga xos klasslar (yangi Android versiyalarida
# mavjud emas) haqidagi ogohlantirishlarni e'tiborsiz qoldirish xavfsiz ---
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# --- Kotlin coroutines: debug metadata klasslari ixtiyoriy ---
-dontwarn kotlinx.coroutines.debug.**

# --- SQLCipher (Room bazasini shifrlash — JNI/native ko'prik klasslari
# reflektsiya orqali chaqiriladi, saqlanishi shart) ---
-keep,includedescriptorclasses class net.sqlcipher.** { *; }
-keep,includedescriptorclasses interface net.sqlcipher.** { *; }
-dontwarn net.sqlcipher.**
