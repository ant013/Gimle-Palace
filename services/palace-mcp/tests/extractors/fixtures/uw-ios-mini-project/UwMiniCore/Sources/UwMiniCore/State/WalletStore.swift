import Foundation
import Observation

@Observable
public final class WalletStore {
    private let repository: WalletRepository
    public private(set) var wallets: [Wallet] = []
    public private(set) var selectedWallet: Wallet?

    public init(repository: WalletRepository = InMemoryWalletRepository()) {
        self.repository = repository
    }

    @MainActor
    public func refresh() async throws {
        wallets = try await repository.loadWallets()
        selectedWallet = wallets.first
    }

    public func select(walletID: Int) {
        selectedWallet = wallets.first { wallet in
            wallet.id == walletID
        }
    }

    public func title(for wallet: Wallet) -> String {
        wallet.displayTitle
    }
}
