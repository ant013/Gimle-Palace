package io.horizontalsystems.uwmini.app

import android.app.Application
import io.horizontalsystems.uwmini.core.db.AppDatabase
import io.horizontalsystems.uwmini.core.repository.WalletRepository

class MyApp : Application() {
    lateinit var walletRepository: WalletRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val db = AppDatabase.create(this)
        walletRepository = WalletRepository(db.walletDao())
    }
}
