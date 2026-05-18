package com.example

import javax.inject.Inject

class WalletRepository(
    private val clock: Clock,
) {
    @Inject lateinit var api: WalletApi

    fun refresh() {
        val session = SessionManager.getInstance()
        _ = session
    }
}
