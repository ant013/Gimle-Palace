"""Gradle/Kotlin DSL parser for arch_layer — recovers modules and intra-project deps.

Parses:
  - settings.gradle.kts: include(":module") declarations
  - per-module build.gradle.kts: implementation/api/compileOnly/testImplementation(project(":x"))

External Maven dependencies are owned by dependency_surface; this parser
only handles intra-project project(:x) deps.
Does not invoke Gradle or any network.
"""

from __future__ import annotations

import re
from pathlib import Path

from palace_mcp.extractors.arch_layer.models import (
    Module,
    ModuleEdge,
    ParseResult,
    ParserWarning,
)

# Matches include(":module") or include(":sub:module")
_INCLUDE_RE = re.compile(r'include\s*\(\s*"(?P<path>:[^"]+)"\s*\)')

# Matches implementation(project(":x")), api(project(":x")), etc.
_PROJECT_DEP_RE = re.compile(
    r"(?P<scope>implementation|api|compileOnly|testImplementation|runtimeOnly)"
    r'\s*\(\s*project\s*\(\s*"(?P<path>:[^"]+)"\s*\)',
    re.DOTALL,
)

_SETTINGS_FILENAMES = {"settings.gradle.kts", "settings.gradle"}
_BUILD_FILENAMES = {"build.gradle.kts", "build.gradle"}


def _slug_from_gradle_path(gradle_path: str) -> str:
    """Convert ':core' or ':sub:core' to a canonical slug."""
    return gradle_path.lstrip(":")


def _module_dir_from_path(repo_path: Path, gradle_path: str) -> Path:
    """Derive the module directory path from a Gradle include path."""
    # ':core' -> repo_root/core; ':feature:login' -> repo_root/feature/login
    parts = gradle_path.lstrip(":").split(":")
    return repo_path.joinpath(*parts)


def parse_gradle(repo_path: Path, *, project_id: str, run_id: str) -> ParseResult:
    """Parse settings.gradle.kts and per-module build files."""
    # Find settings file
    settings_file: Path | None = None
    for name in _SETTINGS_FILENAMES:
        candidate = repo_path / name
        if candidate.is_file():
            settings_file = candidate
            break

    if settings_file is None:
        return ParseResult(
            modules=(),
            edges=(),
            warnings=(ParserWarning(message="settings.gradle.kts not found"),),
        )

    settings_rel = str(settings_file.relative_to(repo_path))
    settings_text = settings_file.read_text(encoding="utf-8")
    include_paths = [m.group("path") for m in _INCLUDE_RE.finditer(settings_text)]

    if not include_paths:
        return ParseResult(
            modules=(),
            edges=(),
            warnings=(
                ParserWarning(
                    message=f"gradle: no include() declarations found in {settings_rel}"
                ),
            ),
        )

    slug_set = {_slug_from_gradle_path(p) for p in include_paths}
    modules: list[Module] = []
    edges: list[ModuleEdge] = []
    warnings: list[ParserWarning] = []

    for gradle_path in include_paths:
        slug = _slug_from_gradle_path(gradle_path)
        module_dir = _module_dir_from_path(repo_path, gradle_path)
        build_file: Path | None = None
        for name in _BUILD_FILENAMES:
            candidate = module_dir / name
            if candidate.is_file():
                build_file = candidate
                break

        manifest_path = (
            str(build_file.relative_to(repo_path)) if build_file else settings_rel
        )
        modules.append(
            Module(
                project_id=project_id,
                slug=slug,
                name=slug,
                kind="gradle_module",
                manifest_path=manifest_path,
                source_root=f"{'/'.join(gradle_path.lstrip(':').split(':'))}/src/main",
                run_id=run_id,
            )
        )

        if build_file is None:
            warnings.append(
                ParserWarning(
                    message=f"gradle: no build file found for module {gradle_path!r}"
                )
            )
            continue

        build_text = build_file.read_text(encoding="utf-8")
        build_rel = str(build_file.relative_to(repo_path))
        for dm in _PROJECT_DEP_RE.finditer(build_text):
            scope = dm.group("scope")
            dep_path = dm.group("path")
            dep_slug = _slug_from_gradle_path(dep_path)
            if dep_slug not in slug_set:
                warnings.append(
                    ParserWarning(
                        message=(
                            f"gradle: module {gradle_path!r} depends on {dep_path!r} "
                            "which is not in the include list — skipped"
                        )
                    )
                )
                continue
            edges.append(
                ModuleEdge(
                    src_slug=slug,
                    dst_slug=dep_slug,
                    scope=scope,
                    declared_in=build_rel,
                    evidence_kind="manifest",
                    run_id=run_id,
                )
            )

    return ParseResult(
        modules=tuple(modules),
        edges=tuple(edges),
        warnings=tuple(warnings),
    )
