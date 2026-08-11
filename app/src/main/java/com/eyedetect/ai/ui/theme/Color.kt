package com.eyedetect.ai.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * EYE DETECT AI rang tizimi (6-hujjat: Mobil Dizayn/UX, 2-bo'lim).
 *
 * Ikki qatlam:
 *   1) SVETOFOR — semantik qaror ranglari (butun ilova bo'ylab izchil).
 *   2) NEYTRAL KARKAS — teal brend + Material 3 sirt/matn tokenlari.
 */

// ---- Svetofor (semantik) ------------------------------------------------
val TrafficGreen  = Color(0xFF2E7D32)   // NO_REFER — DR yo'q
val TrafficRed    = Color(0xFFC62828)   // REFER — oftalmologga
val TrafficGrey   = Color(0xFF616161)   // UNGRADABLE — qayta oling
val TrafficYellow = Color(0xFFF9A825)   // faqat real-vaqt kamera "chegaraviy"

// Svetofor yumshoq fonlari (banner/urg'u uchun)
val TrafficGreenContainer  = Color(0xFFE3F4EA)
val TrafficRedContainer    = Color(0xFFFBE4E4)
val TrafficYellowContainer = Color(0xFFFFF8E1)

// ---- Brend (teal — ishonch; svetofor bilan raqobatlashmaydi) ------------
val Primary            = Color(0xFF00696E)
val OnPrimary          = Color(0xFFFFFFFF)
val PrimaryContainer   = Color(0xFF6FF6FE)
val OnPrimaryContainer = Color(0xFF002022)

// ---- Neytral karkas — yorug' rejim --------------------------------------
val SurfaceLight       = Color(0xFFFBFCFC)
val SurfaceVariantLight = Color(0xFFF0F5F5)
val OnSurfaceLight     = Color(0xFF191C1D)
val OnSurfaceVarLight  = Color(0xFF3F484A)
val OutlineLight       = Color(0xFF6F797A)
val OutlineVarLight    = Color(0xFFC4CDCE)
val ErrorLight         = Color(0xFFBA1A1A)

// ---- Neytral karkas — qorong'i rejim (poliklinika xira yorug'ligi) ------
val PrimaryDark        = Color(0xFF4FD8DF)
val OnPrimaryDark      = Color(0xFF00363A)
val PrimaryContainerDark = Color(0xFF004F54)
val SurfaceDark        = Color(0xFF0E1415)
val SurfaceVariantDark = Color(0xFF1A2122)
val OnSurfaceDark      = Color(0xFFE1E3E3)
val OnSurfaceVarDark   = Color(0xFFBFC8CA)
val OutlineDark        = Color(0xFF899294)
val ErrorDark          = Color(0xFFFFB4AB)

/**
 * Qaror kodidan svetofor rangini beradi (ResultScreen/DecisionChip shundan foydalanadi).
 * UNGRADABLE va noma'lum -> kulrang (hech qachon yashil bilan aralashmaydi).
 */
fun decisionColor(decision: String): Color = when (decision) {
    "REFER" -> TrafficRed
    "NO_REFER" -> TrafficGreen
    else -> TrafficGrey
}

/** Qaror kodiga mos svetofor emojisi (rang + ikonka + matn — WCAG 1.4.1). */
fun decisionEmoji(decision: String): String = when (decision) {
    "REFER" -> "🔴"      // 🔴
    "NO_REFER" -> "🟢"   // 🟢
    else -> "⚪"               // ⚪
}

/** REFER/NO_REFER'dan boshqa har qanday qiymat (masalan sifat yetarli emasligi sababli
 * baholab bo'lmagan holat) ungradable hisoblanadi — bir nechta ekranda takrorlangan
 * tekshiruv shu yerga jamlangan. */
fun isUngradableDecision(decision: String?): Boolean = decision != "REFER" && decision != "NO_REFER"
