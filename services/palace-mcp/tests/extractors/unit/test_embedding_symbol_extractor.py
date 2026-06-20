from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors import embedding_symbol as embedding_symbol_module
from palace_mcp.extractors.embedding_symbol import (
    _LOAD_SYMBOL_ROWS,
    _WRITE_EMBEDDINGS,
    EmbeddingSymbolExtractor,
    _embedding_text,
    _embedding_text_hash,
    _read_max_symbols,
)


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self._rows = rows or []

    async def data(self) -> list[dict[str, object]]:
        return self._rows


class _FakeBackend:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(index)] for index, _ in enumerate(texts, start=1)]


def _make_ctx() -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="demo",
        group_id="project/demo",
        repo_path=Path("/tmp/demo"),
        run_id="run-1",
        duration_ms=0,
        logger=logging.getLogger("test.embedding_symbol"),
    )


def _make_graphiti(
    rows: list[dict[str, object]],
) -> tuple[MagicMock, AsyncMock, list[dict[str, object]]]:
    writes: list[dict[str, object]] = []

    async def run_side_effect(query: str, **kwargs: object) -> _FakeResult:
        if query == _LOAD_SYMBOL_ROWS:
            return _FakeResult(rows)
        if query == _WRITE_EMBEDDINGS:
            writes.append(kwargs)
            return _FakeResult()
        raise AssertionError(f"unexpected query: {query}")

    session = AsyncMock()
    session.run = AsyncMock(side_effect=run_side_effect)

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    driver = MagicMock()
    driver.session = MagicMock(return_value=session_cm)

    graphiti = MagicMock()
    graphiti.driver = driver
    return graphiti, session.run, writes


def test_load_symbol_rows_filters_out_deprecated_symbols() -> None:
    assert "NOT s:Deprecated" in _LOAD_SYMBOL_ROWS


@pytest.mark.asyncio
async def test_run_batches_symbols_and_writes_embeddings() -> None:
    rows = [
        {
            "qualified_name": f"demo.symbol.{index}",
            "kind": "function",
            "file_path": f"src/module_{index}.py",
            "module_name": "demo",
            "source_scope": "project",
            "embedding_input_hash": None,
            "has_embedding": False,
        }
        for index in range(65)
    ]
    graphiti, run_mock, writes = _make_graphiti(rows)
    backend = _FakeBackend()

    stats = await EmbeddingSymbolExtractor(backend=backend).run(
        graphiti=graphiti,
        ctx=_make_ctx(),
    )

    assert [len(call) for call in backend.calls] == [64, 1]
    assert [len(call["rows"]) for call in writes] == [64, 1]
    assert all(call["group_id"] == "project/demo" for call in writes)
    assert run_mock.await_count == 3
    assert stats.nodes_written == 65
    assert stats.edges_written == 0


@pytest.mark.asyncio
async def test_run_skips_symbols_with_matching_hash() -> None:
    unchanged_row = {
        "qualified_name": "demo.symbol.unchanged",
        "kind": "function",
        "file_path": "src/unchanged.py",
        "module_name": "demo",
        "source_scope": "project",
        "embedding_input_hash": None,
        "has_embedding": True,
    }
    unchanged_row["embedding_input_hash"] = _embedding_text_hash(
        _embedding_text(unchanged_row)
    )
    stale_row = {
        "qualified_name": "demo.symbol.stale",
        "kind": "class",
        "file_path": "src/stale.py",
        "module_name": "demo",
        "source_scope": "project",
        "embedding_input_hash": "stale-hash",
        "has_embedding": True,
    }
    graphiti, _, writes = _make_graphiti([unchanged_row, stale_row])
    backend = _FakeBackend()

    stats = await EmbeddingSymbolExtractor(backend=backend).run(
        graphiti=graphiti,
        ctx=_make_ctx(),
    )

    assert backend.calls == [[_embedding_text(stale_row)]]
    assert len(writes) == 1
    assert len(writes[0]["rows"]) == 1
    assert writes[0]["rows"][0]["qualified_name"] == "demo.symbol.stale"
    assert stats.nodes_written == 1


@pytest.mark.asyncio
async def test_run_with_all_unchanged_symbols_skips_backend_resolution() -> None:
    unchanged_row = {
        "qualified_name": "demo.symbol.unchanged",
        "kind": "function",
        "file_path": "src/unchanged.py",
        "module_name": "demo",
        "source_scope": "project",
        "embedding_input_hash": None,
        "has_embedding": True,
    }
    unchanged_row["embedding_input_hash"] = _embedding_text_hash(
        _embedding_text(unchanged_row)
    )
    graphiti, run_mock, writes = _make_graphiti([unchanged_row])

    class _UnexpectedBackend:
        def __init__(self) -> None:
            raise AssertionError("backend should not be resolved")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        embedding_symbol_module,
        "QodoEmbeddingBackend",
        _UnexpectedBackend,
    )
    try:
        stats = await EmbeddingSymbolExtractor().run(
            graphiti=graphiti,
            ctx=_make_ctx(),
        )
    finally:
        monkeypatch.undo()

    assert stats.nodes_written == 0
    assert stats.edges_written == 0
    assert writes == []
    assert run_mock.await_count == 1


