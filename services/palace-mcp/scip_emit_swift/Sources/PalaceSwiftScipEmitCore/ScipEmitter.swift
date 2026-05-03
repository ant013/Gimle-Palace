import Foundation
import IndexStoreDB
import SwiftProtobuf

struct ScipEmitter {
    let reader: IndexStoreReader
    let projectRoot: URL
    let pathFilter: PathFilter

    func emit(toolName: String = "palace-swift-scip-emit", toolVersion: String = "0.1.0") throws -> Scip_Index {
        var index = Scip_Index()
        index.metadata.version = .unspecifiedProtocolVersion
        index.metadata.toolInfo.name = toolName
        index.metadata.toolInfo.version = toolVersion
        index.metadata.projectRoot = "file://\(projectRoot.path)"
        index.metadata.textDocumentEncoding = .utf8

        let byFile = reader.collectOccurrencesByFile(pathFilter: pathFilter)
        for (relativePath, records) in byFile.sorted(by: { $0.key < $1.key }) {
            var document = Scip_Document()
            document.relativePath = relativePath
            document.language = "swift"
            document.positionEncoding = .utf8CodeUnitOffsetFromLineStart

            var seenDefinitionSymbols = Set<String>()
            let sortedRecords = records.sorted {
                ($0.line, $0.column, $0.usr, $0.roles.rawValue) < ($1.line, $1.column, $1.usr, $1.roles.rawValue)
            }
            for record in sortedRecords {
                let symbol = SymbolBuilder.scipSymbol(usr: record.usr)
                var occurrence = Scip_Occurrence()
                occurrence.symbol = symbol
                occurrence.symbolRoles = mapRoles(record.roles)
                occurrence.range = makeRange(line: record.line, column: record.column, name: record.name)
                document.occurrences.append(occurrence)

                if record.roles.contains(.definition), !seenDefinitionSymbols.contains(symbol) {
                    var info = Scip_SymbolInformation()
                    info.symbol = symbol
                    info.kind = mapKind(record.kind)
                    info.displayName = DisplayNameBuilder.displayName(name: record.name, kind: record.kind)
                    document.symbols.append(info)
                    seenDefinitionSymbols.insert(symbol)
                }
            }
            index.documents.append(document)
        }
        return index
    }

    private func mapRoles(_ roles: SymbolRole) -> Int32 {
        var bits: Int32 = 0
        if roles.contains(.definition) || roles.contains(.declaration) {
            bits |= Int32(Scip_SymbolRole.definition.rawValue)
        }
        if roles.contains(.implicit) {
            bits |= Int32(Scip_SymbolRole.import.rawValue)
        }
        if roles.contains(.write) {
            bits |= Int32(Scip_SymbolRole.writeAccess.rawValue)
        }
        if roles.contains(.read) {
            bits |= Int32(Scip_SymbolRole.readAccess.rawValue)
        }
        return bits
    }

    private func makeRange(line: Int, column: Int, name: String) -> [Int32] {
        let startLine = Int32(max(0, line - 1))
        let startColumn = Int32(max(0, column - 1))
        let endColumn = startColumn + Int32(max(1, name.utf8.count))
        return [startLine, startColumn, startLine, endColumn]
    }

    private func mapKind(_ kind: IndexSymbolKind) -> Scip_SymbolInformation.Kind {
        switch kind {
        case .class:
            return .class
        case .struct:
            return .struct
        case .enum:
            return .enum
        case .protocol:
            return .protocol
        case .instanceMethod, .classMethod, .staticMethod:
            return .method
        case .function:
            return .function
        case .instanceProperty, .classProperty, .staticProperty:
            return .property
        case .variable:
            return .variable
        case .field:
            return .field
        case .parameter:
            return .parameter
        case .constructor:
            return .constructor
        case .typealias:
            return .typeAlias
        case .extension:
            return .extension
        default:
            return .unspecifiedKind
        }
    }
}
