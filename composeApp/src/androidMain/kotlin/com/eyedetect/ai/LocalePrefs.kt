package com.eyedetect.ai

import android.content.Context
import android.content.res.Configuration
import java.util.Locale

/**
 * Foydalanuvchi tanlagan ilova tilini saqlaydi va har qanday Context'ga
 * (Activity yoki Application) attachBaseContext orqali qo'llaydi — shu bilan
 * fon jarayonlari (Worker/Notification) ham tanlangan tilda ishlaydi.
 */
object LocalePrefs {
    private const val PREFS_NAME = "locale_prefs"
    private const val KEY_LANGUAGE_TAG = "language_tag"

    fun getLanguageTag(context: Context): String? =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString(KEY_LANGUAGE_TAG, null)

    fun setLanguageTag(context: Context, tag: String) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LANGUAGE_TAG, tag)
            .apply()
    }

    /** Agar foydalanuvchi til tanlagan bo'lsa, shu tilga mos konfiguratsiyali Context qaytaradi. */
    fun wrap(context: Context): Context {
        val tag = getLanguageTag(context) ?: return context
        val locale = Locale.forLanguageTag(tag)
        Locale.setDefault(locale)
        val config = Configuration(context.resources.configuration)
        config.setLocale(locale)
        return context.createConfigurationContext(config)
    }
}
