package com.eyedetect.ai.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Kattalashtirilgan Material 3 tipografiya shkalasi (6-hujjat, 3-bo'lim).
 * Dala sharoiti va turli yoshdagi xodimlar uchun: ekranda 15 sp dan kichik matn yo'q.
 * Barchasi `sp` — tizim shrift kattalashtirishini hurmat qiladi.
 */
val AppTypography = Typography(
    headlineMedium = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.SemiBold),  // ekran/brend
    headlineSmall  = TextStyle(fontSize = 26.sp, fontWeight = FontWeight.Bold),       // qaror matni
    titleLarge     = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold),   // karta sarlavhasi
    titleMedium    = TextStyle(fontSize = 18.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge      = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.Normal),     // asosiy matn
    bodyMedium     = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Normal),     // disklaymer/metadata
    labelLarge     = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium),     // tugma matni
)
