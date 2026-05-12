"""SwiftPM parser for arch_layer — recovers targets and internal deps.

Conservative text scanning: if a dependency cannot be mapped to an
internal target it is ignored and recorded in parser warnings.
Does not invoke Swift, the Swift compiler, or any network.
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

# Matches .target(name: "Foo", ...) and .testTarget(name: "Foo", ...)
_TARGET_RE = re.compile(
    r"\.\s*(?:test)?[Tt]arget\s*\(\s*name\s*:\s*\"(?P<name>[^\"]+)\"",
    re.DOTALL,
)

# Matches .target(name: "Dep") inside a dependencies: [...] block
_DEP_ITEM_RE = re.compile(r'"(?P<name>[A-Za-z0-9_\-\.]+)"')

# Find the dependencies: [...] block for a target block.
# We look for "dependencies:" then capture the bracketed list.
_DEPS_BLOCK_RE = re.compile(
    r"dependencies\s*:\s*\[(?P<inner>[^\]]*)\]",
    re.DOTALL,
)

# Matches: .target(name: "Name"), .product(name: "Name", ...) inside deps block
_DEP_TARGET_RE = re.compile(r'\.target\s*\(\s*name\s*:\s*"(?P<name>[^"]+)"')
_DEP_PRODUCT_RE = re.compile(r'\.product\s*\(\s*name\s*:\s*"(?P<name>[^"]+)"')


def parse_spm(repo_path: Path, *, project_id: str, run_id: str) -> ParseResult:
    """Parse Package.swift and return modules + internal dependency edges."""
    package_swift = repo_path / "Package.swift"
    if not package_swift.is_file():
        return ParseResult(
            modules=(),
            edges=(),
            warnings=(ParserWarning(message="Package.swift not found"),),
        )

    manifest_path = "Package.swift"
    text = package_swift.read_text(encoding="utf-8")

    target_names = _extract_target_names(text)
    target_set = set(target_names)

    modules = tuple(
        Module(
            project_id=project_id,
            slug=name,
            name=name,
            kind="swift_target",
            manifest_path=manifest_path,
            source_root=_infer_source_root(name),
            run_id=run_id,
        )
        for name in target_names
    )

    edges, warnings = _extract_edges(text, target_set, manifest_path, run_id)

    return ParseResult(modules=modules, edges=tuple(edges), warnings=tuple(warnings))


def _extract_target_names(text: str) -> list[str]:
    seen: dict[str, int] = {}  # name -> first occurrence position
    for m in _TARGET_RE.finditer(text):
        name = m.group("name")
        if name not in seen:
            seen[name] = m.start()
    return sorted(seen, key=lambda n: seen[n])


def _extract_edges(
    text: str,
    target_set: set[str],
    manifest_path: str,
    run_id: str,
) -> tuple[list[ModuleEdge], list[ParserWarning]]:
    """Extract target-level dependency edges from Package.swift text.

    Strategy: find each .target(...) or .testTarget(...) block, then locate
    its dependencies: [...] sub-block and extract named deps.
    Deps that are .product(...) or cannot be matched to an internal target
    are skipped with a warning (external or ambiguous).
    """
    edges: list[ModuleEdge] = []
    warnings: list[ParserWarning] = []

    # Split the manifest into per-target segments heuristically:
    # we look for each occurrence of .target(name: "X") and take the
    # text from there until the next .target( occurrence.
    target_starts = list(_TARGET_RE.finditer(text))
    for i, m in enumerate(target_starts):
        src_name = m.group("name")
        segment_start = m.start()
        segment_end = (
            target_starts[i + 1].start() if i + 1 < len(target_starts) else len(text)
        )
        segment = text[segment_start:segment_end]

        deps_block = _DEPS_BLOCK_RE.search(segment)
        if not deps_block:
            continue

        inner = deps_block.group("inner")
        # Collect all candidate dep names from the deps block
        seen_candidates: dict[str, None] = {}  # ordered dedup

        for dm in _DEP_TARGET_RE.finditer(inner):
            seen_candidates[dm.group("name")] = None

        # Bare string literals like "TargetName" (common in older Package.swift)
        for dm in _DEP_ITEM_RE.finditer(inner):
            seen_candidates.setdefault(dm.group("name"), None)

        for dep_name in seen_candidates:
            if dep_name not in target_set:
                warnings.append(
                    ParserWarning(
                        message=(
                            f"spm: target {src_name!r} depends on {dep_name!r} "
                            "which is not an internal target — skipped"
                        )
                    )
                )
                continue
            edges.append(
                ModuleEdge(
                    src_slug=src_name,
                    dst_slug=dep_name,
                    scope="target_dep",
                    declared_in=manifest_path,
                    evidence_kind="manifest",
                    run_id=run_id,
                )
            )

    return edges, warnings


def _infer_source_root(target_name: str) -> str:
    return f"Sources/{target_name}"
