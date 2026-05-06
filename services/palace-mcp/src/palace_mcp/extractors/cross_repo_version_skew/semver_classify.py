"""Pairwise semver classification — best-effort with `packaging.version`.

Per spec rev2 R5: PEP 440 parsing is lenient enough for most UW Swift /
Gradle / Python deps. Non-parseable schemes (calver, git-sha, custom)
yield 'unknown'. A group's final severity is the max-rank-across-pairs.
"""

from __future__ import annotations

from itertools import combinations
from typing import Literal

from packaging.version import InvalidVersion, Version

Severity = Literal["major", "minor", "patch", "unknown"]
_RANK: dict[Severity, int] = {"major": 3, "minor": 2, "patch": 1, "unknown": 0}


def severity_rank(severity: Severity) -> int:
    return _RANK[severity]


def classify(v_a: str, v_b: str) -> Severity:
    """Compare two version strings; return semver-style severity or 'unknown'."""
    try:
        a = Version(v_a)
        b = Version(v_b)
    except InvalidVersion:
        return "unknown"

    if a.major != b.major:
        return "major"
    if a.minor != b.minor:
        return "minor"
    # micro / patch differs OR exactly equal — both bucketed as 'patch'
    return "patch"


def max_pairwise_severity(versions: list[str]) -> Severity:
    """Final group severity = max-rank across all version pairs.

    Caller must pass len(versions) >= 2 distinct values. Single-version
    inputs raise ValueError (this function is meant for skew groups).
    """
    if len(versions) < 2:
        raise ValueError(f"max_pairwise_severity requires >= 2 versions; got {len(versions)}")

    best: Severity = "unknown"
    best_rank = _RANK[best]
    for a, b in combinations(versions, 2):
        s = classify(a, b)
        r = _RANK[s]
        if r > best_rank:
            best, best_rank = s, r
    return best
