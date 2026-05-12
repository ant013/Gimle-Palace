import SwiftUI

struct AccessibleView: View {
    var body: some View {
        VStack {
            // All images have accessibility labels — should NOT trigger rule
            Image("logo").accessibilityLabel(Text("App logo"))
            Image(systemName: "star.fill").accessibilityLabel("Favourite")
            // Decorative image — explicitly hidden from a11y
            Image("background-texture").accessibilityHidden(true)
        }
    }
}
