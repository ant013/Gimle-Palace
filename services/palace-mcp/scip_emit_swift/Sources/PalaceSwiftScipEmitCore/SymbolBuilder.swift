import Foundation

public enum SymbolBuilder {
    public static func scipSymbol(usr: String) -> String {
        let module = extractModule(usr: usr) ?? "UnknownModule"
        return "scip-swift apple \(module) . \(escapeForSCIPDescriptor(usr))"
    }

    public static func extractModule(usr: String) -> String? {
        guard usr.hasPrefix("s:") else {
            return nil
        }

        let rest = String(usr.dropFirst(2))
        guard var cursor = rest.firstIndex(where: { $0.isNumber }) else {
            return nil
        }

        var lengthText = ""
        while cursor < rest.endIndex, rest[cursor].isNumber {
            lengthText.append(rest[cursor])
            cursor = rest.index(after: cursor)
        }

        guard let length = Int(lengthText), length > 0 else {
            return nil
        }
        guard rest.distance(from: cursor, to: rest.endIndex) >= length else {
            return nil
        }

        let end = rest.index(cursor, offsetBy: length)
        return String(rest[cursor..<end])
    }

    public static func escapeForSCIPDescriptor(_ value: String) -> String {
        var output = ""
        output.reserveCapacity(value.count)
        for scalar in value.unicodeScalars {
            switch scalar {
            case " ": output += "%20"
            case "(": output += "%28"
            case ")": output += "%29"
            case ",": output += "%2C"
            case ".": output += "%2E"
            case ":": output += "%3A"
            case "/": output += "%2F"
            case "[": output += "%5B"
            case "]": output += "%5D"
            case "<": output += "%3C"
            case ">": output += "%3E"
            case "\\": output += "%5C"
            case "#": output += "%23"
            case "`": output += "%60"
            default: output.unicodeScalars.append(scalar)
            }
        }
        return output
    }
}
