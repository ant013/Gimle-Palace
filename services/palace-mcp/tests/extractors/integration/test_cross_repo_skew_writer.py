"""Integration tests for _write_run_extras."""

from __future__ import annotations

import pytest

from palace_mcp.extractors.cross_repo_version_skew.models import RunSummary
from palace_mcp.extractors.cross_repo_version_skew.neo4j_writer import (
    _write_run_extras,
)


@pytest.mark.asyncio
async def test_write_run_extras_sets_properties(driver):  # type: ignore[no-untyped-def]
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            CREATE (r:IngestRun {id: 'r1'})
            SET r.extractor_name = 'cross_repo_version_skew',
                r.project = 'uw-ios-mini',
                r.success = true
        """)
    summary = RunSummary(
        mode="bundle",
        target_slug="uw-ios-mini",
        member_count=4,
        target_status_indexed_count=4,
        skew_groups_total=2,
        skew_groups_major=1,
        skew_groups_minor=1,
        skew_groups_patch=0,
        skew_groups_unknown=0,
        aligned_groups_total=1,
        warnings_purl_malformed_count=0,
    )
    await _write_run_extras(driver, run_id="r1", summary=summary)

    async with driver.session() as session:
        result = await session.run("""
            MATCH (r:IngestRun {id: 'r1'})
            RETURN r.mode AS mode, r.target_slug AS target,
                   r.skew_groups_total AS total,
                   r.skew_groups_major AS major,
                   r.aligned_groups_total AS aligned
        """)
        row = await result.single()
    assert row["mode"] == "bundle"
    assert row["target"] == "uw-ios-mini"
    assert row["total"] == 2
    assert row["major"] == 1
    assert row["aligned"] == 1
