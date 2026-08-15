#!/usr/bin/env python3
"""Pure release-history resolver for receipt-bound UAudit recovery.

The dispatcher supplies only facts it has proven with direct remote Git probes.
This module deliberately performs no Git, network, cursor, or delivery writes:
an uncertain fact is represented explicitly and selects a full recovery instead
of silently advancing a cursor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^version/(\d+)\.(\d+)$")
ResolutionKind = Literal["no_change", "daily", "bridge", "transition", "rebase", "full_recovery", "split_recovery"]


class ResolutionError(ValueError):
    """Raised for malformed resolver evidence, never for an ambiguous history."""


@dataclass(frozen=True)
class Segment:
    name: str
    branch: str
    from_sha: str
    to_sha: str


@dataclass(frozen=True)
class Resolution:
    kind: ResolutionKind
    selected_branch: str | None
    selected_head: str | None
    segments: tuple[Segment, ...]
    requires_full_audit: bool
    reason: str


def _sha(value: str | None, name: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ResolutionError(f"{name} must be lowercase 40-hex SHA")
    return value


def _branch(value: str | None, name: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ResolutionError(f"{name} must be version/X.Y")
    return value


def _next_release(current: str, candidate: str | None) -> bool:
    if candidate is None:
        return False
    current_match = VERSION_RE.fullmatch(current)
    candidate_match = VERSION_RE.fullmatch(candidate)
    assert current_match and candidate_match
    major, minor = map(int, current_match.groups())
    return tuple(map(int, candidate_match.groups())) == (major, minor + 1)


def resolve_release_history(
    *,
    cursor_sha: str,
    release_branch: str,
    release_head: str | None,
    master_anchor_sha: str | None,
    master_head: str,
    cursor_is_ancestor_of_release: bool | None,
    cursor_is_ancestor_of_master: bool,
    master_is_ancestor_of_release: bool | None,
    next_release_branch: str | None = None,
    next_release_head: str | None = None,
    master_is_ancestor_of_next_release: bool | None = None,
    old_series_equivalence: Literal["equivalent", "changed", "ambiguous", "unavailable"] = "unavailable",
) -> Resolution:
    """Select auditable segments from independently verified Git facts.

    ``None`` means the dispatcher could not prove an ancestry relation. Such a
    condition is availability-first: it returns a full recovery whenever a
    concrete release head is available, and never produces an empty success.
    """

    cursor_sha = _sha(cursor_sha, "cursor_sha")  # type: ignore[assignment]
    release_branch = _branch(release_branch, "release_branch")  # type: ignore[assignment]
    release_head = _sha(release_head, "release_head", required=False)
    master_anchor_sha = _sha(master_anchor_sha, "master_anchor_sha", required=False)
    master_head = _sha(master_head, "master_head")  # type: ignore[assignment]
    next_release_branch = _branch(next_release_branch, "next_release_branch", required=False)
    next_release_head = _sha(next_release_head, "next_release_head", required=False)
    if next_release_head is not None and not _next_release(release_branch, next_release_branch):
        raise ResolutionError("next_release_branch must be the strictly next release line")
    if old_series_equivalence not in {"equivalent", "changed", "ambiguous", "unavailable"}:
        raise ResolutionError("old_series_equivalence is invalid")

    if next_release_head is not None:
        if master_is_ancestor_of_next_release is True and cursor_is_ancestor_of_master:
            return Resolution(
                "transition", next_release_branch, next_release_head,
                (Segment("master", "master", cursor_sha, master_head),
                 Segment("release", next_release_branch or release_branch, master_head, next_release_head)),
                False, "cursor reached master and the strictly next release contains master",
            )
        if master_is_ancestor_of_next_release is False:
            return Resolution(
                "split_recovery", next_release_branch, next_release_head,
                (Segment("master_hotfix", "master", master_anchor_sha or cursor_sha, master_head),
                 Segment("release", next_release_branch or release_branch, cursor_sha, next_release_head)),
                True, "next release does not contain current master; reports remain independent",
            )

    if release_head is None:
        if cursor_is_ancestor_of_master:
            return Resolution("bridge", None, master_head, (Segment("master", "master", cursor_sha, master_head),), True,
                              "release branch is absent; audit the proven master bridge")
        return Resolution("full_recovery", None, master_head, (Segment("master", "master", master_anchor_sha or cursor_sha, master_head),), True,
                          "release is absent and cursor ancestry is not provable")

    if cursor_sha == release_head:
        return Resolution("no_change", release_branch, release_head, (), False, "selected release head equals cursor")
    if cursor_is_ancestor_of_release is True:
        return Resolution("daily", release_branch, release_head, (Segment("release", release_branch, cursor_sha, release_head),), False,
                          "cursor is a proven release ancestor")
    if master_is_ancestor_of_release is True and master_anchor_sha is not None:
        if old_series_equivalence == "equivalent":
            return Resolution("rebase", release_branch, release_head,
                              (Segment("master_hotfix", "master", master_anchor_sha, master_head),), False,
                              "rebased release series is patch-equivalent; only master hotfix is new")
        if old_series_equivalence == "changed":
            return Resolution("rebase", release_branch, release_head,
                              (Segment("master_hotfix", "master", master_anchor_sha, master_head),
                               Segment("changed_release", release_branch, master_head, release_head)), False,
                              "rebase mapping identified changed release patches")
    return Resolution("full_recovery", release_branch, release_head,
                      (Segment("release", release_branch, master_head if master_is_ancestor_of_release else cursor_sha, release_head),), True,
                      "release ancestry or rebase mapping is ambiguous; audit the full proven release range")
