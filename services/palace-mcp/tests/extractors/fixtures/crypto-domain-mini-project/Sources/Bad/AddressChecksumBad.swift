// AddressChecksumBad.swift — triggers address_no_checksum_validation rule
import Foundation

class AddressManager {
    func getHardcoded() -> String {
        // Raw hex literal without EIP-55 checksum validation
        let address = "0xAbCdEf1234567890abcdef1234567890AbCdEF12"
        return address
    }

    func initTron() {
        // Passing raw hex to TronAddress without validation
        let addr = TronAddress("0x1234567890abcdef1234567890AbCdEF12345678")
        _ = addr
    }
}
