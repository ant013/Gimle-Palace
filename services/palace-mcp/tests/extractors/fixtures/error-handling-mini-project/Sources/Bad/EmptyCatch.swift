import Foundation

enum EmptyCatchError: Error {
    case failed
}

func riskyEmptyCatch() throws {}

func emptyCatchBad() {
    do {
        try riskyEmptyCatch()
    } catch { }
}

func emptyCatchReturnBad() {
    do {
        try riskyEmptyCatch()
    } catch { return }
}
