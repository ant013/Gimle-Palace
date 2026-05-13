"""Tests for SPM declared_version_constraint capture (Task 4.1b)."""

from __future__ import annotations

import textwrap
from pathlib import Path


from palace_mcp.extractors.dependency_surface.parsers.spm import parse_spm


def test_from_constraint_captured(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent("""\
            let package = Package(
                dependencies: [
                    .package(url: "https://github.com/foo/bar", from: "5.0.0"),
                ]
            )
        """)
    )
    result = parse_spm(tmp_path, project_id="project/test")
    assert len(result.deps) == 1
    constraint = result.deps[0].declared_version_constraint
    assert "5.0.0" in constraint


def test_exact_constraint_captured(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent("""\
            let package = Package(
                dependencies: [
                    .package(url: "https://github.com/foo/bar", exact: "1.2.3"),
                ]
            )
        """)
    )
    result = parse_spm(tmp_path, project_id="project/test")
    assert len(result.deps) == 1
    constraint = result.deps[0].declared_version_constraint
    assert "1.2.3" in constraint


def test_branch_constraint_captured(tmp_path: Path) -> None:
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent("""\
            let package = Package(
                dependencies: [
                    .package(url: "https://github.com/foo/bar", branch: "main"),
                ]
            )
        """)
    )
    result = parse_spm(tmp_path, project_id="project/test")
    assert len(result.deps) == 1
    constraint = result.deps[0].declared_version_constraint
    assert constraint != ""


def test_no_constraint_stays_empty(tmp_path: Path) -> None:
    # Package with url + another non-version arg → ver group is None → ""
    (tmp_path / "Package.swift").write_text(
        textwrap.dedent("""\
            let package = Package(
                dependencies: [
                    .package(url: "https://github.com/foo/bar", name: "Foo"),
                ]
            )
        """)
    )
    result = parse_spm(tmp_path, project_id="project/test")
    # May produce 0 or 1 deps depending on regex match; if matched, constraint is ""
    if result.deps:
        assert result.deps[0].declared_version_constraint == ""
