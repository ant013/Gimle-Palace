"""Tests for palace.code.semantic_search."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolResult, TextContent

from palace_mcp.embeddings import (
    EmbeddingBackendDispatcher,
    set_embedding_dispatcher_factory,
)


class _FakeResult:
    def __init__(
        self,
        *,
        single_value: dict[str, Any] | None = None,
        data_value: list[dict[str, Any]] | None = None,
    ) -> None:
        self._single_value = single_value
        self._data_value = data_value or []

    async def single(self) -> dict[str, Any] | None:
        return self._single_value

    async def data(self) -> list[dict[str, Any]]:
        return self._data_value


class _FakeSession:
    def __init__(self, run_fn: Any) -> None:
        self._run_fn = run_fn
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, query: str, **params: Any) -> _FakeResult:
        self.calls.append((query, params))
        return self._run_fn(query, params)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class _FakeDriver:
    def __init__(self, run_fn: Any) -> None:
        self._session = _FakeSession(run_fn)

    def session(self) -> _FakeSession:
        return self._session


class _FakeBackend:
    def __init__(
        self,
        *,
        vector: list[float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._vector = vector or [0.25, 0.5]
        self._error = error
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        if self._error is not None:
            raise self._error
        return self._vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


def _make_tool_result(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        isError=False,
    )


@pytest.fixture(autouse=True)
def _reset_embedding_factory() -> None:
    set_embedding_dispatcher_factory(None)
    yield
    set_embedding_dispatcher_factory(None)


@pytest.mark.asyncio
async def test_invalid_query_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(lambda _query, _params: _FakeResult())
    result = await semantic_search(driver=driver, query="   ")
    assert result == {
        "ok": False,
        "error_code": "invalid_query",
        "message": "query must be a non-empty string",
    }


@pytest.mark.asyncio
async def test_invalid_limit_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(lambda _query, _params: _FakeResult())
    result = await semantic_search(driver=driver, query="wallet", limit=0)
    assert result == {
        "ok": False,
        "error_code": "invalid_limit",
        "message": "limit must be between 1 and 50",
    }


@pytest.mark.asyncio
async def test_invalid_context_limit_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(lambda _query, _params: _FakeResult())
    result = await semantic_search(
        driver=driver,
        query="wallet",
        context_limit=11,
    )
    assert result == {
        "ok": False,
        "error_code": "invalid_context_limit",
        "message": "context_limit must be between 0 and 10",
    }


@pytest.mark.asyncio
async def test_invalid_scope_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(lambda _query, _params: _FakeResult())
    result = await semantic_search(
        driver=driver, query="wallet", project="a", projects=["b"]
    )
    assert result["ok"] is False
    assert result["error_code"] == "invalid_scope"


@pytest.mark.asyncio
async def test_project_validation_uses_slug_and_reports_missing_projects() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        assert "p.slug" in query
        assert "p.name" not in query
        return _FakeResult(single_value={"found_projects": ["wallet-core"]})

    driver = _FakeDriver(run_fn)
    result = await semantic_search(
        driver=driver,
        query="signature verification",
        projects=["wallet-core", "missing-kit"],
    )
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"
    assert result["missing_projects"] == ["missing-kit"]


@pytest.mark.asyncio
async def test_unknown_backend_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(_query: str, _params: dict[str, Any]) -> _FakeResult:
        return _FakeResult(single_value={"found_projects": ["wallet-core"]})

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
            backend="missing",
        )
    assert result["ok"] is False
    assert result["error_code"] == "unknown_embedding_backend"


@pytest.mark.asyncio
async def test_embedding_backend_failed_returns_error() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend(error=RuntimeError("encoder offline"))
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(_query: str, _params: dict[str, Any]) -> _FakeResult:
        return _FakeResult(single_value={"found_projects": ["wallet-core"]})

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
        )
    assert result["ok"] is False
    assert result["error_code"] == "embedding_backend_failed"


@pytest.mark.asyncio
async def test_embeddings_not_ready_returns_warning_without_vector_query() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 0})
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
        )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["embedded_symbol_count"] == 0
    assert result["warnings"][0]["code"] == "embeddings_not_ready"
    assert all("queryNodes" not in query for query, _ in driver._session.calls)


@pytest.mark.asyncio
async def test_success_filters_scope_and_skips_context_when_disabled() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(
                single_value={"found_projects": ["wallet-a", "wallet-b"]}
            )
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 3})
        if "queryNodes('symbol_embedding_idx'" in query:
            assert params["query_k"] == 50
            assert params["limit"] == 2
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-a",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletA",
                        "embedding_input_hash": "hash-a",
                        "commit_sha": "sha-a",
                        "score": 0.91,
                    },
                    {
                        "group_id": "project/wallet-b",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/B.swift",
                        "module_name": "WalletB",
                        "embedding_input_hash": "hash-b",
                        "commit_sha": "sha-b",
                        "score": 0.87,
                    },
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    cm_session_getter = MagicMock()
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            cm_session_getter,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            projects=["wallet-a", "wallet-b"],
            limit=2,
            include_context=False,
        )

    assert backend.calls == ["signature verification"]
    assert result["ok"] is True
    assert result["returned_count"] == 2
    assert result["candidate_limit"] == 50
    assert result["result"][0]["project"] == "wallet-a"
    assert result["result"][1]["project"] == "wallet-b"
    assert "context" not in result["result"][0]
    assert result["warnings"] == []
    cm_session_getter.assert_not_called()


@pytest.mark.asyncio
async def test_vector_query_uses_candidate_limit_to_overfetch_before_scope_filter() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 1})
        if "queryNodes('symbol_embedding_idx'" in query:
            assert params["query_k"] == 50
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "embedding_input_hash": "hash-a",
                        "commit_sha": None,
                        "score": 0.91,
                    }
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
            include_context=False,
            limit=1,
        )

    assert result["ok"] is True
    assert result["candidate_limit"] == 50
    assert result["embedded_symbol_count"] == 1
    assert result["returned_count"] == 1
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_context_warning_is_attached_per_hit_when_snippet_provider_unavailable() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 1})
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "embedding_input_hash": "hash-a",
                        "commit_sha": None,
                        "score": 0.91,
                    }
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
        )

    context = result["result"][0]["context"]
    assert context["available"] is False
    assert context["warning_code"] == "snippet_provider_unavailable"
    assert context["warning"] == "snippet provider unavailable"


@pytest.mark.asyncio
async def test_context_limit_zero_returns_empty_usage_preview() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 1})
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "embedding_input_hash": "hash-a",
                        "commit_sha": "sha-a",
                        "score": 0.91,
                    }
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    fake_session = AsyncMock()
    fake_session.call_tool = AsyncMock(
        return_value=_make_tool_result(
            {
                "source": "func verify() {}",
                "language": "swift",
                "start_line": 10,
                "end_line": 12,
            }
        )
    )

    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=fake_session,
        ),
        patch("palace_mcp.code.find_semantic.TantivyBridge") as tantivy_bridge,
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
            context_limit=0,
        )

    context = result["result"][0]["context"]
    assert context["available"] is True
    assert context["usages_preview"] == []
    tantivy_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_dispatcher_factory_is_reused_across_calls() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    factory_calls = 0

    def factory() -> EmbeddingBackendDispatcher:
        nonlocal factory_calls
        factory_calls += 1
        return EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    set_embedding_dispatcher_factory(factory)

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 1})
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "embedding_input_hash": "hash-a",
                        "commit_sha": None,
                        "score": 0.91,
                    }
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)

    first = await semantic_search(
        driver=driver,
        query="first query",
        project="wallet-core",
        include_context=False,
    )
    second = await semantic_search(
        driver=driver,
        query="second query",
        project="wallet-core",
        include_context=False,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    assert factory_calls == 1
    assert backend.calls == ["first query", "second query"]
