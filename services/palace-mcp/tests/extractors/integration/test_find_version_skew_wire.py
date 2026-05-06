"""Wire-contract tests for palace.code.find_version_skew.

Per feedback_wire_test_tautological_assertions: assert on explicit
error_code values, not the isError flag.
"""

import pytest

from palace_mcp.extractors.cross_repo_version_skew.find_version_skew import find_version_skew


@pytest.mark.asyncio
async def test_top_n_out_of_range_zero(driver):
    r = await find_version_skew(driver, project="x", top_n=0)
    assert r["ok"] is False
    assert r["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_top_n_out_of_range_too_high(driver):
    r = await find_version_skew(driver, project="x", top_n=10_000)
    assert r["ok"] is False
    assert r["error_code"] == "top_n_out_of_range"


@pytest.mark.asyncio
async def test_slug_invalid(driver):
    r = await find_version_skew(driver, project="!!!bad-slug!!!", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "slug_invalid"


@pytest.mark.asyncio
async def test_bundle_invalid(driver):
    r = await find_version_skew(driver, bundle="!!!bad-bundle!!!", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "bundle_invalid"


@pytest.mark.asyncio
async def test_mutually_exclusive_args(driver):
    r = await find_version_skew(driver, project="x", bundle="y", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "mutually_exclusive_args"


@pytest.mark.asyncio
async def test_missing_target(driver):
    r = await find_version_skew(driver, top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "missing_target"


@pytest.mark.asyncio
async def test_invalid_severity_filter(driver):
    r = await find_version_skew(driver, project="x", min_severity="critical", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "invalid_severity_filter"


@pytest.mark.asyncio
async def test_invalid_ecosystem_filter(driver):
    r = await find_version_skew(driver, project="x", ecosystem="cocoapods", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "invalid_ecosystem_filter"


@pytest.mark.asyncio
async def test_project_not_registered(driver):
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    r = await find_version_skew(driver, project="ghost-project", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "project_not_registered"


@pytest.mark.asyncio
async def test_bundle_not_registered(driver):
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    r = await find_version_skew(driver, bundle="ghost-bundle", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "bundle_not_registered"


@pytest.mark.asyncio
async def test_dependency_surface_not_indexed(driver):
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("MERGE (p:Project {slug: 'no-deps'})")
    r = await find_version_skew(driver, project="no-deps", top_n=5)
    assert r["ok"] is False
    assert r["error_code"] == "dependency_surface_not_indexed"


@pytest.mark.asyncio
async def test_success_bundle_mode_with_skew(driver):
    """Concrete success-path assertions, not tautologies."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'a'})
            MERGE (b:Project {slug: 'b'})
            MERGE (bd:Bundle {name: 'mini'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(b)
            MERGE (d1:ExternalDependency {purl: 'pkg:pypi/lib@1.5.0'})
              SET d1.ecosystem = 'pypi', d1.resolved_version = '1.5.0'
            MERGE (d2:ExternalDependency {purl: 'pkg:pypi/lib@2.0.0'})
              SET d2.ecosystem = 'pypi', d2.resolved_version = '2.0.0'
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '^1.5'}]->(d1)
            MERGE (b)-[:DEPENDS_ON {scope: 'main', declared_in: 'pyproject.toml', declared_version_constraint: '^2.0'}]->(d2)
        """)
    r = await find_version_skew(driver, bundle="mini", top_n=5)
    assert r["ok"] is True
    assert r["mode"] == "bundle"
    assert r["target_slug"] == "mini"
    assert len(r["skew_groups"]) == 1
    g = r["skew_groups"][0]
    assert g["purl_root"] == "pkg:pypi/lib"
    assert g["severity"] == "major"
    assert g["version_count"] == 2
    assert sum(r["summary_by_severity"].values()) >= len(r["skew_groups"])
    assert isinstance(r["warnings"], list)
    assert "target_status" in r


@pytest.mark.asyncio
async def test_acceptance_21_min_severity_excludes_lower(driver):
    """min_severity='major' excludes minor/patch/unknown; min_severity='unknown' includes all."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'a'})
            MERGE (b:Project {slug: 'b'})
            MERGE (c:Project {slug: 'c'})
            MERGE (bd:Bundle {name: 'mix'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(b)
            MERGE (bd)-[:HAS_MEMBER]->(c)

            // Major
            MERGE (d1:ExternalDependency {purl: 'pkg:pypi/big@1.5.0'}) SET d1.ecosystem='pypi', d1.resolved_version='1.5.0'
            MERGE (d2:ExternalDependency {purl: 'pkg:pypi/big@2.0.0'}) SET d2.ecosystem='pypi', d2.resolved_version='2.0.0'
            MERGE (a)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d1)
            MERGE (b)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d2)

            // Patch
            MERGE (d3:ExternalDependency {purl: 'pkg:pypi/small@1.0.0'}) SET d3.ecosystem='pypi', d3.resolved_version='1.0.0'
            MERGE (d4:ExternalDependency {purl: 'pkg:pypi/small@1.0.1'}) SET d4.ecosystem='pypi', d4.resolved_version='1.0.1'
            MERGE (a)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d3)
            MERGE (c)-[:DEPENDS_ON {scope:'main', declared_in:'p', declared_version_constraint:'x'}]->(d4)
        """)

    r_major = await find_version_skew(driver, bundle="mix", min_severity="major", top_n=10)
    assert r_major["ok"] is True
    severities = {g["severity"] for g in r_major["skew_groups"]}
    assert severities == {"major"}

    r_unknown = await find_version_skew(driver, bundle="mix", min_severity="unknown", top_n=10)
    assert r_unknown["ok"] is True
    assert len(r_unknown["skew_groups"]) >= 2  # major + patch + possibly more


@pytest.mark.asyncio
async def test_acceptance_22_no_fstring_cypher_in_package():
    """Source-grep audit: no f-string Cypher in cross_repo_version_skew/."""
    import re
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[2] / "src" / "palace_mcp" / "extractors" / "cross_repo_version_skew"
    fstring_match_pattern = re.compile(r'f"\s*MATCH|f"""\s*MATCH|\.format\(.*MATCH', re.DOTALL)
    offenders: list[tuple[str, int]] = []
    for py in sorted(pkg.rglob("*.py")):
        text = py.read_text()
        for n, line in enumerate(text.splitlines(), 1):
            if fstring_match_pattern.search(line):
                offenders.append((str(py), n))
    assert offenders == [], f"f-string MATCH found: {offenders}"


@pytest.mark.asyncio
async def test_bundle_member_invalid_slug_emits_warning(driver):
    """W11: invalid bundle member slugs must emit member_invalid_slug warnings,
    not be silently dropped. Per spec §7 edge-case table + AC #24."""
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run("""
            MERGE (a:Project {slug: 'ok-member'})
            MERGE (bad:Project {slug: '!!!CORRUPT!!!'})
            MERGE (bd:Bundle {name: 'mixed'})
            MERGE (bd)-[:HAS_MEMBER]->(a)
            MERGE (bd)-[:HAS_MEMBER]->(bad)
            MERGE (d1:ExternalDependency {purl: 'pkg:pypi/lib@1.0.0'})
              SET d1.ecosystem = 'pypi', d1.resolved_version = '1.0.0'
            MERGE (a)-[:DEPENDS_ON {scope: 'main', declared_in: 'p.toml', declared_version_constraint: '^1.0'}]->(d1)
        """)
    r = await find_version_skew(driver, bundle="mixed", top_n=5)
    assert r["ok"] is True
    slugs_warned = [w["slug"] for w in r["warnings"] if w["code"] == "member_invalid_slug"]
    assert "!!!CORRUPT!!!" in slugs_warned
    assert r["target_status"]["!!!CORRUPT!!!"] == "invalid_slug"
