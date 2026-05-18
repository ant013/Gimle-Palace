final class GlobalLocator {
    func makeService() -> WalletService {
        ServiceLocator.shared.resolve(WalletService.self)
    }
}
