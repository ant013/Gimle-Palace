from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "paperclips/projects/uaudit/runtime"
ISSUE_ID = "11111111-1111-4111-8111-111111111111"
ROUTINE_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"


def git(*args: object, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *(str(arg) for arg in args)],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result.stdout.strip()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commit(repo: Path, text: str) -> str:
    target = repo / "history.txt"
    with target.open("a") as stream:
        stream.write(text + "\n")
    git("add", "history.txt", cwd=repo)
    git("commit", "-m", text, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def make_remote(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "upstream.git"
    producer = tmp_path / "producer"
    git("init", "--bare", remote)
    git("init", "-b", "master", producer)
    git("config", "user.email", "uaudit@example.test", cwd=producer)
    git("config", "user.name", "UAudit Test", cwd=producer)
    first = commit(producer, "first")
    git("branch", "version/0.52", cwd=producer)
    git("remote", "add", "upstream", remote.as_uri(), cwd=producer)
    git("push", "upstream", "master", "version/0.52", cwd=producer)
    return remote, producer, first


def advance_release(producer: Path, text: str) -> str:
    git("checkout", "version/0.52", cwd=producer)
    head = commit(producer, text)
    git("push", "upstream", "version/0.52", cwd=producer)
    return head


def install_runtime(
    tmp_path: Path, *, repo: Path, cursor: Path, lock: Path, remote: Path
):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in (
        "uaudit_daily_intake.py",
        "uaudit_release_resolver.py",
        "uaudit_delivery_contract.py",
    ):
        shutil.copy2(RUNTIME / name, tools / name)
        (tools / name).chmod(0o444)
    write_json(
        tools / "uaudit_release_resolver.manifest.json",
        {
            "schema_version": "uaudit-release-resolver-install/v1",
            "file": "uaudit_release_resolver.py",
            "sha256": digest(tools / "uaudit_release_resolver.py"),
        },
    )
    write_json(
        tools / "uaudit_delivery_contract.manifest.json",
        {
            "schema_version": "uaudit-helper-install/v1",
            "file": "uaudit_delivery_contract.py",
            "sha256": digest(tools / "uaudit_delivery_contract.py"),
        },
    )
    (tools / "uaudit_release_resolver.manifest.json").chmod(0o444)
    (tools / "uaudit_delivery_contract.manifest.json").chmod(0o444)
    write_json(
        tools / "uaudit_daily_routines.json",
        {
            "schema_version": "uaudit-daily-intake-routines/v1",
            "source_config_sha256": "a" * 64,
            "routines": [
                {
                    "id": "daily-android-version-0.52",
                    "live_routine_id": ROUTINE_ID,
                    "app_id": "unstoppable_wallet",
                    "routine_key": "uaudit-daily-android",
                    "platform": "android",
                    "branch": "version/0.52",
                    "base_branch": "master",
                    "repo_url": remote.as_uri(),
                    "repo_path": str(repo),
                    "cursor_path": str(cursor),
                    "lock_path": str(lock),
                }
            ],
        },
    )
    (tools / "uaudit_daily_routines.json").chmod(0o444)
    write_json(
        tools / "uaudit_daily_intake.manifest.json",
        {
            "schema_version": "uaudit-daily-intake-install/v1",
            "files": {
                "uaudit_daily_intake.py": digest(tools / "uaudit_daily_intake.py"),
                "uaudit_daily_routines.json": digest(
                    tools / "uaudit_daily_routines.json"
                ),
                "uaudit_release_resolver.py": digest(
                    tools / "uaudit_release_resolver.py"
                ),
                "uaudit_delivery_contract.py": digest(
                    tools / "uaudit_delivery_contract.py"
                ),
            },
        },
    )
    (tools / "uaudit_daily_intake.manifest.json").chmod(0o444)
    spec = importlib.util.spec_from_file_location(
        "installed_uaudit_daily_intake", tools / "uaudit_daily_intake.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def envelopes(tmp_path: Path, *, identifier: str = "UNS-688") -> tuple[Path, Path]:
    issue = tmp_path / "issue.json"
    routine_run = tmp_path / "routine-run.json"
    write_json(
        issue,
        {
            "id": ISSUE_ID,
            "identifier": identifier,
            "createdAt": "2026-10-05T10:45:00.412Z",
            "originKind": "routine_execution",
            "originId": ROUTINE_ID,
            "originRunId": RUN_ID,
        },
    )
    write_json(
        routine_run,
        {
            "id": RUN_ID,
            "routineId": ROUTINE_ID,
            "linkedIssueId": ISSUE_ID,
            "source": "schedule",
            "triggeredAt": "2026-10-05T10:45:00.248Z",
        },
    )
    return issue, routine_run


def audit_repo(tmp_path: Path, remote: Path, stale_sha: str) -> Path:
    repo = tmp_path / "audit-repo"
    git("init", repo)
    git(
        "fetch",
        remote.as_uri(),
        "+refs/heads/version/0.52:refs/remotes/uaudit-upstream/version/0.52",
        cwd=repo,
    )
    assert (
        git("rev-parse", "refs/remotes/uaudit-upstream/version/0.52", cwd=repo)
        == stale_sha
    )
    return repo


def test_stale_shared_tracking_ref_cannot_produce_no_change(tmp_path: Path):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    advanced = advance_release(producer, "UNS-688 remote advance")
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    output = tmp_path / "runs/UNS-688-intake" / RUN_ID

    result = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )

    assert result["resolution_kind"] == "daily"
    assert result["selected_head"] == advanced
    assert result["next_action"] == "audit"
    assert (
        git("rev-parse", "refs/remotes/uaudit-upstream/version/0.52", cwd=repo) == first
    )
    assert (
        git("rev-parse", f"refs/uaudit-intake/{RUN_ID}/current", cwd=repo) == advanced
    )
    evidence = json.loads((output / "git-evidence.json").read_text())
    assert evidence["refs"]["next"] is None
    assert (
        evidence["attempts"][0]["observation_a"]
        == evidence["attempts"][0]["observation_b"]
    )
    assert lock.is_dir()
    assert json.loads((lock / "metadata.json").read_text())["from_sha"] == first

    repeated = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )
    assert repeated == result

    shutil.rmtree(lock)
    with pytest.raises(module.IntakeError, match="lost its retained routine lock"):
        module.run_intake(
            routine_id="daily-android-version-0.52",
            issue_envelope=issue,
            routine_run_envelope=routine_run,
            output_dir=output,
            allow_file_url=True,
        )


def test_v2_cursor_active_branch_ignores_late_commit_on_previous_release(
    tmp_path: Path,
):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    git("checkout", "master", cwd=producer)
    commit(producer, "master release bridge")
    git("push", "upstream", "master", cwd=producer)
    git("checkout", "-b", "version/0.53", cwd=producer)
    first_053 = commit(producer, "0.53 transition")
    git("push", "upstream", "version/0.53", cwd=producer)
    second_053 = commit(producer, "0.53 advance")
    git("push", "upstream", "version/0.53", cwd=producer)
    git("checkout", "version/0.52", cwd=producer)
    commit(producer, "late 0.52 commit")
    git("push", "upstream", "version/0.52", cwd=producer)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(
        cursor,
        {
            "schema_version": "uaudit-daily-cursor/v2",
            "routine_key": "uaudit-daily-android",
            "active_release_branch": "version/0.53",
            "last_successfully_audited_sha": first_053,
        },
    )
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    output = tmp_path / "runs/UNS-688-intake" / RUN_ID

    result = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )

    assert result["resolution_kind"] == "daily"
    assert result["active_branch"] == "version/0.53"
    assert result["selected_branch"] == "version/0.53"
    assert result["selected_head"] == second_053
    assert result["source_ref"] == {
        "routine_id": "daily-android-version-0.52",
        "routine_key": "uaudit-daily-android",
        "branch": "version/0.53",
        "from_sha": first_053,
        "to_sha": second_053,
        "cursor_from_branch": "version/0.53",
        "cursor_to_branch": "version/0.53",
    }
    resolver_input = json.loads((output / "resolver-input.json").read_text())
    assert resolver_input["release_branch"] == "version/0.53"
    resolver_output = json.loads((output / "resolver-output.json").read_text())
    assert resolver_output["segments"] == [
        {
            "branch": "version/0.53",
            "from_sha": first_053,
            "name": "release",
            "to_sha": second_053,
        }
    ]


