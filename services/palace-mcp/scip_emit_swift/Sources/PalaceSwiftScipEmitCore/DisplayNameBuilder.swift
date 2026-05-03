import Foundation

/// Builds human-readable display names for SCIP symbol information.
///
/// This is a UX field only. Cross-document identity uses `SymbolBuilder.scipSymbol`.
public enum DisplayNameBuilder {
    public static func displayName<Kind>(
        name: String,
        kind: Kind,
        parentChain: [String] = []
    ) -> String {
        displayName(
            name: name,
            kindDescription: String(describing: kind),
            parentChain: parentChain
        )
    }

    public static func displayName(
        name: String,
        kindDescription: String,
        parentChain: [String] = []
    ) -> String {
        let normalized = kindDescription
            .replacingOccurrences(of: "_", with: "")
            .lowercased()

        let suffix: String
        switch normalized {
        case "class", "struct", "enum", "protocol", "extension", "typealias",
            "associatedtype":
            suffix = "#"
        case "instancemethod", "classmethod", "staticmethod", "constructor",
            "destructor", "function", "freefunction", "method":
            suffix = "()."
        default:
            suffix = "."
        }

        return (parentChain + ["\(name)\(suffix)"]).joined()
    }
}
