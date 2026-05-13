import Resolver
import Foundation

final class WalletManager {
    @Injected var api: WalletAPI

    init(clock: Clock) {
        _ = clock
    }

    func refresh() {
        let session = URLSession.shared
        _ = session
    }
}
