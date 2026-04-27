"""3-round eviction for SymbolOccurrenceShadow (GIM-101a, T7).

Architect Finding F2 + Silent-failure F1: ON ERROR FAIL semantics on all
Cypher eviction rounds. If any round fails the entire eviction raises
ExtractorError — caller must decide whether to abort the run.

Round 1 — remove low-importance shadow nodes (bulk delete by score).
Round 2 — remove oldest duplicates per symbol when per-symbol cap exceeded.
Round 3 — remove excess nodes when global cap exceeded (project-scoped).

NEVER-DELETE invariant: def and decl kinds are never evicted regardless
of score or age. Both rounds 1 and 2 guard with `n.kind NOT IN ['def','decl']`.
"""

from __future__ import annotations

from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.errors import ExtractorError, ExtractorErrorCode

# ---------------------------------------------------------------------------
# Cypher — Round 1: low-importance bulk eviction
# ---------------------------------------------------------------------------

_EVICT_R1_CYPHER = """\
MATCH (n:SymbolOccurrenceShadow {group_id: $group_id})
WHERE n.importance < $importance_threshold
  AND n.kind NOT IN ['def', 'decl']
WITH n ORDER BY n.importance ASC, n.last_seen_at ASC
LIMIT $batch_size
DETACH DELETE n
"""

# ---------------------------------------------------------------------------
# Cypher — Round 2: per-symbol cap (oldest uses deleted first)
# ---------------------------------------------------------------------------

_EVICT_R2_CYPHER = """\
MATCH (n:SymbolOccurrenceShadow {group_id: $group_id})
WHERE n.kind NOT IN ['def', 'decl']
WITH n.symbol_qualified_name AS sym,
     n ORDER BY n.last_seen_at ASC
WITH sym, collect(n) AS nodes
WHERE size(nodes) > $per_symbol_cap
UNWIND nodes[0..size(nodes) - $per_symbol_cap] AS victim
DETACH DELETE victim
"""

# ---------------------------------------------------------------------------
# Cypher — Round 3: global project cap (lowest importance deleted first)
# ---------------------------------------------------------------------------

_COUNT_CYPHER = """\
MATCH (n:SymbolOccurrenceShadow {group_id: $group_id})
RETURN count(n) AS total
"""

_EVICT_R3_CYPHER = """\
MATCH (n:SymbolOccurrenceShadow {group_id: $group_id})
WHERE n.kind NOT IN ['def', 'decl']
WITH n ORDER BY n.importance ASC, n.last_seen_at ASC
LIMIT $evict_count
DETACH DELETE n
"""


async def run_eviction(
    driver: AsyncDriver,
    *,
    group_id: str,
    importance_threshold: float,
    per_symbol_cap: int,
    global_cap: int,
    batch_size: int = 10_000,
) -> tuple[int, int, int]:
    """Execute 3 eviction rounds and return (r1_deleted, r2_deleted, r3_deleted).

    Raises ExtractorError on any round failure (ON ERROR FAIL semantics, F1).
    All three rounds skip def/decl nodes — those are never evicted.
    """
    r1 = await _round1(
        driver,
        group_id=group_id,
        importance_threshold=importance_threshold,
        batch_size=batch_size,
    )
    r2 = await _round2(driver, group_id=group_id, per_symbol_cap=per_symbol_cap)
    r3 = await _round3(driver, group_id=group_id, global_cap=global_cap)
    return r1, r2, r3


async def _round1(
    driver: AsyncDriver,
    *,
    group_id: str,
    importance_threshold: float,
    batch_size: int,
) -> int:
    try:
        async with driver.session() as session:
            result = await session.run(
                _EVICT_R1_CYPHER,
                group_id=group_id,
                importance_threshold=importance_threshold,
                batch_size=batch_size,
            )
            summary = await result.consume()
            return summary.counters.nodes_deleted
    except Exception as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.EVICTION_ROUND_1_FAILED,
            message=f"Eviction round 1 failed for group_id={group_id}: {exc}",
            recoverable=False,
            action="retry",
            context={"group_id": group_id, "cause": str(exc)},
        ) from exc


async def _round2(
    driver: AsyncDriver,
    *,
    group_id: str,
    per_symbol_cap: int,
) -> int:
    try:
        async with driver.session() as session:
            result = await session.run(
                _EVICT_R2_CYPHER,
                group_id=group_id,
                per_symbol_cap=per_symbol_cap,
            )
            summary = await result.consume()
            return summary.counters.nodes_deleted
    except Exception as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.EVICTION_ROUND_2_FAILED,
            message=f"Eviction round 2 failed for group_id={group_id}: {exc}",
            recoverable=False,
            action="retry",
            context={"group_id": group_id, "cause": str(exc)},
        ) from exc


async def _round3(
    driver: AsyncDriver,
    *,
    group_id: str,
    global_cap: int,
) -> int:
    try:
        async with driver.session() as session:
            count_result = await session.run(_COUNT_CYPHER, group_id=group_id)
            records = await count_result.data()
            total = records[0]["total"] if records else 0

            if total <= global_cap:
                return 0

            evict_count = total - global_cap
            result = await session.run(
                _EVICT_R3_CYPHER,
                group_id=group_id,
                evict_count=evict_count,
            )
            summary = await result.consume()
            return summary.counters.nodes_deleted
    except ExtractorError:
        raise
    except Exception as exc:
        raise ExtractorError(
            error_code=ExtractorErrorCode.EVICTION_ROUND_3_FAILED,
            message=f"Eviction round 3 failed for group_id={group_id}: {exc}",
            recoverable=False,
            action="retry",
            context={"group_id": group_id, "cause": str(exc)},
        ) from exc
