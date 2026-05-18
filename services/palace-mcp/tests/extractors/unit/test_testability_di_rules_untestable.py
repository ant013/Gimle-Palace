from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.testability_di.rules import extract_untestable_sites
from palace_mcp.extractors.testability_di.scanner import scan_repository

_FIXTURES_DIR = (
    Path(__file__).parent.parent / "fixtures" / "testability_di" / "untestable_sites"
)


def test_extract_untestable_sites_detects_categories_and_ranges() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    findings = extract_untestable_sites(
        sources,
        project_id="project/wallet",
        run_id="run-untestable",
    )
    categories = {
        (finding.language, finding.category, finding.symbol_referenced): finding
        for finding in findings
    }

    assert categories[("swift", "direct_clock", "Date()")].start_line > 0
    assert (
        categories[("swift", "direct_session", "URLSession.shared")].end_line
        >= categories[("swift", "direct_session", "URLSession.shared")].start_line
    )
    assert (
        categories[("swift", "direct_preferences", "UserDefaults.standard")].severity
        == "high"
    )
    assert categories[("swift", "direct_filesystem", "FileManager.default")].message
    assert (
        categories[("swift", "service_locator", "ServiceLocator.shared")].severity
        == "high"
    )
    assert categories[("kotlin", "direct_clock", "Instant.now()")].severity == "high"
    assert (
        categories[
            ("kotlin", "service_locator", "SessionManager.getInstance()")
        ].severity
        == "high"
    )


def test_extract_untestable_sites_allowlists_tests_and_composition_roots() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    findings = extract_untestable_sites(
        sources,
        project_id="project/wallet",
        run_id="run-untestable",
    )
    files = {finding.file for finding in findings}

    assert "Tests/WalletKitTests/WalletManagerTests.swift" not in files
    assert "Sources/AppRoot/CompositionRoot.swift" not in files
    assert "app/src/main/kotlin/com/example/bootstrap/KoinBootstrap.kt" not in files
