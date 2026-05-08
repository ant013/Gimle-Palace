import Foundation

// BAD: unguarded addition on 'balance' variable (triggers bignum_overflow_unguarded)
func addReward(_ balance: Int64, reward: Int64) -> Int64 {
    return balance + reward
}
