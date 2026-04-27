"""Unit tests for TantivyBridge (GIM-101a, T5) — mocked tantivy FFI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.foundation.models import Language, SymbolKind, SymbolOccurrence
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge


def _make_occ(
    symbol_id: int = 42,
    file_path: str = "src/foo.py",
    line: int = 1,
    col_start: int = 0,
    col_end: int = 3,
) -> SymbolOccurrence:
    return SymbolOccurrence(
        doc_key=f"{symbol_id}:{file_path}:{line}:{col_start}",
        symbol_id=symbol_id,
        symbol_qualified_name="foo.bar.Baz",
        kind=SymbolKind.DEF,
        language=Language.PYTHON,
        file_path=file_path,
        line=line,
        col_start=col_start,
        col_end=col_end,
        importance=0.5,
        commit_sha="abc",
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
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
            async with TantivyBridge(tmp_index) as bridge:
                assert bridge._executor is not None
            # executor shut down after exit
            assert bridge._executor is None

    @pytest.mark.asyncio
    async def test_executor_shutdown_on_exception(self, tmp_index: Path) -> None:
        """F-F acceptance: executor must shut down even when an exception escapes the block."""
        mock_tantivy = _mock_tantivy()
        bridge = TantivyBridge(tmp_index)
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
            with pytest.raises(RuntimeError, match="test_exception"):
                async with bridge:
                    raise RuntimeError("test_exception")
        # executor must be shut down even after exception
        assert bridge._executor is None

    @pytest.mark.asyncio
    async def test_commit_called_on_clean_exit(self, tmp_index: Path) -> None:
        mock_tantivy = _mock_tantivy()
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
        # commit called exactly once on clean exit
        writer.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_commit_not_called_on_exception(self, tmp_index: Path) -> None:
        """On exception path, commit should not be called (avoid partial writes)."""
        mock_tantivy = _mock_tantivy()
        bridge = TantivyBridge(tmp_index)
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
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
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
                await bridge.add_or_replace_async(occ)
        # delete_documents called with "doc_key" before add_document
        writer.delete_documents.assert_called_once_with("doc_key", occ.doc_key)
        writer.add_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_by_symbol_ids(self, tmp_index: Path) -> None:
        mock_tantivy = _mock_tantivy()
        with patch("palace_mcp.extractors.foundation.tantivy_bridge.tantivy", mock_tantivy), \
             patch("palace_mcp.extractors.foundation.tantivy_bridge._TANTIVY_AVAILABLE", True):
            async with TantivyBridge(tmp_index) as bridge:
                writer = bridge._writer
                count = await bridge.delete_by_symbol_ids_async([1, 2, 3])
        assert count == 3
        assert writer.delete_documents.call_count == 3
