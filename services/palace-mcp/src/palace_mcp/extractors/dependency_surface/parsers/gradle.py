"""Gradle dependency parser.

Reads gradle/libs.versions.toml (version catalog) + per-module build.gradle.kts.
Resolves aliases to Maven coordinates and maps Gradle scopes to canonical names.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        import tomli as tomllib  # type: ignore[import,no-redef]

from palace_mcp.extractors.dependency_surface.models import (
    ManifestParseResult,
    ParsedDep,
)
from palace_mcp.extractors.dependency_surface.purl import build_purl

# Gradle scope → canonical scope
_SCOPE_MAP = {
    "implementation": "compile",
    "api": "compile",
    "compileOnly": "compile",
    "kapt": "build",
    "annotationProcessor": "build",
    "testImplementation": "test",
    "testCompileOnly": "test",
    "runtimeOnly": "runtime",
    "testRuntimeOnly": "test",
}

# Match: implementation(libs.some.alias)
_DEP_PATTERN = re.compile(
    r"(?P<scope>implementation|api|kapt|annotationProcessor|testImplementation"
    r"|compileOnly|testCompileOnly|runtimeOnly|testRuntimeOnly)"
    r"\s*\(\s*libs\.(?P<alias>[\w.\-]+)\s*\)"
)


def _normalize_alias(alias: str) -> str:
    """Normalize a Gradle alias to canonical form (lowercase, hyphens → dots)."""
    return alias.replace("-", ".").lower()


def _build_alias_map(catalog: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    """Build {normalized_alias: (group, name, version)} from libs.versions.toml."""
    versions: dict[str, Any] = catalog.get("versions", {})
    libraries: dict[str, Any] = catalog.get("libraries", {})

    alias_map: dict[str, tuple[str, str, str]] = {}
    for raw_alias, entry in libraries.items():
        if not isinstance(entry, dict):
            continue
        group = entry.get("group", "")
        name = entry.get("name", "")
        version_ref = entry.get("version", {})
        if isinstance(version_ref, dict):
            ref = version_ref.get("ref", "")
            version = versions.get(ref, "")
        elif isinstance(version_ref, str):
            version = version_ref
        else:
            version = ""

        if not (group and name and version):
            continue

        # Register under both the original alias and dot/hyphen normalized forms
        for key in _alias_variants(raw_alias):
            alias_map[key] = (group, name, version)

    return alias_map


def _alias_variants(raw: str) -> list[str]:
    """Generate all normalized forms Gradle uses for a catalog alias."""
    base = raw.lower()
    # Canonical: hyphens and underscores → dots
    dot_form = base.replace("-", ".").replace("_", ".")
    hyphen_form = base.replace(".", "-").replace("_", "-")
    return list({base, dot_form, hyphen_form})


def parse_gradle(repo_path: Path, *, project_id: str) -> ManifestParseResult:
    """Parse Gradle version catalog + build.gradle.kts files."""
    warnings: list[str] = []
    deps: list[ParsedDep] = []

    catalog_path = repo_path / "gradle" / "libs.versions.toml"
    if not catalog_path.is_file():
        return ManifestParseResult(
            ecosystem="maven",
            deps=(),
            parser_warnings=(
                "libs.versions.toml not found — Gradle dep parsing skipped",
            ),
        )

    catalog = tomllib.loads(catalog_path.read_text(encoding="utf-8"))
    alias_map = _build_alias_map(catalog)

    # Find all build.gradle.kts files
    kts_files = list(repo_path.rglob("build.gradle.kts"))

    for kts_path in kts_files:
        text = kts_path.read_text(encoding="utf-8")
        rel_path = str(kts_path.relative_to(repo_path))

        for m in _DEP_PATTERN.finditer(text):
            raw_alias = m.group("alias")
            gradle_scope = m.group("scope")
            scope = _SCOPE_MAP.get(gradle_scope, "compile")

            norm = _normalize_alias(raw_alias)
            if norm not in alias_map:
                warnings.append(
                    f"unresolved alias '{raw_alias}' in {rel_path} — skipping"
                )
                continue

            group, name, version = alias_map[norm]
            purl = build_purl(
                ecosystem="maven",
                name=f"{group}:{name}",
                version=version,
            )
            deps.append(
                ParsedDep(
                    project_id=project_id,
                    purl=purl,
                    ecosystem="maven",
                    declared_version_constraint=version,
                    resolved_version=version,
                    scope=scope,
                    declared_in=rel_path,
                )
            )

    return ManifestParseResult(
        ecosystem="maven",
        deps=tuple(deps),
        parser_warnings=tuple(warnings),
    )
