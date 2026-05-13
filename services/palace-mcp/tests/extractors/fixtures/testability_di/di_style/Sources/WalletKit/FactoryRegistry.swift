import Factory

struct FactoryRegistry {
    let walletService = Factory<WalletService> { WalletService.live }
}
