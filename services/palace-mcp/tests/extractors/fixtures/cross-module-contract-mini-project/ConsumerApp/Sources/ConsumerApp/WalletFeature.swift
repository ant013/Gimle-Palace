import ProducerKit

struct WalletFeature {
    func render(wallet: Wallet) -> Int {
        wallet.balance()
    }

    func packageOnly() -> String {
        packageHelper()
    }
}
