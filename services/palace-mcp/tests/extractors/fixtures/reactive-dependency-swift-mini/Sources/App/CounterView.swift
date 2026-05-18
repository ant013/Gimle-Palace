import SwiftUI
import Combine

struct CounterView: View {
    @State private var count = 0
    @Binding var externalCount: Int
    @ObservedObject var session: SessionModel

    var body: some View {
        VStack {
            Text("\\(count)")
            Stepper("External", value: $externalCount)
        }
            .onChange(of: count) { _, _ in
                externalCount = count
            }
            .task {
                session.bindTicker(Just(count).eraseToAnyPublisher())
            }
     }
}
