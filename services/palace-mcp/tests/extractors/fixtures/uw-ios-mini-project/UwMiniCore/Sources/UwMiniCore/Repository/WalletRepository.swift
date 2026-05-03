import Foundation

public protocol WalletRepository: Sendable {
    func loadWallets() async throws -> [Wallet]
    func transactions(for wallet: Wallet) async throws -> [Transaction]
}

public actor InMemoryWalletRepository: WalletRepository {
    private var wallets: [Wallet]

    public init(wallets: [Wallet]? = nil) {
        self.wallets = wallets ?? InMemoryWalletRepository.defaultWallets
    }

    public func loadWallets() async throws -> [Wallet] {
        wallets
    }

    public func transactions(for wallet: Wallet) async throws -> [Transaction] {
        [
            Transaction(
                id: UUID(),
                walletID: wallet.id,
                amount: wallet.balance,
                direction: .incoming,
                timestamp: Date()
            )
        ]
    }

    private static let defaultWallets = [
        Wallet(id: 1, name: "Bitcoin", coinCode: "btc", balance: 1.25),
        Wallet(id: 2, name: "Ethereum", coinCode: "eth", balance: 7.5),
    ]
}
