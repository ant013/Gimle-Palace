"""Unit tests for palace_mcp.extractors.foundation.walk (GIM-348)."""

from __future__ import annotations

from pathlib import Path

import pytest

from palace_mcp.extractors.foundation.walk import (
    DEFAULT_STOP_DIRS,
    DEFAULT_STOP_PREFIXES,
    should_skip_path,
    walk_repo,
)


def _write(path: Path, content: str = "x\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# walk_repo tests
# ---------------------------------------------------------------------------


def test_stop_dirs_skipped(tmp_path: Path):
    """Files inside .build/checkouts/ and node_modules/ must not be yielded."""
    _write(tmp_path / ".build" / "checkouts" / "GRDB" / "Source.swift")
    _write(tmp_path / "node_modules" / "foo" / "bar.js")
    _write(tmp_path / "Sources" / "App" / "Main.swift")

    out = {p.relative_to(tmp_path).as_posix() for p in walk_repo(tmp_path)}
    assert out == {"Sources/App/Main.swift"}


def test_source_files_not_skipped(tmp_path: Path):
    """Regular source files are yielded."""
    _write(tmp_path / "Sources" / "App" / "Main.swift")
    _write(tmp_path / "Tests" / "Unit" / "FooTests.swift")

    out = {p.relative_to(tmp_path).as_posix() for p in walk_repo(tmp_path)}
    assert out == {"Sources/App/Main.swift", "Tests/Unit/FooTests.swift"}


def test_extra_excludes_additive(tmp_path: Path):
    """extra_excludes adds on top of the default stop-list."""
    _write(tmp_path / "MyCache" / "data.swift")
    _write(tmp_path / "Sources" / "ok.swift")

    out = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_repo(tmp_path, extra_excludes=frozenset({"MyCache"}))
    }
    assert out == {"Sources/ok.swift"}


def test_prefix_matching(tmp_path: Path):
    """.palace-xcb-* and .palace-scip-* directories are skipped."""
    _write(tmp_path / ".palace-xcb-abc123" / "index.swift")
    _write(tmp_path / ".palace-scip-deadbeef" / "scip.swift")
    _write(tmp_path / "Sources" / "ok.swift")

    out = {p.relative_to(tmp_path).as_posix() for p in walk_repo(tmp_path)}
    assert out == {"Sources/ok.swift"}


def test_suffixes_filter(tmp_path: Path):
    """suffixes= restricts yielded files to matching extensions."""
    _write(tmp_path / "Sources" / "Main.swift")
    _write(tmp_path / "Sources" / "helper.py")
    _write(tmp_path / "Sources" / "README.md")

    out = {
        p.relative_to(tmp_path).as_posix()
        for p in walk_repo(tmp_path, suffixes=frozenset({".swift"}))
    }
    assert out == {"Sources/Main.swift"}


def test_all_default_stop_dirs_excluded(tmp_path: Path):
    """Spot-check several DEFAULT_STOP_DIRS entries are pruned."""
    for stop_dir in (".build", "Pods", "Carthage", "vendor", "DerivedData", ".swiftpm"):
        assert stop_dir in DEFAULT_STOP_DIRS
        _write(tmp_path / stop_dir / "artifact.swift")

    _write(tmp_path / "Sources" / "Real.swift")

    out = {p.relative_to(tmp_path).as_posix() for p in walk_repo(tmp_path)}
    assert out == {"Sources/Real.swift"}


# ---------------------------------------------------------------------------
# should_skip_path tests
# ---------------------------------------------------------------------------


def test_should_skip_path_predicate():
    """should_skip_path returns True for stop-list components, False otherwise."""
    assert should_skip_path([".build", "checkouts", "GRDB", "Source.swift"]) is True
    assert should_skip_path(["node_modules", "foo", "bar.js"]) is True
    assert should_skip_path(["Sources", "App", "Main.swift"]) is False
    assert should_skip_path([".palace-xcb-abc123", "index"]) is True
    assert should_skip_path([".palace-scip-deadbeef", "data"]) is True


def test_should_skip_path_extra_excludes():
    assert should_skip_path(["MyCache"], extra_excludes=frozenset({"MyCache"})) is True
    assert should_skip_path(["Sources"], extra_excludes=frozenset({"MyCache"})) is False


def test_should_skip_path_extra_prefixes():
    assert should_skip_path([".custom-build-x"], extra_prefixes=(".custom-",)) is True
    assert should_skip_path(["Sources"], extra_prefixes=(".custom-",)) is False


def test_default_stop_prefixes_constant():
    assert ".palace-xcb-" in DEFAULT_STOP_PREFIXES
    assert ".palace-scip-" in DEFAULT_STOP_PREFIXES
