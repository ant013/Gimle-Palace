import Foundation

private let scipRoleDefinition = 1
private let scipRoleWriteAccess = 4
private let scipRoleForwardDefinition = 64

public struct ScipEmitter {
    public struct OutputSummary: Sendable {
        public let documentCount: Int
        public let occurrenceCount: Int
        public let symbolCount: Int
    }

    public init() {}

    @discardableResult
    public func emit(
        reader: IndexStoreReader,
        outputURL: URL,
        includeFilters: [String] = [],
        excludeFilters: [String] = [],
        arguments: [String] = []
    ) throws -> OutputSummary {
        let filter = PathFilter(includes: includeFilters, excludes: excludeFilters)
        let recordsByFile = reader.collectOccurrencesByFile(pathFilter: filter)
        let payload = buildPayload(
            recordsByFile: recordsByFile,
            projectRoot: reader.projectRoot,
            arguments: arguments
        )
        try writePayload(payload, outputURL: outputURL)

        let occurrenceCount = payload.documents.reduce(0) { $0 + $1.occurrences.count }
        return OutputSummary(
            documentCount: payload.documents.count,
            occurrenceCount: occurrenceCount,
            symbolCount: payload.symbolCount
        )
    }

    private func buildPayload(
        recordsByFile: [String: [OccurrenceRecord]],
        projectRoot: URL,
        arguments: [String]
    ) -> ScipPayload {
        let documents = recordsByFile.keys.sorted().compactMap { relativePath -> ScipPayload.Document? in
            guard let records = recordsByFile[relativePath], !records.isEmpty else {
                return nil
            }

            let occurrences = records.map { record in
                ScipPayload.Occurrence(
                    range: [max(record.line, 0), max(record.utf8Column, 0), max(record.utf8Column, 0)],
                    symbol: SymbolBuilder.scipSymbol(usr: record.usr),
                    symbolRoles: scipRoles(for: record.roles)
                )
            }

            return ScipPayload.Document(
                language: "swift",
                relativePath: relativePath,
                occurrences: occurrences
            )
        }

        return ScipPayload(
            metadata: .init(
                projectRoot: projectRoot.path,
                toolName: "palace-swift-scip-emit",
                toolVersion: PalaceSwiftScipEmitCore.version,
                arguments: arguments
            ),
            documents: documents
        )
    }

    private func writePayload(_ payload: ScipPayload, outputURL: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        let payloadData: Data
        do {
            payloadData = try encoder.encode(payload)
        } catch {
            throw EmitterError.payloadSerializationFailed(error.localizedDescription)
        }

        let fileManager = FileManager.default
        try fileManager.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: nil
        )

        let tempPayloadURL = fileManager.temporaryDirectory
            .appendingPathComponent("palace-swift-scip-payload-\(UUID().uuidString)")
            .appendingPathExtension("json")
        try payloadData.write(to: tempPayloadURL)
        defer { try? fileManager.removeItem(at: tempPayloadURL) }

        let scriptURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("scripts")
            .appendingPathComponent("build_scip.py")

        guard fileManager.fileExists(atPath: scriptURL.path) else {
            throw EmitterError.pythonSerializerNotFound(scriptURL.path)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [
            scriptURL.path,
            "--payload",
            tempPayloadURL.path,
            "--output",
            outputURL.path,
        ]

        let stderrPipe = Pipe()
        process.standardError = stderrPipe
        process.standardOutput = Pipe()

        try process.run()
        process.waitUntilExit()

        let stderrData = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        let stderrText = String(data: stderrData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard process.terminationStatus == 0 else {
            throw EmitterError.pythonSerializerFailed(
                stderrText.isEmpty ? "exit status \(process.terminationStatus)" : stderrText
            )
        }
    }

    private func scipRoles(for roles: SymbolRole) -> Int {
        if roles.contains(.definition) {
            return scipRoleDefinition
        }
        if roles.contains(.declaration) {
            return scipRoleForwardDefinition
        }
        if roles.contains(.write) {
            return scipRoleWriteAccess
        }
        return 0
    }
}

private struct ScipPayload: Encodable {
    struct Metadata: Encodable {
        let projectRoot: String
        let toolName: String
        let toolVersion: String
        let arguments: [String]
    }

    struct Document: Encodable {
        let language: String
        let relativePath: String
        let occurrences: [Occurrence]
    }

    struct Occurrence: Encodable {
        let range: [Int]
        let symbol: String
        let symbolRoles: Int

        enum CodingKeys: String, CodingKey {
            case range
            case symbol
            case symbolRoles = "symbol_roles"
        }
    }

    let metadata: Metadata
    let documents: [Document]

    var symbolCount: Int {
        Set(
            documents
                .flatMap(\.occurrences)
                .map(\.symbol)
        ).count
    }
    init(metadata: Metadata, documents: [Document]) {
        self.metadata = metadata
        self.documents = documents
    }
}
