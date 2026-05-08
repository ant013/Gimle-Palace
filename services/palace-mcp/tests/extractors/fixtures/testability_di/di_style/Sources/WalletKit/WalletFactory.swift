import Foundation

final class WalletFactory {
    private let api: WalletAPI
    private let clock: Clock

    init(api: WalletAPI, clock: Clock) {
        self.api = api
        self.clock = clock
    }
}
