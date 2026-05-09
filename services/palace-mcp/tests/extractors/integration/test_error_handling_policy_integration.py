"""Integration tests for error_handling_policy extractor (GIM-257)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.audit.contracts import RunInfo
from palace_mcp.audit.fetcher import fetch_audit_data
from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.error_handling_policy.extractor import (
    ErrorHandlingPolicyExtractor,
)
from palace_mcp.extractors.schema import ensure_extractors_schema

_FIXTURE_SOURCES = (
    Path(__file__).parents[2]
    / "extractors"
    / "fixtures"
    / "error-handling-mini-project"
    / "Sources"
)

PROJECT_SLUG = "ehp-integ"
GROUP_ID = f"project/{PROJECT_SLUG}"
EXPECTED_CATCH_SITE_COUNT = 11
EXPECTED_FINDING_COUNT = 19


def _make_ctx(repo_path: Path, run_id: str = "integ-run-1") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_path,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test.error_handling_policy"),
    )


def _fake_settings() -> MagicMock:
    settings = MagicMock()
    settings.palace_error_handling_semgrep_timeout_s = 120
    return settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_integration_synthetic(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    target = tmp_path / "Sources"
    shutil.copytree(_FIXTURE_SOURCES, target)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        stats = await ErrorHandlingPolicyExtractor().run(
            graphiti=graphiti_mock,
            ctx=_make_ctx(tmp_path),
        )

    assert stats.nodes_written == EXPECTED_CATCH_SITE_COUNT + EXPECTED_FINDING_COUNT

    async with driver.session() as session:
        catch_result = await session.run(
            "MATCH (c:CatchSite {project_id: $pid}) RETURN count(c) AS n",
            pid=GROUP_ID,
        )
        catch_row = await catch_result.single()
        finding_result = await session.run(
            "MATCH (f:ErrorFinding {project_id: $pid}) RETURN count(f) AS n",
            pid=GROUP_ID,
        )
        finding_row = await finding_result.single()

    assert catch_row is not None
    assert finding_row is not None
    assert catch_row["n"] == EXPECTED_CATCH_SITE_COUNT
    assert finding_row["n"] == EXPECTED_FINDING_COUNT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_integration_idempotent(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    target = tmp_path / "Sources"
    shutil.copytree(_FIXTURE_SOURCES, target)
    extractor = ErrorHandlingPolicyExtractor()

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        stats1 = await extractor.run(graphiti=graphiti_mock, ctx=_make_ctx(tmp_path))
        stats2 = await extractor.run(
            graphiti=graphiti_mock,
            ctx=_make_ctx(tmp_path, run_id="integ-run-2"),
        )

    assert stats1.nodes_written == EXPECTED_CATCH_SITE_COUNT + EXPECTED_FINDING_COUNT
    assert stats2.nodes_written == EXPECTED_CATCH_SITE_COUNT + EXPECTED_FINDING_COUNT

    async with driver.session() as session:
        catch_result = await session.run(
            "MATCH (c:CatchSite {project_id: $pid}) RETURN count(c) AS n",
            pid=GROUP_ID,
        )
        catch_row = await catch_result.single()
        finding_result = await session.run(
            "MATCH (f:ErrorFinding {project_id: $pid}) RETURN count(f) AS n",
            pid=GROUP_ID,
        )
        finding_row = await finding_result.single()

    assert catch_row is not None
    assert finding_row is not None
    assert catch_row["n"] == EXPECTED_CATCH_SITE_COUNT
    assert finding_row["n"] == EXPECTED_FINDING_COUNT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clean_rerun_replaces_snapshot_and_fetcher_reads_current_contract(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    target = tmp_path / "Sources"
    shutil.copytree(_FIXTURE_SOURCES, target)
    extractor = ErrorHandlingPolicyExtractor()

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        await extractor.run(graphiti=graphiti_mock, ctx=_make_ctx(tmp_path))
        shutil.rmtree(target / "Bad")
        await extractor.run(
            graphiti=graphiti_mock,
            ctx=_make_ctx(tmp_path, run_id="integ-run-clean"),
        )

    async with driver.session() as session:
        catch_result = await session.run(
            "MATCH (c:CatchSite {project_id: $pid}) RETURN count(c) AS n",
            pid=GROUP_ID,
        )
        catch_row = await catch_result.single()
        finding_result = await session.run(
            "MATCH (f:ErrorFinding {project_id: $pid}) RETURN count(f) AS n",
            pid=GROUP_ID,
        )
        finding_row = await finding_result.single()

    assert catch_row is not None
    assert finding_row is not None
    assert catch_row["n"] == 1
    assert finding_row["n"] == 0

    sections = await fetch_audit_data(
        driver,
        {
            "error_handling_policy": RunInfo(
                run_id="integ-run-clean",
                extractor_name="error_handling_policy",
                project=PROJECT_SLUG,
                completed_at="2026-05-09T00:00:00Z",
            )
        },
        {"error_handling_policy": extractor},
    )

    section = sections["error_handling_policy"]
    assert len(section.findings) == 1
    assert section.findings[0]["kind"] == ""
    assert section.findings[0]["catch_site_count"] == 1
    assert section.findings[0]["files_scanned"] == 1
    assert section.findings[0]["swallowed_count"] == 0
    assert section.findings[0]["rethrows_count"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_creation_idempotent(driver: AsyncDriver) -> None:
    await ensure_extractors_schema(driver)
    await ensure_extractors_schema(driver)

    async with driver.session() as session:
        constraint_result = await session.run("SHOW CONSTRAINTS YIELD name")
        constraint_names = [row["name"] async for row in constraint_result]
        index_result = await session.run("SHOW INDEXES YIELD name")
        index_names = [row["name"] async for row in index_result]

    assert "error_finding_unique" in constraint_names
    assert "catch_site_unique" in constraint_names
    assert "error_finding_project" in index_names
    assert "error_finding_severity" in index_names
    assert "catch_site_project" in index_names
    assert "catch_site_module" in index_names
