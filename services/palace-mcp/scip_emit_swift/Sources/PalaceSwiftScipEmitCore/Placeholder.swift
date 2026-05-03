import Foundation

public enum PalaceSwiftScipEmitCore {
    public static let version = "0.1.0"
}

public enum EmitterError: Error, LocalizedError {
    case derivedDataNotFound(String)
    case projectRootNotFound(String)
    case dataStoreNotFound(String)
    case payloadSerializationFailed(String)
    case pythonSerializerNotFound(String)
    case pythonSerializerFailed(String)

    public var errorDescription: String? {
        switch self {
        case .derivedDataNotFound(let path):
            "DerivedData path does not exist: \(path)"
        case .projectRootNotFound(let path):
            "Project root path does not exist: \(path)"
        case .dataStoreNotFound(let path):
            "Could not locate Index.noindex/DataStore or Index/DataStore inside: \(path)"
        case .payloadSerializationFailed(let reason):
            "Could not serialize Swift emitter payload: \(reason)"
        case .pythonSerializerNotFound(let path):
            "Could not locate Python SCIP serializer at: \(path)"
        case .pythonSerializerFailed(let reason):
            "Python SCIP serializer failed: \(reason)"
        }
    }
}
