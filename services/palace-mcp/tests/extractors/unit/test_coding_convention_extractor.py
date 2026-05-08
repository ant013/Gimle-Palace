from __future__ import annotations

import logging
from pathlib import Path

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.coding_convention.extractor import (
    CodingConventionExtractor,
    collect_conventions,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_repo(root: Path) -> Path:
    repo = root / "repo"
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


def _make_ctx(repo_path: Path) -> ExtractorRunContext:
    return ExtractorRunContext(
        project_slug="coding-mini",
        group_id="project/coding-mini",
        repo_path=repo_path,
        run_id="coding-run-001",
        duration_ms=0,
        logger=logging.getLogger("test.coding_convention"),
    )


def test_collect_conventions_aggregates_dominant_choices_and_outliers(
    tmp_path: Path,
) -> None:
    repo = _build_repo(tmp_path)

    summary = collect_conventions(
        project_id="coding-mini", repo_path=repo, run_id="run-1"
    )
    convention_by_kind = {
        (finding.module, finding.kind): finding for finding in summary.findings
    }

    test_class = convention_by_kind[("WalletCore", "naming.test_class")]
    assert test_class.dominant_choice == "suffix_tests"
    assert test_class.sample_count == 5
    assert test_class.outliers == 1
    assert test_class.confidence == "heuristic"

    protocol_kind = convention_by_kind[("WalletCore", "naming.module_protocol")]
    assert protocol_kind.dominant_choice == "suffix_able"
    assert protocol_kind.sample_count == 5
    assert protocol_kind.outliers == 1

    collection_kind = convention_by_kind[("WalletCore", "idiom.collection_init")]
    assert collection_kind.dominant_choice == "literal_empty"
    assert collection_kind.sample_count == 5
    assert collection_kind.outliers == 1
    assert collection_kind.confidence == "heuristic"

    type_kind = convention_by_kind[("WalletCore", "naming.type_class")]
    assert type_kind.dominant_choice == "upper_camel"
    assert type_kind.sample_count == 12
    assert type_kind.outliers == 0

    error_kind = convention_by_kind[("WalletCore", "structural.error_modeling")]
    assert error_kind.dominant_choice == "throws"
    assert error_kind.sample_count == 5
    assert error_kind.outliers == 1

    property_kind = convention_by_kind[("WalletCore", "idiom.computed_vs_property")]
    assert property_kind.dominant_choice == "computed_property"
    assert property_kind.sample_count == 5
    assert property_kind.outliers == 1

    adt_kind = convention_by_kind[("app-mini", "structural.adt_pattern")]
    assert adt_kind.dominant_choice == "sealed"
    assert adt_kind.sample_count == 6
    assert adt_kind.outliers == 2

    kotlin_protocol_kind = convention_by_kind[("app-mini", "naming.module_protocol")]
    assert kotlin_protocol_kind.dominant_choice == "suffix_ing"
    assert kotlin_protocol_kind.sample_count == 5
    assert kotlin_protocol_kind.outliers == 1

    kotlin_property_kind = convention_by_kind[
        ("app-mini", "idiom.computed_vs_property")
    ]
    assert kotlin_property_kind.dominant_choice == "computed_property"
    assert kotlin_property_kind.sample_count == 5
    assert kotlin_property_kind.outliers == 1

    kotlin_error_kind = convention_by_kind[("app-mini", "structural.error_modeling")]
    assert kotlin_error_kind.dominant_choice == "result"
    assert kotlin_error_kind.sample_count == 5
    assert kotlin_error_kind.outliers == 1

    assert any(
        violation.kind == "naming.test_class"
        and violation.file == "Tests/WalletCore/LegacyWalletSpec.swift"
        and violation.severity == "high"
        for violation in summary.violations
    )
    assert any(
        violation.kind == "structural.adt_pattern"
        and violation.file == "app-mini/src/main/kotlin/io/example/WalletLegacy.kt"
        and violation.severity == "high"
        for violation in summary.violations
    )


def test_collect_conventions_skips_groups_below_min_sample_count(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(repo / "Sources" / "Mini" / "A.swift", "struct WALLET_A {}\n")
    _write(repo / "Sources" / "Mini" / "B.swift", "struct WalletB {}\n")
    _write(repo / "Sources" / "Mini" / "C.swift", "struct WalletC {}\n")

    summary = collect_conventions(
        project_id="coding-mini",
        repo_path=repo,
        run_id="run-min-sample",
    )

    assert summary.findings == []
    assert summary.violations == []


@pytest.mark.asyncio
async def test_run_requires_registered_driver(tmp_path: Path) -> None:
    repo = _build_repo(tmp_path)
    ctx = _make_ctx(repo)

    with pytest.raises(Exception):
        await CodingConventionExtractor().run(graphiti=object(), ctx=ctx)
