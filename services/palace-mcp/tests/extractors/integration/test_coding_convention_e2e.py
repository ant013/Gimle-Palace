from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from neo4j import AsyncDriver

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.coding_convention.extractor import CodingConventionExtractor
from palace_mcp.extractors.schema import ensure_extractors_schema


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_repo(root: Path) -> Path:
    repo = root / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8")

    _write(
        repo / "Sources" / "WalletCore" / "WalletStore.swift",
        """
struct WalletStore {}
protocol WalletConnectable {}
func loadWallet() throws -> String { "" }
let primaryWallets = []
var balanceText: String { "0" }
""".strip()
        + "\n",
    )
    _write(
        repo / "Sources" / "WalletCore" / "WalletFormatter.swift",
        """
class WalletFormatter {}
protocol WalletSyncable {}
func persistWallet() throws -> String { "" }
let cachedWallets = []
var titleText: String { "wallet" }
""".strip()
        + "\n",
    )
    _write(
        repo / "Sources" / "WalletCore" / "WalletRecovery.swift",
        """
struct WalletRecovery {}
protocol WalletRecoverable {}
func recoverWallet() throws -> String { "" }
let archivedWallets = []
var subtitleText: String { "restore" }
""".strip()
        + "\n",
    )
    _write(
        repo / "Sources" / "WalletCore" / "WalletHistory.swift",
        """
class WalletHistory {}
protocol WalletTrackable {}
func fetchWalletHistory() throws -> String { "" }
let recentWallets = []
var historyText: String { "history" }
""".strip()
        + "\n",
    )
    _write(
        repo / "Sources" / "WalletCore" / "WalletSummary.swift",
        """
struct WalletSummary {}
protocol WalletProtocol {}
func summarizeWallet() -> Result<String, Never> { .success("") }
let summaryWallets = Array<String>()
lazy var cachedSummary = makeSummary()
""".strip()
        + "\n",
    )
    _write(
        repo / "Tests" / "WalletCore" / "WalletStoreTests.swift",
        "final class WalletStoreTests {}\n",
    )
    _write(
        repo / "Tests" / "WalletCore" / "WalletFormatterTests.swift",
        "final class WalletFormatterTests {}\n",
    )
    _write(
        repo / "Tests" / "WalletCore" / "WalletRecoveryTests.swift",
        "final class WalletRecoveryTests {}\n",
    )
    _write(
        repo / "Tests" / "WalletCore" / "WalletHistoryTests.swift",
        "final class WalletHistoryTests {}\n",
    )
    _write(
        repo / "Tests" / "WalletCore" / "LegacyWalletSpec.swift",
        "final class LegacyWalletSpec {}\n",
    )
    _write(
        repo / "app-mini" / "src" / "main" / "kotlin" / "io" / "example" / "WalletState.kt",
        """
sealed class WalletState
interface WalletCaching
fun loadState(): Result<String> = Result.success("")
val stateItems = listOf<String>()
val stateLabel: String get() = "state"
""".strip()
        + "\n",
    )
    return repo


def _ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="coding-mini",
        group_id="project/coding-mini",
        repo_path=repo_path,
        run_id="coding-e2e-run-001",
        duration_ms=0,
        logger=logging.getLogger("test.coding_convention.integration"),
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_coding_convention_run_writes_snapshot_and_ingest_run(
    driver: AsyncDriver,
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)
    await ensure_extractors_schema(driver)

    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = $group_id,
                p.name = 'Coding Mini',
                p.tags = []
            """,
            slug="coding-mini",
            group_id="project/coding-mini",
        )

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        stats = await CodingConventionExtractor().run(
            graphiti=MagicMock(),
            ctx=_ctx(repo),
        )

    assert stats.nodes_written >= 3

    async with driver.session() as session:
        conventions_result = await session.run(
            "MATCH (c:Convention {project_id: $project}) RETURN count(c) AS count",
            project="coding-mini",
        )
        conventions_row = await conventions_result.single()

        violations_result = await session.run(
            "MATCH (v:ConventionViolation {project_id: $project}) RETURN count(v) AS count",
            project="coding-mini",
        )
        violations_row = await violations_result.single()

        ingest_result = await session.run(
            """
            MATCH (r:IngestRun {run_id: $run_id})
            RETURN r.project AS project,
                   r.extractor_name AS extractor_name,
                   r.success AS success,
                   r.error_code AS error_code
            """,
            run_id="coding-e2e-run-001",
        )
        ingest_row = await ingest_result.single()

    assert conventions_row is not None and conventions_row["count"] >= 3
    assert violations_row is not None and violations_row["count"] >= 1
    assert ingest_row is not None
    assert ingest_row["project"] == "coding-mini"
    assert ingest_row["extractor_name"] == "coding_convention"
    assert ingest_row["success"] is True
    assert ingest_row["error_code"] is None
