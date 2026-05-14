"""Source-context classifier for audit findings (GIM-283-4 Task 3.1/3.1b).

Classifies a file path as: library | example | test | other.
Priority: overrides YAML > example regex > test regex > library regex > other.
All regex matching is case-insensitive (spec §B7 C3/C4).
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Literal

SourceContext = Literal["library", "example", "test", "other"]

_I = re.IGNORECASE

_EXAMPLE_RE = re.compile(
    r"(^|/)(?:[^/]*[-_ ])?(Example|Examples|Sample|Samples|Demo|Demos)(?:[-_ ][^/]*)?(/|$)", _I
)
_TEST_RE = re.compile(r"(^|/)(Tests?|spec)(/|$)", _I)
_TEST_SUFFIX_RE = re.compile(r"Test(s)?\.swift$|_test\.py$|Test\.kt$", _I)
_LIBRARY_RE = re.compile(r"(^|/)(Sources|src|lib|libs)(/|$)", _I)


def classify(
    path: str,
    overrides: dict[str, str] | None = None,
) -> SourceContext:
    """Classify a file path into library | example | test | other.

    Args:
        path: Relative file path (forward- or back-slash separated).
        overrides: Optional dict of fnmatch glob patterns to context values,
            loaded by load_overrides(). Applied before built-in rules.
    """
    p = path.replace("\\", "/")

    if overrides:
        for glob_pat, ctx in overrides.items():
            if fnmatch.fnmatch(p, glob_pat):
                return ctx  # type: ignore[return-value]

    if _EXAMPLE_RE.search(p):
        return "example"
    if _TEST_RE.search(p) or _TEST_SUFFIX_RE.search(p):
        return "test"
    if _LIBRARY_RE.search(p):
        return "library"
    return "other"


def load_overrides(repo_root: str) -> dict[str, str] | None:
    """Load per-project source-context overrides from .gimle/source-context-overrides.yaml.

    Returns None if the file does not exist or is empty/invalid.
    Valid context values: library | example | test | other.
    """
    import yaml  # deferred to avoid hard dep at import time

    overrides_path = Path(repo_root) / ".gimle" / "source-context-overrides.yaml"
    if not overrides_path.exists():
        return None

    try:
        data = yaml.safe_load(overrides_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    valid_contexts: frozenset[str] = frozenset({"library", "example", "test", "other"})
    result = {
        str(k): str(v)
        for k, v in data.items()
        if str(v) in valid_contexts
    }
    return result or None
