import Foundation

public enum FooVendorFormatter {
    public static func render(label: String) -> String {
        "[vendor] \(label)"
    }
}
