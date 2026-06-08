"""Source scope classification for :Symbol nodes.

GIM-839 D0 contract: every :Symbol must carry a persisted ``source_scope``.
Query-time classification is a legacy fallback only when existing nodes lack
the field.

Classification precedence (spec §7.4) — first match wins after normalizing
paths relative to the project root. Within a category, longest matching root
wins.

1. derived  — DerivedData and .palace-scip-derived-data paths
2. generated — recipe generated_roots and generated-file heuristics
3. sdk — Apple SDK / system framework paths
4. workspace_package — recipe workspace_package_roots
5. dependency — recipe dependency_roots
6. project — recipe source_roots
7. dependency (fallback) — unknown external package paths
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from palace_mcp.smoke.recipe import Recipe


class SourceScope(str, Enum):
    PROJECT = "project"
    WORKSPACE_PACKAGE = "workspace_package"
    DEPENDENCY = "dependency"
    GENERATED = "generated"
    DERIVED = "derived"
    SDK = "sdk"


SCOPE_PRECEDENCE: list[SourceScope] = [
    SourceScope.PROJECT,
    SourceScope.WORKSPACE_PACKAGE,
    SourceScope.DEPENDENCY,
    SourceScope.GENERATED,
    SourceScope.DERIVED,
    SourceScope.SDK,
]

_BUILTIN_DERIVED_ROOTS = ("DerivedData", ".palace-scip-derived-data")

# Vendor-package path markers used by the no-recipe heuristic.
# These are directory names that only appear under vendor/dependency roots in
# iOS/macOS Xcode projects (SPM, CocoaPods, Carthage, local SPM build cache).
_BUILTIN_SWIFT_DEPENDENCY_MARKERS = (
    "SourcePackages/",
    "Pods/",
    "Carthage/",
    ".build/",
    ".swiftpm/",
)

# Generated-source markers used by the no-recipe heuristic.
# DerivedSources is Xcode's directory for auto-generated Swift/ObjC sources
# (e.g. interface stubs, generated enums from asset catalogs).
_BUILTIN_GENERATED_MARKERS = ("DerivedSources/",)

_SDK_PATH_PREFIXES = (
    "Platforms/",
    "usr/lib/",
    "usr/include/",
    "System/Library/",
    "Developer/Platforms/",
    "Toolchains/",
)


class ClassificationResult:
    """Result of classify_source_scope with optional warning."""

    __slots__ = ("scope", "warning")

    def __init__(self, scope: SourceScope, warning: str | None = None) -> None:
        self.scope = scope
        self.warning = warning


def classify_source_scope(
    file_path: str,
    *,
    recipe: Recipe | None = None,
) -> ClassificationResult:
    """Classify a symbol's source scope from its file path and recipe roots.

    Returns ClassificationResult with the scope and an optional warning
    when classification fell back to heuristics.
    """
    normalized = _normalize_path(file_path)

    if recipe is not None:
        derived_roots = list(recipe.derived_roots) + list(_BUILTIN_DERIVED_ROOTS)
        if _matches_any_root(normalized, derived_roots):
            return ClassificationResult(SourceScope.DERIVED)

        if _matches_any_root(normalized, recipe.generated_roots):
            return ClassificationResult(SourceScope.GENERATED)

        if _matches_sdk_path(normalized):
            return ClassificationResult(SourceScope.SDK)

        if _matches_any_root(normalized, recipe.workspace_package_roots):
            return ClassificationResult(SourceScope.WORKSPACE_PACKAGE)

        if _matches_any_root(normalized, recipe.dependency_roots):
            return ClassificationResult(SourceScope.DEPENDENCY)

        if _matches_any_root(normalized, recipe.source_roots):
            return ClassificationResult(SourceScope.PROJECT)

        return ClassificationResult(
            SourceScope.DEPENDENCY,
            warning=f"unclassifiable path '{file_path}' — treated as dependency",
        )

    if _matches_sdk_path(normalized):
        return ClassificationResult(SourceScope.SDK)

    for root in _BUILTIN_DERIVED_ROOTS:
        if normalized.startswith(root + "/") or normalized == root:
            return ClassificationResult(SourceScope.DERIVED)

    for marker in _BUILTIN_SWIFT_DEPENDENCY_MARKERS:
        if marker in file_path:
            return ClassificationResult(SourceScope.DEPENDENCY)

    for marker in _BUILTIN_GENERATED_MARKERS:
        if marker in file_path:
            return ClassificationResult(SourceScope.GENERATED)

    return ClassificationResult(
        SourceScope.PROJECT,
        warning=(
            f"no recipe available to classify '{file_path}' — "
            "treated as project (no-recipe heuristic)"
        ),
    )


def _normalize_path(file_path: str) -> str:
    stripped = file_path.lstrip("./")
    while "//" in stripped:
        stripped = stripped.replace("//", "/")
    return stripped


def _matches_any_root(normalized_path: str, roots: list[str] | tuple[str, ...]) -> bool:
    for root in roots:
        nr = _normalize_path(root)
        if not nr:
            continue
        if normalized_path.startswith(nr + "/") or normalized_path == nr:
            return True
    return False


def _matches_sdk_path(normalized_path: str) -> bool:
    for prefix in _SDK_PATH_PREFIXES:
        if normalized_path.startswith(prefix):
            return True
    return False
