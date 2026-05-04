import ArgumentParser
import Foundation
import PalaceSwiftScipEmitCore

@main
struct PalaceSwiftScipEmit: ParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "palace-swift-scip-emit",
        abstract: "Emit canonical Sourcegraph SCIP protobuf from Xcode IndexStoreDB.",
        version: "0.1.0"
    )

    @Option(name: .long, help: "Path to Xcode DerivedData root for the project.")
    var derivedData: String

    @Option(name: .long, help: "Project root path used for relative-path normalization.")
    var projectRoot: String

    @Option(name: [.short, .long], help: "Output path for the SCIP protobuf file.")
    var output: String

    @Option(name: .long, parsing: .upToNextOption, help: "Optional include path fragments relative to project-root.")
    var include: [String] = []

    @Option(name: .long, parsing: .upToNextOption, help: "Optional exclude path fragments relative to project-root.")
    var exclude: [String] = []

    @Flag(help: "Verbose progress output.")
    var verbose = false

    mutating func run() throws {
        let summary = try EmitterRunner.run(
            derivedData: URL(fileURLWithPath: derivedData),
            projectRoot: URL(fileURLWithPath: projectRoot),
            output: URL(fileURLWithPath: output),
            pathFilter: PathFilter(includes: include, excludes: exclude)
        )
        if verbose {
            print("documents=\(summary.documentCount) occurrences=\(summary.occurrenceCount) output=\(output)")
        }
    }
}
