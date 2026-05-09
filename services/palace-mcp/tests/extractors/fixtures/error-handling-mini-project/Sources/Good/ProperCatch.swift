import Foundation

enum ProperCatchError: Error {
    case failed
}

func properRisky() throws {}

func properCatchGood() throws {
    do {
        try properRisky()
    } catch let error as ProperCatchError {
        log(error)
        throw error
    }
}

func log(_ error: ProperCatchError) {}
