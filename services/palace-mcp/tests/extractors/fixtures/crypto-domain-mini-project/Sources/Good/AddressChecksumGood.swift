// AddressChecksumGood.swift — should NOT trigger address_no_checksum_validation rule
import Foundation

class AddressManager {
    func getValidated(input: String) -> ValidatedAddress? {
        // Address comes from user input, validated via a type — no raw hex literal
        return ValidatedAddress(validating: input)
    }

    func isValid(_ hex: String) -> Bool {
        return EIP55.isValid(hex)
    }
}
