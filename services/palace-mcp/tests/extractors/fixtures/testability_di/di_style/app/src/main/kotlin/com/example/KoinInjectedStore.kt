package com.example

import org.koin.core.component.KoinComponent
import org.koin.core.component.inject

class KoinInjectedStore : KoinComponent {
    private val api by inject<WalletApi>()
}
