import Foundation

final class WalletAssembler {
    func build() {
        let resolver = Resolver.root
        _ = resolver.resolve(WalletService.self)
    }
}
