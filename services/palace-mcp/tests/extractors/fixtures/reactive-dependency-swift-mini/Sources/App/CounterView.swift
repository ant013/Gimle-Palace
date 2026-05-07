import SwiftUI

struct CounterView: View {
    @State private var count = 0

    var body: some View {
        Text("\\(count)")
            .onChange(of: count) { _, _ in
                count += 1
            }
    }
}
