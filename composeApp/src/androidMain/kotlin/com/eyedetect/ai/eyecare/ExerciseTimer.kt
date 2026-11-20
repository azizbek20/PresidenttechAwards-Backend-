package com.eyedetect.ai.eyecare

import kotlinx.coroutines.delay

/**
 * [durationMs] tugaguncha har [tickIntervalMs] (taxminan bitta kadr) oralig'ida [onTick]ni
 * shu paytgacha o'tgan vaqt (millisekundda) bilan chaqiradi. Ko'z mashqi ViewModel'laridagi
 * ([FollowDotViewModel], [FocusShiftViewModel], [BlinkPalmViewModel]) bir xil "bosqich
 * davomida davriy UI yangilanishi" siklini bitta joyga jamlaydi.
 */
suspend fun runPhase(durationMs: Long, tickIntervalMs: Long = 16L, onTick: (elapsedMs: Long) -> Unit) {
    val phaseStart = System.currentTimeMillis()
    while (true) {
        val elapsed = System.currentTimeMillis() - phaseStart
        if (elapsed >= durationMs) break
        onTick(elapsed)
        delay(tickIntervalMs)
    }
}
