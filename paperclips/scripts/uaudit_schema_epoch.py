#!/usr/bin/env python3
"""Fail closed when a UAudit deploy would cross an incompatible cursor epoch."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


CURSOR_V2_SCHEMA = "uaudit-daily-cursor/v2"
PLATFORMS = ("android", "ios")
MAX_CURSOR_BYTES = 64 * 1024
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISSUE_RE = re.compile(r"^[A-Z][A-Z0-9]{0,15}-[1-9][0-9]*$")
RELEASE_BRANCH_RE = re.compile(r"^version/(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")

CursorVersion = Literal["v1", "v2"]
Mode = Literal["full", "runtime-only"]

CURSOR_METADATA_KEYS = {
    "last_successful_issue",
    "last_successful_at",
    "last_delivery_summary_sha256",
    "last_telegram_message_id",
}
V1_REQUIRED_KEYS = {"last_successfully_audited_sha"}
V2_REQUIRED_KEYS = {
    "schema_version",
    "active_release_branch",
    "last_successfully_audited_sha",
    *CURSOR_METADATA_KEYS,
}


class EpochError(ValueError):
    """The requested deploy is incompatible with the live UAudit schema epoch."""


def _read_regular_file(path: Path) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise EpochError(f"missing UAudit cursor: {path}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise EpochError(f"UAudit cursor must be a regular non-symlink file: {path}")
    if before.st_size > MAX_CURSOR_BYTES:
        raise EpochError(f"UAudit cursor exceeds {MAX_CURSOR_BYTES} bytes: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (before.st_dev, before.st_ino):
                raise EpochError(f"UAudit cursor changed during preflight: {path}")
            raw = stream.read(MAX_CURSOR_BYTES + 1)
    except OSError as exc:
        raise EpochError(f"cannot safely read UAudit cursor: {path}") from exc
    if len(raw) > MAX_CURSOR_BYTES:
        raise EpochError(f"UAudit cursor exceeds {MAX_CURSOR_BYTES} bytes: {path}")
    return raw


def _load_cursor(path: Path) -> dict[str, Any]:
    raw = _read_regular_file(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EpochError(f"malformed UAudit cursor JSON: {path}") from exc
    if not isinstance(value, dict):
        raise EpochError(f"UAudit cursor root must be an object: {path}")
    return value


def _validate_exact_keys(
    cursor: dict[str, Any],
    required: set[str],
    optional: set[str],
    path: Path,
) -> None:
    missing = sorted(required - set(cursor))
    extra = sorted(set(cursor) - required - optional)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if extra:
            details.append(f"extra={','.join(extra)}")
        raise EpochError(f"UAudit cursor has invalid fields ({'; '.join(details)}): {path}")


def _validate_utc(value: Any, field: str, path: Path) -> None:
    if not isinstance(value, str) or not value.endswith("Z") or len(value) > 64:
        raise EpochError(f"UAudit cursor {field} must be a UTC ISO-8601 string: {path}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EpochError(f"UAudit cursor {field} is not valid ISO-8601: {path}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise EpochError(f"UAudit cursor {field} must be UTC: {path}")


def _validate_cursor_metadata(cursor: dict[str, Any], path: Path) -> None:
    audited_sha = cursor["last_successfully_audited_sha"]
    if not isinstance(audited_sha, str) or not GIT_SHA_RE.fullmatch(audited_sha):
        raise EpochError(f"UAudit cursor has invalid audited SHA: {path}")

    issue = cursor.get("last_successful_issue")
    if issue is not None and (not isinstance(issue, str) or not ISSUE_RE.fullmatch(issue)):
        raise EpochError(f"UAudit cursor has invalid last_successful_issue: {path}")
    successful_at = cursor.get("last_successful_at")
    if successful_at is not None:
        _validate_utc(successful_at, "last_successful_at", path)
    summary_sha = cursor.get("last_delivery_summary_sha256")
    if summary_sha is not None and (
        not isinstance(summary_sha, str) or not SHA256_RE.fullmatch(summary_sha)
    ):
        raise EpochError(f"UAudit cursor has invalid delivery summary SHA: {path}")
    message_id = cursor.get("last_telegram_message_id")
    if message_id is not None and (
        not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0
    ):
        raise EpochError(f"UAudit cursor has invalid Telegram message id: {path}")


def cursor_version(path: Path) -> CursorVersion:
    """Validate one canonical cursor and return its schema generation."""

    cursor = _load_cursor(path)
    if cursor.get("schema_version") == CURSOR_V2_SCHEMA:
        _validate_exact_keys(cursor, V2_REQUIRED_KEYS, set(), path)
        branch = cursor["active_release_branch"]
        if not isinstance(branch, str) or not RELEASE_BRANCH_RE.fullmatch(branch):
            raise EpochError(f"UAudit v2 cursor has invalid active release branch: {path}")
        version: CursorVersion = "v2"
    else:
        _validate_exact_keys(cursor, V1_REQUIRED_KEYS, CURSOR_METADATA_KEYS, path)
        version = "v1"
    _validate_cursor_metadata(cursor, path)
    return version


def check_epoch(
    target_schema: int,
    project_root: Path,
    *,
    mode: Mode = "full",
) -> dict[str, Any]:
    """Validate target config compatibility with the live two-platform epoch."""

    if isinstance(target_schema, bool) or not isinstance(target_schema, int):
        raise EpochError("target schema must be an integer")
    if mode not in ("full", "runtime-only"):
        raise EpochError(f"unsupported UAudit deploy mode: {mode}")
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        raise EpochError(f"UAudit project root must be absolute: {root}")

    if mode == "runtime-only":
        if target_schema != 3:
            raise EpochError("UAudit runtime-only requires target schema 3")
        return {
            "status": "compatible",
            "mode": mode,
            "target_schema": target_schema,
            "schema_epoch": "not-checked",
            "cursor_versions": {},
        }

    if target_schema not in (2, 3):
        raise EpochError(f"unsupported UAudit target schema: {target_schema}")
    versions = {
        platform: cursor_version(root / "state" / f"{platform}-version-audit.json")
        for platform in PLATFORMS
    }
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        raise EpochError(
            "mixed UAudit cursor schema epoch: "
            + ", ".join(f"{platform}={versions[platform]}" for platform in PLATFORMS)
        )

    cursor_epoch = unique_versions.pop()
    if target_schema == 3 and cursor_epoch != "v2":
        raise EpochError("UAudit schema 3 requires both platform cursors to be v2")
    if target_schema == 2 and cursor_epoch == "v2":
        raise EpochError("UAudit rollback below the v2 schema epoch is forbidden")

    return {
        "status": "compatible",
        "mode": mode,
        "target_schema": target_schema,
        "schema_epoch": "release-v2" if cursor_epoch == "v2" else "legacy-v1",
        "cursor_versions": versions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-schema", type=int, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("full", "runtime-only"), default="full")
    args = parser.parse_args(argv)
    try:
        result = check_epoch(args.target_schema, args.project_root, mode=args.mode)
    except EpochError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
