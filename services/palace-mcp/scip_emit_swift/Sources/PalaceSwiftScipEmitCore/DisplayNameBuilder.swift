import Foundation
import IndexStoreDB

public enum DisplayNameBuilder {
    public static func displayName(name: String, kind: IndexSymbolKind, parentChain: [String] = []) -> String {
        let suffix: String
        switch kind {
        case .class, .struct, .enum, .protocol, .extension, .typealias:
            suffix = "#"
        case .instanceMethod, .classMethod, .staticMethod, .constructor, .destructor, .function:
            suffix = "()."
        case .instanceProperty, .classProperty, .staticProperty, .variable, .field, .parameter, .enumConstant:
            suffix = "."
        default:
            suffix = "."
        }
        return (parentChain + ["\(name)\(suffix)"]).joined()
    }
}
