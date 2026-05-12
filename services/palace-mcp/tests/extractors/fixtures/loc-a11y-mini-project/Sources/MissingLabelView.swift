import SwiftUI

struct MissingLabelView: View {
    var body: some View {
        // a11y.missing_label_swiftui — should trigger for both
        Image("logo")
        Image(systemName: "star.fill")
    }
}
