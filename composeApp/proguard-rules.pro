# Data class models (Retrofit/GSON and Room Entities)
-keep class com.eyedetect.ai.data.** { *; }

# Retrofit & OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn retrofit2.**
-keepattributes Signature
-keepattributes Exceptions
-keepattributes *Annotation*

# Room & SQLCipher
-keep class androidx.room.** { *; }
-dontwarn androidx.room.**
-keep class net.zetetic.database.sqlcipher.** { *; }
-keep class androidx.sqlite.db.** { *; }
-dontwarn net.zetetic.database.sqlcipher.**

# ML Kit
-keep class com.google.mlkit.** { *; }
-dontwarn com.google.mlkit.**

# Coroutines
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembernames class kotlinx.** {
    volatile <fields>;
}
