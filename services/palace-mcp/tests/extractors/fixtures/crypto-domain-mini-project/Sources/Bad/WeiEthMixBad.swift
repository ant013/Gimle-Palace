// WeiEthMixBad.swift — triggers wei_eth_unit_mix_string rule
import Foundation

class PaymentService {
    func transferUnit() -> String {
        // Raw unit string literal — mixing wei/gwei without typed conversion
        let unit = "wei"
        return unit
    }

    func displayUnit() -> String {
        return "gwei"
    }
}
