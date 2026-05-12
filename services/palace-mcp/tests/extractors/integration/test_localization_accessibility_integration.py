"""Integration test — localization_accessibility extractor (GIM-275).

Uses real Neo4j via testcontainers (or COMPOSE_NEO4J_URI reuse).

Fixture: tests/extractors/fixtures/loc-a11y-mini-project/
  - 2 Localizable.strings (en=5 keys, ru=4 keys → 80 % coverage)
  - HardcodedView.swift: Text("Hello World") + label.text = "Tap here"
  - MissingLabelView.swift: Image("logo") + Image(systemName: "star.fill")
  - HardcodedScreen.kt: Text("Buy Now") + Text("Send")
  - MissingSemantics.kt: Modifier.clickable without semantics

Expected minimums per spec §7.1:
  ≥2 :LocaleResource  ≥3 :HardcodedString  ≥2 :A11yMissing
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.localization_accessibility.extractor import (
    LocalizationAccessibilityExtractor,
)

PROJECT_SLUG = "loc-a11y-mini"
GROUP_ID = f"project/{PROJECT_SLUG}"
FIXTURE_PATH = (
    Path(__file__).parents[2] / "extractors/fixtures/loc-a11y-mini-project"
)

MIN_LOCALE_RESOURCES = 2
MIN_HARDCODED_STRINGS = 3
MIN_A11Y_MISSING = 2


def _make_ctx(run_id: str = "integration-test-run") -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=FIXTURE_PATH,
        run_id=run_id,
        duration_ms=0,
        logger=logging.getLogger("test.loc_a11y"),
    )


@pytest.fixture
async def registered_project(driver: AsyncDriver) -> None:  # type: ignore[return]
    """Ensure :Project node exists; tear down loc-a11y nodes after test."""
    from palace_mcp.extractors.foundation.schema import ensure_custom_schema

    await ensure_custom_schema(driver)
    async with driver.session() as s:
        await s.run(
            "MERGE (p:Project {slug: $slug, group_id: $gid})",
            slug=PROJECT_SLUG,
            gid=GROUP_ID,
        )
    yield
    async with driver.session() as s:
        await s.run(
            "MATCH (n) WHERE (n:LocaleResource OR n:HardcodedString OR n:A11yMissing) "
            "AND n.project_id = $gid DETACH DELETE n",
            gid=GROUP_ID,
        )
        await s.run(
            "MATCH (p:Project {slug: $slug}) DETACH DELETE p",
            slug=PROJECT_SLUG,
        )


@pytest.mark.integration
async def test_full_flow_locale_resources(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    registered_project: None,
) -> None:
    """Extractor writes ≥2 :LocaleResource nodes with correct provenance."""
    extractor = LocalizationAccessibilityExtractor()
    ctx = _make_ctx()

    stats = await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    assert stats.nodes_written >= MIN_LOCALE_RESOURCES, (
        f"Expected ≥{MIN_LOCALE_RESOURCES} nodes_written, got {stats.nodes_written}"
    )

    async with driver.session() as s:
        result = await s.run(
            "MATCH (lr:LocaleResource {project_id: $gid}) RETURN count(lr) AS cnt",
            gid=GROUP_ID,
        )
        rec = await result.single()

    assert rec is not None
    assert rec["cnt"] >= MIN_LOCALE_RESOURCES, (
        f"Expected ≥{MIN_LOCALE_RESOURCES} :LocaleResource nodes in Neo4j"
    )


@pytest.mark.integration
async def test_full_flow_hardcoded_strings(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    registered_project: None,
) -> None:
    """Extractor writes ≥3 :HardcodedString nodes from semgrep findings."""
    extractor = LocalizationAccessibilityExtractor()
    ctx = _make_ctx()

    await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    async with driver.session() as s:
        result = await s.run(
            "MATCH (h:HardcodedString {project_id: $gid}) RETURN count(h) AS cnt",
            gid=GROUP_ID,
        )
        rec = await result.single()

    assert rec is not None
    assert rec["cnt"] >= MIN_HARDCODED_STRINGS, (
        f"Expected ≥{MIN_HARDCODED_STRINGS} :HardcodedString nodes, got {rec['cnt']}"
    )


@pytest.mark.integration
async def test_full_flow_a11y_missing(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    registered_project: None,
) -> None:
    """Extractor writes ≥2 :A11yMissing nodes from semgrep findings."""
    extractor = LocalizationAccessibilityExtractor()
    ctx = _make_ctx()

    await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    async with driver.session() as s:
        result = await s.run(
            "MATCH (a:A11yMissing {project_id: $gid}) RETURN count(a) AS cnt",
            gid=GROUP_ID,
        )
        rec = await result.single()

    assert rec is not None
    assert rec["cnt"] >= MIN_A11Y_MISSING, (
        f"Expected ≥{MIN_A11Y_MISSING} :A11yMissing nodes, got {rec['cnt']}"
    )


@pytest.mark.integration
async def test_provenance_fields(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    registered_project: None,
) -> None:
    """All written nodes carry correct project_id and run_id."""
    run_id = "provenance-check-run"
    extractor = LocalizationAccessibilityExtractor()
    ctx = _make_ctx(run_id=run_id)

    await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    async with driver.session() as s:
        # LocaleResource provenance
        r = await s.run(
            "MATCH (lr:LocaleResource {project_id: $gid}) "
            "RETURN lr.run_id AS rid, lr.locale AS loc LIMIT 1",
            gid=GROUP_ID,
        )
        rec = await r.single()
    assert rec is not None
    assert rec["rid"] == run_id
    assert rec["loc"] in ("en", "ru")


@pytest.mark.integration
async def test_locale_coverage_pct(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    registered_project: None,
) -> None:
    """English locale has 100 % coverage; Russian has 80 % (4/5 keys)."""
    extractor = LocalizationAccessibilityExtractor()
    ctx = _make_ctx()

    await extractor.run(graphiti=graphiti_mock, ctx=ctx)

    async with driver.session() as s:
        r = await s.run(
            "MATCH (lr:LocaleResource {project_id: $gid}) "
            "RETURN lr.locale AS loc, lr.coverage_pct AS pct",
            gid=GROUP_ID,
        )
        rows = await r.data()

    by_locale = {row["loc"]: row["pct"] for row in rows}
    assert "en" in by_locale
    assert by_locale["en"] == pytest.approx(100.0)
    assert "ru" in by_locale
    assert by_locale["ru"] == pytest.approx(80.0)
