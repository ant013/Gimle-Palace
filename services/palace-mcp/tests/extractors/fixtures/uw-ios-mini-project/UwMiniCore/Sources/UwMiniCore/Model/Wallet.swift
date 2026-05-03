import Foundation

public struct Wallet: Codable, Equatable, Identifiable, Sendable {
    public let id: Int
    public var name: String
    public var coinCode: String
    public var balance: Decimal

    public init(id: Int, name: String, coinCode: String, balance: Decimal) {
        self.id = id
        self.name = name
        self.coinCode = coinCode
        self.balance = balance
    }

    public var displayTitle: String {
        "\(name) (\(coinCode.uppercased()))"
    }
}
