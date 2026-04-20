"""Integration tests for runner error paths with real Neo4j."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractionContext,
    ExtractorConfigError,
    ExtractorStats,
)
from palace_mcp.extractors.heartbeat import HeartbeatExtractor
from palace_mcp.extractors.runner import run_extractor
from palace_mcp.extractors.schema import ensure_extractors_schema


class _FailingExtractor(BaseExtractor):
    name = "__integration_failing"
    description = "raises ExtractorConfigError"
    constraints: list[str] = []
    indexes: list[str] = []

    async def extract(self, ctx: ExtractionContext) -> ExtractorStats:
        raise ExtractorConfigError("test-triggered config error")


@pytest.fixture(autouse=True)
def _registry_setup() -> None:
    snap = dict(registry.EXTRACTORS)
    if "heartbeat" not in registry.EXTRACTORS:
        registry.register(HeartbeatExtractor())
    registry.register(_FailingExtractor())
    yield
    registry.EXTRACTORS.clear()
    registry.EXTRACTORS.update(snap)


@pytest.mark.asyncio
async def test_unknown_extractor_no_ingest_run_created(
    driver: AsyncDriver,
) -> None:
    await ensure_extractors_schema(driver)
    async with driver.session() as s:
        r1 = await s.run("MATCH (n:IngestRun) RETURN count(n) AS c")
        before = (await r1.single())["c"]

    res = await run_extractor(name="does_not_exist", project="gimle", driver=driver)
    assert res["ok"] is False
    assert res["error_code"] == "unknown_extractor"

    async with driver.session() as s:
        r2 = await s.run("MATCH (n:IngestRun) RETURN count(n) AS c")
        after = (await r2.single())["c"]
    assert before == after


@pytest.mark.asyncio
async def test_failing_extractor_finalizes_as_errored(
    driver: AsyncDriver, tmp_path: Path
) -> None:
    await ensure_extractors_schema(driver)

    async with driver.session() as s:
        await s.run(
            "MERGE (p:Project {slug: $slug}) SET p.group_id='project/'+$slug, p.name=$slug, p.tags=[]",
            slug="errtest",
        )
    repo = tmp_path / "repos" / "errtest"
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()

    with patch("palace_mcp.extractors.runner.REPOS_ROOT", tmp_path / "repos"):
        res = await run_extractor(
            name="__integration_failing", project="errtest", driver=driver
        )

    assert res["ok"] is False
    assert res["error_code"] == "extractor_config_error"
    assert res["run_id"] is not None

    async with driver.session() as s:
        r = await s.run("MATCH (r:IngestRun {id: $id}) RETURN r", id=res["run_id"])
        row = await r.single()
    assert row is not None
    ir = dict(row["r"])
    assert ir["success"] is False
    assert len(ir["errors"]) >= 1
    assert "test-triggered" in ir["errors"][0]
