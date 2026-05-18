import SwiftUI

struct LocalizedView: View {
    var body: some View {
        VStack {
            // Properly localised — NSLocalizedString key
            Text(NSLocalizedString("hello_world", comment: "greeting"))
            // Text(verbatim:) is deliberate — should NOT be flagged (spec §9 R2)
            Text(verbatim: "Bitcoin")
            Text(verbatim: "Ethereum")
            // String(localized:) pattern
            Text(String(localized: "sign_in_button"))
        }
    }
}
