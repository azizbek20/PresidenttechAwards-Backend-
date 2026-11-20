package com.eyedetect.ai.data.history

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * SQLCipher Room bazasi uchun parolni boshqaradi (xavfsizlik/maxfiylik
 * bo'shlig'i — bemor ID va skrining natijalari PHI hisoblanadi).
 *
 * Parolning o'zi tasodifiy 256-bitli qiymat sifatida generatsiya qilinadi va
 * hech qachon ochiq holda diskka yozilmaydi: u faqat Android Keystore'dagi
 * apparat-himoyalangan (mumkin bo'lsa StrongBox) AES-GCM kaliti bilan
 * shifrlangan holda oddiy SharedPreferences'da saqlanadi. Keystore kaliti
 * qurilmadan hech qachon chiqarilmaydi va nusxa (backup) orqali ko'chmaydi,
 * shu sababli shifrlangan parol fayli boshqa qurilmada yoki root orqali
 * o'qilsa ham ma'nosiz baytlar bo'lib qoladi.
 */
internal object DatabaseKeyProvider {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "eyedetect_history_db_key"
    private const val PREFS_NAME = "eyedetect_history_db_keystore"
    private const val PREF_CIPHERTEXT = "passphrase_ciphertext"
    private const val PREF_IV = "passphrase_iv"
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val GCM_TAG_BITS = 128
    private const val PASSPHRASE_BYTES = 32

    fun getOrCreatePassphrase(context: Context): ByteArray {
        val prefs = context.applicationContext
            .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val storedCiphertext = prefs.getString(PREF_CIPHERTEXT, null)
        val storedIv = prefs.getString(PREF_IV, null)
        val key = getOrCreateKeystoreKey()

        if (storedCiphertext != null && storedIv != null) {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                GCMParameterSpec(GCM_TAG_BITS, Base64.decode(storedIv, Base64.NO_WRAP)),
            )
            return cipher.doFinal(Base64.decode(storedCiphertext, Base64.NO_WRAP))
        }

        val passphrase = ByteArray(PASSPHRASE_BYTES).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val ciphertext = cipher.doFinal(passphrase)
        prefs.edit()
            .putString(PREF_CIPHERTEXT, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            .putString(PREF_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .apply()
        return passphrase
    }

    private fun getOrCreateKeystoreKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            ANDROID_KEYSTORE,
        )
        val spec = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()
        keyGenerator.init(spec)
        return keyGenerator.generateKey()
    }
}
