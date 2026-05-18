"""Regression test: error_handling_policy must not raise IsADirectoryError (GIM-348).

Reproduces the GIM-334 failure mode: .build/checkouts/ contains a directory
whose name ends in .swift (e.g. GRDB.swift), causing path.read_text() to raise
IsADirectoryError when the old rglob("*.swift") walker yielded it.
"""

from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.error_handling_policy.extractor import _collect_catch_sites


def test_collect_catch_sites_ignores_build_checkouts(tmp_path: Path):
    """_collect_catch_sites completes without IsADirectoryError on .build/checkouts/."""
    # Simulate the exact failing structure from BitcoinCore.Swift:
    # .build/checkouts/GRDB.swift  — a DIRECTORY whose name ends in .swift
    grdb_dir = tmp_path / ".build" / "checkouts" / "GRDB.swift"
    grdb_dir.mkdir(parents=True)
    # Put a real Swift file inside it (which the walker must NOT see)
    (grdb_dir / "Database.swift").write_text("class Database {}\n")

    # A real source file in the repo
    sources = tmp_path / "Sources" / "App"
    sources.mkdir(parents=True)
    (sources / "Service.swift").write_text(
        "func run() {\n  do {\n    try action()\n  } catch {}\n}\n"
    )

    # Must not raise; must return a list (possibly empty or with findings)
    result = _collect_catch_sites(tmp_path)
    assert isinstance(result, list)


def test_collect_catch_sites_directory_named_swift_skipped(tmp_path: Path):
    """A directory literally named Foo.swift is skipped; no IsADirectoryError."""
    swift_dir = tmp_path / "Foo.swift"
    swift_dir.mkdir()
    (swift_dir / "inner.txt").write_text("not swift\n")

    # No real Swift files — should return empty list without error
    result = _collect_catch_sites(tmp_path)
    assert result == []