# ---------------------------------------------------------------------------
# _read_max_symbols
# ---------------------------------------------------------------------------


def test_read_max_symbols_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PALACE_EMBEDDING_MAX_SYMBOLS", raising=False)
    assert _read_max_symbols() is None


def test_read_max_symbols_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_EMBEDDING_MAX_SYMBOLS", "128")
    assert _read_max_symbols() == 128


def test_read_max_symbols_invalid_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_EMBEDDING_MAX_SYMBOLS", "not-a-number")
    assert _read_max_symbols() is None


# ---------------------------------------------------------------------------
# Bounded policy applied in run()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_respects_max_symbols_and_prefers_project_over_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PALACE_EMBEDDING_MAX_SYMBOLS", "1")

    rows = [
        {
            "qualified_name": "SDK.NSObject",
            "kind": "class",
            "file_path": "Developer/Platforms/MacOSX.sdk/NSObject.h",
            "module_name": None,
            "source_scope": "sdk",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
        {
            "qualified_name": "MyApp.Wallet",
            "kind": "class",
            "file_path": "src/Wallet.swift",
            "module_name": "MyApp",
            "source_scope": "project",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
    ]
    graphiti, _, writes = _make_graphiti(rows)
    backend = _FakeBackend()

    stats = await EmbeddingSymbolExtractor(backend=backend).run(
        graphiti=graphiti,
        ctx=_make_ctx(),
    )

    assert stats.nodes_written == 1
    assert len(writes) == 1
    # The project symbol should be selected, not the SDK symbol
    written_names = [r["qualified_name"] for r in writes[0]["rows"]]
    assert written_names == ["MyApp.Wallet"]


@pytest.mark.asyncio
async def test_run_respects_max_symbols_and_prefers_project_over_generated_and_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PALACE_EMBEDDING_MAX_SYMBOLS", "1")

    rows = [
        {
            "qualified_name": "Assets.walletIcon",
            "kind": "enum",
            "file_path": "Build/GeneratedAssetSymbols.swift",
            "module_name": "MyApp",
            "source_scope": "generated",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
        {
            "qualified_name": "Derived.assetName",
            "kind": "enum",
            "file_path": "Build/Intermediates.noindex/DerivedAssetSymbols.swift",
            "module_name": "MyApp",
            "source_scope": "derived",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
        {
            "qualified_name": "MyApp.MoneroAdapter",
            "kind": "class",
            "file_path": "Sources/Monero/MoneroAdapter.swift",
            "module_name": "MyApp",
            "source_scope": "project",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
    ]
    graphiti, _, writes = _make_graphiti(rows)
    backend = _FakeBackend()

    stats = await EmbeddingSymbolExtractor(backend=backend).run(
        graphiti=graphiti,
        ctx=_make_ctx(),
    )

    assert stats.nodes_written == 1
    assert len(writes) == 1
    written_names = [r["qualified_name"] for r in writes[0]["rows"]]
    assert written_names == ["MyApp.MoneroAdapter"]


@pytest.mark.asyncio
async def test_run_without_max_symbols_embeds_all_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PALACE_EMBEDDING_MAX_SYMBOLS", raising=False)

    rows = [
        {
            "qualified_name": "SDK.NSObject",
            "kind": "class",
            "file_path": "Developer/Platforms/MacOSX.sdk/NSObject.h",
            "module_name": None,
            "source_scope": "sdk",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
        {
            "qualified_name": "MyApp.Wallet",
            "kind": "class",
            "file_path": "src/Wallet.swift",
            "module_name": "MyApp",
            "source_scope": "project",
            "embedding_input_hash": None,
            "has_embedding": False,
        },
    ]
    graphiti, _, writes = _make_graphiti(rows)
    backend = _FakeBackend()

    stats = await EmbeddingSymbolExtractor(backend=backend).run(
        graphiti=graphiti,
        ctx=_make_ctx(),
    )

    assert stats.nodes_written == 2


def test_embedding_timeout_default_is_ten_hours() -> None:
    """The old hardcoded 7200s (2h) cap timed out large projects (uw-ios-app ~248k
    symbols ~5.6h). Default is now 10h, overridable via PALACE_EMBEDDING_TIMEOUT_S."""
    assert EmbeddingSymbolExtractor.timeout_s == 36000.0
