"""Allowlist loader for loc-a11y extractor (LA-D4).

Reads <repo_root>/.gimle/loc-allowlist.txt (one literal per line).
Strings in the allowlist are skipped during hard-coded detection.
"""

from __future__ import annotations

from pathlib import Path

_ALLOWLIST_PATH = Path(".gimle") / "loc-allowlist.txt"


def load_allowlist(repo_root: Path) -> frozenset[str]:
    """Load allowlist from <repo_root>/.gimle/loc-allowlist.txt.

    Returns empty frozenset when the file does not exist.
    """
    path = repo_root / _ALLOWLIST_PATH
    if not path.exists():
        return frozenset()
    lines = path.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip() for line in lines if line.strip())


def is_allowlisted(literal: str, allowlist: frozenset[str]) -> bool:
    """Return True if the literal appears in the allowlist."""
    return literal in allowlist
