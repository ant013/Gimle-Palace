#!/usr/bin/env python3
"""Pure release-history resolver for receipt-bound UAudit recovery.

The dispatcher supplies only facts it has proven with direct remote Git probes.
This module deliberately performs no Git, network, cursor, or delivery writes:
an uncertain fact is represented explicitly and selects a full recovery instead
of silently advancing a cursor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Literal, Sequence


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^version/(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
CURSOR_SCHEMA = "uaudit-daily-cursor/v2"
SELECTION_SCHEMA = "uaudit-release-selection/v2"
MAX_RELEASE_REFS = 128
MAX_MISSING_VERSIONS = 128
ResolutionKind = Literal["no_change", "daily", "bridge", "transition", "rebase", "full_recovery", "split_recovery"]


class ResolutionError(ValueError):
    """Raised for malformed resolver evidence, never for an ambiguous history."""


INSTALL_SCHEMA = "uaudit-release-resolver-install/v1"
INSTALL_MANIFEST = "uaudit_release_resolver.manifest.json"


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


@dataclass(frozen=True)
class VerifiedSelection:
    routine_key: str
    platform: str
    from_branch: str
    selected_branch: str
    cursor_sha: str
    selected_head: str
    resolution_kind: str
    selection_sha256: str


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


def parse_release_branch(value: str) -> tuple[int, int]:
    """Return a canonical numeric release tuple without accepting aliases."""

    branch = _branch(value, "release branch")
    assert branch is not None
    match = VERSION_RE.fullmatch(branch)
    assert match is not None
    return tuple(map(int, match.groups()))  # type: ignore[return-value]


def _release_cursor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResolutionError("cursor must be an object")
    required = {
        "schema_version", "active_release_branch", "last_successfully_audited_sha",
        "last_successful_issue", "last_successful_at", "last_delivery_summary_sha256",
        "last_telegram_message_id",
    }
    if set(value) != required or value.get("schema_version") != CURSOR_SCHEMA:
        raise ResolutionError("discover requires a canonical uaudit-daily-cursor/v2 cursor")
    branch = _branch(value.get("active_release_branch"), "cursor.active_release_branch")
    cursor_sha = _sha(value.get("last_successfully_audited_sha"), "cursor.last_successfully_audited_sha")
    return {**value, "active_release_branch": branch, "last_successfully_audited_sha": cursor_sha}


def _ancestry(value: Mapping[str, bool | None], branch: str) -> bool | None:
    result = value.get(branch)
    if result not in (True, False, None):
        raise ResolutionError(f"ancestry[{branch!r}] must be boolean or null")
    return result


def _selection(
    *,
    routine_key: str,
    platform: str,
    release_major: int,
    from_branch: str,
    selected_branch: str | None,
    cursor_sha: str,
    selected_head: str | None,
    master_head: str,
    resolution_kind: str,
    segment: dict[str, str] | None,
    release_heads: Mapping[str, str],
    missing_versions: list[str],
    selected_ancestry: bool | None,
    master_ancestry: bool | None,
    active_present: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SELECTION_SCHEMA,
        "routine_key": routine_key,
        "platform": platform,
        "release_major": release_major,
        "from_branch": from_branch,
        "selected_branch": selected_branch,
        "cursor_sha": cursor_sha,
        "selected_head": selected_head,
        "master_head": master_head,
        "resolution_kind": resolution_kind,
        "segment": segment,
        "release_heads": dict(sorted(release_heads.items())),
        "missing_versions": missing_versions,
        "proof": {
            "active_branch_present": active_present,
            "cursor_is_ancestor_of_selected": selected_ancestry,
            "cursor_is_ancestor_of_master": master_ancestry,
        },
    }


def plan_release_selection(
    *,
    cursor: Any,
    release_major: int,
    release_heads: Mapping[str, str],
    master_head: str,
    ancestry: Mapping[str, bool | None],
    routine_key: str,
    platform: str,
) -> dict[str, Any]:
    """Plan one deterministic selection from already verified remote Git facts."""

    cursor = _release_cursor(cursor)
    if not isinstance(release_major, int) or isinstance(release_major, bool) or release_major < 0:
        raise ResolutionError("release_major must be a non-negative integer")
    if platform not in {"android", "ios"}:
        raise ResolutionError("platform must be android or ios")
    if not isinstance(routine_key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", routine_key):
        raise ResolutionError("routine_key is invalid")
    if not isinstance(release_heads, Mapping) or len(release_heads) > MAX_RELEASE_REFS:
        raise ResolutionError(f"release_heads must contain at most {MAX_RELEASE_REFS} refs")
    if not isinstance(ancestry, Mapping):
        raise ResolutionError("ancestry must be an object")
    normalized_heads: dict[str, str] = {}
    parsed_heads: dict[str, tuple[int, int]] = {}
    for branch, head in release_heads.items():
        parsed_heads[branch] = parse_release_branch(branch)
        normalized = _sha(head, f"release_heads[{branch!r}]")
        assert normalized is not None
        normalized_heads[branch] = normalized
    master_head = _sha(master_head, "master_head")  # type: ignore[assignment]
    from_branch = cursor["active_release_branch"]
    cursor_sha = cursor["last_successfully_audited_sha"]
    from_major, from_minor = parse_release_branch(from_branch)
    if from_major != release_major:
        raise ResolutionError("cursor active branch major differs from configured release major")
    master_ancestry = _ancestry(ancestry, "master")

    if from_branch in normalized_heads:
        selected_head = normalized_heads[from_branch]
        selected_ancestry = True if cursor_sha == selected_head else _ancestry(ancestry, from_branch)
        if cursor_sha == selected_head:
            kind, segment = "no_change", None
        elif selected_ancestry is True:
            kind = "daily"
            segment = {"branch": from_branch, "from_sha": cursor_sha, "to_sha": selected_head}
        else:
            kind, segment = "blocked_active_divergence", None
        return _selection(
            routine_key=routine_key, platform=platform, release_major=release_major,
            from_branch=from_branch, selected_branch=from_branch, cursor_sha=cursor_sha,
            selected_head=selected_head, master_head=master_head, resolution_kind=kind,
            segment=segment, release_heads=normalized_heads, missing_versions=[],
            selected_ancestry=selected_ancestry, master_ancestry=master_ancestry,
            active_present=True,
        )

    candidates = sorted(
        (version, branch)
        for branch, version in parsed_heads.items()
        if version[0] == release_major and version[1] > from_minor
    )
    if candidates:
        (_, selected_minor), selected_branch = candidates[0]
        selected_head = normalized_heads[selected_branch]
        selected_ancestry = True if cursor_sha == selected_head else _ancestry(ancestry, selected_branch)
        if selected_minor - from_minor - 1 > MAX_MISSING_VERSIONS:
            raise ResolutionError("release version gap exceeds the bounded proof limit")
        missing = [f"version/{release_major}.{minor}" for minor in range(from_minor + 1, selected_minor)]
        if cursor_sha == selected_head:
            kind, segment = "branch_transition", None
        elif selected_ancestry is True:
            kind = "transition"
            segment = {"branch": selected_branch, "from_sha": cursor_sha, "to_sha": selected_head}
        else:
            kind, segment = "blocked_divergent_successor", None
        return _selection(
            routine_key=routine_key, platform=platform, release_major=release_major,
            from_branch=from_branch, selected_branch=selected_branch, cursor_sha=cursor_sha,
            selected_head=selected_head, master_head=master_head, resolution_kind=kind,
            segment=segment, release_heads=normalized_heads, missing_versions=missing,
            selected_ancestry=selected_ancestry, master_ancestry=master_ancestry,
            active_present=False,
        )

    if any(version[0] > release_major for version in parsed_heads.values()):
        kind, segment = "blocked_major_transition", None
    elif cursor_sha == master_head:
        kind, segment = "no_change_waiting_release", None
    elif master_ancestry is True:
        kind = "bridge"
        segment = {"branch": "master", "from_sha": cursor_sha, "to_sha": master_head}
    else:
        kind, segment = "blocked_unproven_master", None
    return _selection(
        routine_key=routine_key, platform=platform, release_major=release_major,
        from_branch=from_branch, selected_branch=None, cursor_sha=cursor_sha,
        selected_head=None, master_head=master_head, resolution_kind=kind,
        segment=segment, release_heads=normalized_heads, missing_versions=[],
        selected_ancestry=None, master_ancestry=master_ancestry,
        active_present=False,
    )


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
    cursor_is_ancestor_of_next_release: bool | None = None,
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
        if release_head is None and cursor_sha == next_release_head:
            return Resolution(
                "no_change", next_release_branch, next_release_head, (), False,
                "configured release is absent and proven strict successor head equals cursor",
            )
        # NEW: If release is absent but cursor is already in next_release, continue incrementally
        if release_head is None and cursor_is_ancestor_of_next_release is True:
            if cursor_sha == next_release_head:
                return Resolution(
                    "no_change", next_release_branch, next_release_head, (), False,
                    "configured release is absent; cursor already at next release head",
                )
            return Resolution(
                "daily", next_release_branch, next_release_head,
                (Segment("release", next_release_branch, cursor_sha, next_release_head),),
                False, "configured release is absent; cursor is already in next release, continuing incrementally",
            )
        if master_is_ancestor_of_next_release is True and cursor_is_ancestor_of_master:
            return Resolution(
                "transition", next_release_branch, next_release_head,
                (Segment("master", "master", cursor_sha, master_head),
                 Segment("release", next_release_branch or release_branch, master_head, next_release_head)),
                False, "cursor reached master and the strictly next release contains master",
            )
        if release_head is None and master_is_ancestor_of_next_release is True:
            return Resolution(
                "full_recovery", next_release_branch, next_release_head,
                (Segment("release", next_release_branch or release_branch, master_head, next_release_head),),
                True, "configured release is absent; recover from master to its strict successor",
            )
        if master_is_ancestor_of_next_release is False:
            return Resolution(
                "split_recovery", next_release_branch, next_release_head,
                (Segment("master_hotfix", "master", master_anchor_sha or cursor_sha, master_head),
                 Segment("release", next_release_branch or release_branch, cursor_sha, next_release_head)),
                True, "next release does not contain current master; reports remain independent",
            )

    if release_head is None:
        if master_head == cursor_sha:
            return Resolution(
                "no_change", None, master_head, (), False,
                "configured release is absent and cursor already equals master head",
            )
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


def _resolution_json(result: Resolution) -> dict[str, Any]:
    return {
        "kind": result.kind,
        "selected_branch": result.selected_branch,
        "selected_head": result.selected_head,
        "segments": [
            {"name": segment.name, "branch": segment.branch, "from_sha": segment.from_sha, "to_sha": segment.to_sha}
            for segment in result.segments
        ],
        "requires_full_audit": result.requires_full_audit,
        "reason": result.reason,
    }


def resolve_json(value: Any) -> dict[str, Any]:
    """Resolve a dispatcher-produced JSON evidence object without side effects."""

    if not isinstance(value, dict):
        raise ResolutionError("resolver input must be an object")
    allowed = {
        "cursor_sha", "release_branch", "release_head", "master_anchor_sha", "master_head",
        "cursor_is_ancestor_of_release", "cursor_is_ancestor_of_master", "master_is_ancestor_of_release",
        "next_release_branch", "next_release_head", "master_is_ancestor_of_next_release",
        "cursor_is_ancestor_of_next_release",
        "old_series_equivalence",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ResolutionError(f"resolver input has unknown fields: {', '.join(unknown)}")
    required = {
        "cursor_sha", "release_branch", "release_head", "master_anchor_sha", "master_head",
        "cursor_is_ancestor_of_release", "cursor_is_ancestor_of_master", "master_is_ancestor_of_release",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ResolutionError(f"resolver input missing fields: {', '.join(missing)}")
    return _resolution_json(resolve_release_history(**value))


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _create_or_match(path: Path, value: Any) -> None:
    raw = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise ResolutionError(f"selection output is unreadable: {path}") from exc
        if existing != raw:
            raise ResolutionError("selection output conflicts with existing immutable selection")
        return
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _git(repo_path: Path | None, args: Sequence[str], *, timeout: int = 30) -> str:
    command = ["git"]
    if repo_path is not None:
        command.extend(("-C", str(repo_path)))
    command.extend(args)
    try:
        result = subprocess.run(
            command, text=True, capture_output=True, check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResolutionError("bounded Git command failed") from exc
    if len(result.stdout.encode("utf-8")) > 1024 * 1024 or len(result.stderr.encode("utf-8")) > 256 * 1024:
        raise ResolutionError("Git command output exceeds the bounded limit")
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown error"
        raise ResolutionError(f"Git command failed: {detail[:300]}")
    return result.stdout


def _remote_heads(remote_url: str) -> tuple[dict[str, str], str]:
    if (
        not isinstance(remote_url, str) or not remote_url or remote_url != remote_url.strip()
        or remote_url.startswith("-") or "\x00" in remote_url or "\n" in remote_url or "\r" in remote_url
    ):
        raise ResolutionError("remote_url is invalid")
    raw = _git(None, ("ls-remote", "--heads", remote_url))
    releases: dict[str, str] = {}
    master_head: str | None = None
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not SHA_RE.fullmatch(parts[0]) or not parts[1].startswith("refs/heads/"):
            raise ResolutionError("ls-remote returned a malformed head record")
        oid, ref = parts
        if ref == "refs/heads/master":
            if master_head is not None:
                raise ResolutionError("ls-remote returned duplicate master refs")
            master_head = oid
        elif ref.startswith("refs/heads/version/"):
            branch = ref.removeprefix("refs/heads/")
            parse_release_branch(branch)
            if branch in releases:
                raise ResolutionError("ls-remote returned duplicate release refs")
            releases[branch] = oid
    if len(releases) > MAX_RELEASE_REFS:
        raise ResolutionError(f"remote has more than {MAX_RELEASE_REFS} release refs")
    if master_head is None:
        raise ResolutionError("authoritative remote has no master branch")
    return releases, master_head


def _private_ref(platform: str, branch: str) -> str:
    suffix = "master" if branch == "master" else branch.removeprefix("version/").replace(".", "-")
    return f"refs/uaudit/{platform}/{suffix}"


def _fetch_advertised(
    repo_path: Path,
    remote_url: str,
    *,
    platform: str,
    branch: str,
    advertised_oid: str,
) -> None:
    remote_ref = f"refs/heads/{branch}"
    destination = _private_ref(platform, branch)
    _git(
        repo_path,
        ("fetch", "--no-tags", "--no-write-fetch-head", "--force", remote_url, f"+{remote_ref}:{destination}"),
    )
    fetched = _git(repo_path, ("rev-parse", "--verify", destination)).strip()
    if fetched != advertised_oid:
        raise ResolutionError(f"remote ref moved while fetching {branch}")


def _is_ancestor(repo_path: Path, older: str, newer: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "merge-base", "--is-ancestor", older, newer],
        text=True, capture_output=True, check=False, timeout=30,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise ResolutionError("Git ancestry proof could not be established")


def _validate_repo(repo_path: Path) -> Path:
    repo = repo_path.resolve()
    if not repo.is_dir() or _git(repo, ("rev-parse", "--is-inside-work-tree")).strip() != "true":
        raise ResolutionError("repo_path is not a Git worktree")
    return repo


def _snapshot_for_selection(
    *, repo_path: Path, remote_url: str, cursor: Mapping[str, Any],
    release_major: int, platform: str,
) -> tuple[dict[str, str], str, dict[str, bool]]:
    from_branch = cursor["active_release_branch"]
    _, from_minor = parse_release_branch(from_branch)
    last_error: ResolutionError | None = None
    for _attempt in range(2):
        try:
            releases, master_head = _remote_heads(remote_url)
            selected: str | None = None
            if from_branch in releases:
                selected = from_branch
            else:
                candidates = sorted(
                    (parse_release_branch(branch), branch)
                    for branch in releases
                    if parse_release_branch(branch)[0] == release_major
                    and parse_release_branch(branch)[1] > from_minor
                )
                if candidates:
                    selected = candidates[0][1]
            _fetch_advertised(
                repo_path, remote_url, platform=platform, branch="master", advertised_oid=master_head,
            )
            if selected is not None:
                _fetch_advertised(
                    repo_path, remote_url, platform=platform, branch=selected,
                    advertised_oid=releases[selected],
                )
            cursor_sha = cursor["last_successfully_audited_sha"]
            ancestry = {"master": _is_ancestor(repo_path, cursor_sha, master_head)}
            if selected is not None:
                ancestry[selected] = _is_ancestor(repo_path, cursor_sha, releases[selected])
            return releases, master_head, ancestry
        except ResolutionError as exc:
            last_error = exc
    assert last_error is not None
    raise ResolutionError(f"remote snapshot was not stable after one retry: {last_error}")


def discover_release_selection(
    *,
    repo_path: Path,
    remote_url: str,
    cursor_path: Path,
    routine_key: str,
    platform: str,
    release_major: int,
    output_path: Path,
) -> dict[str, Any]:
    repo = _validate_repo(repo_path)
    try:
        raw = cursor_path.resolve().read_bytes()
        if len(raw) > 64 * 1024:
            raise ResolutionError("cursor exceeds the bounded size limit")
        cursor = _release_cursor(json.loads(raw))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("cursor is unreadable") from exc
    releases, master_head, ancestry = _snapshot_for_selection(
        repo_path=repo, remote_url=remote_url, cursor=cursor,
        release_major=release_major, platform=platform,
    )
    selection = plan_release_selection(
        cursor=cursor, release_major=release_major, release_heads=releases,
        master_head=master_head, ancestry=ancestry, routine_key=routine_key,
        platform=platform,
    )
    _create_or_match(output_path.resolve(), selection)
    return selection


def _load_selection(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.resolve().read_bytes()
        if len(raw) > 256 * 1024:
            raise ResolutionError("selection exceeds the bounded size limit")
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("selection is unreadable") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SELECTION_SCHEMA:
        raise ResolutionError("selection schema is invalid")
    expected = {
        "schema_version", "routine_key", "platform", "release_major", "from_branch",
        "selected_branch", "cursor_sha", "selected_head", "master_head", "resolution_kind",
        "segment", "release_heads", "missing_versions", "proof",
    }
    if set(value) != expected:
        raise ResolutionError("selection fields are invalid")
    # Re-plan from the embedded verified facts to validate every cross-field invariant.
    proof = value.get("proof")
    if not isinstance(proof, dict) or set(proof) != {
        "active_branch_present", "cursor_is_ancestor_of_selected", "cursor_is_ancestor_of_master",
    }:
        raise ResolutionError("selection proof is invalid")
    cursor = {
        "schema_version": CURSOR_SCHEMA,
        "active_release_branch": value["from_branch"],
        "last_successfully_audited_sha": value["cursor_sha"],
        "last_successful_issue": None,
        "last_successful_at": None,
        "last_delivery_summary_sha256": None,
        "last_telegram_message_id": None,
    }
    ancestry: dict[str, bool | None] = {"master": proof["cursor_is_ancestor_of_master"]}
    if value["selected_branch"] is not None:
        ancestry[value["selected_branch"]] = proof["cursor_is_ancestor_of_selected"]
    expected_value = plan_release_selection(
        cursor=cursor, release_major=value["release_major"], release_heads=value["release_heads"],
        master_head=value["master_head"], ancestry=ancestry,
        routine_key=value["routine_key"], platform=value["platform"],
    )
    if value != expected_value:
        raise ResolutionError("selection content is internally inconsistent")
    return value, hashlib.sha256(raw).hexdigest()


def verify_selection(
    *, repo_path: Path, remote_url: str, selection_path: Path,
) -> VerifiedSelection:
    repo = _validate_repo(repo_path)
    selection, digest = _load_selection(selection_path)
    from_branch = selection["from_branch"]
    selected_branch = selection["selected_branch"]
    selected_head = selection["selected_head"]
    if selected_branch is None or selected_head is None:
        raise ResolutionError("selection outcome cannot mutate daily state")
    releases, _master_head = _remote_heads(remote_url)
    if selected_branch != from_branch and from_branch in releases:
        raise ResolutionError("active branch was restored after delivery")
    if selected_branch != from_branch:
        from_major, from_minor = parse_release_branch(from_branch)
        candidates = sorted(
            (version, branch)
            for branch, version in (
                (branch, parse_release_branch(branch)) for branch in releases
            )
            if version[0] == from_major and version[1] > from_minor
        )
        if not candidates or candidates[0][1] != selected_branch:
            raise ResolutionError("selected release is no longer the lowest same-major successor")
    if releases.get(selected_branch) != selected_head:
        raise ResolutionError("selected release head changed after delivery")
    _fetch_advertised(
        repo,
        remote_url,
        platform=selection["platform"],
        branch=selected_branch,
        advertised_oid=selected_head,
    )
    return VerifiedSelection(
        routine_key=selection["routine_key"], platform=selection["platform"],
        from_branch=from_branch, selected_branch=selected_branch,
        cursor_sha=selection["cursor_sha"], selected_head=selected_head,
        resolution_kind=selection["resolution_kind"], selection_sha256=digest,
    )


def _selection_capability(
    selection_path: Path,
    *,
    allowed_kinds: set[str],
) -> VerifiedSelection:
    selection, digest = _load_selection(selection_path)
    selected_branch = selection["selected_branch"]
    selected_head = selection["selected_head"]
    if (
        selection["resolution_kind"] not in allowed_kinds
        or not isinstance(selected_branch, str)
        or not isinstance(selected_head, str)
    ):
        raise ResolutionError("selection outcome cannot perform this finalization")
    return VerifiedSelection(
        routine_key=selection["routine_key"],
        platform=selection["platform"],
        from_branch=selection["from_branch"],
        selected_branch=selected_branch,
        cursor_sha=selection["cursor_sha"],
        selected_head=selected_head,
        resolution_kind=selection["resolution_kind"],
        selection_sha256=digest,
    )


def _migration_capability(
    *,
    cursor_path: Path,
    routine_key: str,
    platform: str,
    active_branch: str,
) -> VerifiedSelection:
    active_branch = _branch(active_branch, "active_branch")  # type: ignore[assignment]
    if platform not in {"android", "ios"} or routine_key != f"uaudit-daily-{platform}":
        raise ResolutionError("migration routine or platform is invalid")
    try:
        raw = cursor_path.resolve().read_bytes()
        if len(raw) > 64 * 1024:
            raise ResolutionError("cursor exceeds the bounded size limit")
        cursor = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("cursor is unreadable") from exc
    if not isinstance(cursor, dict):
        raise ResolutionError("cursor must be an object")
    cursor_sha = _sha(
        cursor.get("last_successfully_audited_sha"),
        "cursor.last_successfully_audited_sha",
    )
    if cursor.get("schema_version") == CURSOR_SCHEMA and cursor.get("active_release_branch") != active_branch:
        raise ResolutionError("existing cursor v2 branch conflicts with requested migration")
    proof = {
        "schema_version": "uaudit-cursor-migration-proof/v1",
        "routine_key": routine_key,
        "platform": platform,
        "active_release_branch": active_branch,
        "release_head": cursor_sha,
    }
    return VerifiedSelection(
        routine_key=routine_key,
        platform=platform,
        from_branch=active_branch,
        selected_branch=active_branch,
        cursor_sha=cursor_sha,
        selected_head=cursor_sha,
        resolution_kind="migration",
        selection_sha256=hashlib.sha256(_canonical_bytes(proof)).hexdigest(),
    )


def verify_cursor_migration(
    *,
    repo_path: Path,
    remote_url: str,
    cursor_path: Path,
    routine_key: str,
    platform: str,
    active_branch: str,
) -> VerifiedSelection:
    repo = _validate_repo(repo_path)
    candidate = _migration_capability(
        cursor_path=cursor_path,
        routine_key=routine_key,
        platform=platform,
        active_branch=active_branch,
    )
    last_error: ResolutionError | None = None
    for _attempt in range(2):
        try:
            releases, _master = _remote_heads(remote_url)
            head = releases.get(candidate.selected_branch)
            if head is None:
                raise ResolutionError("active release branch is absent during migration")
            if head != candidate.cursor_sha:
                raise ResolutionError("cursor SHA does not equal the authoritative active release head")
            _fetch_advertised(
                repo,
                remote_url,
                platform=platform,
                branch=candidate.selected_branch,
                advertised_oid=head,
            )
            return candidate
        except ResolutionError as exc:
            last_error = exc
    assert last_error is not None
    raise ResolutionError(f"migration ref proof was not stable after one retry: {last_error}")


def verify_install(manifest: Any) -> dict[str, Any]:
    """Verify that a deployed resolver is bound to its adjacent manifest."""

    path = Path(manifest).resolve()
    if path.name != INSTALL_MANIFEST or path.is_symlink():
        raise ResolutionError("resolver install manifest path is invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolutionError("resolver install manifest is unreadable") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "file", "sha256"}:
        raise ResolutionError("resolver install manifest has invalid fields")
    if value["schema_version"] != INSTALL_SCHEMA or value["file"] != "uaudit_release_resolver.py":
        raise ResolutionError("resolver install manifest has invalid identity")
    if not isinstance(value["sha256"], str) or not SHA256_RE.fullmatch(value["sha256"]):
        raise ResolutionError("resolver install manifest has invalid sha256")
    source = Path(__file__).resolve()
    if source.name != value["file"] or source.parent != path.parent:
        raise ResolutionError("resolver install manifest is not adjacent to deployed resolver")
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != value["sha256"]:
        raise ResolutionError("resolver install digest mismatch")
    return {"status": "verified", "sha256": actual}


def _delivery_module(helper_manifest: Path) -> Any:
    try:
        import uaudit_delivery_contract as delivery
    except ImportError as exc:
        raise ResolutionError("adjacent delivery helper is unavailable") from exc
    try:
        delivery._verify_own_install(helper_manifest.resolve())
    except delivery.ContractError as exc:
        raise ResolutionError(f"delivery helper install verification failed: {exc}") from exc
    return delivery


def _delivery_capability(delivery: Any, verified: VerifiedSelection) -> Any:
    return delivery._verified_release_capability(
        selection_sha256=verified.selection_sha256,
        routine_key=verified.routine_key,
        platform=verified.platform,
        from_branch=verified.from_branch,
        selected_branch=verified.selected_branch,
        cursor_sha=verified.cursor_sha,
        selected_head=verified.selected_head,
        resolution_kind=verified.resolution_kind,
    )


def finalize_daily(args: argparse.Namespace) -> dict[str, Any]:
    delivery = _delivery_module(args.helper_manifest)
    try:
        local = _selection_capability(
            args.selection,
            allowed_kinds={"daily", "transition"},
        )
        recovery = delivery.recover_daily_without_fence(
            args,
            _delivery_capability(delivery, local),
        )
        if recovery.get("status") != "fencing_required":
            return recovery
        verified = verify_selection(
            repo_path=args.repo,
            remote_url=args.remote_url,
            selection_path=args.selection,
        )
        return delivery.reconcile_daily_verified(
            args,
            _delivery_capability(delivery, verified),
        )
    except delivery.ContractError as exc:
        raise ResolutionError(f"daily finalization failed: {exc}") from exc


def migrate_cursor(args: argparse.Namespace) -> dict[str, Any]:
    delivery = _delivery_module(args.helper_manifest)
    try:
        local = _migration_capability(
            cursor_path=args.cursor,
            routine_key=args.routine_key,
            platform=args.platform,
            active_branch=args.active_branch,
        )
        recovery = delivery.recover_cursor_migration_without_fence(
            args,
            _delivery_capability(delivery, local),
        )
        if recovery.get("status") != "fencing_required":
            return recovery
        verified = verify_cursor_migration(
            repo_path=args.repo,
            remote_url=args.remote_url,
            cursor_path=args.cursor,
            routine_key=args.routine_key,
            platform=args.platform,
            active_branch=args.active_branch,
        )
        return delivery.migrate_cursor_verified(
            args,
            _delivery_capability(delivery, verified),
        )
    except delivery.ContractError as exc:
        raise ResolutionError(f"cursor migration failed: {exc}") from exc


def finalize_daily_status(args: argparse.Namespace) -> dict[str, Any]:
    delivery = _delivery_module(args.helper_manifest)
    try:
        local = _selection_capability(
            args.selection,
            allowed_kinds={"branch_transition"},
        )
        recovery = delivery.recover_daily_status_without_fence(
            args,
            _delivery_capability(delivery, local),
        )
        if recovery.get("status") != "fencing_required":
            return recovery
        verified = verify_selection(
            repo_path=args.repo,
            remote_url=args.remote_url,
            selection_path=args.selection,
        )
        return delivery.reconcile_daily_status_verified(
            args,
            _delivery_capability(delivery, verified),
        )
    except delivery.ContractError as exc:
        raise ResolutionError(f"daily status finalization failed: {exc}") from exc


def _build_command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser("verify-install", help="verify the installed release tool")
    install.add_argument("--manifest", type=Path, required=True)
    install.set_defaults(func=lambda args: verify_install(args.manifest), verify_self=False)

    discover = commands.add_parser("discover", help="discover and bind the current release selection")
    discover.add_argument("--manifest", type=Path, required=True)
    discover.add_argument("--repo", type=Path, required=True)
    discover.add_argument("--remote-url", required=True)
    discover.add_argument("--cursor", type=Path, required=True)
    discover.add_argument("--routine-key", required=True)
    discover.add_argument("--platform", choices=("android", "ios"), required=True)
    discover.add_argument("--release-major", type=int, required=True)
    discover.add_argument("--output", type=Path, required=True)
    discover.set_defaults(
        func=lambda args: discover_release_selection(
            repo_path=args.repo, remote_url=args.remote_url, cursor_path=args.cursor,
            routine_key=args.routine_key, platform=args.platform,
            release_major=args.release_major, output_path=args.output,
        ),
        verify_self=True,
    )

    finalize = commands.add_parser("finalize-daily", help="fence refs and apply receipt-bound daily cursor CAS")
    finalize.add_argument("--manifest", type=Path, required=True)
    finalize.add_argument("--helper-manifest", type=Path, required=True)
    finalize.add_argument("--repo", type=Path, required=True)
    finalize.add_argument("--remote-url", required=True)
    finalize.add_argument("--selection", type=Path, required=True)
    finalize.add_argument("--run-dir", type=Path, required=True)
    finalize.add_argument("--cursor", type=Path, required=True)
    finalize.add_argument("--lock-dir", type=Path, required=True)
    finalize.add_argument("--reconciled-at", required=True)
    finalize.add_argument("--approval-comments", type=Path)
    finalize.add_argument("--approvers", type=Path)
    finalize.set_defaults(func=finalize_daily, verify_self=True)

    finalize_status = commands.add_parser(
        "finalize-daily-status",
        help="fence refs and apply a receipt-bound same-head branch transition",
    )
    finalize_status.add_argument("--manifest", type=Path, required=True)
    finalize_status.add_argument("--helper-manifest", type=Path, required=True)
    finalize_status.add_argument("--repo", type=Path, required=True)
    finalize_status.add_argument("--remote-url", required=True)
    finalize_status.add_argument("--selection", type=Path, required=True)
    finalize_status.add_argument("--run-dir", type=Path, required=True)
    finalize_status.add_argument("--cursor", type=Path, required=True)
    finalize_status.add_argument("--lock-dir", type=Path, required=True)
    finalize_status.set_defaults(func=finalize_daily_status, verify_self=True)

    migrate = commands.add_parser("migrate-cursor", help="verify active ref and migrate a quiesced cursor to v2")
    migrate.add_argument("--manifest", type=Path, required=True)
    migrate.add_argument("--helper-manifest", type=Path, required=True)
    migrate.add_argument("--repo", type=Path, required=True)
    migrate.add_argument("--remote-url", required=True)
    migrate.add_argument("--cursor", type=Path, required=True)
    migrate.add_argument("--lock-dir", type=Path, required=True)
    migrate.add_argument("--routine-key", required=True)
    migrate.add_argument("--platform", choices=("android", "ios"), required=True)
    migrate.add_argument("--active-branch", required=True)
    migrate.add_argument("--migrated-at", required=True)
    migrate.set_defaults(func=migrate_cursor, verify_self=True)
    return parser


def _legacy_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=argparse.FileType("r", encoding="utf-8"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.manifest is not None:
            verify_install(args.manifest)
        if args.input is None:
            if args.manifest is None:
                raise ResolutionError("--input is required unless --manifest is supplied")
            result = verify_install(args.manifest)
        else:
            value = json.load(args.input)
            result = resolve_json(value)
    except (OSError, json.JSONDecodeError, ResolutionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, separators=(",", ":")))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values or values[0] not in {
        "verify-install", "discover", "finalize-daily", "finalize-daily-status", "migrate-cursor",
    }:
        return _legacy_main(values)
    parser = _build_command_parser()
    args = parser.parse_args(values)
    try:
        if args.verify_self:
            verify_install(args.manifest)
        result = args.func(args)
    except (OSError, json.JSONDecodeError, ResolutionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
