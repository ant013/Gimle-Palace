"""Graphiti runtime factory and public helpers.

This module owns the Graphiti singleton and exposes a stable API so
extractors never touch graphiti.driver directly.

Public API (consumed by HeartbeatExtractor, GIM-77 bridge extractor, etc.):
  build_graphiti(settings) -> Graphiti
  ensure_graphiti_schema(g) -> None
  save_entity_node(g, node) -> None
  save_entity_edge(g, edge) -> None
  batch_save_entity_nodes(g, nodes) -> None
  batch_save_entity_edges(g, edges) -> None
  close_graphiti(g) -> None
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EntityNode

from palace_mcp.config import Settings

logger = logging.getLogger(__name__)

# OpenAI embeddings API accepts up to 2048 inputs per request; use 512 to
# stay within token-count limits on long node names.
_EMBED_BATCH_SIZE = 512

_DEDUPLICATE_SYMBOLS_QUERY = """
MATCH (s:Symbol)
WHERE s.group_id IS NOT NULL AND s.qualified_name IS NOT NULL
WITH s
ORDER BY coalesce(s.created_at, ''), s.uuid
WITH s.group_id AS group_id, s.qualified_name AS qualified_name, collect(s) AS nodes
WHERE size(nodes) > 1
CALL apoc.refactor.mergeNodes(
    nodes,
    {
        properties: 'discard',
        mergeRels: true,
        produceSelfRef: false,
        preserveExistingSelfRels: false,
        avoidDuplicates: true,
        relationshipSelectionStrategy: 'merge'
    }
) YIELD node
RETURN count(*) AS merged_groups
"""


def build_graphiti(settings: Settings) -> Graphiti:
    """Construct Graphiti wired to the existing palace-mcp Neo4j container.

    graphiti-core 0.28.2 trap: llm_client=None at constructor still spawns
    a default OpenAI client, which raises if OPENAI_API_KEY is absent. We
    pass an explicit OpenAIClient stub; writes go through add_triplet which
    does not invoke LLM, so the stub is never called on the hot path.

    Embedder must be called explicitly via generate_name_embedding() before save() — real key required.
    """
    api_key = settings.openai_api_key.get_secret_value()
    llm_stub = OpenAIClient(config=LLMConfig(api_key=api_key))
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=api_key,
            embedding_model="text-embedding-3-small",
        )
    )
    return Graphiti(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password.get_secret_value(),
        llm_client=llm_stub,
        embedder=embedder,
        cross_encoder=None,  # use search(), not search_()
    )


async def ensure_graphiti_schema(g: Graphiti) -> None:
    """Idempotent bootstrap — safe to call on every startup."""
    merged_groups = await _dedupe_symbol_nodes(g.driver)
    if merged_groups:
        logger.warning(
            "Merged duplicate Symbol groups before Graphiti schema bootstrap: %s",
            merged_groups,
        )
    await g.build_indices_and_constraints(delete_existing=False)


async def _dedupe_symbol_nodes(driver: Any) -> int:
    async with driver.session() as session:
        result = await session.run(_DEDUPLICATE_SYMBOLS_QUERY)
        row = await result.single()
    if row is None:
        return 0
    return int(row["merged_groups"] or 0)


async def save_entity_node(g: Graphiti, node: EntityNode) -> None:
    """Persist an EntityNode. Stable contract for extractors — never touch g.driver directly."""
    if node.name_embedding is None:
        await node.generate_name_embedding(g.embedder)
    await node.save(g.driver)


async def save_entity_edge(g: Graphiti, edge: EntityEdge) -> None:
    """Persist an EntityEdge. Stable contract for extractors."""
    if edge.fact_embedding is None:
        await edge.generate_embedding(g.embedder)
    await edge.save(g.driver)


async def batch_save_entity_nodes(g: Graphiti, nodes: list[EntityNode]) -> None:
    """Embed all nodes in one batch call, then save concurrently.

    Reduces N sequential OpenAI embedding API calls to ceil(N/_EMBED_BATCH_SIZE)
    calls, then fans out Neo4j writes in parallel.
    """
    to_embed = [n for n in nodes if n.name_embedding is None]
    for i in range(0, len(to_embed), _EMBED_BATCH_SIZE):
        chunk = to_embed[i : i + _EMBED_BATCH_SIZE]
        embeddings = await g.embedder.create_batch(
            [n.name.replace("\n", " ") for n in chunk]
        )
        for node, emb in zip(chunk, embeddings, strict=True):
            node.name_embedding = emb
    await asyncio.gather(*(n.save(g.driver) for n in nodes))


async def batch_save_entity_edges(g: Graphiti, edges: list[EntityEdge]) -> None:
    """Embed all edges in one batch call, then save concurrently."""
    to_embed = [e for e in edges if e.fact_embedding is None]
    for i in range(0, len(to_embed), _EMBED_BATCH_SIZE):
        chunk = to_embed[i : i + _EMBED_BATCH_SIZE]
        embeddings = await g.embedder.create_batch(
            [e.fact.replace("\n", " ") for e in chunk]
        )
        for edge, emb in zip(chunk, embeddings, strict=True):
            edge.fact_embedding = emb
    await asyncio.gather(*(e.save(g.driver) for e in edges))


async def close_graphiti(g: Graphiti) -> None:
    """Shutdown helper. Always await on lifespan teardown."""
    await g.close()  # type: ignore[no-untyped-call]
