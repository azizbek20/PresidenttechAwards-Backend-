package com.eyedetect.ai.data.history

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.security.SecureRandom

object DbKeyProvider {
    private const val PREFS_FILENAME = "db_secure_prefs"
    private const val KEY_PASSPHRASE = "db_passphrase"

    fun getPassphrase(context: Context): ByteArray {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        val sharedPreferences = EncryptedSharedPreferences.create(
            context,
            PREFS_FILENAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        var passphraseString = sharedPreferences.getString(KEY_PASSPHRASE, null)
        if (passphraseString == null) {
            val random = SecureRandom()
            val bytes = ByteArray(32) // 256-bit key
            random.nextBytes(bytes)
            passphraseString = bytes.joinToString("") { "%02x".format(it) }
            
            sharedPreferences.edit()
                .putString(KEY_PASSPHRASE, passphraseString)
                .apply()
        }

        return passphraseString.toByteArray(Charsets.UTF_8)
    }
}
