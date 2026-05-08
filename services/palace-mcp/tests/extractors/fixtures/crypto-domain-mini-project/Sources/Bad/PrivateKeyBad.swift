import Foundation

// BAD: mnemonic stored in UserDefaults (triggers words_joined_userdefaults)
class KeyStorageBad {
    func save(words: [String]) {
        UserDefaults.standard.set(words.joined(separator: " "), forKey: "mnemonic_words")
    }
}
