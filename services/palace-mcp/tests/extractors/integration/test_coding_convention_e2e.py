from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.extractors import runner as extractor_runner
from palace_mcp.extractors.schema import ensure_extractors_schema


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_repo(root: Path, project_slug: str) -> Path:
    repo = root / project_slug
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text(
        "0123456789abcdef0123456789abcdef01234567\n", encoding="utf-8"
    )

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
        repo
        / "app-mini"
        / "src"
        / "main"
        / "kotlin"
        / "io"
        / "example"
        / "WalletState.kt",
        """
sealed class WalletState
interface WalletCaching
fun loadState(): Result<String> = Result.success("")
val stateItems = listOf<String>()
val stateLabel: String get() = "state"
""".strip()
        + "\n",
    )
    _write(
        repo
        / "app-mini"
        / "src"
        / "main"
        / "kotlin"
        / "io"
        / "example"
        / "WalletMode.kt",
        """
sealed class WalletMode
interface WalletSyncing
fun loadMode(): Result<String> = Result.success("")
val modeItems = listOf<String>()
val modeLabel: String get() = "mode"
""".strip()
        + "\n",
    )
    _write(
        repo
        / "app-mini"
        / "src"
        / "main"
        / "kotlin"
        / "io"
        / "example"
        / "WalletPhase.kt",
        """
sealed class WalletPhase
interface WalletTracking
fun loadPhase(): Result<String> = Result.success("")
val phaseItems = listOf<String>()
val phaseLabel: String get() = "phase"
""".strip()
        + "\n",
    )
    _write(
        repo
        / "app-mini"
        / "src"
        / "main"
        / "kotlin"
        / "io"
        / "example"
        / "WalletFlow.kt",
        """
sealed class WalletFlow
interface WalletRouting
fun loadFlow(): Result<String> = Result.success("")
val flowItems = listOf<String>()
val flowLabel: String get() = "flow"
""".strip()
        + "\n",
    )
    _write(
        repo
        / "app-mini"
        / "src"
        / "main"
        / "kotlin"
        / "io"
        / "example"
        / "WalletLegacy.kt",
        """
enum class WalletLegacy { LEGACY }
interface WalletProtocol
fun loadLegacy(): String? = null
val legacyItems = ArrayList()
val legacyLabel by lazy { "legacy" }
""".strip()
        + "\n",
    )
    return repo


@pytest.mark.asyncio
@pytest.mark.integration
async def test_coding_convention_runner_path_writes_single_ingest_run_snapshot(
    driver: AsyncDriver,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_slug = "coding-mini"
    _build_repo(tmp_path, project_slug)
    await ensure_extractors_schema(driver)
    monkeypatch.setattr(extractor_runner, "REPOS_ROOT", tmp_path)

    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Project {slug: $slug})
            SET p.group_id = $group_id,
                p.name = 'Coding Mini',
                p.tags = []
            """,
            slug=project_slug,
            group_id=f"project/{project_slug}",
        )

    with patch("palace_mcp.mcp_server.get_driver", return_value=driver):
        result = await extractor_runner.run_extractor(
            "coding_convention",
            project_slug,
            driver=driver,
            graphiti=cast(Graphiti, object()),
        )

    assert result["ok"] is True
    assert result["extractor"] == "coding_convention"
    run_id = result["run_id"]

    async with driver.session() as session:
        conventions_result = await session.run(
            """
            MATCH (c:Convention {project_id: $project, run_id: $run_id})
            RETURN count(c) AS count, collect(DISTINCT c.kind) AS kinds
            """,
            project=project_slug,
            run_id=run_id,
        )
        conventions_row = await conventions_result.single()

        violations_result = await session.run(
            """
            MATCH (v:ConventionViolation {project_id: $project, run_id: $run_id})
            RETURN count(v) AS count, collect(DISTINCT v.kind) AS kinds
            """,
            project=project_slug,
            run_id=run_id,
        )
        violations_row = await violations_result.single()

        ingest_by_id_result = await session.run(
            """
            MATCH (r:IngestRun {id: $id})
            RETURN count(r) AS count,
                   head(collect(r.project)) AS project,
                   head(collect(r.extractor_name)) AS extractor_name,
                   head(collect(r.success)) AS success
            """,
            id=run_id,
        )
        ingest_by_id_row = await ingest_by_id_result.single()

        ingest_by_run_id_result = await session.run(
            "MATCH (r:IngestRun {run_id: $run_id}) RETURN count(r) AS count",
            run_id=run_id,
        )
        ingest_by_run_id_row = await ingest_by_run_id_result.single()

    expected_kinds = {
        "naming.type_class",
        "naming.test_class",
        "naming.module_protocol",
        "structural.adt_pattern",
        "structural.error_modeling",
        "idiom.collection_init",
        "idiom.computed_vs_property",
    }

    assert conventions_row is not None
    assert conventions_row["count"] >= 8
    assert set(conventions_row["kinds"]) == expected_kinds

    assert violations_row is not None
    assert violations_row["count"] >= 8
    assert {
        "naming.test_class",
        "naming.module_protocol",
        "structural.adt_pattern",
        "structural.error_modeling",
        "idiom.collection_init",
        "idiom.computed_vs_property",
    }.issubset(set(violations_row["kinds"]))

    assert ingest_by_id_row is not None
    assert ingest_by_id_row["count"] == 1
    assert ingest_by_id_row["project"] == project_slug
    assert ingest_by_id_row["extractor_name"] == "coding_convention"
    assert ingest_by_id_row["success"] is True

    assert ingest_by_run_id_row is not None
    assert ingest_by_run_id_row["count"] == 0
