import Foundation
import SwiftProtobuf

public enum EmitterError: Error, CustomStringConvertible {
    case derivedDataNotFound(path: String)
    case dataStoreNotFound(path: String)
    case libIndexStoreNotFound(path: String)

    public var description: String {
        switch self {
        case .derivedDataNotFound(let path):
            return "DerivedData not found: \(path)"
        case .dataStoreNotFound(let path):
            return "IndexStore DataStore not found under DerivedData: \(path)"
        case .libIndexStoreNotFound(let path):
            return "libIndexStore.dylib not found: \(path)"
        }
    }
}

public struct EmitSummary {
    public let documentCount: Int
    public let occurrenceCount: Int
}

public enum EmitterRunner {
    public static func run(
        derivedData: URL,
        projectRoot: URL,
        output: URL,
        pathFilter: PathFilter = PathFilter()
    ) throws -> EmitSummary {
        guard FileManager.default.fileExists(atPath: derivedData.path) else {
            throw EmitterError.derivedDataNotFound(path: derivedData.path)
        }
        let index: Scip_Index
        if IndexStoreReader.dataStoreIfPresent(in: derivedData) == nil {
            index = ScipEmitter.emptyIndex(projectRoot: projectRoot)
        } else {
            let reader = try IndexStoreReader(derivedDataPath: derivedData, projectRoot: projectRoot)
            let emitter = ScipEmitter(reader: reader, projectRoot: projectRoot, pathFilter: pathFilter)
            index = try emitter.emit()
        }
        let parent = output.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        try index.serializedData().write(to: output)
        return EmitSummary(
            documentCount: index.documents.count,
            occurrenceCount: index.documents.reduce(0) { $0 + $1.occurrences.count }
        )
    }
}
