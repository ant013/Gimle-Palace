"""Integration tests for dead_code neo4j_writer eviction pass."""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.dead_code.models import (
    DeadFinding,
    FindingKind,
    MemberEntry,
    Severity,
)
from palace_mcp.extractors.dead_code.neo4j_writer import write_dead_findings

GROUP_ID = "project/eviction-test"
PROJECT = "eviction-test"


def _finding(finding_id: str, name: str) -> DeadFinding:
    return DeadFinding(
        finding_id=finding_id,
        kind=FindingKind.DEAD_SYMBOL,
        severity=Severity.LOW,
        project=PROJECT,
        members=[MemberEntry(qualified_name=name, kind="function")],
        size=1,
    )


async def _count_findings(driver: AsyncDriver) -> int:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:DeadFinding {group_id: $gid}) RETURN count(f) AS n",
            gid=GROUP_ID,
        )
        row = await result.single()
        return row["n"]


@pytest.mark.asyncio
async def test_dead_code_rerun_evicts_stale_findings(driver: AsyncDriver) -> None:
    finding_a = _finding("fd-aaa", "ModuleA.unusedFoo")
    finding_b = _finding("fd-bbb", "ModuleB.unusedBar")
    finding_c = _finding("fd-ccc", "ModuleC.unusedBaz")

    # Run 1: write A, B, C → count must be 3
    s1 = await write_dead_findings(
        driver=driver,
        findings=[finding_a, finding_b, finding_c],
        group_id=GROUP_ID,
    )
    assert await _count_findings(driver) == 3
    assert s1.nodes_deleted == 0

    # Run 2: only A, B present → C evicted, count = 2
    s2 = await write_dead_findings(
        driver=driver,
        findings=[finding_a, finding_b],
        group_id=GROUP_ID,
    )
    assert await _count_findings(driver) == 2
    assert s2.nodes_deleted == 1

    # Run 3: same as run 2 → idempotent, count still 2
    s3 = await write_dead_findings(
        driver=driver,
        findings=[finding_a, finding_b],
        group_id=GROUP_ID,
    )
    assert await _count_findings(driver) == 2
    assert s3.nodes_deleted == 0
