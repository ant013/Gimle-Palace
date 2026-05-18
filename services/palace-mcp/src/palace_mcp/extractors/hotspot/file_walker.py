from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from palace_mcp.extractors.foundation.walk import walk_repo

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
    for p in walk_repo(root, suffixes=_LIZARD_EXTENSIONS):
        rel_parts = p.relative_to(root).parts
        if _has_subseq(rel_parts, _FIXTURE_STOP_PARTS):
            continue
        yield p
