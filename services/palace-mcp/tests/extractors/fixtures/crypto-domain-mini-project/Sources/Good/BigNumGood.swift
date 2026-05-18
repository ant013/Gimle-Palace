import Foundation
import BigInt

// GOOD: BigUInt used with descriptive names outside the rule's variable-name regex
func addReward(_ currentHoldings: BigUInt, reward: BigUInt) -> BigUInt {
    return currentHoldings + reward
}

// GOOD: explicit overflow check with built-in Swift checked arithmetic
func addSafe(_ x: Int64, _ y: Int64) -> Int64? {
    return x.addingReportingOverflow(y).overflow ? nil : x &+ y
}
