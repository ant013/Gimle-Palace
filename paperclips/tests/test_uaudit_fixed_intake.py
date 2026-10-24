from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from test_uaudit_daily_intake import (
    RUN_ID,
    audit_repo,
    commit,
    envelopes,
    git,
    install_runtime,
    make_remote,
    write_json,
)


def fixed_runtime(
    tmp_path: Path, *, legacy: bool = False, cursor_sha: str | None = None
):
    remote, producer, first = make_remote(tmp_path)
    git("branch", "develop", cwd=producer)
    git("push", "upstream", "develop", cwd=producer)
    repo = audit_repo(tmp_path, remote, first)
    cursor = tmp_path / "state/android-version-audit.json"
    state = {"last_successfully_audited_sha": cursor_sha or first}
    if not legacy:
        state.update(
            schema_version="uaudit-daily-cursor/v2",
            routine_key="uaudit-daily-android",
            active_release_branch="develop",
        )
    write_json(cursor, state)
    lock = tmp_path / "state/locks/daily-android-version-0.52.lock"
    module = install_runtime(
        tmp_path,
        repo=repo,
        cursor=cursor,
        lock=lock,
        remote=remote,
        tracking_mode="fixed_branch",
        branch="develop",
    )
    issue, routine_run = envelopes(tmp_path)
    args = dict(
        routine_id="daily-android-version-0.52",
        issue_envelope=issue,
        routine_run_envelope=routine_run,
        output_dir=tmp_path / "runs/UNS-688-intake" / RUN_ID,
        allow_file_url=True,
    )
    return module, producer, repo, cursor, lock, args


def test_fixed_branch_survives_release_merge_and_ignores_version_refs(tmp_path: Path):
    module, producer, _repo, cursor, lock, args = fixed_runtime(tmp_path)
    first = json.loads(cursor.read_text())["last_successfully_audited_sha"]
    git("checkout", "develop", cwd=producer)
    audited = commit(producer, "first development delta")
    git("push", "upstream", "develop", cwd=producer)
    git("checkout", "master", cwd=producer)
    git("merge", "--no-ff", "develop", "-m", "release", cwd=producer)
    git("push", "upstream", "master", cwd=producer)
    git("checkout", "develop", cwd=producer)
    head = commit(producer, "next development delta")
    git("push", "upstream", "develop", cwd=producer)
    # Previously delivered audit ended at audited, before the master release merge.
    state = json.loads(cursor.read_text())
    state["last_successfully_audited_sha"] = audited
    write_json(cursor, state)
    result = module.run_intake(**args)
    assert result["resolution_kind"] == "daily"
    assert result["source_ref"]["from_sha"] == audited
    assert result["source_ref"]["to_sha"] == head
    evidence = json.loads((args["output_dir"] / "git-evidence.json").read_text())
    assert evidence["branches"] == {"base": "master", "current": "develop"}
    assert evidence["tracking_mode"] == "fixed_branch"
    assert json.loads(cursor.read_text()) == state
    assert first != audited
    assert lock.is_dir()


@pytest.mark.parametrize("state_kind", ["legacy", "wrong_branch"])
def test_fixed_intake_requires_explicit_matching_migration(
    tmp_path: Path, state_kind: str
):
    module, _, _, cursor, lock, args = fixed_runtime(
        tmp_path, legacy=state_kind == "legacy"
    )
    if state_kind == "wrong_branch":
        state = json.loads(cursor.read_text())
        state["active_release_branch"] = "version/0.52"
        write_json(cursor, state)
    before = cursor.read_bytes()
    with pytest.raises(module.IntakeError, match="migration"):
        module.run_intake(**args)
    assert cursor.read_bytes() == before
    assert not lock.exists()
    assert not args["output_dir"].exists()


@pytest.mark.parametrize("bridge", [False, True])
def test_deleted_fixed_branch_uses_master_without_switching_policy(
    tmp_path: Path, bridge: bool
):
    module, producer, _, cursor, _, args = fixed_runtime(tmp_path)
    if bridge:
        commit(producer, "master bridge after deletion")
        git("push", "upstream", "master", cwd=producer)
    git("push", "upstream", "--delete", "develop", cwd=producer)
    before = cursor.read_bytes()
    result = module.run_intake(**args)
    assert result["resolution_kind"] == ("bridge" if bridge else "no_change")
    assert cursor.read_bytes() == before
    if bridge:
        assert result["source_ref"]["branch"] == "master"
        assert result["source_ref"]["cursor_to_branch"] == "develop"
    else:
        assert (
            "absent"
            in json.loads(
                (args["output_dir"] / "daily-status-handoff.json").read_text()
            )["status"]["reason"]
        )


@pytest.mark.parametrize("recoverable", [False, True])
def test_missing_cursor_object_produces_deliverable_recovery(
    tmp_path: Path, recoverable: bool
):
    module, producer, _, cursor, lock, args = fixed_runtime(
        tmp_path, cursor_sha="f" * 40
    )
    if recoverable:
        git("checkout", "develop", cwd=producer)
        commit(producer, "recoverable current development")
        git("push", "upstream", "develop", cwd=producer)
    before = cursor.read_bytes()
    result = module.run_intake(**args)
    assert result["resolution_kind"] == (
        "full_recovery" if recoverable else "blocked_recovery"
    )
    assert result["audit_kind"] == ("forced_full" if recoverable else None)
    assert cursor.read_bytes() == before
    evidence = json.loads((args["output_dir"] / "git-evidence.json").read_text())
    assert evidence["history"]["cursor_available"] is False
    if not recoverable:
        handoff = args["output_dir"] / "daily-status-handoff.json"
        assert handoff.exists()
        assert not lock.exists()


