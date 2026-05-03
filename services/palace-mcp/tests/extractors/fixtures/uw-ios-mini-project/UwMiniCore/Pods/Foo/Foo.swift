import Foundation
import UwMiniCore

public enum FooVendorFormatter {
    public static func render(label: String) -> String {
        "[vendor] \(label)"
    }

    public static func selectDefaultWallet(in store: WalletStore) {
        store.select(walletID: 2)
    }
}
