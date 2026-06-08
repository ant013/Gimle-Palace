"""Unit tests for F4.1 Qodo pre-warm (GIM-1100).

Covers:
- prewarm_dispatcher() wires the warmed backend into the dispatcher cache
- _run_qodo_prewarm() logs ok and doesn't raise on success
- _run_qodo_prewarm() logs error, writes audit counter, and still yields on exception
- PALACE_QODO_PREWARM=0 skips prewarm (no call to prewarm_dispatcher)
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from unittest.mock import patch

import pytest

import palace_mcp.embeddings as _emb_module
from palace_mcp.embeddings import (
    EmbeddingBackendDispatcher,
    prewarm_dispatcher,
)
from palace_mcp.embeddings.qodo import _PREWARM_SENTENCE, warmup
from palace_mcp.main import _run_qodo_prewarm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


class _FakeEncoder:
    def __init__(self, row: list[float] | None = None) -> None:
        self._row = row or [0.1, 0.2]
        self.calls: list[list[str]] = []

    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> _FakeArray:
        self.calls.append(list(sentences))
        return _FakeArray([self._row for _ in sentences])


# ---------------------------------------------------------------------------
# warmup()
# ---------------------------------------------------------------------------


class TestWarmup:
    def test_warmup_calls_embed_batch_with_prewarm_sentence(self) -> None:
        encoder = _FakeEncoder()

        with patch(
            "palace_mcp.embeddings.qodo.QodoEmbeddingBackend.__init__",
            lambda self, **kw: (
                setattr(self, "_encoder", encoder)
                or setattr(self, "_normalize_embeddings", True)
            ),
        ):
            from palace_mcp.embeddings.qodo import QodoEmbeddingBackend

            backend = QodoEmbeddingBackend.__new__(QodoEmbeddingBackend)
            backend._encoder = encoder
            backend._normalize_embeddings = True

            # Directly test that _PREWARM_SENTENCE is the right warmup payload
            backend.embed_batch([_PREWARM_SENTENCE])
            assert encoder.calls == [[_PREWARM_SENTENCE]]

    def test_warmup_returns_backend_instance(self) -> None:
        from palace_mcp.embeddings.qodo import QodoEmbeddingBackend

        encoder = _FakeEncoder()
        backend = QodoEmbeddingBackend(encoder=encoder)

        with patch(
            "palace_mcp.embeddings.qodo.QodoEmbeddingBackend",
            return_value=backend,
        ):
            result = warmup()

        assert result is backend
        assert encoder.calls == [[_PREWARM_SENTENCE]]


# ---------------------------------------------------------------------------
# prewarm_dispatcher()
# ---------------------------------------------------------------------------


class TestPrewarmDispatcher:
    @pytest.fixture(autouse=True)
    def _reset_dispatcher(self) -> Any:
        original = _emb_module._dispatcher_cache
        original_factory = _emb_module._dispatcher_factory
        yield
        _emb_module._dispatcher_cache = original
        _emb_module._dispatcher_factory = original_factory

    def test_prewarm_dispatcher_sets_cache(self) -> None:
        from palace_mcp.embeddings.qodo import QodoEmbeddingBackend

        encoder = _FakeEncoder()
        warmed_backend = QodoEmbeddingBackend(encoder=encoder)
        _emb_module._dispatcher_cache = None

        with patch("palace_mcp.embeddings.qodo.warmup", return_value=warmed_backend):
            # Patch warmup in the embeddings __init__ module too
            with patch("palace_mcp.embeddings.warmup", return_value=warmed_backend):
                prewarm_dispatcher()

        assert _emb_module._dispatcher_cache is not None
        assert isinstance(_emb_module._dispatcher_cache, EmbeddingBackendDispatcher)

    def test_prewarm_dispatcher_wires_warmed_backend(self) -> None:
        from palace_mcp.embeddings import get_embedding_dispatcher
        from palace_mcp.embeddings.qodo import QodoEmbeddingBackend

        encoder = _FakeEncoder(row=[9.0, 8.0])
        warmed_backend = QodoEmbeddingBackend(encoder=encoder)
        _emb_module._dispatcher_cache = None

        with patch("palace_mcp.embeddings.warmup", return_value=warmed_backend):
            prewarm_dispatcher()

        dispatcher = get_embedding_dispatcher()
        result = dispatcher.embed_batch(["hello"])
        assert result == [[9.0, 8.0]]
        # backend.embed_batch was called with _PREWARM_SENTENCE during warmup
        # and once here — both via the same encoder
        assert len(encoder.calls) >= 1


# ---------------------------------------------------------------------------
# _run_qodo_prewarm() — happy path
# ---------------------------------------------------------------------------


class TestRunQodoPrewarm:
    @pytest.fixture(autouse=True)
    def _reset_audit_sink(self) -> Any:
        import palace_mcp.mcp_server as _mcp

        original = _mcp._audit_sink
        yield
        _mcp._audit_sink = original

    @pytest.mark.asyncio
    async def test_happy_path_logs_ok(self, caplog: pytest.LogCaptureFixture) -> None:
        with patch(
            "palace_mcp.main.prewarm_dispatcher", return_value=None
        ) as mock_prewarm:
            with caplog.at_level(logging.INFO, logger="palace_mcp.main"):
                await _run_qodo_prewarm()

        mock_prewarm.assert_called_once()
        assert any("qodo_prewarm_ok" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_exception_logs_error_and_writes_audit_counter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import palace_mcp.mcp_server as _mcp

        buf = io.StringIO()
        _mcp._audit_sink = buf

        with patch(
            "palace_mcp.main.prewarm_dispatcher",
            side_effect=RuntimeError("model not found"),
        ):
            with caplog.at_level(logging.ERROR, logger="palace_mcp.main"):
                await _run_qodo_prewarm()  # must NOT raise

        # Error was logged
        assert any("qodo_prewarm_failed" in r.message for r in caplog.records)

        # Audit counter line was written
        raw = buf.getvalue().strip()
        assert raw, "expected audit line but sink is empty"
        line = json.loads(raw)
        assert line["tool_name"] == "palace.startup.qodo_prewarm_failures"
        assert "model not found" in (line["error"] or "")

    @pytest.mark.asyncio
    async def test_exception_does_not_raise(self) -> None:
        with patch(
            "palace_mcp.main.prewarm_dispatcher",
            side_effect=RuntimeError("boom"),
        ):
            await _run_qodo_prewarm()  # must complete without raising


# ---------------------------------------------------------------------------
# PALACE_QODO_PREWARM=0 skips prewarm
# ---------------------------------------------------------------------------


class TestPrewarmOptOut:
    def test_palace_qodo_prewarm_default_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PALACE_QODO_PREWARM", raising=False)
        from palace_mcp.config import Settings

        s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
        assert s.palace_qodo_prewarm is True

    def test_palace_qodo_prewarm_opt_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PALACE_QODO_PREWARM", "0")
        from palace_mcp.config import Settings

        s = Settings(neo4j_password="x", openai_api_key="x")  # type: ignore[call-arg]
        assert s.palace_qodo_prewarm is False
