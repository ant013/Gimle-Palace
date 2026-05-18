import Foundation

// BAD: raw division on 'amount' variable (triggers decimal_raw_uint_arithmetic_div)
func convertToDisplay(_ amount: Int64) -> Double {
    return Double(amount / 1_000_000)
}
