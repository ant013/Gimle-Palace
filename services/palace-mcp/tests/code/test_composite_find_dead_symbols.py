"""Tests for palace.code.find_dead_symbols composite MCP tool (GIM-228, S0.2).

3 cases per spec:
  - project_not_registered → error response
  - empty graph (no DeadSymbolCandidate nodes) → ok=True, result=[]
  - seeded fixture → ok=True, result has expected items

Happy-path tests require Neo4j; marked @integration so they are skipped when
testcontainers are unavailable.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest_plugins = ("tests.integration.hotspot_wire_support",)


# ---------------------------------------------------------------------------
# Error path (mocked driver)
# ---------------------------------------------------------------------------


def _mock_driver_no_project() -> MagicMock:
    """Returns a driver that always finds no :Project node."""
    single_result = AsyncMock()
    single_result.single = AsyncMock(return_value=None)
    session = AsyncMock()
    session.run = AsyncMock(return_value=single_result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


class _FakeResult:
    def __init__(
        self,
        *,
        single_value: Any | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self._single_value = single_value
        self._rows = rows or []

    async def single(self) -> Any | None:
        return self._single_value

    def __aiter__(self) -> Any:
        async def _iterate() -> Any:
            for row in self._rows:
                yield row

        return _iterate()


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


def _run_fn_dead_symbols(
    rows: list[dict[str, Any]],
    *,
    observed: list[tuple[str, dict[str, Any]]] | None = None,
) -> Any:
    def run_fn(query: str, params: dict[str, Any]) -> _FakeResult:
        if observed is not None:
            observed.append((query, params))
        if "MATCH (p:Project" in query:
            return _FakeResult(single_value={"slug": params["slug"]})
        if "RETURN count(c) AS total" in query:
            if params["include_dependencies"]:
                total = len(rows)
            else:
                markers = tuple(params["dependency_markers"])
                total = sum(
                    1
                    for row in rows
                    if not any(
                        marker in (row.get("source_file") or "") for marker in markers
                    )
                )
            return _FakeResult(single_value={"total": total})
        if "MATCH (c:DeadSymbolCandidate" in query:
            filtered = rows
            if not params["include_dependencies"]:
                markers = tuple(params["dependency_markers"])
                filtered = [
                    row
                    for row in rows
                    if not any(
                        marker in (row.get("source_file") or "") for marker in markers
                    )
                ]
            start = int(params["offset"])
            end = start + int(params["limit"])
            return _FakeResult(rows=filtered[start:end])
        raise AssertionError(f"unexpected query: {query}")

    return run_fn


@pytest.mark.asyncio
async def test_find_dead_symbols_project_not_registered() -> None:
    """find_dead_symbols returns error when project is not registered."""
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    driver = _mock_driver_no_project()
    result = await find_dead_symbols(driver=driver, project="no-such-project")
    assert result["ok"] is False
    assert result["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_find_dead_symbols_excludes_dependency_paths_by_default() -> None:
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    rows = [
        {
            "id": "project-row",
            "display_name": "ProjectOnly",
            "kind": "class",
            "module_name": "AppModule",
            "language": "swift",
            "candidate_state": "unused_candidate",
            "confidence": "high",
            "accessibility": "internal",
            "source_file": "Unstoppable/Services/BalanceService.swift",
            "source_line": 12,
            "hints": ["unused"],
            "commit_sha": "abc123",
            "evidence_source": "periphery",
        },
        {
            "id": "dep-row",
            "display_name": "DependencyOnly",
            "kind": "class",
            "module_name": "WalletKit",
            "language": "swift",
            "candidate_state": "unused_candidate",
            "confidence": "high",
            "accessibility": "internal",
            "source_file": "checkouts/WalletKit/Sources/WalletClient.swift",
            "source_line": 4,
            "hints": ["unused"],
            "commit_sha": "def456",
            "evidence_source": "periphery",
        },
    ]
    driver = _FakeDriver(_run_fn_dead_symbols(rows))

    result = await find_dead_symbols(driver=driver, project="uw-ios-app")

    assert result["ok"] is True
    assert [row["display_name"] for row in result["result"]] == ["ProjectOnly"]


@pytest.mark.asyncio
async def test_find_dead_symbols_can_include_dependency_paths() -> None:
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    rows = [
        {
            "id": "dep-row",
            "display_name": "DependencyOnly",
            "kind": "class",
            "module_name": "WalletKit",
            "language": "swift",
            "candidate_state": "unused_candidate",
            "confidence": "high",
            "accessibility": "internal",
            "source_file": "checkouts/WalletKit/Sources/WalletClient.swift",
            "source_line": 4,
            "hints": ["unused"],
            "commit_sha": "def456",
            "evidence_source": "periphery",
        }
    ]
    driver = _FakeDriver(_run_fn_dead_symbols(rows))

    result = await find_dead_symbols(
        driver=driver,
        project="uw-ios-app",
        include_dependencies=True,
    )

    assert result["ok"] is True
    assert [row["display_name"] for row in result["result"]] == ["DependencyOnly"]


@pytest.mark.asyncio
async def test_find_dead_symbols_keeps_query_bounded_before_dependency_filtering() -> (
    None
):
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    observed: list[tuple[str, dict[str, Any]]] = []
    rows = [
        {
            "id": "dep-row",
            "display_name": "DependencyOnly",
            "kind": "class",
            "module_name": "WalletKit",
            "language": "swift",
            "candidate_state": "unused_candidate",
            "confidence": "high",
            "accessibility": "internal",
            "source_file": "checkouts/WalletKit/Sources/WalletClient.swift",
            "source_line": 4,
            "hints": ["unused"],
            "commit_sha": "def456",
            "evidence_source": "periphery",
        },
        {
            "id": "project-row",
            "display_name": "ProjectOnly",
            "kind": "class",
            "module_name": "AppModule",
            "language": "swift",
            "candidate_state": "unused_candidate",
            "confidence": "high",
            "accessibility": "internal",
            "source_file": "Unstoppable/Services/BalanceService.swift",
            "source_line": 12,
            "hints": ["unused"],
            "commit_sha": "abc123",
            "evidence_source": "periphery",
        },
    ]
    driver = _FakeDriver(_run_fn_dead_symbols(rows, observed=observed))

    result = await find_dead_symbols(driver=driver, project="uw-ios-app", limit=23)

    assert result["ok"] is True
    query, params = next(
        (query, params)
        for query, params in observed
        if "MATCH (c:DeadSymbolCandidate" in query and "LIMIT $limit" in query
    )
    assert "LIMIT $limit" in query
    assert params["limit"] == 23


# ---------------------------------------------------------------------------
# Happy-path integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dead_symbols_empty_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"ds-empty-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
    yield slug
    with drv.session() as sess:
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.fixture(scope="module")
def dead_symbols_seeded_project(
    neo4j_uri: str, neo4j_auth: tuple[str, str]
) -> Iterator[str]:
    from neo4j import GraphDatabase

    slug = f"ds-seeded-{uuid.uuid4().hex[:8]}"
    drv = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    with drv.session() as sess:
        sess.run("MERGE (p:Project {slug: $s})", s=slug)
        sess.run(
            """
            CREATE (c:DeadSymbolCandidate {
                id: 'c1', project: $slug, group_id: $gid,
                module_name: 'CoreModule', language: 'swift',
                display_name: 'UnusedView', kind: 'class',
                candidate_state: 'unused_candidate',
                confidence: 'high',
                accessibility: 'internal',
                evidence_source: 'periphery', evidence_mode: 'static',
                commit_sha: 'abc123', symbol_key: 'CoreModule.UnusedView',
                hints: ['unused', 'declared'],
                schema_version: 1
            })
            """,
            slug=slug,
            gid=f"project/{slug}",
        )
    yield slug
    with drv.session() as sess:
        sess.run(
            "MATCH (n) WHERE n.project = $s OR n.group_id = $g DETACH DELETE n",
            s=slug,
            g=f"project/{slug}",
        )
        sess.run("MATCH (p:Project {slug: $s}) DETACH DELETE p", s=slug)
    drv.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_empty_graph(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    dead_symbols_empty_project: str,
) -> None:
    """Empty graph returns ok=True with empty result list."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_dead_symbols(driver=drv, project=dead_symbols_empty_project)
    finally:
        await drv.close()
    assert result["ok"] is True
    assert result["result"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_dead_symbols_seeded(
    neo4j_uri: str,
    neo4j_auth: tuple[str, str],
    dead_symbols_seeded_project: str,
) -> None:
    """Seeded fixture returns expected dead symbol items with required fields."""
    from neo4j import AsyncGraphDatabase
    from palace_mcp.code.find_dead_symbols import find_dead_symbols

    drv = AsyncGraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
    try:
        result = await find_dead_symbols(
            driver=drv, project=dead_symbols_seeded_project
        )
    finally:
        await drv.close()
    assert result["ok"] is True
    rows = result["result"]
    assert len(rows) >= 1
    row = rows[0]
    for field in (
        "display_name",
        "kind",
        "module_name",
        "language",
        "candidate_state",
        "confidence",
        "accessibility",
        "hints",
    ):
        assert field in row, f"Missing field: {field}"
    assert row["display_name"] == "UnusedView"
    assert row["candidate_state"] == "unused_candidate"
    assert row["accessibility"] == "internal"
    assert row["hints"] == ["unused", "declared"]
