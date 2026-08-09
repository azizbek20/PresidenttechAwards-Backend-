# Backend bilan almashinadigan JSON model klasslari (Gson reflektsiya orqali
# maydon nomlarini o'qiydi) — hech qachon obfuskatsiya/qisqartirilmasin.
-keep class com.eyedetect.ai.data.** { *; }

# --- Retrofit (https://square.github.io/retrofit/ , rasmiy ProGuard tavsiyasi) ---
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations, AnnotationDefault
-keepattributes Exceptions

-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

-dontwarn org.codehaus.mojo.animal_sniffer.*
-dontwarn javax.annotation.**
-dontwarn kotlin.Unit
-dontwarn retrofit2.KotlinExtensions
-dontwarn retrofit2.KotlinExtensions$*

-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface <1>

# `ApiService` Retrofit dinamik proksi (java.lang.reflect.Proxy) orqali
# implementatsiya qilinadi — interfeys o'zi saqlanishi shart.
-keep,allowobfuscation interface com.eyedetect.ai.data.ApiService

# --- Gson (https://github.com/google/gson , rasmiy ProGuard tavsiyasi) ---
-keepattributes Signature
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken
-keep,allowobfuscation,allowshrinking class com.google.gson.reflect.TypeToken

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
