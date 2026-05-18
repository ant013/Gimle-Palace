"""Integration tests for _compute_skew_groups() on a seeded fixture.

The fixture is created via direct Cypher MERGE (not by running
dependency_surface), so this test is hermetic to GIM-191.
"""

from __future__ import annotations

import pytest

from palace_mcp.extractors.cross_repo_version_skew.compute import (
    _compute_skew_groups,
)


async def _seed_skew_fixture(driver) -> None:  # type: ignore[no-untyped-def]
    """4 projects, 1 bundle, 7 :ExternalDependency, planned skew."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            // Projects
            MERGE (a:Project {slug: 'uw-ios-app'})
            MERGE (m:Project {slug: 'MarketKit'})
            MERGE (e:Project {slug: 'EvmKit'})
            MERGE (b:Project {slug: 'BitcoinKit'})

            // Bundle
            MERGE (bd:Bundle {name: 'uw-ios-mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(m)
            MERGE (bd)-[:HAS_MEMBER]->(e)
            MERGE (bd)-[:HAS_MEMBER]->(b)

            // ExternalDependency: marketkit MAJOR skew
            MERGE (mk_15:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@1.5.0'})
              SET mk_15.ecosystem = 'github', mk_15.resolved_version = '1.5.0'
            MERGE (mk_20:ExternalDependency {purl: 'pkg:github/horizontalsystems/marketkit@2.0.1'})
              SET mk_20.ecosystem = 'github', mk_20.resolved_version = '2.0.1'

            // ExternalDependency: BigInt PATCH+MINOR skew (3 pinnings)
            MERGE (bi_5:ExternalDependency {purl: 'pkg:github/numerics/big@1.0.5'})
              SET bi_5.ecosystem = 'github', bi_5.resolved_version = '1.0.5'
            MERGE (bi_7:ExternalDependency {purl: 'pkg:github/numerics/big@1.0.7'})
              SET bi_7.ecosystem = 'github', bi_7.resolved_version = '1.0.7'
            MERGE (bi_10:ExternalDependency {purl: 'pkg:github/numerics/big@1.1.0'})
              SET bi_10.ecosystem = 'github', bi_10.resolved_version = '1.1.0'

            // ExternalDependency: aligned (single-source — only EvmKit pins it)
            MERGE (sng:ExternalDependency {purl: 'pkg:pypi/notused@5.0.0'})
              SET sng.ecosystem = 'pypi', sng.resolved_version = '5.0.0'

            // ExternalDependency: aligned cross-member (MarketKit and BitcoinKit both pin same)
            MERGE (al:ExternalDependency {purl: 'pkg:pypi/aligned@3.1.0'})
              SET al.ecosystem = 'pypi', al.resolved_version = '3.1.0'

            // DEPENDS_ON edges
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.5.0'}]->(mk_15)
            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^2.0.0'}]->(mk_20)

            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.0.5'}]->(bi_5)
            MERGE (e)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.0.7'}]->(bi_7)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.1.0'}]->(bi_10)

            MERGE (e)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '5.0.0'}]->(sng)

            MERGE (m)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '3.1.0'}]->(al)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '3.1.0'}]->(al)
        """)


@pytest.mark.asyncio
async def test_compute_bundle_mode_finds_two_skew_groups(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    # marketkit (2 versions: major), big (3 versions: patch+minor → minor)
    purl_roots = {g.purl_root for g in result.skew_groups}
    assert "pkg:github/horizontalsystems/marketkit" in purl_roots
    assert "pkg:github/numerics/big" in purl_roots

    # marketkit severity = major (1.5.0 vs 2.0.1)
    mk = next(
        g
        for g in result.skew_groups
        if g.purl_root == "pkg:github/horizontalsystems/marketkit"
    )
    assert mk.severity == "major"
    assert mk.version_count == 2

    # big severity = minor (1.0.5/1.0.7 → patch; vs 1.1.0 → minor; max = minor)
    big = next(
        g for g in result.skew_groups if g.purl_root == "pkg:github/numerics/big"
    )
    assert big.severity == "minor"
    assert big.version_count == 3


@pytest.mark.asyncio
async def test_compute_excludes_single_source_and_aligned(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    purl_roots = {g.purl_root for g in result.skew_groups}
    # 'pkg:pypi/notused' is single-source → excluded
    assert "pkg:pypi/notused" not in purl_roots
    # 'pkg:pypi/aligned' has 2 entries but identical version → excluded from skew
    assert "pkg:pypi/aligned" not in purl_roots


@pytest.mark.asyncio
async def test_compute_aligned_count_present(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem=None,
    )
    # 'pkg:pypi/aligned' has 2 entries with same version → 1 aligned group
    # 'pkg:pypi/notused' has 1 entry → not aligned, not skew (single-source filter)
    assert result.aligned_groups_total == 1


@pytest.mark.asyncio
async def test_compute_ecosystem_filter(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=["uw-ios-app", "MarketKit", "EvmKit", "BitcoinKit"],
        ecosystem="github",
    )
    # only github-prefix purls
    for g in result.skew_groups:
        assert g.ecosystem == "github"


@pytest.mark.asyncio
async def test_compute_project_mode_single_member(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="project",
        member_slugs=["MarketKit"],
        ecosystem=None,
    )
    # MarketKit alone has marketkit@2.0.1 (1 entry) and big@1.0.5 (1 entry)
    # No intra-project skew (each purl_root has 1 version) → 0 skew groups
    assert result.skew_groups == []