def test_metadata_migration_preserves_sha_history_and_retries(tmp_path: Path):
    module, producer, _, cursor, lock, _ = fixed_runtime(tmp_path)
    before = json.loads(cursor.read_text())
    before.update(
        active_release_branch="version/0.52",
        last_successful_issue="UNS-123",
        last_delivery_summary_sha256="b" * 64,
    )
    write_json(cursor, before)
    git("checkout", "develop", cwd=producer)
    commit(producer, "not yet audited")
    git("push", "upstream", "develop", cwd=producer)
    kwargs = dict(
        routine_id="daily-android-version-0.52",
        active_branch="develop",
        backup_dir=tmp_path / "backup",
        allow_file_url=True,
    )
    dry = module.migrate_cursor(**kwargs, dry_run=True)
    assert dry["status"] == "ready"
    assert not kwargs["backup_dir"].exists()
    result = module.migrate_cursor(**kwargs)
    assert result["status"] == "migrated"
    after = json.loads(cursor.read_text())
    assert after == {**before, "active_release_branch": "develop"}
    assert Path(result["backup_path"]).read_bytes() == module._canonical_bytes(before)
    journal = json.loads(Path(result["journal_path"]).read_text())
    assert journal["old_state_sha256"] != journal["new_state_sha256"]
    assert module.migrate_cursor(**kwargs)["status"] == "already_applied"
    assert not lock.exists()


@pytest.mark.parametrize("after_replace", [False, True])
def test_migration_resumes_own_crash_without_stealing_active_lock(
    tmp_path: Path, after_replace: bool
):
    module, _, _, cursor, lock, _ = fixed_runtime(tmp_path, legacy=True)
    kwargs = dict(
        routine_id="daily-android-version-0.52",
        active_branch="develop",
        backup_dir=tmp_path / "backup",
        allow_file_url=True,
    )
    before = cursor.read_bytes()
    # A genuine child process dies after journal publication, with/without cursor replacement.
    pid = os.fork()
    if pid == 0:
        original = module._replace_json

        def crash(path, value):
            if path != cursor:
                return original(path, value)
            if after_replace:
                original(path, value)
            os._exit(73)

        module._replace_json = crash
        module.migrate_cursor(**kwargs)
        os._exit(74)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 73
    assert lock.is_dir()
    assert (cursor.read_bytes() != before) == after_replace
    # A lock claiming an active foreign process is never adopted.
    owner_path = lock / "cursor-migration.json"
    owner = json.loads(owner_path.read_text())
    stale_owner = dict(owner)
    owner["pid"] = os.getppid()
    owner["hostname"] = socket.gethostname()
    write_json(owner_path, owner)
    with pytest.raises(module.IntakeError, match="active|held"):
        module.migrate_cursor(**kwargs)
    write_json(owner_path, stale_owner)
    result = module.migrate_cursor(**kwargs)
    assert result["status"] == ("already_applied" if after_replace else "migrated")
    assert json.loads(cursor.read_text())["active_release_branch"] == "develop"
    assert not lock.exists()


def test_stale_migration_retry_cannot_adopt_unlinked_lease_or_remove_new_audit_lock(
    tmp_path: Path,
):
    module, _, _, cursor, lock, _ = fixed_runtime(tmp_path, legacy=True)
    kwargs = dict(
        routine_id="daily-android-version-0.52",
        active_branch="develop",
        backup_dir=tmp_path / "backup",
        allow_file_url=True,
    )
    # Leave a genuine dead migration owner with an immutable prepared journal.
    crashed = os.fork()
    if crashed == 0:
        original_replace = module._replace_json

        def crash_before_cursor(path, value):
            if path == cursor:
                os._exit(73)
            return original_replace(path, value)

        module._replace_json = crash_before_cursor
        module.migrate_cursor(**kwargs)
        os._exit(74)
    _, crashed_status = os.waitpid(crashed, 0)
    assert os.waitstatus_to_exitcode(crashed_status) == 73
    opened_read, opened_write = os.pipe()
    resume_read, resume_write = os.pipe()
    outcome = tmp_path / "delayed-retry.json"
    delayed = os.fork()
    if delayed == 0:
        os.close(opened_read)
        os.close(resume_write)
        original_flock = module.fcntl.flock

        def delayed_flock(fd, operation):
            os.write(opened_write, b"1")
            assert os.read(resume_read, 1) == b"1"
            return original_flock(fd, operation)

        module.fcntl.flock = delayed_flock
        try:
            result = module.migrate_cursor(**kwargs)
        except module.IntakeError as exc:
            write_json(outcome, {"status": "refused", "reason": str(exc)})
        else:
            write_json(outcome, {"status": "unexpected_success", "result": result})
        os._exit(0)
    os.close(opened_write)
    os.close(resume_read)
    try:
        # Delayed retry has validated dead owner and opened the original lease inode.
        assert os.read(opened_read, 1) == b"1"
        completed = module.migrate_cursor(**kwargs)
        assert completed["status"] == "migrated"
        assert not lock.exists()
        lock.mkdir()
        foreign_owner = {"issue_identifier": "UNS-999", "origin_run_id": "new-audit"}
        write_json(lock / "intake-owner.json", foreign_owner)
        before = cursor.read_bytes()
        os.write(resume_write, b"1")
        _, delayed_status = os.waitpid(delayed, 0)
        assert os.waitstatus_to_exitcode(delayed_status) == 0
        assert json.loads(outcome.read_text())["status"] == "refused"
        assert json.loads((lock / "intake-owner.json").read_text()) == foreign_owner
        assert not (lock / "cursor-migration.json").exists()
        assert cursor.read_bytes() == before
    finally:
        os.close(opened_read)
        os.close(resume_write)
