"""SPM (Swift Package Manager) dependency parser.

Reads Package.swift (declared deps) and Package.resolved (pinned versions).
Supports Package.resolved v2 (object.pins) and v3 (top-level pins).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from palace_mcp.extractors.dependency_surface.models import ManifestParseResult, ParsedDep
from palace_mcp.extractors.dependency_surface.purl import spm_purl_from_url

# Matches .package(url: "...", from|exact|branch|revision: "...")
_PKG_PATTERN = re.compile(
    r'\.package\s*\(\s*url:\s*"(?P<url>[^"]+)"\s*,'
    r'(?:[^)]*?(?:from|exact|branch|revision)\s*:\s*"(?P<ver>[^"]+)")?',
    re.DOTALL,
)


def _normalize_url(url: str) -> str:
    """Normalize for matching: lowercase, strip .git suffix."""
    return url.rstrip("/").lower().removesuffix(".git")


def parse_spm(repo_path: Path, *, project_id: str) -> ManifestParseResult:
    """Parse SPM manifests in repo_path. Returns ManifestParseResult."""
    warnings: list[str] = []
    deps: list[ParsedDep] = []

    package_swift = repo_path / "Package.swift"
    if not package_swift.is_file():
        return ManifestParseResult(
            ecosystem="github",
            deps=(),
            parser_warnings=("Package.swift not found",),
        )

    text = package_swift.read_text(encoding="utf-8")
    declared: list[str] = [m.group("url") for m in _PKG_PATTERN.finditer(text)]

    # Build resolution map from Package.resolved
    resolved_versions: dict[str, str] = {}
    package_resolved = repo_path / "Package.resolved"

    if package_resolved.is_file():
        data = json.loads(package_resolved.read_text(encoding="utf-8"))
        # v3: top-level "pins"; v2: "object" -> "pins"
        if "pins" in data:
            pins = data["pins"]
        elif "object" in data and "pins" in data["object"]:
            pins = data["object"]["pins"]
        else:
            pins = []

        for pin in pins:
            location = pin.get("location") or pin.get("repositoryURL") or ""
            state = pin.get("state", {})
            version = state.get("version")
            if version:
                resolved_versions[_normalize_url(location)] = version
            else:
                # Branch/revision pin — use short revision as marker, but keep unresolved
                resolved_versions[_normalize_url(location)] = "unresolved"
    else:
        warnings.append("Package.resolved missing — resolved_version set to 'unresolved'")

    for url in declared:
        norm = _normalize_url(url)
        resolved = resolved_versions.get(norm, "unresolved")
        purl = spm_purl_from_url(url, resolved)
        deps.append(
            ParsedDep(
                project_id=project_id,
                purl=purl,
                ecosystem="github",
                declared_version_constraint="",
                resolved_version=resolved,
                scope="compile",
                declared_in="Package.swift",
            )
        )

    return ManifestParseResult(
        ecosystem="github",
        deps=tuple(deps),
        parser_warnings=tuple(warnings),
    )
