from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_uaudit_daily_intake import commit, git, write_json
from test_uaudit_delivery_contract import (
    CREATED_AT,
    DELIVERED_AT,
    RECONCILED_AT,
    PAIRS,
    call,
    write_handoff,
)
from test_uaudit_fixed_intake import fixed_runtime


def deliver_intake(
    tmp_path: Path, module, repo: Path, cursor: Path, lock: Path, result: dict
):
    """Use real intake binding and Git diff; simulate only the external send receipt."""
    run = tmp_path / "audit"
    run.mkdir()
    helper = Path(module.__file__).with_name("uaudit_delivery_contract.py")
    ref = result["source_ref"]
    write_json(
        run / "intake.json",
        {
            "schema_version": 1,
            "issue_identifier": result["issue_identifier"],
            "platform": "android",
            "audit_kind": "daily_delta",
            "generation_created_at": CREATED_AT,
            "source_ref": ref,
        },
    )
    write_json(run / "profile.json", {"branch": ref["branch"]})
    (run / "commits.tsv").write_text(
        git("log", "--format=%H%x09%s", f"{ref['from_sha']}..{ref['to_sha']}", cwd=repo)
        + "\n"
    )
    (run / "files.tsv").write_text(
        git("diff", "--name-only", ref["from_sha"], ref["to_sha"], cwd=repo) + "\n"
    )
    (run / "diff.patch").write_text(
        git("diff", ref["from_sha"], ref["to_sha"], cwd=repo) + "\n"
    )
    call(
        helper,
        "bind-context",
        "--run-dir",
        run,
        "--intake",
        run / "intake.json",
        "--lock-dir",
        lock,
    )
    binding = json.loads((run / "run-context.json").read_text())
    for stage, agent, filename in PAIRS[("daily_delta", "android")]:
        sidecar = run / filename
        write_json(
            sidecar,
            {
                "schema_version": 1,
                "run_binding": binding,
                "stage": stage,
                "source_agent": agent,
                "audit_status": "complete",
                "findings": [],
                "limitations": [],
                "block_reason": None,
            },
        )
        call(helper, "validate-stage", "--run-dir", run, "--sidecar", sidecar)
    assert call(helper, "aggregate", "--run-dir", run)["mode"] == "message"
    fixture = {"helper": helper, "run": run, "binding": binding}
    handoff = write_handoff(fixture)
    call(
        helper,
        "verify-payload",
        "--run-dir",
        run,
        "--handoff",
        handoff,
        "--expected-mode",
        "message",
        "--company-id",
        "test-company",
        "--agent-id",
        "test-agent",
    )
    params = json.loads((run / "payload.ru.json").read_text())["params"]
    response = run / "delivery-plugin-response.json"
    write_json(
        response,
        {
            "data": {
                "data": {
                    "ok": True,
                    "mode": "message",
                    "routeSource": "file_route",
                    "routeName": "UAudit",
                    "issueIdentifier": result["issue_identifier"],
                    "projectKey": "UNS",
                    "messageId": 321,
                    "chatId": "-100123",
                    "idempotencyKey": params["idempotencyKey"],
                }
            }
        },
    )
    before = cursor.read_bytes()
    failed = call(
        helper,
        "reconcile-daily",
        "--run-dir",
        run,
        "--cursor",
        cursor,
        "--lock-dir",
        lock,
        "--reconciled-at",
        RECONCILED_AT,
        ok=False,
    )
    assert failed["ok"] is False
    assert cursor.read_bytes() == before
    call(
        helper,
        "record-delivery",
        "--run-dir",
        run,
        "--response",
        response,
        "--delivered-at",
        DELIVERED_AT,
    )
    applied = call(
        helper,
        "reconcile-daily",
        "--run-dir",
        run,
        "--cursor",
        cursor,
        "--lock-dir",
        lock,
        "--reconciled-at",
        RECONCILED_AT,
    )
    assert applied["status"] == "applied"
    assert (
        json.loads(cursor.read_text())["last_successfully_audited_sha"] == ref["to_sha"]
    )
    # The delivery operator releases its retained routine lock after reconciliation.
    shutil.rmtree(lock)


