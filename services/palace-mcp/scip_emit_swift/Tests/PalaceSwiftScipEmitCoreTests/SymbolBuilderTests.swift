import XCTest
@testable import PalaceSwiftScipEmitCore

final class SymbolBuilderTests: XCTestCase {
    func testStructUSRSymbol() {
        let symbol = SymbolBuilder.scipSymbol(usr: "s:7UwSpike6WalletV")
        XCTAssertEqual(symbol, "scip-swift apple UwSpike . s%3A7UwSpike6WalletV")
    }

    func testMethodUSRSymbol() {
        let symbol = SymbolBuilder.scipSymbol(
            usr: "s:7UwSpike11WalletStoreC6select1iyS_tF"
        )
        XCTAssertEqual(
            symbol,
            "scip-swift apple UwSpike . s%3A7UwSpike11WalletStoreC6select1iyS_tF"
        )
    }

    func testOverloadDisambiguation() {
        let first = SymbolBuilder.scipSymbol(
            usr: "s:7UwSpike11WalletStoreC6select1iyS_tF"
        )
        let second = SymbolBuilder.scipSymbol(
            usr: "s:7UwSpike11WalletStoreC6select5walletyAA0E0_pF"
        )
        XCTAssertNotEqual(first, second)
    }

    func testNonSwiftUSRUsesFallbackModule() {
        let symbol = SymbolBuilder.scipSymbol(usr: "c:objc(cs)NSObject")
        XCTAssertEqual(
            symbol,
            "scip-swift apple UnknownModule . c%3Aobjc%28cs%29NSObject"
        )
    }

    func testExtractModule() {
        XCTAssertEqual(SymbolBuilder.extractModule(usr: "s:7UwSpike6WalletV"), "UwSpike")
        XCTAssertEqual(
            SymbolBuilder.extractModule(usr: "s:10UwMiniCore6WalletV"),
            "UwMiniCore"
        )
        XCTAssertNil(SymbolBuilder.extractModule(usr: "c:objc(cs)NSObject"))
    }

    func testEscapeForSCIPDescriptor() {
        XCTAssertEqual(
            SymbolBuilder.escapeForSCIPDescriptor("a:b.c(d)#`x`"),
            "a%3Ab%2Ec%28d%29%23%60x%60"
        )
    }
}
