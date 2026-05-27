"""Tests for source_scope filtering in palace.code.semantic_search (GIM-920).

Covers:
- Default search returns only project + workspace_package scope hits.
- Dependency hits excluded by default; included when include_dependencies=True.
- Generated/derived hits excluded by default; included when include_generated=True.
- SDK hits excluded by default; included when include_sdk=True.
- Explicit source_scopes list is authoritative (overrides flags).
- Legacy null source_scope treated as "dependency" (excluded from defaults).
- scope_excluded_count reported in response.
- Cross-project search works with explicit scope flags.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from palace_mcp.embeddings import EmbeddingBackendDispatcher


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

    async def run(self, query: str, **params: Any) -> _FakeResult:
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
    def embed_text(self, text: str) -> list[float]:
        return [0.1, 0.2]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def _dispatcher() -> EmbeddingBackendDispatcher:
    return EmbeddingBackendDispatcher(
        {"qodo": _FakeBackend()}, default_backend="qodo"
    )


def _make_run_fn(rows: list[dict[str, Any]]) -> Any:
    """Return a run_fn that delivers the given rows for the vector query."""

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(single_value={"found_projects": ["wallet-core"]})
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[
                    {"source_scope": "project", "total": 10, "embedded_cnt": 5}
                ]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(data_value=rows)
        raise AssertionError(f"unexpected query: {query}")

    return run_fn


def _project_hit(scope: str | None) -> dict[str, Any]:
    return {
        "group_id": "project/wallet-core",
        "qualified_name": f"Sym.{scope or 'null'}",
        "kind": "function",
        "file_path": "Sources/X.swift",
        "module_name": "WalletCore",
        "source_scope": scope,
        "embedding_input_hash": "hash",
        "commit_sha": None,
        "score": 0.90,
    }


@pytest.mark.asyncio
async def test_default_includes_project_scope() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("project")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_default_includes_workspace_package_scope() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("workspace_package")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_default_excludes_dependency_scope() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("dependency")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["scope_excluded_count"] == 1


@pytest.mark.asyncio
async def test_default_excludes_generated_scope() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("generated")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["scope_excluded_count"] == 1


@pytest.mark.asyncio
async def test_default_excludes_sdk_scope() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("sdk")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["scope_excluded_count"] == 1


@pytest.mark.asyncio
async def test_null_scope_treated_as_dependency_excluded_by_default() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit(None)]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
    ):
        result = await semantic_search(
            driver=driver, query="auth", project="wallet-core", include_context=False
        )

    assert result["ok"] is True
    assert result["returned_count"] == 0
    assert result["scope_excluded_count"] == 1


@pytest.mark.asyncio
async def test_null_scope_included_when_dependency_requested() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit(None)]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            include_dependencies=True,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_include_dependencies_flag() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(
        _make_run_fn([_project_hit("project"), _project_hit("dependency")])
    )
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            include_dependencies=True,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 2
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_include_generated_flag_includes_generated_and_derived() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(
        _make_run_fn([_project_hit("generated"), _project_hit("derived")])
    )
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            include_generated=True,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 2
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_include_sdk_flag() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    driver = _FakeDriver(_make_run_fn([_project_hit("sdk")]))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            include_sdk=True,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["scope_excluded_count"] == 0


@pytest.mark.asyncio
async def test_explicit_source_scopes_overrides_flags() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    rows = [
        _project_hit("project"),
        _project_hit("dependency"),
        _project_hit("sdk"),
    ]
    driver = _FakeDriver(_make_run_fn(rows))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            source_scopes=["sdk"],
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 1
    assert result["result"][0]["source_scope"] == "sdk"
    assert result["scope_excluded_count"] == 2


@pytest.mark.asyncio
async def test_scope_excluded_count_reported_in_mixed_results() -> None:
    from palace_mcp.code.find_semantic import semantic_search

    rows = [
        _project_hit("project"),
        _project_hit("workspace_package"),
        _project_hit("dependency"),
        _project_hit("generated"),
        _project_hit("sdk"),
    ]
    driver = _FakeDriver(_make_run_fn(rows))
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="auth",
            project="wallet-core",
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 2
    assert result["scope_excluded_count"] == 3


@pytest.mark.asyncio
async def test_cross_project_search_with_scope_filter() -> None:
    """Explicit projects list + include_dependencies covers cross-project expert search."""
    from palace_mcp.code.find_semantic import semantic_search

    def run_fn(query: str, _params: dict[str, Any]) -> _FakeResult:
        if "collect(p.slug)" in query:
            return _FakeResult(
                single_value={"found_projects": ["app", "kit-a", "toolkit"]}
            )
        if "embedded_cnt" in query:
            return _FakeResult(
                data_value=[{"source_scope": "project", "total": 30, "embedded_cnt": 10}]
            )
        if "queryNodes('symbol_embedding_idx'" in query:
            return _FakeResult(
                data_value=[
                    {
                        "group_id": "project/app",
                        "qualified_name": "App.boot",
                        "kind": "function",
                        "file_path": "App/Boot.swift",
                        "module_name": "App",
                        "source_scope": "project",
                        "embedding_input_hash": "h1",
                        "commit_sha": None,
                        "score": 0.95,
                    },
                    {
                        "group_id": "project/kit-a",
                        "qualified_name": "Kit.init",
                        "kind": "function",
                        "file_path": "Kit/Init.swift",
                        "module_name": "KitA",
                        "source_scope": "workspace_package",
                        "embedding_input_hash": "h2",
                        "commit_sha": None,
                        "score": 0.85,
                    },
                    {
                        "group_id": "project/toolkit",
                        "qualified_name": "Util.parse",
                        "kind": "function",
                        "file_path": "Toolkit/Parser.swift",
                        "module_name": "Toolkit",
                        "source_scope": "dependency",
                        "embedding_input_hash": "h3",
                        "commit_sha": None,
                        "score": 0.80,
                    },
                ]
            )
        raise AssertionError(f"unexpected query: {query}")

    driver = _FakeDriver(run_fn)
    with (
        patch(
            "palace_mcp.code.find_semantic.get_embedding_dispatcher",
            return_value=_dispatcher(),
        ),
        patch(
            "palace_mcp.code.find_semantic.code_router.get_cm_session",
            return_value=None,
        ),
    ):
        result = await semantic_search(
            driver=driver,
            query="init boot",
            projects=["app", "kit-a", "toolkit"],
            include_dependencies=True,
            include_context=False,
        )

    assert result["ok"] is True
    assert result["returned_count"] == 3
    assert result["scope_excluded_count"] == 0
    projects = {h["project"] for h in result["result"]}
    assert projects == {"app", "kit-a", "toolkit"}
