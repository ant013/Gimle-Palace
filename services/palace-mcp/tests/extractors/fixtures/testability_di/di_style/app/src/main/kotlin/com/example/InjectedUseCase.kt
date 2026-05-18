package com.example

import javax.inject.Inject

class InjectedUseCase {
    @Inject lateinit var api: WalletApi
}
