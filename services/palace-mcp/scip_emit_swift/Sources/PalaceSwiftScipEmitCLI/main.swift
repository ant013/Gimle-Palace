import ArgumentParser
import Foundation
import PalaceSwiftScipEmitCore

@main
struct PalaceSwiftScipEmit: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "palace-swift-scip-emit",
        abstract: "Emit canonical Sourcegraph SCIP protobuf from Xcode IndexStoreDB.",
        version: PalaceSwiftScipEmitCore.version
    )

    @Option(name: .long, help: "Path to Xcode DerivedData root for the project.")
    var derivedData: String

    @Option(name: .long, help: "Project root path (used for relative-path normalization).")
    var projectRoot: String

    @Option(name: [.short, .long], help: "Output path for SCIP protobuf file.")
    var output: String

    @Option(name: .long, help: "Optional explicit path to libIndexStore.dylib.")
    var libIndexStorePath: String?

    @Option(
        name: .long,
        parsing: .upToNextOption,
        help: "Optional include path globs (relative to project-root). Default: all in-project paths."
    )
    var include: [String] = []

    @Option(
        name: .long,
        parsing: .upToNextOption,
        help: "Optional exclude path globs (in addition to system-framework defaults). Default: empty."
    )
    var exclude: [String] = []

    @Flag(help: "Verbose progress output.")
    var verbose: Bool = false

    mutating func run() throws {
        let reader = try IndexStoreReader(
            derivedDataPath: URL(fileURLWithPath: derivedData),
            projectRoot: URL(fileURLWithPath: projectRoot),
            libIndexStorePath: libIndexStorePath.map { URL(fileURLWithPath: $0) }
        )
        let emitter = ScipEmitter()
        let summary = try emitter.emit(
            reader: reader,
            outputURL: URL(fileURLWithPath: output),
            includeFilters: include,
            excludeFilters: exclude,
            arguments: CommandLine.arguments
        )

        if verbose {
            let sampledUSRCount = reader.canonicalUSRCount(limit: 1_000)
            FileHandle.standardError.write(
                """
                palace-swift-scip-emit \(PalaceSwiftScipEmitCore.version)
                wrote \(summary.documentCount) documents, \(summary.occurrenceCount) occurrences, \(summary.symbolCount) symbols
                sampled canonical USRs: \(sampledUSRCount)
                output: \(output)

                """.data(using: .utf8)!
            )
        }
    }
}
