import SwiftUI
import UIKit

struct HardcodedView: View {
    var body: some View {
        // loc.hardcoded_swiftui — should trigger
        Text("Hello World")
    }
}

class HardcodedVC: UIViewController {
    func setup() {
        let label = UILabel()
        // loc.hardcoded_uikit — should trigger
        label.text = "Tap here"
    }
}
