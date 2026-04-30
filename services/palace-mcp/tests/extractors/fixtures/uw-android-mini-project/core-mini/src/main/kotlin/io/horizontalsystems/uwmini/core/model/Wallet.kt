package io.horizontalsystems.uwmini.core.model

/** Domain model — synthesized (Phase 1.0). */
data class Wallet(
    val id: Long,
    val address: String,
    val label: String,
    val balance: Long,
)
