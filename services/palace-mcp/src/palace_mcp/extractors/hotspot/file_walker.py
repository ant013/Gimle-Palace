from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

_STOP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".gradle",
        ".kotlin",
        ".idea",
        "node_modules",
        "build",
        "dist",
        "target",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".tantivy",
        "__MACOSX",
    }
)

_FIXTURE_STOP_PARTS: tuple[str, ...] = ("tests", "extractors", "fixtures")

_LIZARD_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".java",
        ".kt",
        ".kts",
        ".swift",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".sol",
        ".c",
        ".cpp",
        ".cc",
        ".h",
        ".hpp",
        ".m",
        ".mm",
        ".rb",
        ".php",
        ".scala",
    }
)


def _has_subseq(parts: tuple[str, ...], subseq: tuple[str, ...]) -> bool:
    if not subseq:
        return True
    n = len(subseq)
    return any(parts[i : i + n] == subseq for i in range(len(parts) - n + 1))


def _walk(root: Path) -> Iterator[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in _LIZARD_EXTENSIONS:
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _STOP_DIRS for part in rel_parts):
            continue
        if _has_subseq(rel_parts, _FIXTURE_STOP_PARTS):
            continue
        yield p
