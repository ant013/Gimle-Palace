import Foundation

public struct Transaction: Codable, Equatable, Identifiable, Sendable {
    public enum Direction: String, Codable, Sendable {
        case incoming
        case outgoing
    }

    public let id: UUID
    public let walletID: Int
    public let amount: Decimal
    public let direction: Direction
    public let timestamp: Date

    public init(id: UUID, walletID: Int, amount: Decimal, direction: Direction, timestamp: Date) {
        self.id = id
        self.walletID = walletID
        self.amount = amount
        self.direction = direction
        self.timestamp = timestamp
    }
}
