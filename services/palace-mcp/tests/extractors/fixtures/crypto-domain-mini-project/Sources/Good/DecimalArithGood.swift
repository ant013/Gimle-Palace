import Foundation
import BigInt

// GOOD: BigUInt used for amount arithmetic
func convertToDisplay(_ rawAmount: BigUInt) -> Decimal {
    return Decimal(string: String(rawAmount))! / 1_000_000
}
