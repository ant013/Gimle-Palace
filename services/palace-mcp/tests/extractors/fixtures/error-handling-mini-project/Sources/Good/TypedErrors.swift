import Foundation

enum WalletError: Error {
    case offline
}

func typedResultGood() -> Result<String, WalletError> {
    return Result.failure(.offline)
}

func typedThrowGood() throws {
    throw WalletError.offline
}
