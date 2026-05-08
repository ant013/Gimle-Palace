"""Integration tests for crypto_domain_model extractor (GIM-239).

D.1 — test_run_integration_synthetic: invoke extractor against the mini-project
       fixture using a real Neo4j testcontainer; assert 7 :CryptoFinding nodes.
D.2 — test_schema_creation_idempotent: verify crypto constraints + indexes are
       created and re-creating them (IF NOT EXISTS) does not error.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.crypto_domain_model.extractor import (
    CryptoDomainModelExtractor,
)
from palace_mcp.extractors.schema import ensure_extractors_schema

_FIXTURE_SOURCES = (
    Path(__file__).parents[2]
    / "extractors"
    / "fixtures"
    / "crypto-domain-mini-project"
    / "Sources"
)

PROJECT_SLUG = "crypto-integ"
GROUP_ID = f"project/{PROJECT_SLUG}"

# 5 bad files: 2 (AddressChecksum) + 1 (BigNum) + 1 (DecimalArith) + 1 (PrivateKey) + 2 (WeiEthMix)
# All 7 have distinct (file, line, kind) keys; D5 dedup leaves them intact.
EXPECTED_FINDING_COUNT = 7


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_path,
        run_id="integ-run-1",
        duration_ms=0,
        logger=logging.getLogger("test.crypto_domain_model"),
    )


def _fake_settings() -> MagicMock:
    s = MagicMock()
    s.palace_crypto_semgrep_timeout_s = 120
    return s


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_integration_synthetic(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    """D.1: extractor writes exactly 7 :CryptoFinding nodes from 5 bad fixtures."""
    # Copy fixtures out of tests/ to avoid semgrep's default .semgrepignore
    target = tmp_path / "Sources"
    shutil.copytree(_FIXTURE_SOURCES, target)

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        stats = await CryptoDomainModelExtractor().run(
            graphiti=graphiti_mock,
            ctx=_make_ctx(tmp_path),
        )

    assert stats.nodes_written == EXPECTED_FINDING_COUNT

    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:CryptoFinding {project_id: $pid}) RETURN count(f) AS n",
            pid=GROUP_ID,
        )
        row = await result.single()
    assert row is not None
    assert row["n"] == EXPECTED_FINDING_COUNT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_integration_idempotent(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    """D.1b: second run MERGEs the same nodes — node count stays at 7."""
    target = tmp_path / "Sources"
    shutil.copytree(_FIXTURE_SOURCES, target)

    ctx1 = _make_ctx(tmp_path)
    ctx2 = ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=tmp_path,
        run_id="integ-run-2",
        duration_ms=0,
        logger=logging.getLogger("test.crypto_domain_model"),
    )
    extractor = CryptoDomainModelExtractor()

    with patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()):
        stats1 = await extractor.run(graphiti=graphiti_mock, ctx=ctx1)
        stats2 = await extractor.run(graphiti=graphiti_mock, ctx=ctx2)

    assert stats1.nodes_written == EXPECTED_FINDING_COUNT
    # MERGE on same (project_id, kind, file, start_line, end_line) → idempotent, same count
    assert stats2.nodes_written == EXPECTED_FINDING_COUNT

    async with driver.session() as session:
        result = await session.run(
            "MATCH (f:CryptoFinding {project_id: $pid}) RETURN count(f) AS n",
            pid=GROUP_ID,
        )
        row = await result.single()
    assert row is not None
    assert row["n"] == EXPECTED_FINDING_COUNT


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schema_creation_idempotent(driver: AsyncDriver) -> None:
    """D.2: crypto_domain_model constraints + indexes created; re-run is no-op."""
    # First application
    await ensure_extractors_schema(driver)
    # Second application — IF NOT EXISTS makes this idempotent
    await ensure_extractors_schema(driver)

    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name")
        constraint_names = [row["name"] async for row in result]

    assert "crypto_finding_unique" in constraint_names

    async with driver.session() as session:
        result = await session.run("SHOW INDEXES YIELD name")
        index_names = [row["name"] async for row in result]

    assert "crypto_finding_project" in index_names
    assert "crypto_finding_severity" in index_names
