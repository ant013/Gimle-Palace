import Foundation
import UwMiniCore

@main
struct UwMiniApp {
    static func main() async throws {
        let store = WalletStore()
        try await store.refresh()
        store.select(walletID: 2)
        if let selectedWallet = store.selectedWallet {
            print(store.title(for: selectedWallet))
        }
    }
}
