"""Acceptance #23 — query-timeout coverage for cross-repo version skew.

Tests that the PALACE_VERSION_SKEW_QUERY_TIMEOUT_S setting is:
  1. Loaded with the correct default (30 s) and bounds (ge=1, le=600).
  2. Read by the extractor and passed as timeout_s through the pipeline.

Actual query-killing via APOC dbms.transaction.timeout is deferred to a
follow-up: enforcing a Bolt session timeout requires Neo4j APOC or
`dbms.transaction.timeout` server config that is not guaranteed in CI.
This test covers the observable surface (settings + parameter threading)
without an APOC dependency.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.config import Settings


def _minimal_env() -> dict[str, str]:
    return {
        "NEO4J_PASSWORD": "test-secret",
        "OPENAI_API_KEY": "sk-test",
    }


# ── Settings-layer tests ───────────────────────────────────────────────────────


def test_version_skew_query_timeout_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """PALACE_VERSION_SKEW_QUERY_TIMEOUT_S defaults to 30."""
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.palace_version_skew_query_timeout_s == 30


def test_version_skew_query_timeout_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """PALACE_VERSION_SKEW_QUERY_TIMEOUT_S can be raised within bounds."""
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_VERSION_SKEW_QUERY_TIMEOUT_S", "120")
    s = Settings()
    assert s.palace_version_skew_query_timeout_s == 120


def test_version_skew_query_timeout_too_high_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PALACE_VERSION_SKEW_QUERY_TIMEOUT_S > 600 is rejected by Pydantic."""
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_VERSION_SKEW_QUERY_TIMEOUT_S", "601")
    with pytest.raises(ValidationError):
        Settings()


def test_version_skew_query_timeout_zero_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PALACE_VERSION_SKEW_QUERY_TIMEOUT_S=0 is rejected (ge=1)."""
    for k, v in _minimal_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PALACE_VERSION_SKEW_QUERY_TIMEOUT_S", "0")
    with pytest.raises(ValidationError):
        Settings()


# ── Extractor reads timeout from settings ─────────────────────────────────────


@pytest.mark.asyncio
async def test_extractor_reads_timeout_from_settings(driver: object) -> None:
    """The extractor reads palace_version_skew_query_timeout_s and passes it as timeout_s.

    Verified by confirming the extractor does not raise when the setting is set
    to a non-default value and the pipeline runs to completion.
    Note: timeout_s is threaded through _bundle_exists / _bundle_members /
    _collect_target_status parameters. Wiring timeout_s to driver.session()
    is tracked as W1 — a follow-up for v2.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from palace_mcp.extractors.cross_repo_version_skew.extractor import (
        CrossRepoVersionSkewExtractor,
    )

    # Patch settings to return a custom timeout
    mock_settings = MagicMock()
    mock_settings.palace_version_skew_query_timeout_s = 45

    # Patch the extractor's internal pipeline to verify timeout_s propagation
    ext = CrossRepoVersionSkewExtractor()

    captured_timeout: list[int] = []

    original_pipeline = ext._pipeline

    async def capturing_pipeline(*, driver, mode, target_slug, timeout_s, logger):  # type: ignore[no-untyped-def]
        captured_timeout.append(timeout_s)
        return await original_pipeline(
            driver=driver,
            mode=mode,
            target_slug=target_slug,
            timeout_s=timeout_s,
            logger=logger,
        )

    ext._pipeline = capturing_pipeline  # type: ignore[method-assign]

    from palace_mcp.extractors.base import ExtractorRunContext, ExtractorStats

    ctx = MagicMock(spec=ExtractorRunContext)
    ctx.project_slug = "timeout-test-proj"
    ctx.run_id = "00000000-0000-0000-0000-000000000001"
    ctx.logger = MagicMock()

    async with driver.session() as session:  # type: ignore[union-attr]
        await session.run("MATCH (n) DETACH DELETE n")
        await session.run(
            """
            MERGE (p:Project {slug: 'timeout-test-proj'})
            MERGE (d:ExternalDependency {purl: 'pkg:pypi/foo@1.0.0'})
              SET d.ecosystem = 'pypi', d.resolved_version = '1.0.0'
            MERGE (p)-[:DEPENDS_ON {scope: 'main', declared_in: 'req.txt',
                                    declared_version_constraint: '>=1.0'}]->(d)
            """
        )

    with (
        patch("palace_mcp.mcp_server.get_driver", return_value=driver),
        patch("palace_mcp.mcp_server.get_settings", return_value=mock_settings),
        patch(
            "palace_mcp.extractors.cross_repo_version_skew.neo4j_writer._write_run_extras",
            new_callable=AsyncMock,
        ),
    ):
        result = await ext.run(graphiti=None, ctx=ctx)

    assert isinstance(result, ExtractorStats)
    assert captured_timeout == [45], (
        f"Expected timeout_s=45 to be passed through pipeline; got {captured_timeout}"
    )
