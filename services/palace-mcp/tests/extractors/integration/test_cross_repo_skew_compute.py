"""Integration tests for _compute_skew_groups() on a seeded fixture.

The dependency fixture is created via direct Cypher MERGE (not by running
dependency_surface), while bundle membership uses the production CRUD helpers.
"""

from __future__ import annotations

import pytest

from palace_mcp.extractors.cross_repo_version_skew.compute import (
    _compute_skew_groups,
)
from palace_mcp.memory.bundle import add_to_bundle, register_bundle
from palace_mcp.memory.models import Tier


async def _seed_skew_fixture(driver) -> None:  # type: ignore[no-untyped-def]
    """4 projects, 1 bundle, 7 :ExternalDependency, planned skew."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            // Projects
            MERGE (a:Project {slug: 'hs-extensions'})
              SET a.name = 'HsExtensions.Swift'
            MERGE (m:Project {slug: 'hs-toolkit'})
              SET m.name = 'HsToolKit.Swift'
            MERGE (e:Project {slug: 'hs-crypto-kit'})
              SET e.name = 'HsCryptoKit.Swift'
            MERGE (b:Project {slug: 'bitcoin-core'})
              SET b.name = 'BitcoinCore.Swift'
        """)

    await register_bundle(driver, name="uw-ios-mini", description="UW iOS mini fixture")
    for slug in (
        "hs-extensions",
        "hs-toolkit",
        "hs-crypto-kit",
        "bitcoin-core",
    ):
        await add_to_bundle(driver, bundle="uw-ios-mini", project=slug, tier=Tier.USER)

    async with driver.session() as session:
        await session.run("""
            MATCH (a:Project {slug: 'hs-extensions'})
            MATCH (m:Project {slug: 'hs-toolkit'})
            MATCH (e:Project {slug: 'hs-crypto-kit'})
            MATCH (b:Project {slug: 'bitcoin-core'})

            // ExternalDependency: HsToolKit.Swift MAJOR skew
            MERGE (mk_15:ExternalDependency {purl: 'pkg:github/horizontalsystems/HsToolKit.Swift@1.5.0'})
              SET mk_15.ecosystem = 'github', mk_15.resolved_version = '1.5.0'
            MERGE (mk_20:ExternalDependency {purl: 'pkg:github/horizontalsystems/HsToolKit.Swift@2.0.1'})
              SET mk_20.ecosystem = 'github', mk_20.resolved_version = '2.0.1'

            // ExternalDependency: HsCryptoKit PATCH+MINOR skew (3 pinnings)
            MERGE (bi_5:ExternalDependency {purl: 'pkg:github/horizontalsystems/HsCryptoKit.Swift@1.0.5'})
              SET bi_5.ecosystem = 'github', bi_5.resolved_version = '1.0.5'
            MERGE (bi_7:ExternalDependency {purl: 'pkg:github/horizontalsystems/HsCryptoKit.Swift@1.0.7'})
              SET bi_7.ecosystem = 'github', bi_7.resolved_version = '1.0.7'
            MERGE (bi_10:ExternalDependency {purl: 'pkg:github/horizontalsystems/HsCryptoKit.Swift@1.1.0'})
              SET bi_10.ecosystem = 'github', bi_10.resolved_version = '1.1.0'

            // ExternalDependency: aligned (single-source — only HsCryptoKit pins it)
            MERGE (sng:ExternalDependency {purl: 'pkg:pypi/notused@5.0.0'})
              SET sng.ecosystem = 'pypi', sng.resolved_version = '5.0.0'

            // ExternalDependency: aligned cross-member (HsToolKit and BitcoinCore both pin same)
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
        member_slugs=[
            "hs-extensions",
            "hs-toolkit",
            "hs-crypto-kit",
            "bitcoin-core",
        ],
        ecosystem=None,
    )
    # HsToolKit.Swift (2 versions: major), HsCryptoKit.Swift (3 versions: patch+minor → minor)
    purl_roots = {g.purl_root for g in result.skew_groups}
    assert "pkg:github/horizontalsystems/HsToolKit.Swift" in purl_roots
    assert "pkg:github/horizontalsystems/HsCryptoKit.Swift" in purl_roots

    # HsToolKit.Swift severity = major (1.5.0 vs 2.0.1)
    mk = next(
        g
        for g in result.skew_groups
        if g.purl_root == "pkg:github/horizontalsystems/HsToolKit.Swift"
    )
    assert mk.severity == "major"
    assert mk.version_count == 2

    # HsCryptoKit.Swift severity = minor (1.0.5/1.0.7 → patch; vs 1.1.0 → minor; max = minor)
    big = next(
        g
        for g in result.skew_groups
        if g.purl_root == "pkg:github/horizontalsystems/HsCryptoKit.Swift"
    )
    assert big.severity == "minor"
    assert big.version_count == 3


@pytest.mark.asyncio
async def test_compute_excludes_single_source_and_aligned(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=[
            "hs-extensions",
            "hs-toolkit",
            "hs-crypto-kit",
            "bitcoin-core",
        ],
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
        member_slugs=[
            "hs-extensions",
            "hs-toolkit",
            "hs-crypto-kit",
            "bitcoin-core",
        ],
        ecosystem=None,
    )
    # 'pkg:pypi/aligned' has 2 entries with same version → 1 aligned group
    # 'pkg:pypi/notused' has 1 entry → not aligned, not skew (single-source filter)
    assert result.aligned_groups_total == 1


@pytest.mark.asyncio
async def test_compute_includes_declared_constraint_only_skew(driver):  # type: ignore[no-untyped-def]
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'kit-a'})
              SET a.name = 'HsExtensions.Swift'
            MERGE (b:Project {slug: 'kit-b'})
              SET b.name = 'BitcoinCore.Swift'
            MERGE (dep:ExternalDependency {purl: 'pkg:github/apple/swift-collections@1.1.0'})
              SET dep.ecosystem = 'github', dep.resolved_version = '1.1.0'
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^1.0.0'}]->(dep)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'Package.swift', declared_version_constraint: '^2.0.0'}]->(dep)
        """)

    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=["kit-a", "kit-b"],
        ecosystem=None,
    )

    assert len(result.skew_groups) == 1
    group = result.skew_groups[0]
    assert group.purl_root == "pkg:github/apple/swift-collections"
    assert group.severity == "major"
    assert group.version_count == 2
    assert {entry.version for entry in group.entries} == {"1.1.0"}
    assert {entry.declared_constraint for entry in group.entries} == {
        "^1.0.0",
        "^2.0.0",
    }


@pytest.mark.asyncio
async def test_compute_ecosystem_filter(driver):  # type: ignore[no-untyped-def]
    await _seed_skew_fixture(driver)
    result = await _compute_skew_groups(
        driver,
        mode="bundle",
        member_slugs=[
            "hs-extensions",
            "hs-toolkit",
            "hs-crypto-kit",
            "bitcoin-core",
        ],
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
        member_slugs=["hs-toolkit"],
        ecosystem=None,
    )
    # HsToolKit.Swift alone has HsToolKit.Swift@2.0.1 (1 entry) and
    # HsCryptoKit.Swift@1.0.5 (1 entry)
    # No intra-project skew (each purl_root has 1 version) → 0 skew groups
    assert result.skew_groups == []
