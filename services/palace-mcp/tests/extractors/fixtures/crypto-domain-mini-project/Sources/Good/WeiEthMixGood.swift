// WeiEthMixGood.swift — should NOT trigger wei_eth_unit_mix_string rule
import Foundation

enum EthUnit {
    case wei, gwei, eth
}

class PaymentService {
    // Typed enum avoids raw unit string literals
    func transfer(amount: UInt256, unit: EthUnit) {
        let inWei: UInt256
        switch unit {
        case .wei: inWei = amount
        case .gwei: inWei = amount * 1_000_000_000
        case .eth: inWei = amount * 1_000_000_000_000_000_000
        }
        send(inWei)
    }
}
