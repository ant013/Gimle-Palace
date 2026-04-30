package io.horizontalsystems.uwmini.app

import io.horizontalsystems.uwmini.core.model.Wallet

sealed interface UiState {
    object Loading : UiState
    data class Success(val wallets: List<Wallet>) : UiState
    data class Error(val message: String) : UiState
}
