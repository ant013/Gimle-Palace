import Foundation

enum CatchOnlyLogsError: Error {
    case failed
}

struct Logger {
    func error(_ message: String) {}
}

func riskyLogOnly() throws {}

func catchOnlyLogsBad(logger: Logger) {
    do {
        try riskyLogOnly()
    } catch { logger.error("swallowed") }
}

func catchOnlyPrintBad() {
    do {
        try riskyLogOnly()
    } catch { print("swallowed") }
}

func genericCatchAllBad() {
    do {
        try riskyLogOnly()
    } catch { consume(error) }
}

func consume(_ value: Any) {}

func stringErrorBad() -> Result<String, Never> {
    return Result.failure("boom")
}
