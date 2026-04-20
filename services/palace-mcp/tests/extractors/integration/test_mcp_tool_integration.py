"""Integration test — end-to-end via run_extractor runner (tool handler bypass).

Calls the runner directly to verify wire-up between HeartbeatExtractor,
:IngestRun lifecycle, and :ExtractorHeartbeat persistence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema


@pytest.fixture(autouse=True)
def _heartbeat_ready() -> None:
    if "heartbeat" not in registry.EXTRACTORS:
        registry.register(HeartbeatExtractor())
    yield


@pytest.fixture
async def _project_and_repo(driver: AsyncDriver, tmp_path: Path) -> Path:
    """Set up :Project node and /repos/<slug>/.git on disk."""
    async with driver.session() as s:
        await s.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = 'project/' + $slug,
                p.name = $name,
                p.tags = []
            """,
            slug="testproj",
            name="TestProj",
        )
    repo = tmp_path / "repos" / "testproj"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return tmp_path / "repos"


@pytest.mark.asyncio
async def test_run_extractor_end_to_end(
    driver: AsyncDriver, _project_and_repo: Path
) -> None:
    await ensure_extractors_schema(driver)

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo):
        res = await run_extractor(name="heartbeat", project="testproj", driver=driver)

    assert res["ok"] is True
    assert res["extractor"] == "heartbeat"
    assert res["project"] == "testproj"
    assert res["nodes_written"] == 1

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:ExtractorHeartbeat {run_id: $run_id}) RETURN h",
            run_id=res["run_id"],
        )
        row = await result.single()
    assert row is not None

    async with driver.session() as s:
        result = await s.run(
            "MATCH (r:IngestRun {id: $id}) RETURN r",
            id=res["run_id"],
        )
        row = await result.single()
    assert row is not None
    r = dict(row["r"])
    assert r["source"] == "extractor.heartbeat"
    assert r["success"] is True
    assert r["nodes_written"] == 1


@pytest.mark.asyncio
async def test_rerun_creates_separate_records(
    driver: AsyncDriver, _project_and_repo: Path
) -> None:
    await ensure_extractors_schema(driver)

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", _project_and_repo):
        res1 = await run_extractor(name="heartbeat", project="testproj", driver=driver)
        res2 = await run_extractor(name="heartbeat", project="testproj", driver=driver)

    assert res1["run_id"] != res2["run_id"]

    async with driver.session() as s:
        result = await s.run("MATCH (h:ExtractorHeartbeat) RETURN count(h) AS c")
        row = await result.single()
    assert row is not None
    assert row["c"] == 2
