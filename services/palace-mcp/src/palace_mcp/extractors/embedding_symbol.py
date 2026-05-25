"""Populate :Symbol.embedding vectors for a single project."""

from __future__ import annotations

from hashlib import sha256
import os
from typing import TYPE_CHECKING, TypedDict, cast

from palace_mcp.embeddings import EmbeddingBackend, QodoEmbeddingBackend
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorRunContext,
    ExtractorStats,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver


_BATCH_SIZE = 64

_LOAD_SYMBOL_ROWS = """
MATCH (s:Symbol {group_id: $group_id})
RETURN
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.embedding_input_hash AS embedding_input_hash,
  s.embedding IS NOT NULL AS has_embedding,
  CASE
    WHEN s.file_path STARTS WITH ".palace-scip-derived-data/" THEN 1
    WHEN s.file_path CONTAINS "/.palace-scip-derived-data/" THEN 1
    WHEN s.file_path STARTS WITH ".build/" THEN 1
    WHEN s.file_path CONTAINS "/.build/" THEN 1
    ELSE 0
  END AS embedding_priority
ORDER BY embedding_priority, s.qualified_name
"""


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_positive_int(name: str, *, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{name} must be >= 1")
    return parsed


def _env_optional_non_negative_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return None
    parsed = int(value)
    if parsed < 0:
        raise ValueError(f"{name} must be >= 0")
    return parsed

_WRITE_EMBEDDINGS = """
UNWIND $rows AS row
MATCH (s:Symbol {group_id: $group_id, qualified_name: row.qualified_name})
SET
  s.embedding = row.embedding,
  s.embedding_input_hash = row.embedding_input_hash
"""


class _LoadedSymbolRow(TypedDict):
    qualified_name: str
    kind: str | None
    file_path: str | None
    module_name: str | None
    embedding_input_hash: str | None
    has_embedding: bool


class _PendingSymbolRow(TypedDict):
    qualified_name: str
    embedding_text: str
    embedding_input_hash: str


class _WriteRow(TypedDict):
    qualified_name: str
    embedding: list[float]
    embedding_input_hash: str


def _embedding_text(row: _LoadedSymbolRow) -> str:
    parts = [f"qualified_name: {row['qualified_name']}"]
    if row["kind"]:
        parts.append(f"kind: {row['kind']}")
    if row["module_name"]:
        parts.append(f"module_name: {row['module_name']}")
    if row["file_path"]:
        parts.append(f"file_path: {row['file_path']}")
    return "\n".join(parts)


def _embedding_text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


async def _load_symbol_rows(
    driver: AsyncDriver,
    group_id: str,
) -> list[_LoadedSymbolRow]:
    async with driver.session() as session:
        result = await session.run(_LOAD_SYMBOL_ROWS, group_id=group_id)
        return cast(list[_LoadedSymbolRow], await result.data())


async def _write_embeddings(
    driver: AsyncDriver,
    group_id: str,
    rows: list[_WriteRow],
) -> None:
    async with driver.session() as session:
        await session.run(_WRITE_EMBEDDINGS, group_id=group_id, rows=rows)


class EmbeddingSymbolExtractor(BaseExtractor):
    name = "embedding_symbol"
    description = "Populate :Symbol.embedding vectors for a single project."

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self._backend = backend

    def _resolve_backend(self) -> EmbeddingBackend:
        if self._backend is None:
            self._backend = QodoEmbeddingBackend(
                local_files_only=_env_bool("PALACE_QODO_LOCAL_FILES_ONLY")
            )
        return self._backend

    async def run(
        self,
        *,
        graphiti: object,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        driver = graphiti.driver  # type: ignore[attr-defined]
        pending_rows: list[_PendingSymbolRow] = []
        max_symbols = _env_optional_non_negative_int("PALACE_EMBEDDING_MAX_SYMBOLS")
        for row in await _load_symbol_rows(driver, ctx.group_id):
            text = _embedding_text(row)
            text_hash = _embedding_text_hash(text)
            if row["has_embedding"] and row["embedding_input_hash"] == text_hash:
                continue
            pending_rows.append(
                {
                    "qualified_name": row["qualified_name"],
                    "embedding_text": text,
                    "embedding_input_hash": text_hash,
                }
            )
            if max_symbols is not None and len(pending_rows) >= max_symbols:
                break

        if not pending_rows:
            return ExtractorStats(nodes_written=0, edges_written=0)

        backend = self._resolve_backend()
        batch_size = _env_positive_int("PALACE_EMBEDDING_BATCH_SIZE", default=_BATCH_SIZE)
        nodes_written = 0
        for index in range(0, len(pending_rows), batch_size):
            batch = pending_rows[index : index + batch_size]
            embeddings = backend.embed_batch([row["embedding_text"] for row in batch])
            write_rows: list[_WriteRow] = [
                {
                    "qualified_name": row["qualified_name"],
                    "embedding": embedding,
                    "embedding_input_hash": row["embedding_input_hash"],
                }
                for row, embedding in zip(batch, embeddings, strict=True)
            ]
            await _write_embeddings(driver, ctx.group_id, write_rows)
            nodes_written += len(write_rows)

        return ExtractorStats(nodes_written=nodes_written, edges_written=0)
