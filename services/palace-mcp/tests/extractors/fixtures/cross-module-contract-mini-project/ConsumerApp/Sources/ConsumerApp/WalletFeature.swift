import ProducerKit

struct WalletFeature {
    func render() -> Int {
        let wallet = Wallet(id: "fixture")
        return wallet.balance()
    }

    func packageOnly() -> String {
        packageHelper()
    }
}
