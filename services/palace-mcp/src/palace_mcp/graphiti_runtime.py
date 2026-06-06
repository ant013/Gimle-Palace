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
from collections.abc import Iterable
from typing import cast

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EntityNode

from palace_mcp.config import Settings
from palace_mcp.embeddings import EmbeddingBackend, get_embedding_dispatcher

# Keep Graphiti memory embedding writes in moderate chunks. This remains small
# enough for the OpenAI fallback and avoids oversized batch payloads.
_EMBED_BATCH_SIZE = 512
_DEFAULT_EMBEDDING_DIM = 1024


def _coerce_text(
    input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
) -> str:
    if isinstance(input_data, str):
        return input_data
    return next(iter(cast(Iterable[str], input_data)))


class QodoGraphitiEmbedder(EmbedderClient):
    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self._backend = backend or get_embedding_dispatcher().backend("qodo")

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        return self._backend.embed_text(_coerce_text(input_data))

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return self._backend.embed_batch(input_data_list)


class _NoopEmbedder(EmbedderClient):
    def __init__(self, embedding_dim: int = _DEFAULT_EMBEDDING_DIM) -> None:
        self._embedding_dim = embedding_dim

    async def create(
        self,
        input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]],
    ) -> list[float]:
        return [0.0] * self._embedding_dim

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        return [[0.0] * self._embedding_dim for _ in input_data_list]


def build_graphiti(settings: Settings) -> Graphiti:
    """Construct Graphiti wired to the existing palace-mcp Neo4j container.

    graphiti-core 0.28.2 trap: llm_client=None at constructor still spawns
    a default OpenAI client. We pass an explicit OpenAIClient stub so the
    default qodo/noop memory paths work without OPENAI_API_KEY; writes go
    through add_triplet which does not invoke LLM on the hot path.
    """
    api_key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else None
    )
    llm_stub = OpenAIClient(config=LLMConfig(api_key=api_key), client=object())
    if settings.palace_memory_embedder == "qodo":
        embedder: EmbedderClient = QodoGraphitiEmbedder()
    elif settings.palace_memory_embedder == "noop":
        embedder = _NoopEmbedder()
    else:
        if api_key is None:
            raise ValueError(
                "OPENAI_API_KEY is required when PALACE_MEMORY_EMBEDDER=openai"
            )
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
    await g.build_indices_and_constraints(delete_existing=False)


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
