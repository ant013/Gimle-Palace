package com.example

class WalletLocator {
    fun prefs(): Preferences {
        return Preferences.getInstance()
    }
}
