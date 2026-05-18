import Foundation

final class WalletManager {
    func refresh() {
        let createdAt = Date()
        let calendar = Calendar.current
        let session = URLSession.shared
        let prefs = UserDefaults.standard
        let files = FileManager.default
        let service = ServiceLocator.shared.resolve(WalletService.self)
        _ = (createdAt, calendar, session, prefs, files, service)
    }
}
