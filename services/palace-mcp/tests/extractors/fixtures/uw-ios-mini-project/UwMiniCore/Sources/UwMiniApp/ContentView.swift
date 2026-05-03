import Foundation
import UwMiniCore

struct ContentView {
    private let store: WalletStore

    init(store: WalletStore) {
        self.store = store
    }

    func bootstrap() async throws {
        try await store.refresh()
        store.select(walletID: 2)
    }

    var renderedTitle: String? {
        guard let selectedWallet = store.selectedWallet else {
            return nil
        }
        return store.title(for: selectedWallet)
    }
}
