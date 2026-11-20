package com.eyedetect.ai.data

/**
 * Backend/Room/Retrofit hamon xom "left"/"right" satrni ishlatadi (kontraktni o'zgartirmaslik
 * uchun) — bu enum faqat UI qatlamida solishtirish va label tanlashni bir joyga jamlaydi
 * ([com.eyedetect.ai.ui.eyeLabel], [com.eyedetect.ai.ui.eyeShortLabel]).
 */
enum class Eye(val apiValue: String) {
    LEFT("left"), RIGHT("right");

    companion object {
        fun from(raw: String?): Eye? = entries.find { it.apiValue == raw }
    }
}
