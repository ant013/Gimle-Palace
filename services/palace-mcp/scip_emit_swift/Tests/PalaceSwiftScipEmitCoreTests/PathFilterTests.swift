@testable import PalaceSwiftScipEmitCore
import XCTest

final class PathFilterTests: XCTestCase {
    func testAcceptsProjectVendorPathsByDefault() {
        let filter = PathFilter()
        XCTAssertTrue(filter.accepts(absolutePath: "/repo/Pods/A/Source.swift", relativePath: "Pods/A/Source.swift"))
        XCTAssertTrue(filter.accepts(absolutePath: "/repo/SourcePackages/A/Source.swift", relativePath: "SourcePackages/A/Source.swift"))
    }

    func testRejectsSystemPaths() {
        let filter = PathFilter()
        XCTAssertFalse(filter.accepts(
            absolutePath: "/Applications/Xcode.app/Contents/Developer/usr/lib/Swift.swift",
            relativePath: "Swift.swift"
        ))
    }
}
