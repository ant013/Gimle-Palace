"""Neo4j writer for dead_symbol_binary_surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.dead_symbol_binary_surface.correlation import (
    CorrelationResult,
)

_MERGE_CANDIDATE = """
MERGE (candidate:DeadSymbolCandidate {id: $candidate_id})
SET candidate += $candidate_props
"""

_MERGE_BINARY_SURFACE = """
MERGE (surface:BinarySurfaceRecord {id: $surface_id})
SET surface += $surface_props
"""

_MERGE_BACKED_BY_SYMBOL = """
MATCH (candidate:DeadSymbolCandidate {id: $candidate_id})
MATCH (shadow:SymbolOccurrenceShadow {symbol_id: $backed_symbol_id})
MERGE (candidate)-[:BACKED_BY_SYMBOL]->(shadow)
"""

_MERGE_BACKED_BY_PUBLIC_API = """
MATCH (candidate:DeadSymbolCandidate {id: $candidate_id})
MATCH (symbol:PublicApiSymbol {id: $public_symbol_id})
MERGE (candidate)-[:BACKED_BY_PUBLIC_API]->(symbol)
"""

_MERGE_HAS_BINARY_SURFACE = """
MATCH (candidate:DeadSymbolCandidate {id: $candidate_id})
MATCH (surface:BinarySurfaceRecord {id: $surface_id})
MERGE (candidate)-[:HAS_BINARY_SURFACE]->(surface)
"""

_MERGE_BLOCKED_BY_CONTRACT_SYMBOL = """
MATCH (candidate:DeadSymbolCandidate {id: $candidate_id})
MATCH (symbol:PublicApiSymbol {id: $public_symbol_id})
MERGE (candidate)-[rel:BLOCKED_BY_CONTRACT_SYMBOL]->(symbol)
SET rel += $edge_props
"""


@dataclass(frozen=True)
class DeadSymbolWriteSummary:
    """Counter-precise summary from Neo4j write operations."""

    nodes_created: int = 0
    relationships_created: int = 0
    properties_set: int = 0


async def write_dead_symbol_graph(
    *, driver: AsyncDriver, rows: tuple[CorrelationResult, ...]
) -> DeadSymbolWriteSummary:
    """Write dead symbol graph rows in one execute_write transaction."""

    async with driver.session() as session:
        return await session.execute_write(_write_batch, rows)


async def _write_batch(
    tx: Any, rows: tuple[CorrelationResult, ...]
) -> DeadSymbolWriteSummary:
    nodes_created = 0
    relationships_created = 0
    properties_set = 0

    for row in rows:
        candidate = row.candidate
        if candidate is None:
            continue

        summary = await _consume(
            tx,
            _MERGE_CANDIDATE,
            candidate_id=candidate.id,
            candidate_props=candidate.model_dump(mode="python"),
        )
        nodes_created += summary.nodes_created
        relationships_created += summary.relationships_created
        properties_set += summary.properties_set

        if row.binary_surface is not None:
            binary_surface = row.binary_surface
            summary = await _consume(
                tx,
                _MERGE_BINARY_SURFACE,
                surface_id=binary_surface.id,
                surface_props=binary_surface.model_dump(mode="python"),
            )
            nodes_created += summary.nodes_created
            relationships_created += summary.relationships_created
            properties_set += summary.properties_set

            summary = await _consume(
                tx,
                _MERGE_HAS_BINARY_SURFACE,
                candidate_id=candidate.id,
                surface_id=binary_surface.id,
            )
            nodes_created += summary.nodes_created
            relationships_created += summary.relationships_created
            properties_set += summary.properties_set

        if row.backed_symbol_id is not None:
            summary = await _consume(
                tx,
                _MERGE_BACKED_BY_SYMBOL,
                candidate_id=candidate.id,
                backed_symbol_id=row.backed_symbol_id,
            )
            nodes_created += summary.nodes_created
            relationships_created += summary.relationships_created
            properties_set += summary.properties_set

        if row.backed_public_api_symbol_id is not None:
            summary = await _consume(
                tx,
                _MERGE_BACKED_BY_PUBLIC_API,
                candidate_id=candidate.id,
                public_symbol_id=row.backed_public_api_symbol_id,
            )
            nodes_created += summary.nodes_created
            relationships_created += summary.relationships_created
            properties_set += summary.properties_set

        if row.backed_public_api_symbol_id is not None and row.blocked_contract_symbols:
            for blocked_symbol in row.blocked_contract_symbols:
                summary = await _consume(
                    tx,
                    _MERGE_BLOCKED_BY_CONTRACT_SYMBOL,
                    candidate_id=candidate.id,
                    public_symbol_id=blocked_symbol.public_symbol_id,
                    edge_props={
                        "contract_snapshot_id": blocked_symbol.contract_snapshot_id,
                        "consumer_module_name": blocked_symbol.consumer_module_name,
                        "producer_module_name": blocked_symbol.producer_module_name,
                        "commit_sha": blocked_symbol.commit_sha,
                        "use_count": blocked_symbol.use_count,
                        "evidence_paths_sample": list(
                            blocked_symbol.evidence_paths_sample
                        ),
                    },
                )
                nodes_created += summary.nodes_created
                relationships_created += summary.relationships_created
                properties_set += summary.properties_set

    return DeadSymbolWriteSummary(
        nodes_created=nodes_created,
        relationships_created=relationships_created,
        properties_set=properties_set,
    )


async def _consume(tx: Any, query: str, **params: object) -> DeadSymbolWriteSummary:
    result = await tx.run(query, **params)
    summary = await result.consume()
    counters = summary.counters
    return DeadSymbolWriteSummary(
        nodes_created=counters.nodes_created,
        relationships_created=counters.relationships_created,
        properties_set=counters.properties_set,
    )
