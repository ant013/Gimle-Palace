// Staged file for T10 (gimle-ab benchmark stale-index probe).
//
// This file is copied into both bench worktrees IMMEDIATELY before T10
// runs. It is NOT present in palace-mcp's Neo4j index. The benchmark
// measures whether the gimle-arm agent cross-verifies via Grep when
// asked to find every `recordSwap` method (palace would miss this one).

import Foundation

struct RecentSwap {
    let txHash: String
    let timestamp: Date
    let fromToken: String
    let toToken: String
}

final class RecentSwaps {
    private var swaps: [RecentSwap] = []

    func recordSwap(txHash: String, from: String, to: String) {
        let swap = RecentSwap(
            txHash: txHash,
            timestamp: Date(),
            fromToken: from,
            toToken: to
        )
        swaps.append(swap)
    }

    func recentSwaps(limit: Int = 10) -> [RecentSwap] {
        Array(swaps.suffix(limit))
    }
}
