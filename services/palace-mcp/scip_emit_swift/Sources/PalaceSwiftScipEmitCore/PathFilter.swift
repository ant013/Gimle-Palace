import Foundation

/// Path filter for the Swift SCIP emitter.
///
/// The emitter excludes only system and user-requested paths. Project-local
/// vendor paths still pass through and are classified later by the Python
/// extractor during phase routing.
public struct PathFilter {
    public let includes: [String]
    public let excludes: [String]

    public static let alwaysExcludePrefixes: [String] = [
        "/Library/Developer/",
        "/Applications/Xcode.app/",
        "/Applications/Xcode-beta.app/",
    ]

    public init(includes: [String] = [], excludes: [String] = []) {
        self.includes = includes
        self.excludes = excludes
    }

    public func accepts(absolutePath: String, relativePath: String) -> Bool {
        if Self.alwaysExcludePrefixes.contains(where: { absolutePath.hasPrefix($0) }) {
            return false
        }

        if excludes.contains(where: { relativePath.contains($0) }) {
            return false
        }

        if !includes.isEmpty && !includes.contains(where: { relativePath.contains($0) }) {
            return false
        }

        return true
    }
}
