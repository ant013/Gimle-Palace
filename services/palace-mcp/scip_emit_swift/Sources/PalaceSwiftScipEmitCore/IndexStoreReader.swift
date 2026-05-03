import Foundation
import IndexStoreDB

public struct OccurrenceRecord: Sendable {
    public let usr: String
    public let symbolName: String
    public let absolutePath: String
    public let filePath: String
    public let moduleName: String
    public let line: Int
    public let utf8Column: Int
    public let isSystem: Bool
    public let roles: SymbolRole
}

/// Wraps IndexStoreDB queries for the Swift SCIP emitter.
///
/// Task 3 runtime proof on the operator dev Mac established that:
/// - `allSymbolNames()` succeeds on Xcode 26 DataStore records
/// - `canonicalOccurrences(ofName:)` succeeds when called in a separate pass
/// - the broad empty-pattern canonical traversal from the original draft plan
///   returns 0 USRs on the same store
/// - nesting canonical lookups inside `forEachSymbolName` can trigger LMDB
///   reader-slot reuse (`MDB_BAD_RSLOT`)
///
/// Because of that, all "iterate everything" helpers in this file follow a
/// two-phase model:
/// 1. materialize `allSymbolNames()`
/// 2. iterate those names and call `canonicalOccurrences(ofName:)`
public struct IndexStoreReader {
    public let derivedData: URL
    public let projectRoot: URL
    private let store: IndexStoreDB

    public init(
        derivedDataPath: URL,
        projectRoot: URL,
        libIndexStorePath: URL? = nil
    ) throws {
        guard FileManager.default.fileExists(atPath: derivedDataPath.path) else {
            throw EmitterError.derivedDataNotFound(derivedDataPath.path)
        }
        guard FileManager.default.fileExists(atPath: projectRoot.path) else {
            throw EmitterError.projectRootNotFound(projectRoot.path)
        }

        self.derivedData = derivedDataPath
        self.projectRoot = projectRoot

        let dataStorePath = try Self.locateDataStore(in: derivedDataPath)
        let libPath = libIndexStorePath ?? Self.defaultLibIndexStorePath()
        let library = try IndexStoreLibrary(dylibPath: libPath.path)
        let databasePath = derivedDataPath.appendingPathComponent(".palace-scip-cache")

        self.store = try IndexStoreDB(
            storePath: dataStorePath.path,
            databasePath: databasePath.path,
            library: library,
            listenToUnitEvents: true
        )
        self.store.pollForUnitChangesAndWait()
    }

    public static func locateDataStore(in derivedData: URL) throws -> URL {
        let noindex = derivedData
            .appendingPathComponent("Index.noindex")
            .appendingPathComponent("DataStore")
        if FileManager.default.fileExists(atPath: noindex.path) {
            return noindex
        }

        let legacy = derivedData
            .appendingPathComponent("Index")
            .appendingPathComponent("DataStore")
        if FileManager.default.fileExists(atPath: legacy.path) {
            return legacy
        }

        throw EmitterError.dataStoreNotFound(derivedData.path)
    }

    public static func defaultLibIndexStorePath() -> URL {
        URL(
            fileURLWithPath:
                "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/libIndexStore.dylib"
        )
    }

    public func allSymbolNames() -> [String] {
        store.allSymbolNames()
    }

    public func canonicalUSRCount(limit: Int? = nil) -> Int {
        var seen = Set<String>()
        for name in store.allSymbolNames() {
            for occurrence in store.canonicalOccurrences(ofName: name) {
                let usr = occurrence.symbol.usr
                if usr.isEmpty {
                    continue
                }
                seen.insert(usr)
                if let limit, seen.count >= limit {
                    return seen.count
                }
            }
        }
        return seen.count
    }

    public func collectOccurrencesByFile(
        pathFilter: PathFilter = PathFilter(),
        limitUSRs: Int? = nil
    ) -> [String: [OccurrenceRecord]] {
        var byFile: [String: [OccurrenceRecord]] = [:]
        var seenUSRs = Set<String>()
        var seenOccurrences = Set<String>()

        for name in store.allSymbolNames() {
            let canonicalOccurrences = store.canonicalOccurrences(ofName: name)
            for canonical in canonicalOccurrences {
                let usr = canonical.symbol.usr
                if usr.isEmpty || seenUSRs.contains(usr) {
                    continue
                }
                seenUSRs.insert(usr)

                store.forEachSymbolOccurrence(byUSR: usr, roles: .all) { occurrence in
                    guard occurrence.symbol.language == .swift else {
                        return true
                    }
                    guard let relativePath = relativePathIfInsideProject(occurrence.location.path)
                    else { return true }
                    guard pathFilter.accepts(
                        absolutePath: occurrence.location.path,
                        relativePath: relativePath
                    ) else { return true }

                    let occurrenceKey = [
                        relativePath,
                        String(occurrence.location.line),
                        String(occurrence.location.utf8Column),
                        usr,
                        String(occurrence.roles.rawValue),
                    ].joined(separator: ":")
                    guard !seenOccurrences.contains(occurrenceKey) else {
                        return true
                    }
                    seenOccurrences.insert(occurrenceKey)

                    byFile[relativePath, default: []].append(
                        OccurrenceRecord(
                            usr: usr,
                            symbolName: occurrence.symbol.name,
                            absolutePath: occurrence.location.path,
                            filePath: relativePath,
                            moduleName: occurrence.location.moduleName,
                            line: occurrence.location.line,
                            utf8Column: occurrence.location.utf8Column,
                            isSystem: occurrence.location.isSystem,
                            roles: occurrence.roles
                        )
                    )
                    return true
                }

                if let limitUSRs, seenUSRs.count >= limitUSRs {
                    return sortOccurrences(byFile)
                }
            }
        }

        return sortOccurrences(byFile)
    }

    private func relativePathIfInsideProject(_ absolutePath: String) -> String? {
        let path = URL(fileURLWithPath: absolutePath).standardizedFileURL.path
        let root = projectRoot.standardizedFileURL.path
        guard path.hasPrefix(root) else { return nil }

        if path == root {
            return ""
        }

        let index = path.index(path.startIndex, offsetBy: root.count)
        let remainder = String(path[index...])
        return remainder.hasPrefix("/") ? String(remainder.dropFirst()) : remainder
    }

    private func sortOccurrences(_ input: [String: [OccurrenceRecord]]) -> [String: [OccurrenceRecord]] {
        input.mapValues { records in
            records.sorted {
                ($0.line, $0.utf8Column, $0.usr, $0.symbolName)
                    < ($1.line, $1.utf8Column, $1.usr, $1.symbolName)
            }
        }
    }
}
