import SwiftUI

struct MissingLabelView: View {
    var body: some View {
        VStack {
            // Missing .accessibilityLabel — screen reader can't describe this
            Image("logo")
            Image(systemName: "star.fill")
            Image("chart-icon")
        }
    }
}
