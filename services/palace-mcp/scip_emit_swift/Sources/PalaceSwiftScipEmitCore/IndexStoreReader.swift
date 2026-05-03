import Foundation
import IndexStoreDB

struct OccurrenceRecord {
    let usr: String
    let name: String
    let kind: IndexSymbolKind
    let roles: SymbolRole
    let line: Int
    let column: Int
}

struct IndexStoreReader {
    let derivedData: URL
    let projectRoot: URL
    private let store: IndexStoreDB

    init(derivedDataPath: URL, projectRoot: URL, libIndexStorePath: URL? = nil) throws {
        self.derivedData = derivedDataPath
        self.projectRoot = projectRoot

        let dataStorePath = try Self.locateDataStore(in: derivedDataPath)
        let libPath: URL
        if let libIndexStorePath {
            libPath = libIndexStorePath
        } else {
            libPath = try Self.defaultLibIndexStorePath()
        }
        let library = try IndexStoreLibrary(dylibPath: libPath.path)
        let dbPath = derivedDataPath.appendingPathComponent(".palace-scip-cache")

        self.store = try IndexStoreDB(
            storePath: dataStorePath.path,
            databasePath: dbPath.path,
            library: library,
            listenToUnitEvents: false
        )
        store.pollForUnitChangesAndWait()
    }

    static func locateDataStore(in derivedData: URL) throws -> URL {
        let noindex = derivedData.appendingPathComponent("Index.noindex/DataStore")
        if FileManager.default.fileExists(atPath: noindex.path) {
            return noindex
        }

        let legacy = derivedData.appendingPathComponent("Index/DataStore")
        if FileManager.default.fileExists(atPath: legacy.path) {
            return legacy
        }

        throw EmitterError.dataStoreNotFound(path: derivedData.path)
    }

    static func defaultLibIndexStorePath() throws -> URL {
        let developerDir = ProcessInfo.processInfo.environment["DEVELOPER_DIR"]
            ?? "/Applications/Xcode.app/Contents/Developer"
        let libPath = URL(fileURLWithPath: developerDir)
            .appendingPathComponent("Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib")
        guard FileManager.default.fileExists(atPath: libPath.path) else {
            throw EmitterError.libIndexStoreNotFound(path: libPath.path)
        }
        return libPath
    }

    func countSymbols() -> Int {
        var seen = Set<String>()
        for name in store.allSymbolNames() {
            for occurrence in store.canonicalOccurrences(ofName: name) {
                if !occurrence.symbol.usr.isEmpty {
                    seen.insert(occurrence.symbol.usr)
                }
            }
        }
        return seen.count
    }

    func collectOccurrencesByFile(pathFilter: PathFilter) -> [String: [OccurrenceRecord]] {
        var seenUSRs = Set<String>()
        for name in store.allSymbolNames() {
            for occurrence in store.canonicalOccurrences(ofName: name) {
                if !occurrence.symbol.usr.isEmpty {
                    seenUSRs.insert(occurrence.symbol.usr)
                }
            }
        }

        var result: [String: [OccurrenceRecord]] = [:]
        let rootPath = projectRoot.path
        for usr in seenUSRs.sorted() {
            store.forEachSymbolOccurrence(byUSR: usr, roles: .all) { occurrence in
                let absolutePath = occurrence.location.path
                guard absolutePath.hasPrefix(rootPath + "/") else {
                    return true
                }

                let relativePath = String(absolutePath.dropFirst(rootPath.count + 1))
                guard relativePath.hasSuffix(".swift") else {
                    return true
                }
                guard pathFilter.accepts(absolutePath: absolutePath, relativePath: relativePath) else {
                    return true
                }

                result[relativePath, default: []].append(
                    OccurrenceRecord(
                        usr: occurrence.symbol.usr,
                        name: occurrence.symbol.name,
                        kind: occurrence.symbol.kind,
                        roles: occurrence.roles,
                        line: occurrence.location.line,
                        column: occurrence.location.utf8Column
                    )
                )
                return true
            }
        }
        return result
    }
}
