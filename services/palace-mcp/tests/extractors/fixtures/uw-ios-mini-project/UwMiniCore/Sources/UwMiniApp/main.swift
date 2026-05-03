import Foundation
import UwMiniCore

let store = WalletStore()
let view = ContentView(store: store)
try await view.bootstrap()
print(view.renderedTitle ?? "No wallet selected")
