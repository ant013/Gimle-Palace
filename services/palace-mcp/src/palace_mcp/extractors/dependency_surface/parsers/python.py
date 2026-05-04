"""Python dependency parser (pyproject.toml PEP 621 + uv.lock).

Reads [project.dependencies] and [project.optional-dependencies], resolves
versions from uv.lock [[package]] entries.
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        import tomli as tomllib  # type: ignore[import,no-redef]

from packaging.requirements import Requirement

from palace_mcp.extractors.dependency_surface.models import (
    ManifestParseResult,
    ParsedDep,
)
from palace_mcp.extractors.dependency_surface.purl import build_purl

# optional-dependency group → canonical scope
_OPT_DEP_SCOPE: dict[str, str] = {
    "test": "test",
    "tests": "test",
    "testing": "test",
    "dev": "build",
    "development": "build",
    "build": "build",
    "lint": "build",
    "docs": "build",
}


def _group_scope(group_name: str) -> str:
    return _OPT_DEP_SCOPE.get(group_name.lower(), "build")


def parse_python(repo_path: Path, *, project_id: str) -> ManifestParseResult:
    """Parse pyproject.toml + uv.lock for Python deps."""
    warnings: list[str] = []
    deps: list[ParsedDep] = []

    pyproject_path = repo_path / "pyproject.toml"
    if not pyproject_path.is_file():
        return ManifestParseResult(
            ecosystem="pypi",
            deps=(),
            parser_warnings=("pyproject.toml not found",),
        )

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = pyproject.get("project", {})

    # Build lock map: {canonical_name: version}
    lock_map: dict[str, str] = {}
    lock_path = repo_path / "uv.lock"
    if lock_path.is_file():
        lock_data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
        for pkg in lock_data.get("package", []):
            pkg_name = pkg.get("name", "").lower().replace("-", "-")
            pkg_ver = pkg.get("version", "")
            if pkg_name and pkg_ver:
                lock_map[pkg_name] = pkg_ver
    else:
        warnings.append("uv.lock not found — resolved_version set to 'unresolved'")

    def _make_dep(req_str: str, scope: str) -> ParsedDep | None:
        try:
            req = Requirement(req_str)
        except Exception:
            warnings.append(f"failed to parse requirement {req_str!r}")
            return None
        name = req.name
        canonical = name.lower().replace("_", "-")
        resolved = lock_map.get(canonical, "unresolved")
        if resolved == "unresolved" and lock_map:
            warnings.append(
                f"'{name}' not found in uv.lock — resolved_version='unresolved'"
            )
        purl = build_purl(ecosystem="pypi", name=name, version=resolved)
        return ParsedDep(
            project_id=project_id,
            purl=purl,
            ecosystem="pypi",
            declared_version_constraint=str(req.specifier),
            resolved_version=resolved,
            scope=scope,
            declared_in="pyproject.toml",
        )

    for req_str in project.get("dependencies", []):
        dep = _make_dep(req_str, "compile")
        if dep:
            deps.append(dep)

    for group, reqs in project.get("optional-dependencies", {}).items():
        scope = _group_scope(group)
        for req_str in reqs:
            dep = _make_dep(req_str, scope)
            if dep:
                deps.append(dep)

    return ManifestParseResult(
        ecosystem="pypi",
        deps=tuple(deps),
        parser_warnings=tuple(warnings),
    )
