import SwiftProtobuf
@testable import PalaceSwiftScipEmitCore
import XCTest

final class ProtoSmokeTests: XCTestCase {
    func testEmptyIndexRoundtrip() throws {
        let data = try Scip_Index().serializedData()
        let decoded = try Scip_Index(serializedData: data)
        XCTAssertEqual(decoded.documents.count, 0)
    }
}
