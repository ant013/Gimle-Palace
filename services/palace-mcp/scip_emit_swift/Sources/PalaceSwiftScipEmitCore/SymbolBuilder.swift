import Foundation

/// Builds SCIP `symbol` values using the rev3 USR-as-descriptor identity scheme.
public enum SymbolBuilder {
    /// Build the stable SCIP symbol string for an IndexStoreDB USR.
    public static func scipSymbol(usr: String) -> String {
        let module = extractModule(usr: usr) ?? "UnknownModule"
        let escapedUSR = escapeForSCIPDescriptor(usr)
        return "scip-swift apple \(module) . \(escapedUSR)"
    }

    /// Extract the module segment from a mangled Swift USR (`s:<len><module>...`).
    public static func extractModule(usr: String) -> String? {
        guard usr.hasPrefix("s:") else {
            return nil
        }

        let rest = String(usr.dropFirst(2))
        guard let digitStart = rest.firstIndex(where: { $0.isNumber }) else {
            return nil
        }

        var index = digitStart
        var lengthDigits = ""
        while index < rest.endIndex, rest[index].isNumber {
            lengthDigits.append(rest[index])
            index = rest.index(after: index)
        }

        guard
            let moduleLength = Int(lengthDigits),
            moduleLength > 0,
            rest.distance(from: index, to: rest.endIndex) >= moduleLength
        else {
            return nil
        }

        let moduleEnd = rest.index(index, offsetBy: moduleLength)
        return String(rest[index..<moduleEnd])
    }

    /// Percent-encode characters that are special in SCIP descriptor grammar.
    public static func escapeForSCIPDescriptor(_ input: String) -> String {
        var output = ""
        output.reserveCapacity(input.count)

        for scalar in input.unicodeScalars {
            switch scalar {
            case " ":
                output += "%20"
            case "(":
                output += "%28"
            case ")":
                output += "%29"
            case ",":
                output += "%2C"
            case ".":
                output += "%2E"
            case ":":
                output += "%3A"
            case "/":
                output += "%2F"
            case "[":
                output += "%5B"
            case "]":
                output += "%5D"
            case "<":
                output += "%3C"
            case ">":
                output += "%3E"
            case "\\":
                output += "%5C"
            case "#":
                output += "%23"
            case "`":
                output += "%60"
            default:
                output.unicodeScalars.append(scalar)
            }
        }

        return output
    }
}
