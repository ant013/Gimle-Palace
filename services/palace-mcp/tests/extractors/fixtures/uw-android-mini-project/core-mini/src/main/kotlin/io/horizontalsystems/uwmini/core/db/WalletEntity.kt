package io.horizontalsystems.uwmini.core.db

import androidx.room.Entity
import androidx.room.PrimaryKey
import io.horizontalsystems.uwmini.core.model.Wallet

/**
 * Room @Entity — synthesized (Phase 1.0) following UW DAO patterns from
 * app/.../core/storage/ (snake_case table names, primary keys, etc.).
 */
@Entity(tableName = "wallets")
data class WalletEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val address: String,
    val label: String,
    val balance: Long,
) {
    fun toDomain(): Wallet = Wallet(id = id, address = address, label = label, balance = balance)

    companion object {
        fun fromDomain(w: Wallet): WalletEntity =
            WalletEntity(id = w.id, address = w.address, label = w.label, balance = w.balance)
    }
}
