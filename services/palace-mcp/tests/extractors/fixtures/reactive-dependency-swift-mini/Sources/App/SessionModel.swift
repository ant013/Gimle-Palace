import Combine
import SwiftUI

final class SessionModel: ObservableObject {
    @Published var username = ""
    let ticker = PassthroughSubject<String, Never>()
    private var cancellables = Set<AnyCancellable>()

    init() {
        ticker
            .sink { [weak self] value in
                self?.username = value
            }
            .store(in: &cancellables)
    }

    func bindTicker(_ publisher: AnyPublisher<Int, Never>) {
        publisher
            .map(String.init)
            .sink { [weak self] value in
                self?.username = value
            }
            .store(in: &cancellables)
    }
}
