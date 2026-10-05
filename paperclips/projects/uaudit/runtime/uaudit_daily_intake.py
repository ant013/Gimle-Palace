#!/usr/bin/env python3
"""Deterministic authoritative intake for UAudit daily release routines."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INSTALL_SCHEMA = "uaudit-daily-intake-install/v1"
INSTALL_MANIFEST = "uaudit_daily_intake.manifest.json"
CONFIG_SCHEMA = "uaudit-daily-intake-routines/v1"
RESULT_SCHEMA = "uaudit-daily-intake-result/v1"
HANDOFF_SCHEMA = "uaudit-daily-status-handoff/v1"
STATUS_SCHEMA_V1 = "uaudit-daily-slot-status/v1"
STATUS_PROOF_SCHEMA_V2 = "uaudit-daily-slot-status-proof/v2"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}-[1-9][0-9]*$")
VERSION_RE = re.compile(r"^version/(\d+)\.(\d+)$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")

CommandRunner = Callable[[Sequence[str], Path | None], subprocess.CompletedProcess[str]]


class IntakeError(ValueError):
    """Raised when daily intake cannot produce authoritative evidence."""


class SnapshotError(IntakeError):
    """Raised after both authoritative snapshot attempts disagree."""

    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        super().__init__(
            "authoritative refs moved or mismatched across both snapshot attempts"
        )
        self.attempts = attempts


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IntakeError(f"{where} must be an object")
    if set(value) != keys:
        raise IntakeError(f"{where} has invalid fields")
    return value


def _string(value: Any, where: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise IntakeError(f"{where} must be a non-empty trimmed string")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise IntakeError(f"{where} must be single-line")
    return value


def _uuid(value: Any, where: str) -> str:
    text = _string(value, where, maximum=64)
    if not UUID_RE.fullmatch(text):
        raise IntakeError(f"{where} must be a lowercase UUID")
    return text


def _sha(value: Any, where: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise IntakeError(f"{where} must be a lowercase 40-hex SHA")
    return value


def _iso_utc(value: Any, where: str) -> str:
    text = _string(value, where, maximum=64)
    if not text.endswith("Z"):
        raise IntakeError(f"{where} must be UTC with a Z suffix")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise IntakeError(f"{where} is not valid ISO-8601") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise IntakeError(f"{where} must be UTC")
    return text


def _load_json(path: Path, where: str, *, maximum: int = 1024 * 1024) -> Any:
    if path.is_symlink():
        raise IntakeError(f"{where} must not be a symlink")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IntakeError(f"{where} is unreadable") from exc
    if len(raw) > maximum:
        raise IntakeError(f"{where} is too large")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntakeError(f"{where} is not valid JSON") from exc


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_bytes(value)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise IntakeError(f"immutable artifact conflicts: {path.name}")
        return
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _default_runner(
    command: Sequence[str], cwd: Path | None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntakeError(f"command failed to execute: {command[0]}") from exc


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    allowed: set[int] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = runner(command, cwd)
    accepted = allowed or {0}
    if result.returncode not in accepted:
        detail = " ".join(result.stderr.strip().split())[:500]
        raise IntakeError(
            f"command failed ({result.returncode}): {command[0]} {detail}".rstrip()
        )
    return result


def verify_install(manifest_path: Path | None = None) -> dict[str, Any]:
    helper = Path(__file__).resolve()
    manifest_path = (manifest_path or helper.with_name(INSTALL_MANIFEST)).resolve()
    if manifest_path.parent != helper.parent or manifest_path.name != INSTALL_MANIFEST:
        raise IntakeError("intake install manifest must be adjacent to the helper")
    if not manifest_path.is_file() or manifest_path.stat().st_mode & (
        stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    ):
        raise IntakeError("intake install manifest must be a read-only file")
    manifest = _exact(
        _load_json(manifest_path, "intake install manifest", maximum=32 * 1024),
        {"schema_version", "files"},
        "intake install manifest",
    )
    if manifest["schema_version"] != INSTALL_SCHEMA:
        raise IntakeError("unsupported intake install schema")
    files = _exact(
        manifest["files"],
        {
            "uaudit_daily_intake.py",
            "uaudit_daily_routines.json",
            "uaudit_release_resolver.py",
            "uaudit_delivery_contract.py",
        },
        "intake install files",
    )
    for name, expected in files.items():
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            raise IntakeError(f"intake install digest is invalid: {name}")
        path = helper.parent / name
        if path.is_symlink() or not path.is_file():
            raise IntakeError(f"intake install file is invalid: {name}")
        if path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise IntakeError(f"intake install file must be read-only: {name}")
        if _sha256_path(path) != expected:
            raise IntakeError(f"intake install digest mismatch: {name}")
    return {"status": "verified", "manifest_sha256": _sha256_path(manifest_path)}


def _load_config(path: Path, *, allow_file_url: bool) -> tuple[dict[str, Any], str]:
    value = _exact(
        _load_json(path, "daily intake routines", maximum=128 * 1024),
        {"schema_version", "source_config_sha256", "routines"},
        "daily intake routines",
    )
    if value["schema_version"] != CONFIG_SCHEMA:
        raise IntakeError("unsupported daily intake routines schema")
    if not isinstance(value["source_config_sha256"], str) or not SHA256_RE.fullmatch(
        value["source_config_sha256"]
    ):
        raise IntakeError("daily intake source config digest is invalid")
    if not isinstance(value["routines"], list) or not value["routines"]:
        raise IntakeError("daily intake routines must be a non-empty list")
    seen: set[str] = set()
    for index, item in enumerate(value["routines"]):
        routine = _exact(
            item,
            {
                "id",
                "live_routine_id",
                "app_id",
                "routine_key",
                "platform",
                "branch",
                "base_branch",
                "repo_url",
                "repo_path",
                "cursor_path",
                "lock_path",
            },
            f"daily intake routines[{index}]",
        )
        for key in ("id", "app_id", "routine_key"):
            text = _string(
                routine[key], f"daily intake routines[{index}].{key}", maximum=128
            )
            if not NAME_RE.fullmatch(text.replace(".", "_")):
                raise IntakeError(f"daily intake routines[{index}].{key} is invalid")
        routine["live_routine_id"] = _uuid(
            routine["live_routine_id"],
            f"daily intake routines[{index}].live_routine_id",
        )
        if routine["id"] in seen:
            raise IntakeError("daily intake routine ids must be unique")
        seen.add(routine["id"])
        if routine["platform"] not in {"android", "ios"}:
            raise IntakeError("daily intake routine platform is invalid")
        if not VERSION_RE.fullmatch(
            _string(routine["branch"], "daily intake release branch")
        ):
            raise IntakeError("daily intake release branch is invalid")
        if routine["base_branch"] != "master":
            raise IntakeError("daily intake base_branch must be master")
        repo_url = _string(routine["repo_url"], "daily intake repo_url")
        if not repo_url.startswith("https://") and not (
            allow_file_url and repo_url.startswith("file://")
        ):
            raise IntakeError("daily intake repo_url must be configured HTTPS")
        for key in ("repo_path", "cursor_path", "lock_path"):
            if not Path(
                _string(routine[key], f"daily intake {key}", maximum=2048)
            ).is_absolute():
                raise IntakeError(f"daily intake {key} must be absolute")
    return value, _sha256_path(path)


def _next_branch(branch: str) -> str:
    match = VERSION_RE.fullmatch(branch)
    assert match
    major, minor = map(int, match.groups())
    return f"version/{major}.{minor + 1}"


def _validate_envelopes(
    issue_path: Path, run_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    issue = _exact(
        _load_json(issue_path, "issue envelope", maximum=32 * 1024),
        {"id", "identifier", "createdAt", "originKind", "originId", "originRunId"},
        "issue envelope",
    )
    run = _exact(
        _load_json(run_path, "routine run envelope", maximum=32 * 1024),
        {"id", "routineId", "linkedIssueId", "source", "triggeredAt"},
        "routine run envelope",
    )
    issue["id"] = _uuid(issue["id"], "issue envelope.id")
    identifier = _string(issue["identifier"], "issue envelope.identifier", maximum=64)
    if not ISSUE_RE.fullmatch(identifier):
        raise IntakeError("issue envelope.identifier is invalid")
    issue["identifier"] = identifier
    issue["createdAt"] = _iso_utc(issue["createdAt"], "issue envelope.createdAt")
    if issue["originKind"] != "routine_execution":
        raise IntakeError("issue envelope.originKind must be routine_execution")
    issue["originId"] = _uuid(issue["originId"], "issue envelope.originId")
    issue["originRunId"] = _uuid(issue["originRunId"], "issue envelope.originRunId")
    run["id"] = _uuid(run["id"], "routine run envelope.id")
    run["routineId"] = _uuid(run["routineId"], "routine run envelope.routineId")
    run["linkedIssueId"] = _uuid(
        run["linkedIssueId"], "routine run envelope.linkedIssueId"
    )
    if run["source"] != "schedule":
        raise IntakeError("routine run envelope.source must be schedule")
    run["triggeredAt"] = _iso_utc(
        run["triggeredAt"], "routine run envelope.triggeredAt"
    )
    if issue["originId"] != run["routineId"]:
        raise IntakeError("issue/routine origin mismatch")
    if issue["originRunId"] != run["id"]:
        raise IntakeError("issue/routine run mismatch")
    if issue["id"] != run["linkedIssueId"]:
        raise IntakeError("routine run linked issue mismatch")
    return issue, run


def _ls_remote(
    runner: CommandRunner, repo_url: str, branches: Mapping[str, str]
) -> dict[str, str | None]:
    refs = [f"refs/heads/{branch}" for branch in branches.values()]
    result = _run(runner, ["git", "ls-remote", "--heads", "--refs", repo_url, *refs])
    by_ref: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or not SHA_RE.fullmatch(fields[0]) or fields[1] not in refs:
            raise IntakeError("git ls-remote returned unexpected output")
        if fields[1] in by_ref:
            raise IntakeError("git ls-remote returned a duplicate ref")
        by_ref[fields[1]] = fields[0]
    return {
        name: by_ref.get(f"refs/heads/{branch}") for name, branch in branches.items()
    }


def _scoped_ref(run_id: str, label: str) -> str:
    ref = f"refs/uaudit-intake/{run_id}/{label}"
    if not NAME_RE.fullmatch(label):
        raise IntakeError("intake ref label is invalid")
    return ref


def _fetch_snapshot(
    runner: CommandRunner,
    repo: Path,
    repo_url: str,
    branches: Mapping[str, str],
    run_id: str,
    observed: Mapping[str, str | None],
) -> dict[str, str | None]:
    refspecs: list[str] = []
    for label, branch in branches.items():
        target = _scoped_ref(run_id, label)
        if observed[label] is None:
            _run(runner, ["git", "update-ref", "-d", target], cwd=repo)
        else:
            refspecs.append(f"+refs/heads/{branch}:{target}")
    if refspecs:
        _run(
            runner,
            ["git", "fetch", "--no-tags", "--force", repo_url, *refspecs],
            cwd=repo,
        )
    fetched: dict[str, str | None] = {}
    for label in branches:
        if observed[label] is None:
            fetched[label] = None
            continue
        result = _run(
            runner,
            [
                "git",
                "rev-parse",
                "--verify",
                f"{_scoped_ref(run_id, label)}^{{commit}}",
            ],
            cwd=repo,
        )
        fetched[label] = _sha(result.stdout.strip(), f"fetched {label}")
    return fetched


def _authoritative_snapshot(
    runner: CommandRunner,
    repo: Path,
    repo_url: str,
    branches: Mapping[str, str],
    run_id: str,
) -> tuple[dict[str, str | None], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for number in (1, 2):
        started_at = _now_utc()
        before = _ls_remote(runner, repo_url, branches)
        fetched = _fetch_snapshot(runner, repo, repo_url, branches, run_id, before)
        after = _ls_remote(runner, repo_url, branches)
        stable = before == fetched == after
        attempts.append(
            {
                "attempt": number,
                "started_at": started_at,
                "completed_at": _now_utc(),
                "observation_a": before,
                "fetched": fetched,
                "observation_b": after,
                "stable": stable,
            }
        )
        if stable:
            return after, {"attempts": attempts, "selected_attempt": number}
    raise SnapshotError(attempts)


def _is_ancestor(
    runner: CommandRunner, repo: Path, ancestor: str, descendant: str
) -> bool:
    result = _run(
        runner,
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        allowed={0, 1},
    )
    return result.returncode == 0


def _invoke_json(
    command: Sequence[str], *, runner: CommandRunner, cwd: Path | None = None
) -> dict[str, Any]:
    result = _run(runner, command, cwd=cwd)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise IntakeError(f"{command[0]} returned invalid JSON") from exc
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise IntakeError(f"{command[0]} returned an unsuccessful result")
    return value


def _artifact(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": _sha256_path(path)}


def _validate_existing_result(
    output_dir: Path,
    issue: Mapping[str, Any],
    expected_manifest_sha: str,
    expected_routine_id: str,
) -> dict[str, Any] | None:
    marker = output_dir / "intake-result.json"
    if not marker.exists():
        return None
    result = _load_json(marker, "intake result", maximum=256 * 1024)
    if not isinstance(result, dict) or result.get("schema_version") != RESULT_SCHEMA:
        raise IntakeError("existing intake result is invalid")
    if (
        result.get("issue_identifier") != issue["identifier"]
        or result.get("origin_run_id") != issue["originRunId"]
        or result.get("routine_id") != expected_routine_id
    ):
        raise IntakeError(
            "existing intake result belongs to a different execution or routine"
        )
    if result.get("install_manifest_sha256") != expected_manifest_sha:
        raise IntakeError(
            "existing intake result belongs to a different installed generation"
        )
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise IntakeError("existing intake result has invalid artifacts")
    for name, item in artifacts.items():
        if not isinstance(name, str):
            raise IntakeError("existing intake result artifact name is invalid")
        entry = _exact(item, {"path", "sha256"}, f"existing intake artifact {name}")
        configured_artifact = Path(
            _string(
                entry["path"], f"existing intake artifact {name}.path", maximum=2048
            )
        )
        if configured_artifact.is_symlink():
            raise IntakeError(f"existing intake artifact is a symlink: {name}")
        artifact_path = configured_artifact.resolve()
        if artifact_path.parent != output_dir or not artifact_path.is_file():
            raise IntakeError(f"existing intake artifact is outside its bundle: {name}")
        if entry["sha256"] != _sha256_path(artifact_path):
            raise IntakeError(f"existing intake artifact digest mismatch: {name}")
    return result


def _validate_retained_lock(
    lock_dir: Path, result: Mapping[str, Any], issue: Mapping[str, Any]
) -> None:
    if not lock_dir.is_dir() or lock_dir.is_symlink():
        raise IntakeError("completed audit intake has lost its retained routine lock")
    owner = _exact(
        _load_json(
            lock_dir / "intake-owner.json", "intake lock owner", maximum=16 * 1024
        ),
        {
            "schema_version",
            "issue_identifier",
            "origin_run_id",
            "routine_id",
            "output_dir",
            "pid",
            "hostname",
            "created_at",
        },
        "intake lock owner",
    )
    metadata = _exact(
        _load_json(
            lock_dir / "metadata.json", "intake lock metadata", maximum=16 * 1024
        ),
        {
            "schema_version",
            "issue_identifier",
            "routine_id",
            "from_sha",
            "to_sha",
            "run_binding_sha256",
        },
        "intake lock metadata",
    )
    if (
        owner.get("issue_identifier") != issue["identifier"]
        or owner.get("origin_run_id") != issue["originRunId"]
        or owner.get("routine_id") != result.get("routine_id")
        or metadata.get("issue_identifier") != issue["identifier"]
        or metadata.get("routine_id") != result.get("routine_id")
        or metadata.get("to_sha") != result.get("selected_head")
    ):
        raise IntakeError("completed audit intake retained lock binding mismatch")


def _lock_owner(
    lock_dir: Path,
    *,
    issue: Mapping[str, Any],
    routine_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    owner = _exact(
        _load_json(
            lock_dir / "intake-owner.json", "intake lock owner", maximum=16 * 1024
        ),
        {
            "schema_version",
            "issue_identifier",
            "origin_run_id",
            "routine_id",
            "output_dir",
            "pid",
            "hostname",
            "created_at",
        },
        "intake lock owner",
    )
    _iso_utc(owner["created_at"], "intake lock owner.created_at")
    if (
        not isinstance(owner["pid"], int)
        or isinstance(owner["pid"], bool)
        or owner["pid"] <= 0
    ):
        raise IntakeError("intake lock owner.pid is invalid")
    _string(owner["hostname"], "intake lock owner.hostname", maximum=255)
    stored_output = Path(
        _string(owner["output_dir"], "intake lock owner.output_dir", maximum=2048)
    )
    if not stored_output.is_absolute():
        raise IntakeError("intake lock owner.output_dir must be absolute")
    owner["same_execution"] = (
        owner["issue_identifier"] == issue["identifier"]
        and owner["origin_run_id"] == issue["originRunId"]
        and owner["routine_id"] == routine_id
        and stored_output.resolve() == output_dir
    )
    return owner


def _owner_process_is_active(owner: Mapping[str, Any]) -> bool:
    if owner.get("pid") == os.getpid():
        return False
    if owner.get("hostname") != socket.gethostname():
        return True
    try:
        os.kill(int(owner["pid"]), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _discard_lock(lock_dir: Path) -> None:
    if not lock_dir.exists():
        return
    quarantine = Path(
        tempfile.mkdtemp(prefix=f".{lock_dir.name}.released.", dir=lock_dir.parent)
    )
    quarantine.rmdir()
    try:
        os.rename(lock_dir, quarantine)
    except FileNotFoundError:
        return
    shutil.rmtree(quarantine)


def _acquire_or_resume_lock(
    lock_dir: Path,
    *,
    issue: Mapping[str, Any],
    routine_id: str,
    output_dir: Path,
) -> None:
    owner_value = {
        "schema_version": RESULT_SCHEMA,
        "issue_identifier": issue["identifier"],
        "origin_run_id": issue["originRunId"],
        "routine_id": routine_id,
        "output_dir": str(output_dir),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": _now_utc(),
    }
    for _attempt in range(3):
        try:
            lock_dir.mkdir()
        except FileExistsError:
            if lock_dir.is_symlink() or not lock_dir.is_dir():
                raise IntakeError("daily routine lock path is invalid")
            try:
                owner = _lock_owner(
                    lock_dir,
                    issue=issue,
                    routine_id=routine_id,
                    output_dir=output_dir,
                )
            except IntakeError as exc:
                age = max(
                    0.0,
                    datetime.now(timezone.utc).timestamp() - lock_dir.stat().st_mtime,
                )
                if age < 300:
                    raise IntakeError(
                        "daily routine lock is held without recoverable ownership"
                    ) from exc
                _discard_lock(lock_dir)
                continue
            if owner["same_execution"]:
                if _owner_process_is_active(owner):
                    raise IntakeError(
                        "daily routine intake is already active for this execution"
                    )
                return
            if (lock_dir / "metadata.json").exists():
                raise IntakeError(
                    "daily routine lock is retained by an audit awaiting reconciliation"
                )
            previous_result = Path(owner["output_dir"]) / "intake-result.json"
            if previous_result.is_file() and not previous_result.is_symlink():
                value = _load_json(
                    previous_result, "previous intake result", maximum=256 * 1024
                )
                if (
                    isinstance(value, dict)
                    and value.get("origin_run_id") == owner["origin_run_id"]
                    and value.get("next_action") == "daily_status"
                ):
                    _discard_lock(lock_dir)
                    continue
                raise IntakeError(
                    "daily routine lock has a committed non-status result"
                )
            if _owner_process_is_active(owner):
                raise IntakeError("daily routine lock is held by an active intake")
            _discard_lock(lock_dir)
            continue
        _atomic_json(lock_dir / "intake-owner.json", owner_value)
        return
    raise IntakeError("daily routine lock recovery did not converge")


def _release_owned_lock(lock_dir: Path, issue: Mapping[str, Any]) -> None:
    if not lock_dir.exists():
        return
    try:
        owner = _load_json(
            lock_dir / "intake-owner.json", "intake lock owner", maximum=16 * 1024
        )
    except IntakeError:
        return
    if (
        isinstance(owner, dict)
        and owner.get("issue_identifier") == issue["identifier"]
        and owner.get("origin_run_id") == issue["originRunId"]
    ):
        _discard_lock(lock_dir)


def run_intake(
    *,
    routine_id: str,
    issue_envelope: Path,
    routine_run_envelope: Path,
    output_dir: Path,
    manifest_path: Path | None = None,
    runner: CommandRunner = _default_runner,
    allow_file_url: bool = False,
) -> dict[str, Any]:
    install = verify_install(manifest_path)
    helper_dir = Path(__file__).resolve().parent
    config, config_sha = _load_config(
        helper_dir / "uaudit_daily_routines.json", allow_file_url=allow_file_url
    )
    issue, routine_run = _validate_envelopes(issue_envelope, routine_run_envelope)
    if output_dir.is_symlink():
        raise IntakeError("output directory must not be a symlink")
    output_dir = output_dir.resolve()
    if (
        output_dir.name != issue["originRunId"]
        or output_dir.parent.name != f"{issue['identifier']}-intake"
    ):
        raise IntakeError("output directory must be issue- and run-scoped")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    matches = [item for item in config["routines"] if item["id"] == routine_id]
    if len(matches) != 1:
        raise IntakeError("routine id is not uniquely configured")
    routine = matches[0]
    if routine_run["routineId"] != routine["live_routine_id"]:
        raise IntakeError("routine execution does not match configured live routine")
    configured_repo = Path(routine["repo_path"])
    configured_cursor = Path(routine["cursor_path"])
    configured_lock = Path(routine["lock_path"])
    if (
        configured_repo.is_symlink()
        or configured_cursor.is_symlink()
        or configured_lock.is_symlink()
    ):
        raise IntakeError("configured runtime paths must not be symlinks")
    repo = configured_repo.resolve()
    cursor_path = configured_cursor.resolve()
    lock_dir = configured_lock.resolve()
    existing = _validate_existing_result(
        output_dir, issue, install["manifest_sha256"], routine_id
    )
    if existing is not None:
        if existing.get("next_action") == "audit":
            _validate_retained_lock(lock_dir, existing, issue)
        else:
            _release_owned_lock(lock_dir, issue)
        return existing
    if not repo.is_dir():
        raise IntakeError("configured repository path is invalid")
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    _acquire_or_resume_lock(
        lock_dir,
        issue=issue,
        routine_id=routine_id,
        output_dir=output_dir,
    )
    retained_lock = False
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{issue['originRunId']}.", dir=output_dir.parent)
    )
    try:
        cursor = _load_json(cursor_path, "daily audit cursor", maximum=64 * 1024)
        if not isinstance(cursor, dict):
            raise IntakeError("daily audit cursor must be an object")
        cursor_sha = _sha(
            cursor.get("last_successfully_audited_sha"), "daily audit cursor SHA"
        )
        assert cursor_sha is not None
        branches = {
            "base": routine["base_branch"],
            "current": routine["branch"],
            "next": _next_branch(routine["branch"]),
        }
        try:
            refs, snapshot_evidence = _authoritative_snapshot(
                runner,
                repo,
                routine["repo_url"],
                branches,
                issue["originRunId"],
            )
        except SnapshotError as exc:
            failures_root = output_dir.parent / f"{issue['originRunId']}-failures"
            if failures_root.is_symlink():
                raise IntakeError(
                    "snapshot failure evidence root must not be a symlink"
                ) from exc
            failures_root.mkdir(parents=True, exist_ok=True)
            failure_dir = Path(
                tempfile.mkdtemp(prefix="snapshot.", dir=failures_root)
            ).resolve()
            _atomic_json(
                failure_dir / "git-evidence.json",
                {
                    "schema_version": RESULT_SCHEMA,
                    "repo_url": routine["repo_url"],
                    "installed_config_sha256": config_sha,
                    "routine_id": routine["id"],
                    "origin_run_id": issue["originRunId"],
                    "branches": branches,
                    "attempts": exc.attempts,
                    "selected_attempt": None,
                },
            )
            _atomic_json(
                failure_dir / "intake-error.json",
                {
                    "schema_version": RESULT_SCHEMA,
                    "issue_identifier": issue["identifier"],
                    "origin_run_id": issue["originRunId"],
                    "routine_id": routine["id"],
                    "error": str(exc),
                },
            )
            raise IntakeError(f"{exc}; evidence: {failure_dir}") from exc
        base_head = refs["base"]
        current_head = refs["current"]
        next_head = refs["next"]
        if base_head is None:
            raise IntakeError("configured base branch is proven absent")
        _run(runner, ["git", "cat-file", "-e", f"{cursor_sha}^{{commit}}"], cwd=repo)
        resolver_input = {
            "cursor_sha": cursor_sha,
            "release_branch": routine["branch"],
            "release_head": current_head,
            "master_anchor_sha": None,
            "master_head": base_head,
            "cursor_is_ancestor_of_release": None
            if current_head is None
            else _is_ancestor(runner, repo, cursor_sha, current_head),
            "cursor_is_ancestor_of_master": _is_ancestor(
                runner, repo, cursor_sha, base_head
            ),
            "master_is_ancestor_of_release": None
            if current_head is None
            else _is_ancestor(runner, repo, base_head, current_head),
            "next_release_branch": branches["next"],
            "next_release_head": next_head,
            "master_is_ancestor_of_next_release": None
            if next_head is None
            else _is_ancestor(runner, repo, base_head, next_head),
            "cursor_is_ancestor_of_next_release": None
            if next_head is None
            else _is_ancestor(runner, repo, cursor_sha, next_head),
            "old_series_equivalence": "unavailable",
        }
        git_evidence = {
            "schema_version": RESULT_SCHEMA,
            "repo_url": routine["repo_url"],
            "installed_config_sha256": config_sha,
            "routine_id": routine["id"],
            "origin_run_id": issue["originRunId"],
            "branches": branches,
            "refs": refs,
            **snapshot_evidence,
        }
        git_path = temporary / "git-evidence.json"
        resolver_input_path = temporary / "resolver-input.json"
        resolver_output_path = temporary / "resolver-output.json"
        _atomic_json(git_path, git_evidence)
        _atomic_json(resolver_input_path, resolver_input)
        resolver_path = helper_dir / "uaudit_release_resolver.py"
        resolver_manifest = helper_dir / "uaudit_release_resolver.manifest.json"
        resolver_output = _invoke_json(
            [
                sys.executable,
                str(resolver_path),
                "--manifest",
                str(resolver_manifest),
                "--input",
                str(resolver_input_path),
            ],
            runner=runner,
        )
        _atomic_json(resolver_output_path, resolver_output)
        kind = resolver_output.get("kind")
        selected_head = _sha(
            resolver_output.get("selected_head"),
            "resolver selected head",
            nullable=True,
        )
        result: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA,
            "issue_identifier": issue["identifier"],
            "origin_run_id": issue["originRunId"],
            "routine_id": routine["id"],
            "platform": routine["platform"],
            "resolution_kind": kind,
            "selected_head": selected_head,
            "next_action": "daily_status" if kind == "no_change" else "audit",
            "audit_kind": None
            if kind == "no_change"
            else (
                "daily_delta"
                if kind in {"daily", "bridge", "transition"}
                else "forced_full"
            ),
            "artifacts": {
                "git_evidence": _artifact(git_path),
                "resolver_input": _artifact(resolver_input_path),
                "resolver_output": _artifact(resolver_output_path),
            },
            "install_manifest_sha256": install["manifest_sha256"],
        }
        final_paths = {
            name: str(output_dir / Path(item["path"]).name)
            for name, item in result["artifacts"].items()
        }
        for name, path in final_paths.items():
            result["artifacts"][name]["path"] = path
        if kind == "no_change":
            routine_digest = _sha256_bytes(_canonical_bytes(routine))
            descriptor_path = temporary / "daily-status-descriptor.json"
            proof_path = temporary / "daily-status-slot-proof.json"
            descriptor = {
                "schema_version": STATUS_SCHEMA_V1,
                "app_id": routine["app_id"],
                "routine_key": routine["routine_key"],
                "platform": routine["platform"],
                "config_sha256": routine_digest,
            }
            _atomic_json(descriptor_path, descriptor)
            proof = {
                "schema_version": STATUS_PROOF_SCHEMA_V2,
                "routine_key": routine["routine_key"],
                "platform": routine["platform"],
                "scheduled_utc_slot": routine_run["triggeredAt"],
                "descriptor_sha256": _sha256_path(descriptor_path),
                "source": "paperclip_scheduled",
                "issue_id": issue["id"],
                "issue_identifier": issue["identifier"],
                "origin_kind": issue["originKind"],
                "origin_id": issue["originId"],
                "origin_run_id": issue["originRunId"],
            }
            _atomic_json(proof_path, proof)
            delivery = helper_dir / "uaudit_delivery_contract.py"
            delivery_manifest = helper_dir / "uaudit_delivery_contract.manifest.json"
            _invoke_json(
                [
                    sys.executable,
                    str(delivery),
                    "verify-install",
                    "--manifest",
                    str(delivery_manifest),
                ],
                runner=runner,
            )
            prepared = _invoke_json(
                [
                    sys.executable,
                    str(delivery),
                    "prepare-daily-status",
                    "--state-root",
                    str(cursor_path.parent),
                    "--descriptor",
                    str(descriptor_path),
                    "--slot-proof",
                    str(proof_path),
                    "--issue-identifier",
                    issue["identifier"],
                    "--outcome",
                    "no_change",
                    "--selected-head",
                    str(selected_head),
                    "--reason",
                    str(resolver_output.get("reason", "No new commits.")),
                    "--attempt-id",
                    issue["originRunId"],
                    "--created-at",
                    issue["createdAt"],
                ],
                runner=runner,
            )
            status_run = Path(
                _string(
                    prepared.get("run_dir"), "prepared status run_dir", maximum=2048
                )
            ).resolve()
            summary_path = status_run / "status-summary.json"
            summary_sha = _sha256_path(summary_path)
            if prepared.get("summary_sha256") != summary_sha:
                raise IntakeError("prepared daily status summary digest mismatch")
            descriptor_final = output_dir / descriptor_path.name
            proof_final = output_dir / proof_path.name
            handoff_path = temporary / "daily-status-handoff.json"
            handoff = {
                "schema_version": HANDOFF_SCHEMA,
                "issue_identifier": issue["identifier"],
                "origin_run_id": issue["originRunId"],
                "descriptor": {
                    "path": str(descriptor_final),
                    "sha256": _sha256_path(descriptor_path),
                },
                "slot_proof": {
                    "path": str(proof_final),
                    "sha256": _sha256_path(proof_path),
                },
                "status": {
                    "state_root": str(cursor_path.parent),
                    "run_dir": str(status_run),
                    "summary_sha256": summary_sha,
                    "outcome": "no_change",
                    "selected_head": selected_head,
                    "reason": str(resolver_output.get("reason", "No new commits.")),
                    "attempt_id": issue["originRunId"],
                    "created_at": issue["createdAt"],
                },
            }
            _atomic_json(handoff_path, handoff)
            result["artifacts"].update(
                {
                    "descriptor": {
                        "path": str(descriptor_final),
                        "sha256": _sha256_path(descriptor_path),
                    },
                    "slot_proof": {
                        "path": str(proof_final),
                        "sha256": _sha256_path(proof_path),
                    },
                    "handoff": {
                        "path": str(output_dir / handoff_path.name),
                        "sha256": _sha256_path(handoff_path),
                    },
                }
            )
            result["status_run_dir"] = str(status_run)
            result["status_summary_sha256"] = summary_sha
        else:
            if selected_head is None:
                raise IntakeError("audit resolution is missing selected head")
            _atomic_json(
                lock_dir / "metadata.json",
                {
                    "schema_version": 1,
                    "issue_identifier": issue["identifier"],
                    "routine_id": routine["id"],
                    "from_sha": cursor_sha,
                    "to_sha": selected_head,
                    "run_binding_sha256": None,
                },
            )
        _atomic_json(temporary / "intake-result.json", result)
        try:
            os.replace(temporary, output_dir)
        except OSError as exc:
            existing = _validate_existing_result(
                output_dir, issue, install["manifest_sha256"], routine_id
            )
            if existing is None:
                raise IntakeError("could not publish intake result") from exc
            result = existing
        if kind != "no_change":
            retained_lock = True
        return result
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if not retained_lock:
            _release_owned_lock(lock_dir, issue)


def verify_handoff(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_issue_identifier: str | None = None,
    expected_origin_run_id: str | None = None,
    manifest_path: Path | None = None,
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    verify_install(manifest_path)
    if path.is_symlink():
        raise IntakeError("daily status handoff must not be a symlink")
    handoff_path = path.resolve()
    if expected_sha256 is not None:
        if not SHA256_RE.fullmatch(expected_sha256):
            raise IntakeError("daily status handoff expected digest is invalid")
        if _sha256_path(handoff_path) != expected_sha256:
            raise IntakeError("daily status handoff digest mismatch")
    handoff = _exact(
        _load_json(handoff_path, "daily status handoff", maximum=128 * 1024),
        {
            "schema_version",
            "issue_identifier",
            "origin_run_id",
            "descriptor",
            "slot_proof",
            "status",
        },
        "daily status handoff",
    )
    if handoff["schema_version"] != HANDOFF_SCHEMA:
        raise IntakeError("unsupported daily status handoff schema")
    _uuid(handoff["origin_run_id"], "daily status handoff.origin_run_id")
    issue = _string(
        handoff["issue_identifier"], "daily status handoff.issue_identifier", maximum=64
    )
    if not ISSUE_RE.fullmatch(issue):
        raise IntakeError("daily status handoff issue identifier is invalid")
    if expected_issue_identifier is not None and issue != expected_issue_identifier:
        raise IntakeError("daily status handoff belongs to a different issue")
    if (
        expected_origin_run_id is not None
        and handoff["origin_run_id"] != expected_origin_run_id
    ):
        raise IntakeError("daily status handoff belongs to a different routine run")
    helper_dir = Path(__file__).resolve().parent
    artifacts: dict[str, Path] = {}
    for key in ("descriptor", "slot_proof"):
        item = _exact(handoff[key], {"path", "sha256"}, f"daily status handoff.{key}")
        configured_artifact = Path(
            _string(item["path"], f"daily status handoff.{key}.path", maximum=2048)
        )
        if configured_artifact.is_symlink():
            raise IntakeError(f"daily status handoff {key} must not be a symlink")
        artifact_path = configured_artifact.resolve()
        if artifact_path.parent != handoff_path.parent:
            raise IntakeError(f"daily status handoff {key} escapes its bundle")
        if item["sha256"] != _sha256_path(artifact_path):
            raise IntakeError(f"daily status handoff {key} digest mismatch")
        artifacts[key] = artifact_path
    status = _exact(
        handoff["status"],
        {
            "state_root",
            "run_dir",
            "summary_sha256",
            "outcome",
            "selected_head",
            "reason",
            "attempt_id",
            "created_at",
        },
        "daily status handoff.status",
    )
    if status["attempt_id"] != handoff["origin_run_id"]:
        raise IntakeError("daily status handoff attempt does not match its routine run")
    delivery = helper_dir / "uaudit_delivery_contract.py"
    prepared = _invoke_json(
        [
            sys.executable,
            str(delivery),
            "prepare-daily-status",
            "--state-root",
            _string(status["state_root"], "daily status state_root", maximum=2048),
            "--descriptor",
            str(artifacts["descriptor"]),
            "--slot-proof",
            str(artifacts["slot_proof"]),
            "--issue-identifier",
            issue,
            "--outcome",
            _string(status["outcome"], "daily status outcome"),
            "--selected-head",
            str(_sha(status["selected_head"], "daily status selected_head")),
            "--reason",
            _string(status["reason"], "daily status reason", maximum=280),
            "--attempt-id",
            _string(status["attempt_id"], "daily status attempt_id", maximum=128),
            "--created-at",
            _iso_utc(status["created_at"], "daily status created_at"),
        ],
        runner=runner,
    )
    run_dir = Path(
        _string(prepared.get("run_dir"), "verified status run_dir", maximum=2048)
    ).resolve()
    if (
        run_dir
        != Path(
            _string(status["run_dir"], "daily status run_dir", maximum=2048)
        ).resolve()
    ):
        raise IntakeError("daily status handoff run directory mismatch")
    summary_sha = _sha256_path(run_dir / "status-summary.json")
    if (
        summary_sha != status["summary_sha256"]
        or prepared.get("summary_sha256") != summary_sha
    ):
        raise IntakeError("daily status handoff summary digest mismatch")
    summary = _load_json(
        run_dir / "status-summary.json",
        "prepared daily status summary",
        maximum=64 * 1024,
    )
    identity = summary.get("identity") if isinstance(summary, dict) else None
    if (
        not isinstance(identity, dict)
        or summary.get("issue_identifier") != issue
        or identity.get("origin_run_id") != handoff["origin_run_id"]
        or summary.get("attempt_id") != handoff["origin_run_id"]
    ):
        raise IntakeError("daily status handoff summary origin binding mismatch")
    return {
        "status": "verified",
        "run_dir": str(run_dir),
        "summary_sha256": summary_sha,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-install")
    verify.add_argument("--manifest", type=Path)
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--manifest", type=Path)
    resolve.add_argument("--routine-id", required=True)
    resolve.add_argument("--issue-envelope", type=Path, required=True)
    resolve.add_argument("--routine-run-envelope", type=Path, required=True)
    resolve.add_argument("--output-dir", type=Path, required=True)
    handoff = subparsers.add_parser("verify-handoff")
    handoff.add_argument("--manifest", type=Path)
    handoff.add_argument("--handoff", type=Path, required=True)
    handoff.add_argument("--expected-sha256", required=True)
    handoff.add_argument("--expected-issue-identifier", required=True)
    handoff.add_argument("--expected-origin-run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify-install":
            result = verify_install(args.manifest)
        elif args.command == "resolve":
            result = run_intake(
                routine_id=args.routine_id,
                issue_envelope=args.issue_envelope,
                routine_run_envelope=args.routine_run_envelope,
                output_dir=args.output_dir,
                manifest_path=args.manifest,
            )
        else:
            result = verify_handoff(
                args.handoff,
                expected_sha256=args.expected_sha256,
                expected_issue_identifier=args.expected_issue_identifier,
                expected_origin_run_id=args.expected_origin_run_id,
                manifest_path=args.manifest,
            )
    except (IntakeError, OSError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True
            ),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {"ok": True, **result},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
