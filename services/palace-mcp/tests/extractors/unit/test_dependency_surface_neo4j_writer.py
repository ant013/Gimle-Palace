"""Unit-only tests for neo4j_writer argument shapes — Task 6.

Counter-based idempotency tests (which need real Neo4j) live in:
  tests/extractors/integration/test_dependency_surface_integration.py
"""

from __future__ import annotations

import pytest

from palace_mcp.extractors.dependency_surface.models import ParsedDep
from palace_mcp.extractors.dependency_surface.neo4j_writer import (
    _UPSERT_DEPENDS_ON_EDGE,
    write_to_neo4j,
)


def test_write_to_neo4j_is_importable() -> None:
    """Smoke: module imports cleanly and exposes write_to_neo4j."""
    assert callable(write_to_neo4j)


def test_depends_on_edge_query_cannot_orphan_dependency_nodes() -> None:
    """Writer must not create :ExternalDependency without a source :Project edge."""
    assert "MERGE (p:Project {slug: $project_slug})" in _UPSERT_DEPENDS_ON_EDGE
    assert "p.group_id = $group_id" in _UPSERT_DEPENDS_ON_EDGE
    assert (
        "WITH p\nMATCH (d:ExternalDependency {purl: $purl})" in _UPSERT_DEPENDS_ON_EDGE
    )


class _FakeCounters:
    nodes_created = 1
    relationships_created = 1


class _FakeSummary:
    counters = _FakeCounters()


class _FakeResult:
    async def consume(self) -> _FakeSummary:
        return _FakeSummary()


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    async def run(self, query: str, **params: object) -> _FakeResult:
        self.calls.append((query, params))
        return _FakeResult()


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


@pytest.mark.asyncio
async def test_write_to_neo4j_passes_group_id_to_project_merge() -> None:
    session = _FakeSession()
    dep = ParsedDep(
        project_id="evm-kit",
        purl="pkg:npm/example@1.0.0",
        ecosystem="npm",
        declared_version_constraint="^1.0.0",
        resolved_version="1.0.0",
        scope="compile",
        declared_in="package.json",
    )

    nodes_created, relationships_created = await write_to_neo4j(
        _FakeDriver(session),  # type: ignore[arg-type]
        [dep],
        project_slug="evm-kit",
        group_id="gimle/evm-kit",
    )

    assert (nodes_created, relationships_created) == (1, 1)
    edge_query, edge_params = session.calls[1]
    assert edge_query == _UPSERT_DEPENDS_ON_EDGE
    assert edge_params["project_slug"] == "evm-kit"
    assert edge_params["group_id"] == "gimle/evm-kit"
