"""Unit tests for TantivyBridge (GIM-101a, T5) — mocked tantivy FFI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.foundation.models import (
    Language,
    SymbolKind,
    SymbolOccurrence,
    TantivyOccurrenceMatch,
    build_symbol_occurrence_doc_key,
)
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge


def _make_occ(
    symbol_id: int = 42,
    file_path: str = "src/foo.py",
    line: int = 1,
    col_start: int = 0,
    col_end: int = 3,
) -> SymbolOccurrence:
    commit_sha = "abc"
    return SymbolOccurrence(
        doc_key=build_symbol_occurrence_doc_key(
            symbol_id=symbol_id,
            file_path=file_path,
            line=line,
            col_start=col_start,
            commit_sha=commit_sha,
        ),
        symbol_id=symbol_id,
        symbol_qualified_name="foo.bar.Baz",
        kind=SymbolKind.DEF,
        language=Language.PYTHON,
        file_path=file_path,
        line=line,
        col_start=col_start,
        col_end=col_end,
        importance=0.5,
        commit_sha=commit_sha,
        ingest_run_id="run-1",
    )


def _mock_tantivy() -> MagicMock:
    """Return a mock tantivy module with the minimal interface TantivyBridge uses."""
    mock = MagicMock()
    schema = MagicMock()
    mock.SchemaBuilder.return_value.build.return_value = schema
    index = MagicMock()
    mock.Index.return_value = index
    writer = MagicMock()
    index.writer.return_value = writer
    mock.Document = MagicMock(side_effect=lambda **kw: MagicMock())
    return mock


@pytest.fixture()
def tmp_index(tmp_path: Path) -> Path:
    return tmp_path / "tantivy-test"


class TestTantivyBridgeLifecycle:
    @pytest.mark.asyncio
    async def test_context_manager_opens_and_closes(self, tmp_index: Path) -> None:
        mock_tantivy = _mock_tantivy()
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            async with TantivyBridge(tmp_index) as bridge:
                assert bridge._executor is not None
            # executor shut down after exit
            assert bridge._executor is None

    @pytest.mark.asyncio
    async def test_executor_shutdown_on_exception(self, tmp_index: Path) -> None:
        """F-F acceptance: executor must shut down even when an exception escapes the block."""
        mock_tantivy = _mock_tantivy()
        bridge = TantivyBridge(tmp_index)
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            with pytest.raises(RuntimeError, match="test_exception"):
                async with bridge:
                    raise RuntimeError("test_exception")
        # executor must be shut down even after exception
        assert bridge._executor is None

    @pytest.mark.asyncio
    async def test_commit_called_on_clean_exit(self, tmp_index: Path) -> None:
        mock_tantivy = _mock_tantivy()
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
        # commit called exactly once on clean exit
        writer.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_not_called_on_exception(self, tmp_index: Path) -> None:
        """On exception path, commit should not be called (avoid partial writes)."""
        mock_tantivy = _mock_tantivy()
        bridge = TantivyBridge(tmp_index)
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            try:
                async with bridge:
                    writer = bridge._writer
                    raise ValueError("oops")
            except ValueError:
                pass
        writer.commit.assert_not_called()


class TestTantivyBridgeOperations:
    @pytest.mark.asyncio
    async def test_add_or_replace_deletes_then_adds(self, tmp_index: Path) -> None:
        """F4: doc_key uniqueness — delete-by-doc_key then add."""
        mock_tantivy = _mock_tantivy()
        occ = _make_occ()
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
                await bridge.add_or_replace_async(occ, "phase1_defs")
        # delete_documents called with "doc_key" before add_document
        writer.delete_documents.assert_called_once_with("doc_key", occ.doc_key)
        writer.add_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_symbol_ids(self, tmp_index: Path) -> None:
        mock_tantivy = _mock_tantivy()
        with (
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy
            ),
            patch(
                "palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE",
                True,
            ),
        ):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
                count = await bridge.delete_by_symbol_ids_async([1, 2, 3])
        assert count == 3
        assert writer.delete_documents.call_count == 3

    def test_search_occurrences_filters_hits_to_exact_commit(self) -> None:
        bridge = TantivyBridge(Path("/tmp/tantivy-test"))
        searcher = MagicMock()
        current_doc = MagicMock()
        current_doc.to_dict.return_value = {
            "doc_key": [
                build_symbol_occurrence_doc_key(
                    symbol_id=42,
                    file_path="src/current.py",
                    line=8,
                    col_start=14,
                    commit_sha="a" * 40,
                )
            ],
            "file_path": ["src/current.py"],
            "commit_sha": ["a" * 40],
        }
        old_doc = MagicMock()
        old_doc.to_dict.return_value = {
            "doc_key": [
                build_symbol_occurrence_doc_key(
                    symbol_id=42,
                    file_path="src/old.py",
                    line=8,
                    col_start=14,
                    commit_sha="b" * 40,
                )
            ],
            "file_path": ["src/old.py"],
            "commit_sha": ["b" * 40],
        }
        searcher.doc.side_effect = [current_doc, old_doc]
        searcher.search.return_value = MagicMock(hits=[(1.0, "current"), (1.0, "old")])
        bridge._index = MagicMock()
        bridge._index.searcher.return_value = searcher
        bridge._index.parse_query.return_value = MagicMock()

        matches = bridge._search_occurrences_sync(
            symbol_id=42,
            commit_sha="a" * 40,
            phases=("phase2_user_uses",),
            limit=10,
        )

        assert matches == [
            TantivyOccurrenceMatch(
                doc_key=build_symbol_occurrence_doc_key(
                    symbol_id=42,
                    file_path="src/current.py",
                    line=8,
                    col_start=14,
                    commit_sha="a" * 40,
                ),
                symbol_id=42,
                file_path="src/current.py",
                line=8,
                col_start=14,
                col_end=None,
                commit_sha="a" * 40,
            )
        ]
