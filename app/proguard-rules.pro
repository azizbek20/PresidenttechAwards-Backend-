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
