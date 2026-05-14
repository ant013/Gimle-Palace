"""Language profile → audit extractor mapping (GIM-283-1 Task 2.0/2.1).

A LanguageProfile declares which extractors are expected to run for a given
project type. The audit pipeline uses this to distinguish:
  - NOT_APPLICABLE (extractor not expected for this profile)
  - NOT_ATTEMPTED  (expected but never run)
  - RUN_FAILED     (run but failed)
  - FETCH_FAILED   (run succeeded but fetcher errored)
  - OK             (run succeeded + data fetched)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

_GET_LANGUAGE_PROFILE = (
    "MATCH (p:Project {slug: $slug}) RETURN p.language_profile AS language_profile"
)

# Manifest file → profile name (first match wins, order matters)
_MANIFEST_RULES: tuple[tuple[str, str], ...] = (
    ("Package.swift", "swift_kit"),
    ("settings.gradle.kts", "android_kit"),
    ("build.gradle.kts", "android_kit"),
    ("pyproject.toml", "python_service"),
)


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    audit_extractors: frozenset[str]


PROFILES: dict[str, LanguageProfile] = {
    "swift_kit": LanguageProfile(
        "swift_kit",
        frozenset(
            {
                "arch_layer",
                "code_ownership",
                "coding_convention",
                "crypto_domain_model",
                "cross_module_contract",
                "cross_repo_version_skew",
                "dead_symbol_binary_surface",
                "dependency_surface",
                "error_handling_policy",
                "hot_path_profiler",
                "hotspot",
                "localization_accessibility",
                "public_api_surface",
                "reactive_dependency_tracer",
                "testability_di",
            }
        ),
    ),
    "python_service": LanguageProfile(
        "python_service",
        frozenset(
            {
                "code_ownership",
                "dependency_surface",
                "hotspot",
            }
        ),
    ),
    "android_kit": LanguageProfile(
        "android_kit",
        frozenset(
            {
                "arch_layer",
                "code_ownership",
                "dependency_surface",
                "hotspot",
            }
        ),
    ),
}


async def resolve_profile(
    driver: Any,
    project_slug: str,
    repo_path: Path | None = None,
) -> LanguageProfile:
    """Resolve a LanguageProfile for the given project.

    Resolution order:
    1. Explicit :Project.language_profile from Neo4j
    2. Manifest file inference (Package.swift → swift_kit, etc.)
    3. ValueError("unknown_language_profile: ...")
    """
    # Step 1: explicit attribute in Neo4j
    async with driver.session() as session:
        result = await session.run(_GET_LANGUAGE_PROFILE, slug=project_slug)
        row = await result.single()

    if row is not None:
        lp = row["language_profile"]
        if lp is not None:
            if lp not in PROFILES:
                raise ValueError(
                    f"unknown_language_profile: {lp!r} is not a known profile name"
                )
            return PROFILES[lp]

    # Step 2: manifest file inference
    path = repo_path if repo_path is not None else Path(f"/repos/{project_slug}")
    for manifest_file, profile_name in _MANIFEST_RULES:
        if (path / manifest_file).exists():
            return PROFILES[profile_name]

    raise ValueError(
        f"unknown_language_profile: no language_profile on :Project{{slug: {project_slug!r}}} "
        f"and no recognized manifest in {path}"
    )
