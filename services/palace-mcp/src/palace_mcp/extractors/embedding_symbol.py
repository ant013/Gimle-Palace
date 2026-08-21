"""Populate :Symbol.embedding vectors for a single project."""

from __future__ import annotations

import os
from hashlib import sha256
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast

from palace_mcp.code.embedding_candidate_policy import CandidateRow, apply_policy
from palace_mcp.embeddings import EmbeddingBackend, QodoEmbeddingBackend
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorExecutionMode,
    ExtractorIncrementalCapability,
    ExtractorOutcome,
    ExtractorRunContext,
    ExtractorStats,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver


_BATCH_SIZE = 64

_LOAD_SYMBOL_ROWS = """
MATCH (s:Symbol {group_id: $group_id})
WHERE NOT s:Deprecated
RETURN
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.source_scope AS source_scope,
  s.embedding_input_hash AS embedding_input_hash,
  s.embedding IS NOT NULL AS has_embedding
"""

_LOAD_DELTA_SYMBOL_ROWS = """
MATCH (s:Symbol {group_id: $group_id})
WHERE NOT s:Deprecated
  AND (
    s.qualified_name IN $qualified_names
    OR (size($qualified_names) = 0 AND s.file_path IN $changed_paths)
  )
RETURN
  s.qualified_name AS qualified_name,
  s.kind AS kind,
  s.file_path AS file_path,
  s.module_name AS module_name,
  s.source_scope AS source_scope,
  s.embedding_input_hash AS embedding_input_hash,
  s.embedding IS NOT NULL AS has_embedding
ORDER BY qualified_name
"""

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
    source_scope: str | None
    embedding_input_hash: str | None
    has_embedding: bool


class _PendingSymbolRow(TypedDict):
    qualified_name: str
    embedding_text: str
    embedding_input_hash: str
    kind: str | None
    file_path: str | None
    source_scope: str | None


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


def _read_max_symbols() -> int | None:
    raw = os.environ.get("PALACE_EMBEDDING_MAX_SYMBOLS", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _load_symbol_rows(
    driver: AsyncDriver,
    group_id: str,
) -> list[_LoadedSymbolRow]:
    async with driver.session() as session:
        result = await session.run(_LOAD_SYMBOL_ROWS, group_id=group_id)
        return cast(list[_LoadedSymbolRow], await result.data())


async def _load_delta_symbol_rows(
    driver: AsyncDriver,
    group_id: str,
    *,
    qualified_names: tuple[str, ...],
    changed_paths: tuple[str, ...],
) -> list[_LoadedSymbolRow]:
    async with driver.session() as session:
        result = await session.run(
            _LOAD_DELTA_SYMBOL_ROWS,
            group_id=group_id,
            qualified_names=list(qualified_names),
            changed_paths=list(changed_paths),
        )
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
    incremental_capability = ExtractorIncrementalCapability.DELTA
    # Large projects (uw-ios-app ~248k symbols) need >2h; the old 7200s cap timed
    # out mid-run. Configurable via PALACE_EMBEDDING_TIMEOUT_S; default 10h.
    timeout_s: ClassVar[float] = float(
        os.environ.get("PALACE_EMBEDDING_TIMEOUT_S", "36000")
    )
    allow_global_backfill: ClassVar[bool] = False

    def __init__(self, backend: EmbeddingBackend | None = None) -> None:
        self._backend = backend

    def _resolve_backend(self) -> EmbeddingBackend:
        if self._backend is None:
            self._backend = QodoEmbeddingBackend()
        return self._backend

    async def run(
        self,
        *,
        graphiti: object,
        ctx: ExtractorRunContext,
    ) -> ExtractorStats:
        driver = graphiti.driver  # type: ignore[attr-defined]
        if ctx.execution_mode is ExtractorExecutionMode.INCREMENTAL:
            delta = ctx.analysis_delta
            if delta is None:
                return ExtractorStats(
                    outcome=ExtractorOutcome.MISSING_INPUT,
                    message="incremental embedding requires an AnalysisDelta",
                    next_action="Rerun project_analyze after its durable delta is available.",
                    mode=ExtractorExecutionMode.SKIPPED,
                )
            if not delta.changed_symbol_ids and not delta.changed_paths:
                return ExtractorStats(
                    outcome=ExtractorOutcome.SKIPPED,
                    message="no_changed_symbols",
                    mode=ExtractorExecutionMode.SKIPPED,
                )
            loaded_rows = await _load_delta_symbol_rows(
                driver,
                ctx.group_id,
                qualified_names=delta.changed_symbol_ids,
                changed_paths=delta.changed_paths,
            )
        else:
            if not self.allow_global_backfill:
                return ExtractorStats(
                    outcome=ExtractorOutcome.MISSING_INPUT,
                    message=(
                        "embedding_symbol does not perform a global scan; "
                        "run embedding_backfill explicitly."
                    ),
                    next_action="Run extractor embedding_backfill for historical embeddings.",
                    mode=ExtractorExecutionMode.SKIPPED,
                )
            loaded_rows = await _load_symbol_rows(driver, ctx.group_id)
        pending_rows: list[_PendingSymbolRow] = []
        for row in loaded_rows:
            text = _embedding_text(row)
            text_hash = _embedding_text_hash(text)
            if row["has_embedding"] and row["embedding_input_hash"] == text_hash:
                continue
            pending_rows.append(
                {
                    "qualified_name": row["qualified_name"],
                    "embedding_text": text,
                    "embedding_input_hash": text_hash,
                    "kind": row["kind"],
                    "file_path": row["file_path"],
                    "source_scope": row.get("source_scope"),
                }
            )

        if not pending_rows:
            return ExtractorStats(
                nodes_written=0,
                edges_written=0,
                outcome=(
                    ExtractorOutcome.SKIPPED
                    if ctx.execution_mode is ExtractorExecutionMode.INCREMENTAL
                    else ExtractorOutcome.OK
                ),
                message=(
                    "no_changed_symbols"
                    if ctx.execution_mode is ExtractorExecutionMode.INCREMENTAL
                    else None
                ),
                mode=(
                    ExtractorExecutionMode.SKIPPED
                    if ctx.execution_mode is ExtractorExecutionMode.INCREMENTAL
                    else None
                ),
            )

        max_symbols = _read_max_symbols()
        if (
            max_symbols is not None
            and ctx.execution_mode is not ExtractorExecutionMode.INCREMENTAL
        ):
            selected, _ = apply_policy(
                cast(list[CandidateRow], pending_rows), max_symbols
            )
            pending_rows = cast(list[_PendingSymbolRow], selected)

        backend = self._resolve_backend()
        nodes_written = 0
        for index in range(0, len(pending_rows), _BATCH_SIZE):
            batch = pending_rows[index : index + _BATCH_SIZE]
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

        return ExtractorStats(
            nodes_written=nodes_written,
            edges_written=0,
            mode=(
                ExtractorExecutionMode.INCREMENTAL
                if ctx.execution_mode is ExtractorExecutionMode.INCREMENTAL
                else None
            ),
        )


class EmbeddingBackfillExtractor(EmbeddingSymbolExtractor):
    """Explicit, globally-scoped historical embedding operation."""

    name = "embedding_backfill"
    description = "Backfill embeddings for every stale or missing project Symbol."
    incremental_capability = ExtractorIncrementalCapability.FULL_ONLY
    allow_global_backfill = True
