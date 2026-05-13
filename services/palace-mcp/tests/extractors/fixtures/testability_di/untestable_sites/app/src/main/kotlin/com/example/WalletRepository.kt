package com.example

import java.time.Instant
import java.util.Calendar

class WalletRepository {
    fun refresh() {
        val now = Instant.now()
        val calendar = Calendar.getInstance()
        val prefs = Preferences.getInstance()
        val session = SessionManager.getInstance()
        _ = listOf(now, calendar, prefs, session)
    }
}
