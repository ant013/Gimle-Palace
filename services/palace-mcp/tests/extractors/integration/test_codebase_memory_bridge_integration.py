"""Integration tests — CodebaseMemoryBridgeExtractor with real Neo4j.

CM calls are mocked so no CM subprocess is required. Tests verify that
EntityNode rows land in Neo4j with correct labels, group_id, and cm_id.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.codebase_memory_bridge import (
    CodebaseMemoryBridgeExtractor,
    _load_state,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


_FAKE_REPO_PATH = Path("/repos/integ-proj")
_EXPECTED_CM_PROJECT = "repos-integ-proj"  # _cm_project_name(_FAKE_REPO_PATH)


def _ctx(tmp_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="integ-proj",
        group_id="project/integ-proj",
        repo_path=_FAKE_REPO_PATH,
        run_id="integ-run-bridge-001",
        duration_ms=0,
        logger=logging.getLogger("test"),
    )


def _fake_cm(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    architecture: dict[str, Any] | None = None,
) -> Any:
    """Return an async fake for _call_cm that handles tool routing.

    Routes on actual tool names used by the extractor:
      search_graph  → node queries by label
      query_graph   → hash fetch (returns []) or edge fetch (returns edges)
      get_architecture → Louvain/hotspot data

    Asserts that search_graph and query_graph receive the CM-derived project name
    (repos-integ-proj, not the Graphiti slug integ-proj) to catch slug mismatches.
    """
    edges = edges or []

    async def _call(
        tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        if tool == "search_graph":
            got = args.get("project")
            assert got == _EXPECTED_CM_PROJECT, (
                f"search_graph received project={got!r}, expected {_EXPECTED_CM_PROJECT!r}"
            )
            return {"nodes": nodes}
        if tool == "query_graph":
            # Hash-fetch query contains "xxh3_hash"; edge queries don't.
            q = args.get("query", "")
            if "xxh3_hash" in q:
                assert _EXPECTED_CM_PROJECT in q, (
                    f"query_graph hash query uses wrong project: {q!r}"
                )
                return {"result": []}  # no prior hashes → first-run projects all
            return {"result": edges}
        if tool == "get_architecture":
            return architecture or {"communities": [], "hotspots": []}
        return {}

    return _call


# ---------------------------------------------------------------------------
# Task 7 integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bridge_project_node_written_to_neo4j(
    driver: AsyncDriver, graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    """Extractor projects a :Project node into real Neo4j."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "bridge-state.json"

    fake_call = _fake_cm(
        nodes=[
            {
                "uuid": "proj-uuid",
                "name": "integ-proj",
                "labels": ["Project"],
                "qualified_name": "integ-proj",
            },
        ],
    )

    with patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call):
        stats = await ex.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path))

    assert stats.nodes_written >= 1

    async with driver.session() as s:
        result = await s.run(
            "MATCH (n:Project {group_id: $gid}) RETURN n.name AS name, n.cm_id AS cm_id",
            gid="project/integ-proj",
        )
        rows = [r async for r in result]

    assert len(rows) == 1
    assert rows[0]["name"] == "integ-proj"
    assert rows[0]["cm_id"] == "integ-proj:proj-uuid"


@pytest.mark.asyncio
async def test_bridge_symbol_node_written_to_neo4j(
    driver: AsyncDriver, graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    """Extractor projects a :Symbol node into real Neo4j."""
    ex = CodebaseMemoryBridgeExtractor()
    ex._state_path = tmp_path / "bridge-state.json"

    fake_call = _fake_cm(
        nodes=[
            {
                "uuid": "fn-uuid",
                "name": "my_func",
                "labels": ["Function"],
                "qualified_name": "integ_proj.my_func",
                "xxh3": "hash-abc",
                "path": "src/main.py",
            },
        ],
    )

    with patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call):
        stats = await ex.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path))

    assert stats.nodes_written >= 1

    async with driver.session() as s:
        result = await s.run(
            "MATCH (n:Symbol {group_id: $gid}) RETURN n.name AS name, n.cm_id AS cm_id, n.kind AS kind",
            gid="project/integ-proj",
        )
        rows = [r async for r in result]

    assert len(rows) == 1
    assert rows[0]["name"] == "my_func"
    assert rows[0]["cm_id"] == "integ-proj:fn-uuid"
    assert rows[0]["kind"] == "function"


@pytest.mark.asyncio
async def test_bridge_state_file_written_after_run(
    graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    """State file is written after a successful run."""
    ex = CodebaseMemoryBridgeExtractor()
    state_file = tmp_path / "bridge-state.json"
    ex._state_path = state_file

    fake_call = _fake_cm(
        nodes=[
            {
                "uuid": "f-uuid",
                "name": "main.py",
                "labels": ["File"],
                "qualified_name": "integ-proj.main",
                "xxh3": "filehash-xyz",
                "path": "main.py",
            },
        ],
    )

    with patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call):
        await ex.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path))

    assert state_file.exists()
    state = _load_state("integ-proj", state_file)
    assert state.project_slug == "integ-proj"
    assert state.last_run_at is not None
    assert state.last_run_duration_ms is not None
    assert state.nodes_written_by_type  # at least one type written


@pytest.mark.asyncio
async def test_bridge_second_run_skips_unchanged_files(
    graphiti_mock: MagicMock, tmp_path: Path
) -> None:
    """Second run with identical hashes writes 0 nodes (incremental skip)."""
    ex = CodebaseMemoryBridgeExtractor()
    state_file = tmp_path / "bridge-state.json"
    ex._state_path = state_file

    stable_nodes = [
        {
            "uuid": "f-stable",
            "name": "stable.py",
            "labels": ["File"],
            "qualified_name": "integ-proj.stable",
            "xxh3": "stable-hash",
            "path": "stable.py",
        },
    ]
    fake_call = _fake_cm(nodes=stable_nodes)

    with patch("palace_mcp.extractors.codebase_memory_bridge._call_cm", fake_call):
        stats1 = await ex.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path))
        stats2 = await ex.run(graphiti=graphiti_mock, ctx=_ctx(tmp_path))

    assert stats1.nodes_written >= 1
    assert stats2.nodes_written == 0
    assert stats2.edges_written == 0
