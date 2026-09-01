#!/usr/bin/env python3
"""Fail-closed single-slice Git worktree and lease controller for Glitcherry."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = "glitcherry-slice-worktree/v1"
ANDROID_REMOTE = "https://github.com/ant013/Glitcherry-Android.git"
CONTROL_REMOTE = "https://github.com/ant013/Glitcherry.git"
ISSUE_KEY_RE = re.compile(r"^GLA-[1-9][0-9]*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
OWNER_RE = re.compile(r"^Glitcherry[A-Za-z0-9]+$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
TERMINAL_PHASES = {"cleaned", "cancelled"}
MAX_REJECTIONS = 3
CTO = "GlitcherryCTO"
REVIEWER = "GlitcherryCodeReviewer"
IMPLEMENTERS = {"GlitcherryAndroidEngineer", "GlitcherryMediaPipelineEngineer"}


class ContractError(RuntimeError):
    """A fail-closed contract violation safe to show to the operator."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _run(
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise ContractError(f"command failed safely: {args[0]} {args[1] if len(args) > 1 else ''}".strip())
    return result


def _validate_private_file(path: Path, label: str) -> None:
    try:
        value = path.lstat()
    except OSError as exc:
        raise ContractError(f"{label} is unavailable") from exc
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.getuid()
        or stat.S_IMODE(value.st_mode) != 0o600
    ):
        raise ContractError(f"{label} must be an owner-controlled mode-600 file")


def _validate_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path == Path("/"):
        raise ContractError(f"{label} must be a bounded absolute directory")
    try:
        value = path.lstat()
    except OSError as exc:
        raise ContractError(f"{label} does not exist") from exc
    if not stat.S_ISDIR(value.st_mode) or path.is_symlink():
        raise ContractError(f"{label} must be a real directory, not a symlink")
    return path.resolve()


def _load_paths(path: Path) -> dict[str, Any]:
    _validate_private_file(path, "paths file")
    result = _run("yq", "-o=json", ".", str(path))
    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("paths file is not valid YAML") from exc
    if values.get("schemaVersion") != 2:
        raise ContractError("paths file schemaVersion must be 2")
    return values


def _configured_path(values: dict[str, Any], key: str) -> Path:
    raw = values.get(key)
    if not isinstance(raw, str) or not raw:
        raise ContractError(f"paths file is missing {key}")
    return _validate_directory(Path(raw), key)


def _lease_seconds(values: dict[str, Any]) -> int:
    raw = values.get("slice_lease_seconds", 2700)
    if not isinstance(raw, int) or not 60 <= raw <= 7200:
        raise ContractError("slice_lease_seconds must be between 60 and 7200")
    return raw


def _validate_remote(
    configured: Any,
    expected: str,
    *,
    allow_local: bool,
    label: str,
) -> str:
    if not isinstance(configured, str) or not configured:
        raise ContractError(f"paths file is missing {label}_repository_url")
    if allow_local:
        candidate = Path(configured)
        if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_dir():
            raise ContractError("test remotes must be absolute local bare repositories")
        bare = _run("git", "rev-parse", "--is-bare-repository", cwd=candidate).stdout.strip()
        if bare != "true":
            raise ContractError("test remotes must be bare repositories")
        return configured
    if configured != expected:
        raise ContractError(f"{label} repository URL is not allowlisted")
    return configured


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run("git", "-C", str(repo), *args, check=check)


