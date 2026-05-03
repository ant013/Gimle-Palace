import Foundation
import UwMiniCore

@main
struct UwMiniApp {
    static func main() async throws {
        let store = WalletStore()
        let view = ContentView(store: store)
        try await view.bootstrap()
        print(view.renderedTitle ?? "No wallet selected")
    }
}
