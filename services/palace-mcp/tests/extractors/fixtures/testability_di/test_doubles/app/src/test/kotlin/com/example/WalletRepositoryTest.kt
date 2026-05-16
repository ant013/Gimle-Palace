package com.example

import io.mockk.mockk
import org.mockito.kotlin.mock

class WalletRepositoryTest {
    private val gateway = mockk<WalletApi>()
    private val session = mock<SessionStore>()

    class WalletApiFake : WalletApi
    object ClockStub : Clock
}
