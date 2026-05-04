"""Unit tests for Python dependency parser (pyproject.toml + uv.lock) — Task 5."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from palace_mcp.extractors.dependency_surface.parsers.python import parse_python

_PYPROJECT_TOML = textwrap.dedent(
    """
    [project]
    name = "x"
    dependencies = ["neo4j>=5.0", "graphiti-core==0.28.2"]
    [project.optional-dependencies]
    test = ["pytest>=7.0"]
    """
)

_UV_LOCK = textwrap.dedent(
    """
    version = 1
    [[package]]
    name = "neo4j"
    version = "5.28.2"

    [[package]]
    name = "graphiti-core"
    version = "0.28.2"

    [[package]]
    name = "pytest"
    version = "8.3.4"
    """
)


def test_python_parser_pyproject_and_uv_lock(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    (tmp_path / "uv.lock").write_text(_UV_LOCK)

    r = parse_python(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}

    assert "pkg:pypi/neo4j@5.28.2" in by_purl
    assert by_purl["pkg:pypi/neo4j@5.28.2"].scope == "compile"
    assert "pkg:pypi/graphiti-core@0.28.2" in by_purl
    assert by_purl["pkg:pypi/graphiti-core@0.28.2"].scope == "compile"
    assert "pkg:pypi/pytest@8.3.4" in by_purl
    assert by_purl["pkg:pypi/pytest@8.3.4"].scope == "test"


def test_python_parser_no_uv_lock_unresolved(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    # No uv.lock
    r = parse_python(tmp_path, project_id="project/x")
    assert all(d.resolved_version == "unresolved" for d in r.deps)
    assert any("uv.lock" in w for w in r.parser_warnings)


def test_python_parser_dependency_not_in_lock_warns(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "x"
            dependencies = ["foo>=1.0", "neo4j>=5.0"]
            """
        )
    )
    (tmp_path / "uv.lock").write_text(
        textwrap.dedent(
            """
            version = 1
            [[package]]
            name = "neo4j"
            version = "5.28.2"
            """
        )
    )
    r = parse_python(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    # foo not in lock
    assert "pkg:pypi/foo@unresolved" in by_purl
    assert any("foo" in w for w in r.parser_warnings)
    # neo4j in lock
    assert "pkg:pypi/neo4j@5.28.2" in by_purl


def test_python_parser_no_pyproject(tmp_path: Path) -> None:
    r = parse_python(tmp_path, project_id="project/x")
    assert r.deps == ()
    assert any("pyproject.toml" in w for w in r.parser_warnings)


def test_python_parser_project_id_set(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_TOML)
    (tmp_path / "uv.lock").write_text(_UV_LOCK)
    r = parse_python(tmp_path, project_id="project/myproject")
    assert all(d.project_id == "project/myproject" for d in r.deps)


def test_python_parser_dev_group_scope(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "x"
            dependencies = []
            [project.optional-dependencies]
            dev = ["black>=24.0"]
            """
        )
    )
    (tmp_path / "uv.lock").write_text(
        textwrap.dedent(
            """
            version = 1
            [[package]]
            name = "black"
            version = "24.10.0"
            """
        )
    )
    r = parse_python(tmp_path, project_id="project/x")
    by_purl = {d.purl: d for d in r.deps}
    assert "pkg:pypi/black@24.10.0" in by_purl
    assert by_purl["pkg:pypi/black@24.10.0"].scope == "build"