def test_legacy_cursor_on_successor_never_forces_reverse_old_release_range(
    tmp_path: Path,
):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    git("checkout", "master", cwd=producer)
    commit(producer, "master release bridge")
    git("push", "upstream", "master", cwd=producer)
    git("checkout", "-b", "version/0.53", cwd=producer)
    cursor_sha = commit(producer, "0.53 transition")
    git("push", "upstream", "version/0.53", cwd=producer)
    git("checkout", "version/0.52", cwd=producer)
    commit(producer, "late 0.52 commit")
    git("push", "upstream", "version/0.52", cwd=producer)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": cursor_sha})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    output = tmp_path / "runs/UNS-688-intake" / RUN_ID

    result = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )

    assert result["resolution_kind"] == "blocked_recovery"
    assert result["next_action"] == "daily_status"
    assert result["audit_kind"] is None
    assert result["source_ref"] is None
    assert not lock.exists()
    handoff = json.loads((output / "daily-status-handoff.json").read_text())
    assert handoff["status"]["outcome"] == "blocked"


def test_migrate_cursor_v1_to_v2_verifies_remote_branch_and_keeps_backup(
    tmp_path: Path,
):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    git("checkout", "master", cwd=producer)
    git("checkout", "-b", "version/0.53", cwd=producer)
    head_053 = commit(producer, "0.53 migration head")
    git("push", "upstream", "version/0.53", cwd=producer)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": head_053})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    backup_dir = tmp_path / "state/cursor-migration-backups"

    dry_run = module.migrate_cursor(
        routine_id="daily-android-version-0.52",
        active_branch="version/0.53",
        backup_dir=backup_dir,
        allow_file_url=True,
        dry_run=True,
    )
    assert dry_run["status"] == "ready"
    assert json.loads(cursor.read_text()) == {
        "last_successfully_audited_sha": head_053
    }
    assert not backup_dir.exists()
    assert not lock.exists()

    result = module.migrate_cursor(
        routine_id="daily-android-version-0.52",
        active_branch="version/0.53",
        backup_dir=backup_dir,
        allow_file_url=True,
    )

    assert result["status"] == "migrated"
    assert json.loads(cursor.read_text()) == {
        "schema_version": "uaudit-daily-cursor/v2",
        "routine_key": "uaudit-daily-android",
        "active_release_branch": "version/0.53",
        "last_successfully_audited_sha": head_053,
    }
    assert json.loads((backup_dir / "android-version-audit.v1.json").read_text()) == {
        "last_successfully_audited_sha": head_053
    }
    assert not lock.exists()


