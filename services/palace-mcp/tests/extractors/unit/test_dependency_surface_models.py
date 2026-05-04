"""Unit tests for dependency_surface Pydantic v2 models — Task 1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from palace_mcp.extractors.dependency_surface.models import (
    ManifestParseResult,
    ParsedDep,
)

_VALID_DEP = dict(
    project_id="project/x",
    purl="pkg:pypi/neo4j@5.28.2",
    ecosystem="pypi",
    declared_version_constraint=">=5.0",
    resolved_version="5.28.2",
    scope="compile",
    declared_in="pyproject.toml",
)


def test_parsed_dep_purl_must_start_with_pkg() -> None:
    with pytest.raises(ValidationError):
        ParsedDep(**{**_VALID_DEP, "purl": "github/foo/bar@1.0"})


def test_parsed_dep_resolved_version_empty_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedDep(**{**_VALID_DEP, "resolved_version": ""})


def test_parsed_dep_resolved_version_unresolved_sentinel_accepted() -> None:
    dep = ParsedDep(**{**_VALID_DEP, "resolved_version": "unresolved"})
    assert dep.resolved_version == "unresolved"


def test_parsed_dep_frozen() -> None:
    dep = ParsedDep(**_VALID_DEP)
    with pytest.raises(ValidationError):
        dep.purl = "pkg:other/x@2.0"  # type: ignore[misc]


def test_manifest_parse_result_carries_warnings() -> None:
    r = ManifestParseResult(ecosystem="pypi", deps=(), parser_warnings=("missing pin",))
    assert r.parser_warnings == ("missing pin",)


def test_parsed_dep_valid_construction() -> None:
    dep = ParsedDep(**_VALID_DEP)
    assert dep.purl == "pkg:pypi/neo4j@5.28.2"
    assert dep.ecosystem == "pypi"
    assert dep.scope == "compile"


def test_parsed_dep_scope_test() -> None:
    dep = ParsedDep(**{**_VALID_DEP, "scope": "test"})
    assert dep.scope == "test"


def test_manifest_parse_result_empty_warnings() -> None:
    r = ManifestParseResult(ecosystem="pypi", deps=(), parser_warnings=())
    assert r.parser_warnings == ()


def test_manifest_parse_result_multiple_deps() -> None:
    dep1 = ParsedDep(**_VALID_DEP)
    dep2 = ParsedDep(**{**_VALID_DEP, "purl": "pkg:pypi/httpx@0.27.0"})
    r = ManifestParseResult(ecosystem="pypi", deps=(dep1, dep2), parser_warnings=())
    assert len(r.deps) == 2
