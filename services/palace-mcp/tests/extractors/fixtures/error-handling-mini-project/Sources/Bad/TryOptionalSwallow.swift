import Foundation

enum TryOptionalError: Error {
    case failed
}

func riskyTryOptional() throws -> String {
    throw TryOptionalError.failed
}

let swallowedValue = try? riskyTryOptional()
let swallowedDefault = try? riskyTryOptional() ?? "fallback"

func ignoreFailure() {
    _ = try? riskyTryOptional()
}
