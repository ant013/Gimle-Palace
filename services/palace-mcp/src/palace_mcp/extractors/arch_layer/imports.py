"""Lightweight import scanner for arch_layer extractor (GIM-243).

Swift: `import ModuleName`
Kotlin/Java: `import package.name.Class`

Maps import names to known module slugs only when the mapping is
unambiguous. Ambiguous imports produce warnings, not violations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SWIFT_IMPORT_RE = re.compile(r"^import\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)$", re.MULTILINE)
_KOTLIN_IMPORT_RE = re.compile(r"^import\s+(?P<pkg>[A-Za-z_][A-Za-z0-9_.]+)", re.MULTILINE)

_STOP_DIRS = frozenset(
    {
        ".git",
        ".build",
        "build",
        "DerivedData",
        "SourcePackages",
        "Pods",
        ".venv",
        "__pycache__",
        "node_modules",
    }
)
_SWIFT_SUFFIXES = frozenset({".swift"})
_KOTLIN_SUFFIXES = frozenset({".kt", ".kts", ".java"})


@dataclass(frozen=True)
class ImportFact:
    src_module: str
    dst_module: str  # resolved module slug
    file: str
    line: int
    raw_import: str


@dataclass(frozen=True)
class ImportWarning:
    message: str


@dataclass(frozen=True)
class ImportScanResult:
    facts: tuple[ImportFact, ...]
    warnings: tuple[ImportWarning, ...]


def scan_imports(
    repo_path: Path,
    *,
    swift_modules: frozenset[str],  # set of known swift_target slugs
    gradle_modules: frozenset[str],  # set of known gradle_module slugs
    module_source_roots: dict[str, str],  # slug -> repo-relative source root
) -> ImportScanResult:
    """Walk source files and collect unambiguous import facts."""
    all_modules = swift_modules | gradle_modules
    if not all_modules:
        return ImportScanResult(facts=(), warnings=())

    facts: list[ImportFact] = []
    warnings: list[ImportWarning] = []

    for path in _iter_source_files(repo_path):
        src_module = _resolve_source_module(path, repo_path, module_source_roots)
        if src_module is None:
            continue

        rel_path = str(path.relative_to(repo_path))
        text = path.read_text(encoding="utf-8", errors="replace")
        suffix = path.suffix.lower()

        if suffix in _SWIFT_SUFFIXES:
            _scan_swift(
                text=text,
                rel_path=rel_path,
                src_module=src_module,
                known_modules=all_modules,
                facts=facts,
                warnings=warnings,
            )
        elif suffix in _KOTLIN_SUFFIXES:
            _scan_kotlin(
                text=text,
                rel_path=rel_path,
                src_module=src_module,
                known_modules=all_modules,
                facts=facts,
                warnings=warnings,
            )

    return ImportScanResult(facts=tuple(facts), warnings=tuple(warnings))


def _scan_swift(
    *,
    text: str,
    rel_path: str,
    src_module: str,
    known_modules: frozenset[str],
    facts: list[ImportFact],
    warnings: list[ImportWarning],
) -> None:
    for m in _SWIFT_IMPORT_RE.finditer(text):
        name = m.group("name")
        if name not in known_modules:
            continue  # external or stdlib — skip
        if name == src_module:
            continue  # self-import
        line = text.count("\n", 0, m.start()) + 1
        facts.append(
            ImportFact(
                src_module=src_module,
                dst_module=name,
                file=rel_path,
                line=line,
                raw_import=f"import {name}",
            )
        )


def _scan_kotlin(
    *,
    text: str,
    rel_path: str,
    src_module: str,
    known_modules: frozenset[str],
    facts: list[ImportFact],
    warnings: list[ImportWarning],
) -> None:
    for m in _KOTLIN_IMPORT_RE.finditer(text):
        pkg = m.group("pkg")
        # Kotlin imports are fully qualified; try to match against module slugs
        # by checking if the import starts with a known module name (case-insensitive).
        matches = [
            mod for mod in known_modules
            if pkg.lower().startswith(mod.lower().replace("-", ""))
        ]
        if len(matches) == 1:
            dst = matches[0]
            if dst == src_module:
                continue
            line = text.count("\n", 0, m.start()) + 1
            facts.append(
                ImportFact(
                    src_module=src_module,
                    dst_module=dst,
                    file=rel_path,
                    line=line,
                    raw_import=f"import {pkg}",
                )
            )
        elif len(matches) > 1:
            warnings.append(
                ImportWarning(
                    message=(
                        f"imports: ambiguous import {pkg!r} in {rel_path} "
                        f"matches modules {sorted(matches)} — skipped"
                    )
                )
            )


def _iter_source_files(repo_path: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (_SWIFT_SUFFIXES | _KOTLIN_SUFFIXES):
            continue
        rel = path.relative_to(repo_path)
        if any(part in _STOP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return sorted(files)


def _resolve_source_module(
    file_path: Path,
    repo_path: Path,
    module_source_roots: dict[str, str],  # slug -> repo-relative source root
) -> str | None:
    """Find the module whose source_root is a prefix of file_path."""
    rel = str(file_path.relative_to(repo_path))
    best: str | None = None
    best_len = 0
    for slug, source_root in module_source_roots.items():
        if source_root and rel.startswith(source_root.rstrip("/") + "/"):
            if len(source_root) > best_len:
                best = slug
                best_len = len(source_root)
    return best
