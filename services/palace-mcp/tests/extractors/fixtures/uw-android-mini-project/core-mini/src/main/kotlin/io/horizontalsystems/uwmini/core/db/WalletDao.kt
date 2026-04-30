package io.horizontalsystems.uwmini.core.db

import androidx.room.Dao
import androidx.room.Delete
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/**
 * Room @Dao — synthesized (Phase 1.0) following UW patterns:
 * - mixed @Query / @Insert / @Update / @Delete
 * - suspend functions + Flow streams
 * - REPLACE conflict strategy
 *
 * KSP generates WalletDao_Impl at build/generated/ksp/<variant>/kotlin/.../db/WalletDao_Impl.kt
 * (this is the AC#4 KSP-source-visibility target).
 */
@Dao
interface WalletDao {

    @Query("SELECT * FROM wallets ORDER BY label ASC")
    fun observeAll(): Flow<List<WalletEntity>>

    @Query("SELECT * FROM wallets WHERE id = :id LIMIT 1")
    suspend fun findById(id: Long): WalletEntity?

    @Query("SELECT COUNT(*) FROM wallets")
    suspend fun count(): Int

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(wallets: List<WalletEntity>)

    @Update
    suspend fun update(wallet: WalletEntity)

    @Delete
    suspend fun delete(wallet: WalletEntity)

    @Query("DELETE FROM wallets")
    suspend fun deleteAll()
}
