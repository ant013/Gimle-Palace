"""Tests for palace.code.semantic_search."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
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


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _run_text(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _make_tool_result(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        isError=False,
    )


def _is_vector_query(query: str) -> bool:
    return "queryNodes('symbol_embedding_idx'" in query or (
        "VECTOR INDEX symbol_embedding_idx" in query
    )


@pytest.fixture(autouse=True)
def _reset_embedding_factory() -> None:
    try:
        from palace_mcp.code.find_semantic import (
            _reset_vector_search_capability_for_tests,
        )
    except ImportError:
        _reset_vector_search_capability_for_tests = None

    set_embedding_dispatcher_factory(None)
    if _reset_vector_search_capability_for_tests is not None:
        _reset_vector_search_capability_for_tests()
    yield
    set_embedding_dispatcher_factory(None)
    if _reset_vector_search_capability_for_tests is not None:
        _reset_vector_search_capability_for_tests()


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
async def test_semantic_search_tool_defaults_to_compact_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp import mcp_server

    captured: dict[str, Any] = {}

    async def _fake_impl(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"ok": True, "result": [], "returned_count": 0}

    monkeypatch.setattr("palace_mcp.mcp_server._semantic_search_impl", _fake_impl)
    monkeypatch.setattr("palace_mcp.mcp_server.get_settings", lambda: None)
    mcp_server._driver = MagicMock()
    try:
        result = await mcp_server.palace_code_semantic_search(query="wallet")
    finally:
        mcp_server._driver = None

    assert result["ok"] is True
    assert captured["include_context"] is False


@pytest.mark.asyncio
async def test_semantic_search_tool_allows_verbose_context_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from palace_mcp import mcp_server

    captured: dict[str, Any] = {}

    async def _fake_impl(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"ok": True, "result": [], "returned_count": 0}

    monkeypatch.setattr("palace_mcp.mcp_server._semantic_search_impl", _fake_impl)
    monkeypatch.setattr("palace_mcp.mcp_server.get_settings", lambda: None)
    mcp_server._driver = MagicMock()
    try:
        result = await mcp_server.palace_code_semantic_search(
            query="wallet", include_context=True
        )
    finally:
        mcp_server._driver = None

    assert result["ok"] is True
    assert captured["include_context"] is True


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
        if _is_vector_query(query):
            assert params["query_k"] == 50
            all_rows = [
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
            gids = set(params.get("group_ids", []))
            return _FakeResult(
                data_value=[r for r in all_rows if r["group_id"] in gids]
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
    assert result["result"][0]["short_name"] == "verify"
    assert result["result"][0]["kind"] == "function"
    assert result["result"][0]["label"] == "Function"
    assert "context" not in result["result"][0]
    assert result["warnings"] == []
    cm_session_getter.assert_not_called()


@pytest.mark.asyncio
async def test_semantic_search_returns_canonical_struct_identity() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 1, "embedded_cnt": 1}]
            )
        if _is_vector_query(query):
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "WalletKit s:9WalletKit11BalanceDataV",
                        "short_name": "BalanceData",
                        "kind": "struct",
                        "label": "Struct",
                        "file_path": "Sources/BalanceData.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
                        "commit_sha": "sha-a",
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
            query="balance data",
            project="wallet-core",
            limit=1,
            include_context=False,
        )

    hit = result["result"][0]
    assert hit["qualified_name"] == "WalletKit s:9WalletKit11BalanceDataV"
    assert hit["short_name"] == "BalanceData"
    assert hit["kind"] == "struct"
    assert hit["label"] == "Struct"


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
        if _is_vector_query(query):
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
async def test_single_project_search_retries_until_scoped_hits_are_found() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")
    query_ks: list[int] = []

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["small-kit"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {"source_scope": "project", "total": 1500, "embedded_cnt": 1500}
                ]
            )
        if _is_vector_query(query):
            assert params["group_ids"] == ["project/small-kit"]
            query_ks.append(params["query_k"])
            if params["query_k"] < 200:
                return _FakeResult(data_value=[])
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/small-kit",
                        "qualified_name": "SmallKit.verifySignature",
                        "kind": "function",
                        "file_path": "Sources/Verify.swift",
                        "module_name": "SmallKit",
                        "source_scope": "project",
                        "embedding_input_hash": "hash-small",
                        "commit_sha": None,
                        "score": 0.88,
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
            project="small-kit",
            include_context=False,
            limit=1,
        )

    assert query_ks == [50, 200]
    assert result["ok"] is True
    assert result["candidate_limit"] == 200
    assert result["returned_count"] == 1
    assert result["warnings"] == []
    assert result["result"][0]["project"] == "small-kit"


@pytest.mark.asyncio
async def test_include_deprecated_true_returns_seeded_row() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            assert params["include_deprecated"] is True
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 1, "embedded_cnt": 1}]
            )
        if _is_vector_query(query):
            assert params["include_deprecated"] is True
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/wallet-core",
                        "qualified_name": "Crypto.legacyVerify",
                        "kind": "function",
                        "file_path": "Sources/Legacy.swift",
                        "module_name": "WalletCore",
                        "source_scope": "project",
                        "embedding_input_hash": "deprecated-hash",
                        "commit_sha": "deprecated-sha",
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
            query="legacy signature verification",
            project="wallet-core",
            include_deprecated=True,
            include_context=False,
            limit=1,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["result"][0]["qualified_name"] == "Crypto.legacyVerify"


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
        if _is_vector_query(query):
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
async def test_deleted_post_snapshot_hit_is_marked_stale(
    tmp_path: Path,
) -> None:
    from palace_mcp.code.find_semantic import semantic_search

    repo_path = tmp_path / "wallet-core"
    repo_path.mkdir()
    _run(["git", "init", "-q", "-b", "main"], cwd=repo_path)
    _run(["git", "config", "user.email", "t@t"], cwd=repo_path)
    _run(["git", "config", "user.name", "T"], cwd=repo_path)
    (repo_path / "Sources").mkdir()
    (repo_path / "Sources" / "A.swift").write_text("func verify() {}\n")
    _run(["git", "add", "."], cwd=repo_path)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo_path)
    indexed_commit = _run_text(["git", "rev-parse", "HEAD"], cwd=repo_path)
    (repo_path / "Sources" / "A.swift").unlink()
    _run(["git", "add", "-A"], cwd=repo_path)
    _run(["git", "commit", "-m", "delete", "-q"], cwd=repo_path)

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 1, "embedded_cnt": 1}]
            )
        if _is_vector_query(query):
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
                        "commit_sha": indexed_commit,
                        "score": 0.91,
                    }
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)

    async def _resolve_repo_path(_: str) -> Path:
        return repo_path

    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
        patch(
            "palace_mcp.code.find_semantic._resolve_registered_repo_path",
            _resolve_repo_path,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="signature verification",
            project="wallet-core",
            include_context=True,
            context_limit=0,
        )

    hit = result["result"][0]
    assert hit["stale"] is True
    assert hit["indexed_commit"] == indexed_commit
    assert hit["commits_behind_head"] == 1
    assert hit["context"]["warning_code"] == "missing_source_file"


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
        if _is_vector_query(query):
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
        if _is_vector_query(query):
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
        if _is_vector_query(query):
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
        if _is_vector_query(query):
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
        if _is_vector_query(query):
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


@pytest.mark.asyncio
async def test_multi_project_issues_per_project_hnsw_queries() -> None:
    """Multi-project search fans out one HNSW query per project with per_project_k budget."""
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")

    project_rows: dict[str, list[dict[str, Any]]] = {
        "project/alpha": [
            {
                "group_id": "project/alpha",
                "qualified_name": "Alpha.verify",
                "kind": "function",
                "file_path": "Alpha.swift",
                "module_name": "Alpha",
                "source_scope": "project",
                "embedding_input_hash": None,
                "commit_sha": None,
                "score": 0.95,
            }
        ],
        "project/beta": [
            {
                "group_id": "project/beta",
                "qualified_name": "Beta.verify",
                "kind": "function",
                "file_path": "Beta.swift",
                "module_name": "Beta",
                "source_scope": "project",
                "embedding_input_hash": None,
                "commit_sha": None,
                "score": 0.60,
            }
        ],
        "project/gamma": [
            {
                "group_id": "project/gamma",
                "qualified_name": "Gamma.verify",
                "kind": "function",
                "file_path": "Gamma.swift",
                "module_name": "Gamma",
                "source_scope": "project",
                "embedding_input_hash": None,
                "commit_sha": None,
                "score": 0.55,
            }
        ],
    }

    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(
                single_value={"found_projects": ["alpha", "beta", "gamma"]}
            )
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 30, "embedded_cnt": 9}]
            )
        if _is_vector_query(query):
            gids = params.get("group_ids", [])
            rows = [r for gid in gids for r in project_rows.get(gid, [])]
            return _FakeResult(data_value=rows)
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with patch(
        "palace_mcp.code.find_semantic.get_embedding_dispatcher",
        return_value=dispatcher,
    ):
        result = await semantic_search(
            driver=driver,
            query="shared func",
            projects=["alpha", "beta", "gamma"],
            limit=3,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 3
    # _candidate_limit(3, 3) = min(max(90, 50), 500) = 90
    assert result["candidate_limit"] == 90
    # _candidate_limit(3, 1) = min(max(30, 50), 500) = 50
    assert result["per_project_k"] == 50

    # One HNSW query per project, each scoped to a single group_id
    vector_calls = [(q, p) for q, p in driver._session.calls if _is_vector_query(q)]
    assert len(vector_calls) == 3
    queried_groups = {p["group_ids"][0] for _, p in vector_calls}
    assert queried_groups == {"project/alpha", "project/beta", "project/gamma"}
    assert all(p["query_k"] == result["per_project_k"] for _, p in vector_calls)

    # All three projects represented — per-project budget ensures fairness
    result_projects = {r["project"] for r in result["result"]}
    assert result_projects == {"alpha", "beta", "gamma"}


# --------------------------------------------------------------------------
# GIM-SEMANTIC-UNDERFILL (Sprint-1 reliability): pagination must be honest.
# Old behavior: has_more computed against the WHOLE embedded-scope population
# (total_candidates), so a scope-filtered page reported has_more=true with
# 0-2 rows and consumers could never make an absence claim.
# --------------------------------------------------------------------------


def _underfill_run_fn(
    *,
    embedded_total: int,
    vector_rows: list[dict[str, Any]],
    expected_query_k: int | None = None,
) -> Any:
    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-a"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {
                        "source_scope": "project",
                        "total": embedded_total,
                        "embedded_cnt": embedded_total,
                    }
                ]
            )
        if _is_vector_query(query):
            if expected_query_k is not None:
                assert params["query_k"] == expected_query_k
            return _FakeResult(data_value=list(vector_rows))
        raise AssertionError(f"unexpected query: {query}")

    return run_fn


def _mk_row(
    i: int, *, source_scope: str = "project", score: float = 0.9
) -> dict[str, Any]:
    return {
        "group_id": "project/wallet-a",
        "qualified_name": f"Crypto.fn{i}",
        "kind": "function",
        "file_path": f"Sources/F{i}.swift",
        "module_name": "WalletA",
        "source_scope": source_scope,
        "embedding_input_hash": f"hash-{i}",
        "commit_sha": "sha-a",
        "score": score,
    }


async def _run_underfill_search(run_fn: Any, *, limit: int = 3) -> dict[str, Any]:
    from palace_mcp.code.find_semantic import semantic_search

    backend = _FakeBackend()
    dispatcher = EmbeddingBackendDispatcher({"qodo": backend}, default_backend="qodo")
    driver = _FakeDriver(run_fn)
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=dispatcher,
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            MagicMock(),
        ),
    ):
        return await semantic_search(
            driver=driver,
            query="signature verification",
            projects=["wallet-a"],
            limit=limit,
            include_context=False,
        )


@pytest.mark.asyncio
async def test_scope_filtered_page_does_not_claim_has_more() -> None:
    """Repro of GIM-SEMANTIC-UNDERFILL: pool of 5, scope filter keeps 1.

    The whole scope has 1000 embedded symbols; the old envelope said
    has_more=true against that population. Honest: total = surviving rows,
    has_more = false, and the pool being exhausted proves the absence claim.
    """
    rows = [_mk_row(0)] + [_mk_row(i, source_scope="dependency") for i in range(1, 5)]
    result = await _run_underfill_search(
        _underfill_run_fn(embedded_total=1000, vector_rows=rows)
    )
    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["scope_excluded_count"] == 4
    assert result["total"] == 1  # survivors, not the 1000-symbol population
    assert result["has_more"] is False  # absence claim is now safe
    assert result["candidate_pool_exhausted"] is True
    assert result["scope_embedded_total"] == 1000
    assert result["truncated"] is False


@pytest.mark.asyncio
async def test_surviving_rows_beyond_page_report_has_more() -> None:
    rows = [_mk_row(i, score=0.9 - i * 0.01) for i in range(6)]
    result = await _run_underfill_search(
        _underfill_run_fn(embedded_total=1000, vector_rows=rows), limit=2
    )
    assert result["returned_count"] == 2
    assert result["total"] == 6
    assert result["has_more"] is True  # positive fact: 4 more survivors in hand
    assert result["next_offset"] == 2


@pytest.mark.asyncio
async def test_capped_pool_flags_unproven_absence() -> None:
    """Pool returned exactly query_k rows (cap hit) and the scope filter ate
    almost everything: has_more stays false (no survivors in hand) but the
    response must say the absence is NOT proven."""
    query_k = 50  # _candidate_limit(3, 1) -> max(30, 50) = 50
    rows = [_mk_row(0)] + [
        _mk_row(i, source_scope="dependency") for i in range(1, query_k)
    ]
    result = await _run_underfill_search(
        _underfill_run_fn(embedded_total=1000, vector_rows=rows)
    )
    assert result["returned_count"] == 1
    assert result["has_more"] is False
    assert result["candidate_pool_exhausted"] is False
    assert result["truncated"] is True
    assert result["truncated_reason"] == "candidate_pool_capped"
    codes = [w["code"] for w in result["warnings"]]
    assert "candidate_pool_capped" in codes
