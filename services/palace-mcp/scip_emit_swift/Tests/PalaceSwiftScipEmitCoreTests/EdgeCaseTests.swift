import Foundation
@testable import PalaceSwiftScipEmitCore
import XCTest

final class EdgeCaseTests: XCTestCase {
    func testDeterministicReemitForEmptyDerivedData() throws {
        try withTemporaryDirectory { root in
            let derivedData = root.appendingPathComponent("DerivedData", isDirectory: true)
            let projectRoot = root.appendingPathComponent("Project", isDirectory: true)
            try FileManager.default.createDirectory(at: derivedData, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)

            let out1 = root.appendingPathComponent("first.scip")
            let out2 = root.appendingPathComponent("second.scip")

            let summary1 = try EmitterRunner.run(
                derivedData: derivedData,
                projectRoot: projectRoot,
                output: out1
            )
            let summary2 = try EmitterRunner.run(
                derivedData: derivedData,
                projectRoot: projectRoot,
                output: out2
            )

            XCTAssertEqual(summary1.documentCount, 0)
            XCTAssertEqual(summary1.occurrenceCount, 0)
            XCTAssertEqual(summary2.documentCount, 0)
            XCTAssertEqual(summary2.occurrenceCount, 0)
            XCTAssertEqual(try Data(contentsOf: out1), try Data(contentsOf: out2))
        }
    }

    func testMissingDerivedDataThrowsActionableError() throws {
        try withTemporaryDirectory { root in
            let missing = root.appendingPathComponent("no-such-derived-data", isDirectory: true)
            let projectRoot = root.appendingPathComponent("Project", isDirectory: true)
            try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)
            let output = root.appendingPathComponent("out.scip")

            XCTAssertThrowsError(
                try EmitterRunner.run(
                    derivedData: missing,
                    projectRoot: projectRoot,
                    output: output
                )
            ) { error in
                guard case EmitterError.derivedDataNotFound(let path) = error else {
                    XCTFail("expected derivedDataNotFound, got \(error)")
                    return
                }
                XCTAssertEqual(path, missing.path)
                XCTAssertEqual(error.localizedDescription, "DerivedData not found: \(missing.path)")
            }
        }
    }

    func testEmptyIndexStoreWritesValidEmptyScip() throws {
        try withTemporaryDirectory { root in
            let derivedData = root.appendingPathComponent("DerivedData", isDirectory: true)
            let projectRoot = root.appendingPathComponent("Project", isDirectory: true)
            let output = root.appendingPathComponent("empty.scip")
            try FileManager.default.createDirectory(at: derivedData, withIntermediateDirectories: true)
            try FileManager.default.createDirectory(at: projectRoot, withIntermediateDirectories: true)

            let summary = try EmitterRunner.run(
                derivedData: derivedData,
                projectRoot: projectRoot,
                output: output
            )
            let decoded = try Scip_Index(serializedBytes: Data(contentsOf: output))

            XCTAssertEqual(summary.documentCount, 0)
            XCTAssertEqual(summary.occurrenceCount, 0)
            XCTAssertEqual(decoded.documents.count, 0)
            XCTAssertEqual(decoded.metadata.toolInfo.name, "palace-swift-scip-emit")
        }
    }

    private func withTemporaryDirectory(
        _ body: (URL) throws -> Void
    ) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            UUID().uuidString,
            isDirectory: true
        )
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
}