def _validate_repo(repo: Path, remote: str, label: str) -> None:
    if repo.is_symlink() or not repo.is_dir() or not (repo / ".git").exists():
        raise ContractError(f"{label} repository is unmanaged")
    top = Path(_git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != repo:
        raise ContractError(f"{label} repository root does not match configuration")
    if _git(repo, "remote", "get-url", "origin").stdout.strip() != remote:
        raise ContractError(f"{label} origin does not match configured allowlist")


def _fetch(repo: Path) -> None:
    _git(repo, "fetch", "origin", "--prune")


def _require_clean(repo: Path, label: str) -> None:
    if _git(repo, "status", "--porcelain", "--untracked-files=all").stdout:
        raise ContractError(f"{label} is dirty")


def _require_current_develop(repo: Path, label: str) -> str:
    _require_clean(repo, label)
    if _git(repo, "branch", "--show-current").stdout.strip() != "develop":
        raise ContractError(f"{label} is not on develop")
    _fetch(repo)
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    remote = _git(repo, "rev-parse", "origin/develop").stdout.strip()
    if head != remote:
        raise ContractError(f"{label} is not current develop")
    return head


def _validate_issue_key(value: str) -> str:
    if not ISSUE_KEY_RE.fullmatch(value):
        raise ContractError("issue key must match GLA-<positive integer>")
    return value


def _validate_slug(value: str) -> str:
    if not SLUG_RE.fullmatch(value) or len(value) > 64:
        raise ContractError("slug must be bounded lowercase kebab-case")
    return value


def _validate_owner(value: str) -> str:
    if not OWNER_RE.fullmatch(value):
        raise ContractError("owner is not a Glitcherry role name")
    return value


def _validate_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise ContractError("run id has an unsafe format")
    return value


def _state_path(state_root: Path, issue_key: str) -> Path:
    _validate_issue_key(issue_key)
    return state_root / f"{issue_key}.json"


@contextmanager
def _state_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_suffix(".lock")
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ContractError("could not open the slice state lock safely") from exc
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_state(path: Path) -> dict[str, Any]:
    _validate_private_file(path, "slice state")
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("slice state is unreadable") from exc
    if state.get("schema_version") != SCHEMA_VERSION:
        raise ContractError("slice state schema is unsupported")
    return state


def _write_state(path: Path, state: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _emit(state: dict[str, Any]) -> None:
    print(json.dumps(state, indent=2, sort_keys=True))


def _worktree_path(state: dict[str, Any], worktree_root: Path) -> Path:
    path = Path(state["worktree_path"])
    try:
        path.relative_to(worktree_root)
    except ValueError as exc:
        raise ContractError("recorded worktree escapes task_worktree_root") from exc
    return path


def _verify_worktree(state: dict[str, Any], worktree_root: Path, *, clean: bool = True) -> str:
    worktree = _worktree_path(state, worktree_root)
    if worktree.is_symlink() or not worktree.is_dir():
        raise ContractError("recorded task worktree is unavailable")
    top = Path(_git(worktree, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != worktree.resolve():
        raise ContractError("recorded task worktree root does not match")
    if _git(worktree, "branch", "--show-current").stdout.strip() != state["branch"]:
        raise ContractError("task worktree is on the wrong branch")
    if clean:
        _require_clean(worktree, "task worktree")
    return _git(worktree, "rev-parse", "HEAD").stdout.strip()


def _require_lease(state: dict[str, Any], owner: str, run_id: str) -> None:
    lease = state.get("lease")
    if not isinstance(lease, dict):
        raise ContractError("no active lease")
    if lease.get("owner") != owner or lease.get("run_id") != run_id:
        raise ContractError("active lease belongs to another owner or run")
    if _parse_iso(lease["expires_at"]) <= _now():
        raise ContractError("active lease expired; explicit recovery is required")


def _new_lease(owner: str, run_id: str, seconds: int) -> dict[str, str]:
    return {
        "owner": owner,
        "run_id": run_id,
        "expires_at": _iso(_now() + timedelta(seconds=seconds)),
    }


def _active_states(state_root: Path) -> list[str]:
    active: list[str] = []
    for path in sorted(state_root.glob("GLA-*.json")):
        state = _read_state(path)
        if state.get("phase") not in TERMINAL_PHASES:
            active.append(str(state.get("issue_key", path.stem)))
    return active


def _context(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path, Path, str, str, int]:
    values = _load_paths(Path(args.paths))
    primary = _configured_path(values, "primary_repo_root")
    worktrees = _configured_path(values, "task_worktree_root")
    states = _configured_path(values, "task_state_root")
    android_remote = _validate_remote(
        values.get("android_repository_url"),
        ANDROID_REMOTE,
        allow_local=args.allow_local_test_remotes,
        label="android",
    )
    control_remote = _validate_remote(
        values.get("control_repository_url"),
        CONTROL_REMOTE,
        allow_local=args.allow_local_test_remotes,
        label="control",
    )
    _validate_repo(primary, android_remote, "Android")
    return values, primary, worktrees, states, android_remote, control_remote, _lease_seconds(values)


def _create(args: argparse.Namespace) -> dict[str, Any]:
    _, primary, worktree_root, state_root, _, _, lease_seconds = _context(args)
    issue_key = _validate_issue_key(args.issue_key)
    slug = _validate_slug(args.slug)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    if owner != CTO:
        raise ContractError("only GlitcherryCTO may create a slice worktree")
    state_path = _state_path(state_root, issue_key)
    branch = f"feature/{issue_key}-{slug}"
    worktree = worktree_root / f"{issue_key}-{slug}"
    with _state_lock(state_path):
        if state_path.exists():
            raise ContractError("slice state already exists")
        active = _active_states(state_root)
        if active:
            raise ContractError("another active slice state already exists")
        if worktree.exists() or worktree.is_symlink():
            raise ContractError("task worktree path already exists")
        base_sha = _require_current_develop(primary, "canonical Android host clone")
        if _git(primary, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
            raise ContractError("local task branch already exists")
        if _git(primary, "ls-remote", "--exit-code", "--heads", "origin", branch, check=False).returncode == 0:
            raise ContractError("remote task branch already exists")
        _git(primary, "worktree", "add", "-b", branch, str(worktree), "origin/develop")
        head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
        state = {
            "schema_version": SCHEMA_VERSION,
            "issue_id": args.issue_id,
            "issue_key": issue_key,
            "slug": slug,
            "branch": branch,
            "worktree_path": str(worktree),
            "base_sha": base_sha,
            "head_sha": head,
            "reviewed_head": None,
            "phase": "spec",
            "expected_owner": owner,
            "lease": _new_lease(owner, run_id, lease_seconds),
            "primary_implementer": None,
            "review_rejections": 0,
            "last_rejected_head": None,
            "android_pr_number": None,
            "android_merge_sha": None,
            "control_branch": None,
            "control_merge_sha": None,
            "recovery": [],
            "recovery_resume_owner": None,
            "recovery_resume_phase": None,
            "created_at": _iso(_now()),
            "updated_at": _iso(_now()),
            "cleaned_at": None,
        }
        _write_state(state_path, state)
        return state


def _claim(args: argparse.Namespace) -> dict[str, Any]:
    _, _, worktree_root, state_root, _, _, lease_seconds = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        if state["phase"] in TERMINAL_PHASES or state["phase"] == "blocked":
            raise ContractError("terminal or blocked slice cannot be claimed")
        lease = state.get("lease")
        if lease:
            if lease.get("owner") == owner and lease.get("run_id") == run_id:
                lease["expires_at"] = _iso(_now() + timedelta(seconds=lease_seconds))
                state["updated_at"] = _iso(_now())
                _write_state(state_path, state)
                return state
            raise ContractError("active lease is held by another owner or run")
        if state.get("expected_owner") != owner:
            raise ContractError("claim owner does not match expected owner")
        head = _verify_worktree(state, worktree_root)
        if head != state["head_sha"]:
            raise ContractError("task worktree HEAD differs from handed-off HEAD")
        state["lease"] = _new_lease(owner, run_id, lease_seconds)
        state["updated_at"] = _iso(_now())
        _write_state(state_path, state)
        return state


def _renew(args: argparse.Namespace) -> dict[str, Any]:
    _, _, _, state_root, _, _, lease_seconds = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        state["lease"]["expires_at"] = _iso(_now() + timedelta(seconds=lease_seconds))
        state["updated_at"] = _iso(_now())
        _write_state(state_path, state)
        return state


def _handoff(args: argparse.Namespace) -> dict[str, Any]:
    _, _, worktree_root, state_root, _, _, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    next_owner = _validate_owner(args.next_owner)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        head = _verify_worktree(state, worktree_root)
        if state["phase"] == "implementation_fix" and head == state.get("last_rejected_head"):
            raise ContractError("review correction handoff requires a new commit")
        if args.next_phase == "implementation":
            if owner != CTO or next_owner not in IMPLEMENTERS:
                raise ContractError("CTO must assign implementation to one engineer")
            if state.get("primary_implementer") not in {None, next_owner}:
                raise ContractError("slice already has another primary implementer")
            state["primary_implementer"] = next_owner
        if state["phase"] == "recovery" and owner == CTO:
            state["recovery_resume_owner"] = None
            state["recovery_resume_phase"] = None
        state.update(
            {
                "head_sha": head,
                "phase": args.next_phase,
                "expected_owner": next_owner,
                "lease": None,
                "updated_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _reject(args: argparse.Namespace) -> dict[str, Any]:
    _, _, worktree_root, state_root, _, _, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    next_owner = _validate_owner(args.next_owner)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        if state["phase"] != "code_review":
            raise ContractError("rejection is allowed only during code_review")
        if owner != REVIEWER or next_owner != state.get("primary_implementer"):
            raise ContractError("code rejection must return to the primary implementer")
        if state["review_rejections"] >= MAX_REJECTIONS:
            raise ContractError("three Code Review rejection cycles are already exhausted")
        head = _verify_worktree(state, worktree_root)
        state.update(
            {
                "head_sha": head,
                "last_rejected_head": head,
                "review_rejections": state["review_rejections"] + 1,
                "phase": "implementation_fix",
                "expected_owner": next_owner,
                "lease": None,
                "updated_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _approve(args: argparse.Namespace) -> dict[str, Any]:
    _, _, worktree_root, state_root, _, _, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    next_owner = _validate_owner(args.next_owner)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        if state["phase"] != "code_review":
            raise ContractError("approval is allowed only during code_review")
        if owner != REVIEWER or next_owner != CTO:
            raise ContractError("code approval must route from reviewer to CTO")
        head = _verify_worktree(state, worktree_root)
        state.update(
            {
                "head_sha": head,
                "reviewed_head": head,
                "phase": "review_approved",
                "expected_owner": next_owner,
                "lease": None,
                "updated_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _block(args: argparse.Namespace) -> dict[str, Any]:
    _, _, _, state_root, _, _, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    if len(args.reason.strip()) < 8:
        raise ContractError("block reason must name a concrete action")
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        state.update(
            {
                "phase": "blocked",
                "expected_owner": None,
                "lease": None,
                "block_reason": args.reason.strip(),
                "updated_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _recover(args: argparse.Namespace) -> dict[str, Any]:
    _, _, _, state_root, _, _, _ = _context(args)
    operator = _validate_owner(args.operator)
    expected_owner = _validate_owner(args.expected_owner)
    expected_run = _validate_run_id(args.expected_run_id)
    if args.terminated_run_id != expected_run:
        raise ContractError("terminated run proof does not match the active lease")
    if operator != CTO:
        raise ContractError("only GlitcherryCTO may recover a slice lease")
    if len(args.evidence.strip()) < 12:
        raise ContractError("recovery requires bounded exact-run evidence")
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        lease = state.get("lease")
        if not lease or lease.get("owner") != expected_owner or lease.get("run_id") != expected_run:
            raise ContractError("recovery target does not match the active lease")
        state["recovery"].append(
            {
                "owner": expected_owner,
                "run_id": expected_run,
                "evidence": args.evidence.strip(),
                "recorded_at": _iso(_now()),
            }
        )
        state["recovery_resume_owner"] = expected_owner
        state["recovery_resume_phase"] = state["phase"]
        state.update(
            {
                "phase": "recovery",
                "expected_owner": operator,
                "lease": None,
                "updated_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _commit_is_on_develop(repo: Path, sha: str) -> None:
    if not SHA_RE.fullmatch(sha):
        raise ContractError("merge SHA has an unsafe format")
    _fetch(repo)
    if _git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode != 0:
        raise ContractError("merge SHA is unavailable")
    if _git(repo, "merge-base", "--is-ancestor", sha, "origin/develop", check=False).returncode != 0:
        raise ContractError("merge SHA is not reachable from origin/develop")


def _record_merge(args: argparse.Namespace) -> dict[str, Any]:
    values, primary, worktree_root, state_root, _, control_remote, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        if owner != CTO:
            raise ContractError("only GlitcherryCTO may record merge evidence")
        if state["phase"] not in {"review_approved", "integrating"}:
            raise ContractError("merge evidence requires an approved review head")
        if args.kind == "android":
            if not args.pr_number or int(args.pr_number) <= 0:
                raise ContractError("Android merge evidence requires a positive PR number")
            _commit_is_on_develop(primary, args.sha)
            if not state.get("reviewed_head"):
                raise ContractError("reviewed head is missing")
            state["android_pr_number"] = int(args.pr_number)
            state["android_merge_sha"] = args.sha
        else:
            if not state.get("android_merge_sha"):
                raise ContractError("control merge evidence requires Android merge evidence first")
            control = _configured_path(values, "control_repo_root")
            _validate_repo(control, control_remote, "control")
            _commit_is_on_develop(control, args.sha)
            state["control_branch"] = f"docs/status-{state['issue_key']}"
            state["control_merge_sha"] = args.sha
        state["phase"] = "integrating"
        state["updated_at"] = _iso(_now())
        _write_state(state_path, state)
        return state


def _cleanup(args: argparse.Namespace) -> dict[str, Any]:
    values, primary, worktree_root, state_root, _, control_remote, _ = _context(args)
    owner = _validate_owner(args.owner)
    run_id = _validate_run_id(args.run_id)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        state = _read_state(state_path)
        _require_lease(state, owner, run_id)
        if owner != CTO:
            raise ContractError("only GlitcherryCTO may clean an integrated slice")
        if not state.get("android_merge_sha") or not state.get("control_merge_sha"):
            raise ContractError("both Android and control merge evidence are required")
        _commit_is_on_develop(primary, state["android_merge_sha"])
        control = _configured_path(values, "control_repo_root")
        _validate_repo(control, control_remote, "control")
        _commit_is_on_develop(control, state["control_merge_sha"])
        worktree = _worktree_path(state, worktree_root)
        if _verify_worktree(state, worktree_root) != state["head_sha"]:
            raise ContractError("task worktree HEAD changed after the recorded handoff")
        branch = state["branch"]
        _git(primary, "worktree", "remove", str(worktree))
        if worktree.exists():
            raise ContractError("exact task worktree still exists after Git removal")
        if _git(primary, "show-ref", "--verify", f"refs/heads/{branch}", check=False).returncode == 0:
            # Squash-merged feature refs require exact force deletion after both
            # integration SHAs have been recorded on develop.
            _git(primary, "branch", "-D", branch)
        if _git(primary, "ls-remote", "--exit-code", "--heads", "origin", branch, check=False).returncode == 0:
            _git(primary, "push", "origin", "--delete", branch)
        _git(primary, "worktree", "prune")
        _fetch(primary)
        control_branch = state["control_branch"]
        if _git(control, "show-ref", "--verify", f"refs/heads/{control_branch}", check=False).returncode == 0:
            _require_clean(control, "canonical control clone")
            if _git(control, "branch", "--show-current").stdout.strip() == control_branch:
                _git(control, "switch", "develop")
            _git(control, "branch", "-D", control_branch)
        if _git(
            control,
            "ls-remote",
            "--exit-code",
            "--heads",
            "origin",
            control_branch,
            check=False,
        ).returncode == 0:
            _git(control, "push", "origin", "--delete", control_branch)
        _fetch(control)
        state.update(
            {
                "phase": "cleaned",
                "expected_owner": None,
                "lease": None,
                "updated_at": _iso(_now()),
                "cleaned_at": _iso(_now()),
            }
        )
        _write_state(state_path, state)
        return state


def _show(args: argparse.Namespace) -> dict[str, Any]:
    _, _, _, state_root, _, _, _ = _context(args)
    state_path = _state_path(state_root, args.issue_key)
    with _state_lock(state_path):
        return _read_state(state_path)


def _add_identity(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--issue-key", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--run-id", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", required=True)
    parser.add_argument("--allow-local-test-remotes", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--issue-id", required=True)
    create.add_argument("--issue-key", required=True)
    create.add_argument("--slug", required=True)
    create.add_argument("--owner", required=True)
    create.add_argument("--run-id", required=True)

    for name in ("claim", "renew"):
        command = sub.add_parser(name)
        _add_identity(command)

    handoff = sub.add_parser("handoff")
    _add_identity(handoff)
    handoff.add_argument("--next-owner", required=True)
    handoff.add_argument("--next-phase", required=True)

    reject = sub.add_parser("reject")
    _add_identity(reject)
    reject.add_argument("--next-owner", required=True)

    approve = sub.add_parser("approve")
    _add_identity(approve)
    approve.add_argument("--next-owner", required=True)

    block = sub.add_parser("block")
    _add_identity(block)
    block.add_argument("--reason", required=True)

    recover = sub.add_parser("recover")
    recover.add_argument("--issue-key", required=True)
    recover.add_argument("--expected-owner", required=True)
    recover.add_argument("--expected-run-id", required=True)
    recover.add_argument("--terminated-run-id", required=True)
    recover.add_argument("--operator", required=True)
    recover.add_argument("--evidence", required=True)

    merge = sub.add_parser("record-merge")
    _add_identity(merge)
    merge.add_argument("--kind", choices=("android", "control"), required=True)
    merge.add_argument("--sha", required=True)
    merge.add_argument("--pr-number")

    cleanup = sub.add_parser("cleanup")
    _add_identity(cleanup)

    show = sub.add_parser("show")
    show.add_argument("--issue-key", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    commands = {
        "create": _create,
        "claim": _claim,
        "renew": _renew,
        "handoff": _handoff,
        "reject": _reject,
        "approve": _approve,
        "block": _block,
        "recover": _recover,
        "record-merge": _record_merge,
        "cleanup": _cleanup,
        "show": _show,
    }
    try:
        state = commands[args.command](args)
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    _emit(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
