import Foundation

enum CryptoSignerError: Error {
    case failed
}

func riskySigner() throws {}
func signPayload() throws -> String { "ok" }

struct CryptoSigner {
    func sign() {
        do {
            try riskySigner()
        } catch { }
    }

    func signWithTryOptional() -> String? {
        try? signPayload()
    }
}
