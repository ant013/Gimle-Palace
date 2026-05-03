import XCTest
@testable import PalaceSwiftScipEmitCore

final class DisplayNameTests: XCTestCase {
    func testStructDisplayName() {
        XCTAssertEqual(
            DisplayNameBuilder.displayName(name: "Wallet", kindDescription: "struct"),
            "Wallet#"
        )
    }

    func testNestedMethodDisplayName() {
        XCTAssertEqual(
            DisplayNameBuilder.displayName(
                name: "select",
                kindDescription: "instanceMethod",
                parentChain: ["WalletStore#"]
            ),
            "WalletStore#select()."
        )
    }

    func testPropertyDisplayName() {
        XCTAssertEqual(
            DisplayNameBuilder.displayName(
                name: "selectedID",
                kindDescription: "instanceProperty",
                parentChain: ["WalletStore#"]
            ),
            "WalletStore#selectedID."
        )
    }
}
