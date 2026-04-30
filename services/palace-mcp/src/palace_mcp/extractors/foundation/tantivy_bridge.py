"""Async-safe Tantivy wrapper with explicit lifecycle (GIM-101a, T5).

Python-pro Finding F-F: executor leak on exception fixed via async context
manager + explicit shutdown in __aexit__.

Silent-failure F4: doc_key primary uniqueness via delete-by-term + add
prevents duplicate occurrences after Phase rerun on crash.

MUST be used as: `async with TantivyBridge(path, heap_mb) as bridge: ...`
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

# tantivy is an optional dependency during test without the real package.
# Import is deferred to __aenter__ so that unit tests can mock it.
try:
    import tantivy

    _TANTIVY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TANTIVY_AVAILABLE = False
    tantivy = None  # type: ignore[assignment]

from palace_mcp.extractors.foundation.models import SymbolOccurrence


class TantivyBridge:
    """Async bridge over the synchronous tantivy-py FFI.

    All tantivy calls run on a dedicated single-thread executor so the
    asyncio event loop is never blocked by Tantivy's GIL-holding C FFI.

    Usage::

        async with TantivyBridge(Path("/var/lib/palace/tantivy"), heap_mb=100) as bridge:
            await bridge.add_or_replace_async(occurrence, phase="phase1_defs")
            await bridge.commit_async()
    """

    def __init__(self, index_path: Path, heap_size_mb: int = 100) -> None:
        self.index_path = index_path
        self.heap_size = heap_size_mb * 1024 * 1024
        self._executor: ThreadPoolExecutor | None = None
        self._index: Any | None = None
        self._writer: Any | None = None

    # ------------------------------------------------------------------
    # Async context manager lifecycle (F-F fix)
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "TantivyBridge":
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tantivy")
        try:
            await self._run(self._open_sync)
        except Exception:
            self._executor.shutdown(wait=False)
            self._executor = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        tb: object,
    ) -> None:
        try:
            if self._writer is not None and exc_type is None:
                await self._run(self._commit_sync)
        finally:
            if self._writer is not None:
                try:
                    await self._run(self._close_sync)
                except Exception:
                    pass
            if self._executor is not None:
                self._executor.shutdown(wait=True)
                self._executor = None

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def add_or_replace_async(self, occ: SymbolOccurrence, phase: str) -> None:
        """Delete any doc with same doc_key then add new one (F4 uniqueness fix)."""
        await self._run(self._add_or_replace_sync, occ, phase)

    async def commit_async(self) -> None:
        """Flush writer buffer to disk."""
        await self._run(self._commit_sync)

    async def search_by_symbol_id_async(
        self, symbol_id: int, limit: int = 1000
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self._run(self._search_by_symbol_id_sync, symbol_id, limit),
        )

    async def delete_by_symbol_ids_async(self, symbol_ids: list[int]) -> int:
        """Delete all docs whose symbol_id matches any id in the list.

        Returns count of deleted docs (approximate — Tantivy merges lazily).
        """
        return cast(int, await self._run(self._delete_by_symbol_ids_sync, symbol_ids))

    async def count_docs_for_run_async(self, run_id: str, phase: str) -> int:
        """Count committed docs matching ingest_run_id and phase (for checkpoint reconciliation)."""
        return cast(int, await self._run(self._count_docs_for_run_sync, run_id, phase))

    # ------------------------------------------------------------------
    # Synchronous internals (run on executor thread)
    # ------------------------------------------------------------------

    def _open_sync(self) -> None:
        if not _TANTIVY_AVAILABLE:
            raise RuntimeError("tantivy package is not installed. Run: uv add tantivy")
        self.index_path.mkdir(parents=True, exist_ok=True)
        schema_builder = tantivy.SchemaBuilder()
        # Primary key for uniqueness (Silent-failure F4); use raw tokenizer
        # so delete_documents("doc_key", value) performs exact-term deletion.
        # Default (whitespace) tokenizer splits on special chars, breaking dedup.
        schema_builder.add_text_field("doc_key", stored=True, tokenizer_name="raw")
        schema_builder.add_integer_field(
            "symbol_id", fast=True, indexed=True, stored=False
        )
        schema_builder.add_integer_field(
            "repo_id", fast=True, indexed=True, stored=False
        )
        schema_builder.add_text_field("file_path", stored=True, index_option="basic")
        schema_builder.add_integer_field("line", fast=True, indexed=True, stored=False)
        schema_builder.add_integer_field(
            "col_start", fast=True, indexed=False, stored=False
        )
        schema_builder.add_integer_field(
            "col_end", fast=True, indexed=False, stored=False
        )
        schema_builder.add_integer_field("role", fast=True, indexed=True, stored=False)
        schema_builder.add_integer_field(
            "language", fast=True, indexed=True, stored=False
        )
        schema_builder.add_text_field("commit_sha", stored=True, index_option="basic")
        schema_builder.add_float_field(
            "importance", fast=True, indexed=False, stored=False
        )
        # raw tokenizer keeps UUIDs as single terms for exact-match queries.
        schema_builder.add_text_field(
            "ingest_run_id", stored=True, tokenizer_name="raw"
        )
        # phase stored as raw term so count_docs_for_run can filter per-phase.
        schema_builder.add_text_field("phase", stored=False, tokenizer_name="raw")
        schema = schema_builder.build()

        try:
            self._index = tantivy.Index(schema, path=str(self.index_path))
        except Exception:
            self._index = tantivy.Index(schema, path=str(self.index_path))

        self._writer = self._index.writer(heap_size=self.heap_size)

    def _add_or_replace_sync(self, occ: SymbolOccurrence, phase: str) -> None:
        assert self._writer is not None
        # Delete any existing doc with same primary key (idempotent rerun)
        self._writer.delete_documents("doc_key", occ.doc_key)
        doc = {
            "doc_key": occ.doc_key,
            "symbol_id": occ.symbol_id,
            "file_path": occ.file_path,
            "line": occ.line,
            "col_start": occ.col_start,
            "col_end": occ.col_end,
            "role": 0,
            "language": 0,
            "commit_sha": occ.commit_sha,
            "importance": occ.importance,
            "ingest_run_id": occ.ingest_run_id,
            "phase": phase,
        }
        self._writer.add_document(tantivy.Document(**doc))

    def _commit_sync(self) -> None:
        assert self._writer is not None
        self._writer.commit()
        # Reload so that subsequent searchers see the committed segments.
        assert self._index is not None
        self._index.reload()

    def _close_sync(self) -> None:
        self._writer = None
        self._index = None

    def _search_by_symbol_id_sync(
        self, symbol_id: int, limit: int
    ) -> list[dict[str, Any]]:
        assert self._index is not None
        searcher = self._index.searcher()
        query = self._index.parse_query(f"symbol_id:{symbol_id}")
        results = searcher.search(query, limit)
        out = []
        for _score, addr in results.hits:
            doc = searcher.doc(addr)
            out.append(doc.to_dict())
        return out

    def _delete_by_symbol_ids_sync(self, symbol_ids: list[int]) -> int:
        assert self._writer is not None
        count = 0
        for sid in symbol_ids:
            self._writer.delete_documents("symbol_id", sid)
            count += 1
        return count

    def _count_docs_for_run_sync(self, run_id: str, phase: str) -> int:
        assert self._index is not None
        searcher = self._index.searcher()
        # Both fields use raw tokenizer → exact-term match, no UUID splitting.
        query = self._index.parse_query(
            f'+ingest_run_id:"{run_id}" +phase:"{phase}"'
        )
        results = searcher.search(query, limit=1)
        return cast(int, results.count)

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    async def _run(self, fn: Any, *args: Any) -> Any:
        assert self._executor is not None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)