def test_no_change_prepares_v2_status_from_triggered_at_and_releases_lock(
    tmp_path: Path,
):
    remote, _producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    output = tmp_path / "runs/UNS-688-intake" / RUN_ID

    result = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )

    assert result["resolution_kind"] == "no_change"
    assert result["next_action"] == "daily_status"
    assert not lock.exists()
    proof = json.loads((output / "daily-status-slot-proof.json").read_text())
    assert proof["schema_version"] == "uaudit-daily-slot-status-proof/v2"
    assert proof["scheduled_utc_slot"] == "2026-10-05T10:45:00.248Z"
    assert proof["scheduled_utc_slot"] != "2026-10-05T10:45:00.412Z"
    handoff_path = output / "daily-status-handoff.json"
    verified = module.verify_handoff(
        handoff_path,
        expected_sha256=digest(handoff_path),
        expected_issue_identifier="UNS-688",
        expected_origin_run_id=RUN_ID,
    )
    assert verified["summary_sha256"] == result["status_summary_sha256"]

    lock.mkdir()
    write_json(
        lock / "intake-owner.json",
        {
            "schema_version": "uaudit-daily-intake-result/v1",
            "issue_identifier": "UNS-688",
            "origin_run_id": RUN_ID,
            "routine_id": "daily-android-version-0.52",
            "output_dir": str(output),
            "pid": 999999,
            "hostname": socket.gethostname(),
            "created_at": "2026-10-05T10:45:00.248Z",
        },
    )
    repeated = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=output,
        allow_file_url=True,
    )
    assert repeated == result
    assert not lock.exists()

    with pytest.raises(module.IntakeError, match="different issue"):
        module.verify_handoff(
            handoff_path,
            expected_sha256=digest(handoff_path),
            expected_issue_identifier="UNS-689",
            expected_origin_run_id=RUN_ID,
        )

    wrong_attempt = json.loads(handoff_path.read_text())
    wrong_attempt["status"]["attempt_id"] = "wrong-attempt"
    wrong_attempt_path = output / "wrong-attempt-handoff.json"
    write_json(wrong_attempt_path, wrong_attempt)
    with pytest.raises(module.IntakeError, match="attempt does not match"):
        module.verify_handoff(
            wrong_attempt_path,
            expected_sha256=digest(wrong_attempt_path),
            expected_issue_identifier="UNS-688",
            expected_origin_run_id=RUN_ID,
        )

    tampered = json.loads((output / "daily-status-handoff.json").read_text())
    tampered["descriptor"] = {"path": str(cursor), "sha256": digest(cursor)}
    write_json(output / "tampered-handoff.json", tampered)
    with pytest.raises(module.IntakeError, match="escapes its bundle"):
        tampered_path = output / "tampered-handoff.json"
        module.verify_handoff(tampered_path, expected_sha256=digest(tampered_path))


