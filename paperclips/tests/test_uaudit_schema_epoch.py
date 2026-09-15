from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"
SCRIPT = SCRIPTS / "uaudit_schema_epoch.py"
sys.path.insert(0, str(SCRIPTS))

from uaudit_schema_epoch import EpochError, check_epoch  # noqa: E402


SHA = "a" * 40


def _cursor(version: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "last_successfully_audited_sha": SHA,
        "last_successful_issue": "UNS-625",
        "last_successful_at": "2026-09-15T12:34:56Z",
        "last_delivery_summary_sha256": "b" * 64,
        "last_telegram_message_id": 625,
    }
    if version == "v1":
        return metadata
    if version == "v2":
        return {
            "schema_version": "uaudit-daily-cursor/v2",
            "active_release_branch": "version/0.52",
            **metadata,
        }
    raise AssertionError(f"unsupported test cursor version: {version}")


def _write_epoch(project_root: Path, android: str, ios: str) -> None:
    state = project_root / "state"
    state.mkdir(parents=True)
    (state / "android-version-audit.json").write_text(json.dumps(_cursor(android)))
    (state / "ios-version-audit.json").write_text(json.dumps(_cursor(ios)))


@pytest.mark.parametrize(
    ("target_schema", "android", "ios", "expected_epoch"),
    (
        (2, "v1", "v1", "legacy-v1"),
        (3, "v2", "v2", "release-v2"),
    ),
)
def test_full_deploy_accepts_only_matching_project_wide_epoch(
    tmp_path: Path,
    target_schema: int,
    android: str,
    ios: str,
    expected_epoch: str,
) -> None:
    _write_epoch(tmp_path, android, ios)

    result = check_epoch(target_schema, tmp_path, mode="full")

    assert result == {
        "status": "compatible",
        "mode": "full",
        "target_schema": target_schema,
        "schema_epoch": expected_epoch,
        "cursor_versions": {"android": android, "ios": ios},
    }


@pytest.mark.parametrize(
    ("target_schema", "android", "ios", "message"),
    (
        (3, "v1", "v1", "requires both platform cursors to be v2"),
        (3, "v1", "v2", "mixed UAudit cursor schema epoch"),
        (3, "v2", "v1", "mixed UAudit cursor schema epoch"),
        (2, "v2", "v2", "rollback below the v2 schema epoch"),
    ),
)
def test_full_deploy_rejects_mixed_or_incompatible_epoch(
    tmp_path: Path,
    target_schema: int,
    android: str,
    ios: str,
    message: str,
) -> None:
    _write_epoch(tmp_path, android, ios)

    with pytest.raises(EpochError, match=message):
        check_epoch(target_schema, tmp_path, mode="full")


@pytest.mark.parametrize("failure", ("missing", "malformed", "symlink", "invalid-v2"))
def test_full_deploy_rejects_untrusted_cursor_files(tmp_path: Path, failure: str) -> None:
    _write_epoch(tmp_path, "v2", "v2")
    cursor = tmp_path / "state" / "android-version-audit.json"

    if failure == "missing":
        cursor.unlink()
    elif failure == "malformed":
        cursor.write_text("{not-json")
    elif failure == "symlink":
        target = tmp_path / "valid-cursor.json"
        target.write_text(json.dumps(_cursor("v2")))
        cursor.unlink()
        cursor.symlink_to(target)
    else:
        value = _cursor("v2")
        value.pop("active_release_branch")
        cursor.write_text(json.dumps(value))

    with pytest.raises(EpochError):
        check_epoch(3, tmp_path, mode="full")


def test_runtime_only_requires_schema_three_and_does_not_read_live_cursors(
    tmp_path: Path,
) -> None:
    missing_project_root = tmp_path / "not-created"

    result = check_epoch(3, missing_project_root, mode="runtime-only")

    assert result == {
        "status": "compatible",
        "mode": "runtime-only",
        "target_schema": 3,
        "schema_epoch": "not-checked",
        "cursor_versions": {},
    }
    with pytest.raises(EpochError, match="runtime-only requires target schema 3"):
        check_epoch(2, missing_project_root, mode="runtime-only")


def test_cli_emits_machine_readable_result_and_fails_closed(tmp_path: Path) -> None:
    _write_epoch(tmp_path, "v2", "v2")
    accepted = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--target-schema",
            "3",
            "--project-root",
            str(tmp_path),
            "--mode",
            "full",
        ],
        capture_output=True,
        text=True,
    )
    rejected = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--target-schema",
            "2",
            "--project-root",
            str(tmp_path),
            "--mode",
            "full",
        ],
        capture_output=True,
        text=True,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert json.loads(accepted.stdout)["schema_epoch"] == "release-v2"
    assert rejected.returncode == 1
    assert "rollback below the v2 schema epoch" in rejected.stderr