def test_real_delta_receipt_release_merge_and_second_delta(tmp_path: Path):
    module, producer, repo, cursor, lock, args = fixed_runtime(tmp_path)
    git("checkout", "develop", cwd=producer)
    first_head = commit(producer, "audited before release")
    git("push", "upstream", "develop", cwd=producer)
    first = module.run_intake(**args)
    deliver_intake(tmp_path, module, repo, cursor, lock, first)
    git("checkout", "master", cwd=producer)
    git("merge", "--no-ff", "develop", "-m", "release", cwd=producer)
    git("push", "upstream", "master", cwd=producer)
    git("checkout", "develop", cwd=producer)
    next_head = commit(producer, "development after release")
    git("push", "upstream", "develop", cwd=producer)
    # New scheduled execution; the first immutable intake and receipt stay intact.
    next_run = "44444444-4444-4444-8444-444444444444"
    issue = json.loads(args["issue_envelope"].read_text())
    issue["originRunId"] = next_run
    run = json.loads(args["routine_run_envelope"].read_text())
    run["id"] = next_run
    write_json(args["issue_envelope"], issue)
    write_json(args["routine_run_envelope"], run)
    args["output_dir"] = args["output_dir"].parent / next_run
    second = module.run_intake(**args)
    assert second["resolution_kind"] == "daily"
    assert second["source_ref"]["from_sha"] == first_head
    assert second["source_ref"]["to_sha"] == next_head
    second_root = tmp_path / "second"
    second_root.mkdir()
    deliver_intake(second_root, module, repo, cursor, lock, second)


def test_real_rewrite_uses_only_proven_master_range(tmp_path: Path):
    module, producer, repo, cursor, _, args = fixed_runtime(tmp_path)
    git("checkout", "develop", cwd=producer)
    old_head = commit(producer, "old development history")
    git("push", "upstream", "develop", cwd=producer)
    git("fetch", str(producer), f"{old_head}:refs/retained-audit/old", cwd=repo)
    state = json.loads(cursor.read_text())
    state["last_successfully_audited_sha"] = old_head
    write_json(cursor, state)
    git("checkout", "master", cwd=producer)
    master = commit(producer, "new master hotfix")
    git("push", "upstream", "master", cwd=producer)
    git("checkout", "-B", "develop", "master", cwd=producer)
    rewritten = commit(producer, "rewritten development")
    git("push", "--force", "upstream", "develop", cwd=producer)
    result = module.run_intake(**args)
    assert result["resolution_kind"] == "full_recovery"
    assert result["audit_kind"] == "forced_full"
    assert result["source_ref"]["from_sha"] == master
    assert result["source_ref"]["to_sha"] == rewritten
    assert json.loads(cursor.read_text()) == state


def test_shallow_clone_recovers_history_before_computing_delta(tmp_path: Path):
    module, producer, repo, cursor, _, args = fixed_runtime(tmp_path)
    original = json.loads(cursor.read_text())["last_successfully_audited_sha"]
    git("checkout", "develop", cwd=producer)
    commit(producer, "intermediate")
    head = commit(producer, "shallow tip")
    git("push", "upstream", "develop", cwd=producer)
    shutil.rmtree(repo)
    git(
        "clone",
        "--depth",
        "1",
        "--branch",
        "develop",
        (tmp_path / "upstream.git").as_uri(),
        repo,
    )
    assert git("rev-parse", "--is-shallow-repository", cwd=repo) == "true"
    result = module.run_intake(**args)
    assert result["resolution_kind"] == "daily"
    assert result["source_ref"]["from_sha"] == original
    assert result["source_ref"]["to_sha"] == head
    evidence = json.loads((args["output_dir"] / "git-evidence.json").read_text())
    assert evidence["history"]["was_shallow"] is True
    assert evidence["history"]["is_shallow"] is False
