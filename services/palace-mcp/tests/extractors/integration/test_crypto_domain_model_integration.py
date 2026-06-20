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
from palace_mcp.extractors.foundation.incremental_scope import (
    IncrementalMode,
    IncrementalPathScope,
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


async def _fetch_findings(driver: AsyncDriver) -> list[dict[str, object]]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (f:CryptoFinding {project_id: $pid})
            RETURN f.file AS file,
                   f.kind AS kind,
                   f.start_line AS start_line,
                   f.end_line AS end_line,
                   f.message AS message,
                   f.run_id AS run_id
            ORDER BY f.file, f.kind, f.start_line, f.end_line
            """,
            pid=GROUP_ID,
        )
        return [row.data() async for row in result]


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
async def test_incremental_run_replaces_changed_file_and_preserves_unchanged_file(
    driver: AsyncDriver,
    graphiti_mock: MagicMock,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    changed_file = "Sources/Changed.swift"
    unchanged_file = "Sources/Unchanged.swift"
    for relative_path in (changed_file, unchanged_file):
        file_path = repo_root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("// fixture\n", encoding="utf-8")

    extractor = CryptoDomainModelExtractor()
    first_ctx = _make_ctx(repo_root)
    second_ctx = ExtractorRunContext(
        project_slug=PROJECT_SLUG,
        group_id=GROUP_ID,
        repo_path=repo_root,
        run_id="integ-run-2",
        duration_ms=0,
        logger=logging.getLogger("test.crypto_domain_model"),
    )

    first_run_findings = [
        {
            "path": str((repo_root / changed_file).resolve()),
            "start": {"line": 10},
            "end": {"line": 10},
            "check_id": "changed_rule",
            "extra": {
                "severity": "WARNING",
                "message": "old changed finding",
                "metadata": {"kind": "changed_kind"},
            },
        },
        {
            "path": str((repo_root / unchanged_file).resolve()),
            "start": {"line": 30},
            "end": {"line": 30},
            "check_id": "unchanged_rule",
            "extra": {
                "severity": "WARNING",
                "message": "stable unchanged finding",
                "metadata": {"kind": "unchanged_kind"},
            },
        },
    ]
    second_run_findings = [
        {
            "path": str((repo_root / changed_file).resolve()),
            "start": {"line": 15},
            "end": {"line": 15},
            "check_id": "changed_rule",
            "extra": {
                "severity": "ERROR",
                "message": "new changed finding",
                "metadata": {"kind": "changed_kind"},
            },
        }
    ]

    with (
        patch("palace_mcp.mcp_server.get_settings", return_value=_fake_settings()),
        patch(
            "palace_mcp.extractors.crypto_domain_model.extractor.derive_incremental_path_scope",
            side_effect=[
                IncrementalPathScope(
                    mode=IncrementalMode.INCREMENTAL,
                    changed_paths={changed_file, unchanged_file},
                    removed_paths=set(),
                ),
                IncrementalPathScope(
                    mode=IncrementalMode.INCREMENTAL,
                    changed_paths={changed_file},
                    removed_paths=set(),
                ),
            ],
        ),
        patch(
            "palace_mcp.extractors.crypto_domain_model.extractor.run_semgrep",
            side_effect=[first_run_findings, second_run_findings],
        ),
    ):
        await extractor.run(graphiti=graphiti_mock, ctx=first_ctx)
        before = await _fetch_findings(driver)
        await extractor.run(graphiti=graphiti_mock, ctx=second_ctx)

    after = await _fetch_findings(driver)
    unchanged_before = [row for row in before if row["file"] == unchanged_file]
    changed_after = [row for row in after if row["file"] == changed_file]
    unchanged_after = [row for row in after if row["file"] == unchanged_file]

    assert before == [
        {
            "file": changed_file,
            "kind": "changed_kind",
            "start_line": 10,
            "end_line": 10,
            "message": "old changed finding",
            "run_id": "integ-run-1",
        },
        {
            "file": unchanged_file,
            "kind": "unchanged_kind",
            "start_line": 30,
            "end_line": 30,
            "message": "stable unchanged finding",
            "run_id": "integ-run-1",
        },
    ]
    assert changed_after == [
        {
            "file": changed_file,
            "kind": "changed_kind",
            "start_line": 15,
            "end_line": 15,
            "message": "new changed finding",
            "run_id": "integ-run-2",
        }
    ]
    assert unchanged_after == unchanged_before
    assert len(after) == 2


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
