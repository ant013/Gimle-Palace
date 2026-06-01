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
        if "embedded_cnt" in query:
            return _FakeResult(data_value=[])  # no embedded symbols
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
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 10, "embedded_cnt": 3}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            assert params["query_k"] == 50
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-a",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletA",
                        "source_scope": "project",
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
                        "source_scope": "project",
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
async def test_vector_query_uses_candidate_limit_to_overfetch_before_scope_filter() -> (
    None
):
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 5, "embedded_cnt": 1}]
            )
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
                        "source_scope": "project",
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
async def test_context_warning_is_attached_per_hit_when_project_not_mounted() -> None:
    """When project is not mounted locally and CM session is absent, per-hit warning."""
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 5, "embedded_cnt": 1}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
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
    # Local provider returns project_not_mounted when /repos/<project> absent;
    # CM fallback is skipped because it is the project_not_mounted path.
    assert context["warning_code"] == "project_not_mounted"


@pytest.mark.asyncio
async def test_context_limit_zero_returns_empty_usage_preview() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 5, "embedded_cnt": 1}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
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
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 5, "embedded_cnt": 1}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
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


@pytest.mark.asyncio
async def test_embedding_coverage_included_in_success_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp.code.find_semantic import semantic_search

    monkeypatch.setenv("PALACE_EMBEDDING_MAX_SYMBOLS", "128")

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {"source_scope": "project", "total": 1000, "embedded_cnt": 120},
                    {
                        "source_scope": "workspace_package",
                        "total": 500,
                        "embedded_cnt": 8,
                    },
                    {"source_scope": "sdk", "total": 251218, "embedded_cnt": 0},
                ]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
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
            query="crypto verify",
            project="wallet-core",
            include_context=False,
        )

    assert result["ok"] is True
    cov = result["embedding_coverage"]
    assert cov["bounded"] is True
    assert cov["max_symbols"] == 128
    assert cov["embedded_symbols"] == 128  # 120 + 8
    assert cov["eligible_symbols"] == 252718  # 1000 + 500 + 251218
    assert cov["source_scope_counts"] == {"project": 120, "workspace_package": 8}


@pytest.mark.asyncio
async def test_embedding_coverage_included_in_no_embeddings_response() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(data_value=[])
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
    cov = result["embedding_coverage"]
    assert cov["bounded"] is False
    assert cov["embedded_symbols"] == 0
    assert cov["eligible_symbols"] == 0
    assert cov["source_scope_counts"] == {}


@pytest.mark.asyncio
async def test_runtime_path_fails_closed_on_coverage_count_mismatch() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")
    settings = MagicMock(neo4j_uri="bolt://neo4j:7687")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["uw-ios-app"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {"source_scope": "dependency", "total": 1024, "embedded_cnt": 512}
                ]
            )
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 2186})
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="monero",
            project="uw-ios-app",
            include_context=False,
            settings=settings,
        )

    assert result["ok"] is False
    assert result["error_code"] == "semantic_search_backend_inconsistent"
    assert result["inconsistency_kind"] == "coverage_count_mismatch"
    assert result["embedded_symbol_count"] == 512
    assert result["live_embedded_symbol_count"] == 2186
    assert result["runtime"] == {
        "git_sha": "unknown",
        "neo4j_uri": "bolt://neo4j:7687",
    }


@pytest.mark.asyncio
async def test_runtime_path_fails_closed_on_missing_vector_hits() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")
    settings = MagicMock(neo4j_uri="bolt://neo4j:7687")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["uw-ios-app"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {"source_scope": "project", "total": 69231, "embedded_cnt": 2186}
                ]
            )
        if "embedded_symbol_count" in query:
            return _FakeResult(single_value={"embedded_symbol_count": 2186})
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/uw-ios-app",
                        "qualified_name": "Unstoppable.ImageResource.nftAmount32",
                        "kind": "enum",
                        "file_path": "GeneratedAssetSymbols.swift",
                        "module_name": "Unstoppable",
                        "source_scope": "dependency",
                        "embedding_input_hash": "stale-hash",
                        "commit_sha": None,
                        "score": 0.99,
                    }
                ]
            )
        if (
            "OPTIONAL MATCH (s:Symbol {group_id: hit.group_id, qualified_name: hit.qualified_name})"
            in query
        ):
            assert params["hits"] == [
                {
                    "group_id": "project/uw-ios-app",
                    "qualified_name": "Unstoppable.ImageResource.nftAmount32",
                }
            ]
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/uw-ios-app",
                        "qualified_name": "Unstoppable.ImageResource.nftAmount32",
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
            query="monero",
            project="uw-ios-app",
            include_context=False,
            settings=settings,
        )

    assert result["ok"] is False
    assert result["error_code"] == "semantic_search_backend_inconsistent"
    assert result["inconsistency_kind"] == "missing_vector_hits"
    assert result["missing_hit_count"] == 1
    assert result["missing_hits"] == [
        {
            "group_id": "project/uw-ios-app",
            "qualified_name": "Unstoppable.ImageResource.nftAmount32",
        }
    ]


@pytest.mark.asyncio
async def test_hydrate_context_runs_loads_concurrently() -> None:
    """_hydrate_context issues both load calls concurrently via asyncio.gather."""
    import asyncio

    from palace_mcp.code.find_semantic import _hydrate_context

    call_order: list[str] = []

    async def fake_snippet(**_: Any) -> tuple[Any, Any, Any]:
        call_order.append("snippet_start")
        await asyncio.sleep(0)
        call_order.append("snippet_end")
        return None, None, None

    async def fake_usage(**_: Any) -> tuple[Any, Any, Any]:
        call_order.append("usage_start")
        await asyncio.sleep(0)
        call_order.append("usage_end")
        return [], None, None

    with (
        patch("palace_mcp.code.find_semantic._load_snippet_context", fake_snippet),
        patch("palace_mcp.code.find_semantic._load_usage_preview", fake_usage),
    ):
        await _hydrate_context(
            settings=None,
            project="proj",
            qualified_name="Foo.bar",
            file_path="src/Foo.swift",
            line_start=1,
            line_end=5,
            commit_sha="abc123",
            context_limit=3,
        )

    # Both loads start before either finishes — confirms gather, not sequential.
    assert call_order.index("usage_start") < call_order.index("snippet_end")


@pytest.mark.asyncio
async def test_semantic_search_hydrates_hits_concurrently() -> None:
    """semantic_search calls _hydrate_context for all hits concurrently via asyncio.gather."""
    import asyncio

    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 10, "embedded_cnt": 5}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.verify",
                        "kind": "function",
                        "file_path": "Sources/A.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
                        "score": 0.91,
                    },
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.sign",
                        "kind": "function",
                        "file_path": "Sources/B.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
                        "score": 0.85,
                    },
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    call_order: list[str] = []

    async def fake_hydrate(*, qualified_name: str, **_: Any) -> dict[str, Any]:
        call_order.append(f"{qualified_name}_start")
        await asyncio.sleep(0)
        call_order.append(f"{qualified_name}_end")
        return {"available": False}

    driver = _FakeDriver(run_fn)
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic._hydrate_context",
            new=fake_hydrate,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
            limit=2,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 2
    # Both hydrations start before either finishes — confirms gather, not sequential.
    assert call_order.index("Crypto.verify_start") < call_order.index("Crypto.sign_end")
    assert call_order.index("Crypto.sign_start") < call_order.index("Crypto.verify_end")
