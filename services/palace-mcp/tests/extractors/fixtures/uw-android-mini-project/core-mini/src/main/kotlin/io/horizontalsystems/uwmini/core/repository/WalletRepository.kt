package io.horizontalsystems.uwmini.core.repository

import io.horizontalsystems.uwmini.core.db.WalletDao
import io.horizontalsystems.uwmini.core.db.WalletEntity
import io.horizontalsystems.uwmini.core.model.Wallet
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Repository wraps WalletDao + maps WalletEntity ↔ Wallet domain.
 * Synthesized in UW style — keeps Room types out of UI/ViewModel layer.
 */
class WalletRepository(private val dao: WalletDao) {

    fun allWallets(): Flow<List<Wallet>> =
        dao.observeAll().map { entities -> entities.map(WalletEntity::toDomain) }

    suspend fun count(): Int = dao.count()

    suspend fun findById(id: Long): Wallet? = dao.findById(id)?.toDomain()

    suspend fun add(wallets: List<Wallet>) {
        dao.insertAll(wallets.map(WalletEntity::fromDomain))
    }

    suspend fun update(wallet: Wallet) {
        dao.update(WalletEntity.fromDomain(wallet))
    }

    suspend fun delete(wallet: Wallet) {
        dao.delete(WalletEntity.fromDomain(wallet))
    }
}
