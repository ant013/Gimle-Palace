from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.testability_di.rules import extract_test_doubles
from palace_mcp.extractors.testability_di.scanner import scan_repository

_FIXTURES_DIR = (
    Path(__file__).parent.parent / "fixtures" / "testability_di" / "test_doubles"
)


def test_extract_test_doubles_detects_framework_and_hand_rolled_doubles() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    doubles = extract_test_doubles(
        sources,
        project_id="project/wallet",
        run_id="run-test-doubles",
    )
    lookup = {(double.language, double.kind): double for double in doubles}

    assert lookup[("swift", "cuckoo")].test_file.endswith("WalletServiceTests.swift")
    assert lookup[("swift", "fake")].target_symbol == "WalletService"
    assert lookup[("swift", "spy")].target_symbol == "PriceFeed"
    assert lookup[("kotlin", "mockk")].test_file.endswith("WalletRepositoryTest.kt")
    assert lookup[("kotlin", "mockito")].test_file.endswith("WalletRepositoryTest.kt")
    assert lookup[("kotlin", "fake")].target_symbol == "WalletApi"
    assert lookup[("kotlin", "stub")].target_symbol == "Clock"


def test_extract_test_doubles_ignores_non_test_files() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    doubles = extract_test_doubles(
        sources,
        project_id="project/wallet",
        run_id="run-test-doubles",
    )

    assert all("FakeCurrencyFormatter" not in double.test_file for double in doubles)
