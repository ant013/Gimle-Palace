import XCTest
@testable import PalaceSwiftScipEmitCore

final class PathFilterTests: XCTestCase {
    func testAcceptsVendorInsideProject() {
        let filter = PathFilter()

        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/Pods/Alamofire/Source/Alamofire.swift",
                relativePath: "Pods/Alamofire/Source/Alamofire.swift"
            )
        )
        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/SourcePackages/checkouts/Alamofire/Source/Alamofire.swift",
                relativePath: "SourcePackages/checkouts/Alamofire/Source/Alamofire.swift"
            )
        )
        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/.build/release/x.swift",
                relativePath: ".build/release/x.swift"
            )
        )
    }

    func testAcceptsProjectSource() {
        let filter = PathFilter()
        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/UnstoppableWallet/Modules/Wallet.swift",
                relativePath: "UnstoppableWallet/Modules/Wallet.swift"
            )
        )
    }

    func testRejectsSystemFrameworks() {
        let filter = PathFilter()

        XCTAssertFalse(
            filter.accepts(
                absolutePath: "/Library/Developer/CommandLineTools/usr/lib/swift/Foundation.swiftmodule/x.swiftinterface",
                relativePath: ".."
            )
        )
        XCTAssertFalse(
            filter.accepts(
                absolutePath: "/Applications/Xcode.app/Contents/Developer/usr/lib/x.swift",
                relativePath: ".."
            )
        )
    }

    func testUserExcludeAdditive() {
        let filter = PathFilter(excludes: ["GeneratedSources/"])

        XCTAssertFalse(
            filter.accepts(
                absolutePath: "/proj/GeneratedSources/Foo.swift",
                relativePath: "GeneratedSources/Foo.swift"
            )
        )
        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/UwMiniCore/Wallet.swift",
                relativePath: "UwMiniCore/Wallet.swift"
            )
        )
    }

    func testIncludeWhitelist() {
        let filter = PathFilter(includes: ["UwMiniCore/"])

        XCTAssertTrue(
            filter.accepts(
                absolutePath: "/proj/UwMiniCore/Wallet.swift",
                relativePath: "UwMiniCore/Wallet.swift"
            )
        )
        XCTAssertFalse(
            filter.accepts(
                absolutePath: "/proj/UwMiniApp/AppDelegate.swift",
                relativePath: "UwMiniApp/AppDelegate.swift"
            )
        )
    }
}
