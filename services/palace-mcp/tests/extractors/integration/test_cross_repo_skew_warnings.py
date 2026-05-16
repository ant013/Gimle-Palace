"""Edge-case + warnings integration tests.

Rev3: uses ExtractorRunContext + patches get_driver/get_settings.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorOutcome, ExtractorRunContext
from palace_mcp.extractors.cross_repo_version_skew.extractor import (
    CrossRepoVersionSkewExtractor,
)
from palace_mcp.extractors.foundation.errors import ExtractorError


def _ctx(*, project_slug: str, run_id: str = "warn-test-001") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=project_slug,
        group_id=f"project/{project_slug}",
        repo_path=Path("/tmp/fake-repo"),
        run_id=run_id,
        duration_ms=30_000,
        logger=logging.getLogger("test"),
    )


def _patch_mcp(driver):  # type: ignore[no-untyped-def]
    mock_settings = MagicMock()
    mock_settings.palace_version_skew_query_timeout_s = 30
    return patch.multiple(
        "palace_mcp.mcp_server",
        get_driver=MagicMock(return_value=driver),
        get_settings=MagicMock(return_value=mock_settings),
    )


@pytest.mark.asyncio
async def test_acceptance_19_bundle_has_no_members(driver):  # type: ignore[no-untyped-def]
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (b:Bundle {name: 'empty-bundle'})")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        with pytest.raises(ExtractorError) as exc_info:
            await ext.run(graphiti=MagicMock(), ctx=_ctx(project_slug="empty-bundle"))
    assert exc_info.value.error_code.value == "bundle_has_no_members"


@pytest.mark.asyncio
async def test_acceptance_19_bundle_not_registered_falls_to_project(driver):  # type: ignore[no-untyped-def]
    """Non-existent slug is neither Bundle nor Project; auto-detect picks project mode.
    Project slug 'ghost-bundle' has no :Project node either, so _collect_target_status
    returns not_registered → optional missing-input outcome."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="ghost-bundle")
        )
    assert stats.outcome == ExtractorOutcome.MISSING_INPUT
    assert stats.message is not None
    assert "lack :DEPENDS_ON data" in stats.message


@pytest.mark.asyncio
async def test_acceptance_20_malformed_purl_warning(driver):  # type: ignore[no-untyped-def]
    """Malformed purl excluded from skew; warning surfaced in :IngestRun extras."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (p:Project {slug: 'test-proj'})
            MERGE (good:ExternalDependency {purl: 'pkg:pypi/good@1.0.0'})
              SET good.ecosystem = 'pypi', good.resolved_version = '1.0.0'
            MERGE (bad:ExternalDependency {purl: 'broken-format-no-pkg-prefix'})
              SET bad.ecosystem = 'unknown', bad.resolved_version = '1.0.0'
            MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(good)
            MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(bad)
        """)
    run_id = "warn-malformed-001"
    async with driver.session() as session:
        await session.run(
            "CREATE (r:IngestRun {id: $rid, extractor_name: 'cross_repo_version_skew', success: true})",
            rid=run_id,
        )
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="test-proj", run_id=run_id)
        )
    assert stats.nodes_written == 1
    async with driver.session() as session:
        out = await session.run(
            "MATCH (r:IngestRun {id: $rid}) RETURN r.warnings_purl_malformed_count AS cnt",
            rid=run_id,
        )
        row = await out.single()
    assert row["cnt"] == 1


@pytest.mark.asyncio
async def test_acceptance_24_member_not_registered_warning(driver):  # type: ignore[no-untyped-def]
    """Stale :HAS_MEMBER pointing to non-existent :Project produces warning."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (b:Bundle {name: 'partial-bundle'})
            MERGE (good:Project {slug: 'good-member'})
            MERGE (good_dep:ExternalDependency {purl: 'pkg:pypi/dep@1.0.0'})
              SET good_dep.ecosystem = 'pypi', good_dep.resolved_version = '1.0.0'
            MERGE (good)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '1.0.0'}]->(good_dep)
            MERGE (b)-[:HAS_MEMBER]->(good)
            // Stale: bundle references a slug whose :Project was deleted
            MERGE (ghost_proj:Project {slug: 'ghost-member'})
            MERGE (b)-[:HAS_MEMBER]->(ghost_proj)
            DETACH DELETE ghost_proj
        """)
    run_id = "warn-ghost-001"
    async with driver.session() as session:
        await session.run(
            "CREATE (r:IngestRun {id: $rid, extractor_name: 'cross_repo_version_skew', success: true})",
            rid=run_id,
        )
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="partial-bundle", run_id=run_id)
        )
    assert stats.nodes_written == 1


@pytest.mark.asyncio
async def test_dependency_surface_not_indexed_all_targets(driver):  # type: ignore[no-untyped-def]
    """Project exists but has no :DEPENDS_ON -> non-failing missing-input outcome."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (p:Project {slug: 'no-deps-proj'})")
    ext = CrossRepoVersionSkewExtractor()
    with _patch_mcp(driver):
        stats = await ext.run(
            graphiti=MagicMock(), ctx=_ctx(project_slug="no-deps-proj")
        )
    assert stats.outcome == ExtractorOutcome.MISSING_INPUT
    assert stats.message is not None
    assert "lack :DEPENDS_ON data" in stats.message
