from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.testability_di.rules import extract_di_patterns
from palace_mcp.extractors.testability_di.scanner import scan_repository

_FIXTURES_DIR = (
    Path(__file__).parent.parent / "fixtures" / "testability_di" / "di_style"
)


def test_extract_di_patterns_detects_swift_and_kotlin_styles() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    patterns = extract_di_patterns(
        sources,
        project_id="project/wallet",
        run_id="run-di-style",
    )
    lookup = {
        (pattern.language, pattern.style, pattern.framework): pattern
        for pattern in patterns
    }

    assert lookup[("swift", "init_injection", None)].sample_count == 1
    assert lookup[("swift", "property_injection", None)].sample_count == 1
    assert lookup[("swift", "framework_bound", "resolver")].sample_count == 1
    assert lookup[("swift", "framework_bound", "swinject")].sample_count == 1
    assert lookup[("swift", "framework_bound", "factory")].sample_count == 1
    assert lookup[("swift", "framework_bound", "needle")].sample_count == 1
    assert lookup[("swift", "service_locator", None)].sample_count == 1
    assert lookup[("kotlin", "init_injection", None)].sample_count == 1
    assert lookup[("kotlin", "property_injection", None)].sample_count == 2
    assert lookup[("kotlin", "framework_bound", "hilt")].sample_count == 1
    assert lookup[("kotlin", "framework_bound", "dagger")].sample_count == 1
    assert lookup[("kotlin", "framework_bound", "koin")].sample_count == 1
    assert lookup[("kotlin", "service_locator", None)].sample_count == 1


def test_extract_di_patterns_sets_confidence_and_outliers() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    patterns = extract_di_patterns(
        sources,
        project_id="project/wallet",
        run_id="run-di-style",
    )

    assert all(pattern.confidence == "heuristic" for pattern in patterns)
    assert all(pattern.outliers == 0 for pattern in patterns)


def test_extract_di_patterns_allowlists_tests_and_composition_roots() -> None:
    sources = scan_repository(repo_path=_FIXTURES_DIR)

    patterns = extract_di_patterns(
        sources,
        project_id="project/wallet",
        run_id="run-di-style",
    )

    service_locator_modules = {
        pattern.module for pattern in patterns if pattern.style == "service_locator"
    }

    assert "AppRoot" not in service_locator_modules
    assert "KoinBootstrap" not in service_locator_modules
