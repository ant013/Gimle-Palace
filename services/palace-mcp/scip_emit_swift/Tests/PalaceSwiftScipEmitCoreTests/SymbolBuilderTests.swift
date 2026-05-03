@testable import PalaceSwiftScipEmitCore
import XCTest

final class SymbolBuilderTests: XCTestCase {
    func testSwiftUSRBecomesScipSymbol() {
        XCTAssertEqual(
            SymbolBuilder.scipSymbol(usr: "s:10UwMiniCore11WalletStoreC"),
            "scip-swift apple UwMiniCore . s%3A10UwMiniCore11WalletStoreC"
        )
    }

    func testNonSwiftUSRFallsBackToUnknownModule() {
        XCTAssertEqual(
            SymbolBuilder.scipSymbol(usr: "c:objc(cs)NSObject"),
            "scip-swift apple UnknownModule . c%3Aobjc%28cs%29NSObject"
        )
    }
}
