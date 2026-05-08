// WeiEthMixGood.swift — should NOT trigger wei_eth_unit_mix_string rule
import Foundation

enum EthUnit {
    case wei, gwei, eth
}

class PaymentService {
    // Typed enum avoids raw unit string literals
    func transfer(qty: UInt256, unit: EthUnit) {
        let inWei: UInt256
        switch unit {
        case .wei: inWei = qty
        case .gwei: inWei = qty * 1_000_000_000
        case .eth: inWei = qty * 1_000_000_000_000_000_000
        }
        send(inWei)
    }
}