def test_proven_absent_current_branch_can_transition_to_strict_next(tmp_path: Path):
    remote, producer, first = make_remote(tmp_path)
    git("checkout", "master", cwd=producer)
    git("branch", "version/0.53", cwd=producer)
    git("push", "upstream", ":version/0.52", "version/0.53", cwd=producer)
    repo = tmp_path / "audit-repo"
    git("init", repo)
    git("fetch", remote.as_uri(), f"{first}:refs/uaudit-test/cursor", cwd=repo)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)

    result = module.run_intake(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
        allow_file_url=True,
    )

    assert result["resolution_kind"] == "no_change"
    evidence = json.loads(
        (tmp_path / "runs/UNS-688-intake" / RUN_ID / "git-evidence.json").read_text()
    )
    assert evidence["refs"]["current"] is None
    assert evidence["refs"]["next"] == first


def test_authoritative_snapshot_retries_whole_sequence_when_remote_moves(
    tmp_path: Path,
):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    real_runner = module._default_runner
    fetches = 0

    def moving_runner(command, cwd):
        nonlocal fetches
        result = real_runner(command, cwd)
        if len(command) > 1 and command[0:2] == ["git", "fetch"] and cwd == repo:
            fetches += 1
            if fetches == 1:
                advance_release(producer, "move between observations")
        return result

    refs, evidence = module._authoritative_snapshot(
        moving_runner,
        repo,
        remote.as_uri(),
        {"base": "master", "current": "version/0.52", "next": "version/0.53"},
        RUN_ID,
    )
    assert evidence["selected_attempt"] == 2
    assert evidence["attempts"][0]["stable"] is False
    assert evidence["attempts"][1]["stable"] is True
    assert refs["current"] == git("rev-parse", "version/0.52", cwd=producer)


def test_two_unstable_snapshots_fail_closed_and_persist_evidence(tmp_path: Path):
    remote, producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    real_runner = module._default_runner
    fetches = 0

    def always_moving_runner(command, cwd):
        nonlocal fetches
        result = real_runner(command, cwd)
        if len(command) > 1 and command[0:2] == ["git", "fetch"] and cwd == repo:
            fetches += 1
            advance_release(producer, f"move after fetch {fetches}")
        return result

    with pytest.raises(module.IntakeError, match="evidence:"):
        module.run_intake(
            routine_id="daily-android-version-0.52",
            issue_envelope=issue,
            routine_run_envelope=routine_run,
            output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
            runner=always_moving_runner,
            allow_file_url=True,
        )

    failures = list(
        (tmp_path / "runs/UNS-688-intake" / f"{RUN_ID}-failures").glob("snapshot.*")
    )
    assert len(failures) == 1
    evidence = json.loads((failures[0] / "git-evidence.json").read_text())
    assert evidence["selected_attempt"] is None
    assert [attempt["stable"] for attempt in evidence["attempts"]] == [False, False]
    assert (failures[0] / "intake-error.json").is_file()
    assert not lock.exists()


def test_routine_lock_is_checked_before_cursor_snapshot(tmp_path: Path):
    remote, _producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/missing-cursor.json"
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    lock.mkdir(parents=True)
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)

    with pytest.raises(module.IntakeError, match="routine lock is held"):
        module.run_intake(
            routine_id="daily-android-version-0.52",
            issue_envelope=issue,
            routine_run_envelope=routine_run,
            output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
            allow_file_url=True,
        )

    os.utime(lock, (0, 0))
    with pytest.raises(module.IntakeError, match="cursor.*unreadable"):
        module.run_intake(
            routine_id="daily-android-version-0.52",
            issue_envelope=issue,
            routine_run_envelope=routine_run,
            output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
            allow_file_url=True,
        )
    assert not lock.exists()


def test_routine_execution_cannot_be_routed_to_another_configured_routine(
    tmp_path: Path,
):
    remote, _producer, first = make_remote(tmp_path)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": first})
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path, repo=repo, cursor=cursor, lock=lock, remote=remote
    )
    issue, routine_run = envelopes(tmp_path)
    other_routine = "44444444-4444-4444-8444-444444444444"
    issue_value = json.loads(issue.read_text())
    run_value = json.loads(routine_run.read_text())
    issue_value["originId"] = other_routine
    run_value["routineId"] = other_routine
    write_json(issue, issue_value)
    write_json(routine_run, run_value)

    with pytest.raises(module.IntakeError, match="configured live routine"):
        module.run_intake(
            routine_id="daily-android-version-0.52",
            issue_envelope=issue,
            routine_run_envelope=routine_run,
            output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
            allow_file_url=True,
        )
