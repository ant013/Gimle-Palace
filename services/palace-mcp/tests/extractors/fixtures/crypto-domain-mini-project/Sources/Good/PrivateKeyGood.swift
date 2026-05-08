import Foundation
import Security

// GOOD: mnemonic stored in Keychain, not UserDefaults
class KeyStorageGood {
    func save(words: [String]) {
        let data = words.joined(separator: " ").data(using: .utf8)!
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "mnemonic",
            kSecValueData as String: data,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }
}
