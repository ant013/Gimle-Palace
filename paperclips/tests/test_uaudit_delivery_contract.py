from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SOURCE_HELPER = REPO / "paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py"
CREATED_AT = "2026-07-16T10:00:00Z"
DELIVERED_AT = "2026-07-16T10:01:00Z"
RECONCILED_AT = "2026-07-16T10:02:00Z"
BASE_SHA = "0123456789abcdef0123456789abcdef01234567"
HEAD_SHA = "89abcdef0123456789abcdef0123456789abcdef"


PAIRS = {
    ("pr", "ios"): (
        ("code", "uaudit-swift-audit-specialist", "code.findings.json"),
        ("bug", "uaudit-bug-hunter", "bug.findings.json"),
        ("security", "uaudit-security-auditor", "security.findings.json"),
        ("crypto", "uaudit-blockchain-auditor", "crypto.findings.json"),
    ),
    ("pr", "android"): (
        ("code", "uaudit-kotlin-audit-specialist", "code.findings.json"),
        ("bug", "uaudit-bug-hunter", "bug.findings.json"),
        ("security", "uaudit-security-auditor", "security.findings.json"),
        ("crypto", "uaudit-blockchain-auditor", "crypto.findings.json"),
    ),
    ("daily_delta", "ios"): (
        ("code", "UWISwiftAuditor", "code.findings.json"),
        ("security", "UWISecurityAuditor", "security.findings.json"),
        ("crypto", "UWICryptoAuditor", "crypto.findings.json"),
        ("infra", "UWIInfraEngineer", "infra.findings.json"),
        ("qa_verify", "UWIQAEngineer", "qa-verify.findings.json"),
    ),
    ("daily_delta", "android"): (
        ("code", "UWAKotlinAuditor", "code.findings.json"),
        ("security", "UWASecurityAuditor", "security.findings.json"),
        ("crypto", "UWACryptoAuditor", "crypto.findings.json"),
        ("infra", "UWAInfraEngineer", "infra.findings.json"),
        ("qa_verify", "UWAQAEngineer", "qa-verify.findings.json"),
    ),
}


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def install_helper(root: Path) -> Path:
    tools = root / ".uaudit-tools"
    tools.mkdir(parents=True)
    helper = tools / "uaudit_delivery_contract.py"
    shutil.copyfile(SOURCE_HELPER, helper)
    digest = hashlib.sha256(helper.read_bytes()).hexdigest()
    write_json(
        tools / "uaudit_delivery_contract.manifest.json",
        {
            "schema_version": "uaudit-helper-install/v1",
            "file": "uaudit_delivery_contract.py",
            "sha256": digest,
        },
    )
    helper.chmod(0o444)
    return helper


def call(helper: Path, *args: object, ok: bool = True) -> dict:
    result = subprocess.run(
        [sys.executable, str(helper), *(str(arg) for arg in args)],
        text=True,
        capture_output=True,
        check=False,
    )
    if ok:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode == 2, (result.stdout, result.stderr)
    payload = json.loads(result.stderr)
    assert payload["ok"] is False
    return payload


def source_ref(kind: str) -> dict:
    if kind == "pr":
        return {
            "repo": "unstoppable-wallet-ios",
            "pr_url": "https://github.com/horizontalsystems/unstoppable-wallet-ios/pull/456",
            "base_sha": BASE_SHA,
            "head_sha": HEAD_SHA,
        }
    return {
        "routine_id": "daily-ios-version-0.49",
        "branch": "version/0.49",
        "from_sha": BASE_SHA,
        "to_sha": HEAD_SHA,
    }


def finding(
    severity: str = "Important",
    *,
    title: str = "Повторная авторизация не проверяется",
    file: str | None = "Sources/Wallet/Auth.swift",
    line: int | None = 42,
    area: str | None = None,
    runtime: bool = False,
) -> dict:
    return {
        "severity": severity,
        "file": file,
        "line": line,
        "area": area,
        "title": title,
        "evidence": "Повторный вход проходит без проверки активной сессии.",
        "impact": "Пользователь может подтвердить действие в неверном состоянии.",
        "recommendation": "Добавить явную проверку сессии перед подтверждением.",
        "needs_runtime_verification": runtime,
    }


def prepare_run(
    root: Path,
    *,
    kind: str = "pr",
    platform: str = "ios",
    statuses: dict[str, str] | None = None,
    findings: dict[str, list[dict]] | None = None,
    diff_patch: bytes | None = None,
    validate: bool = True,
) -> dict:
    helper = install_helper(root)
    run = root / "run"
    run.mkdir()
    ref = source_ref(kind)
    if platform == "android":
        if kind == "pr":
            ref["repo"] = "unstoppable-wallet-android"
            ref["pr_url"] = "https://github.com/horizontalsystems/unstoppable-wallet-android/pull/456"
        else:
            ref["routine_id"] = "daily-android-version-0.49"
    intake = {
        "schema_version": 1,
        "issue_identifier": "UNS-123",
        "platform": platform,
        "audit_kind": kind,
        "generation_created_at": CREATED_AT,
        "source_ref": ref,
    }
    write_json(run / "intake.json", intake)
    if kind == "pr":
        write_json(run / "pr.json", {"number": 456, "base": BASE_SHA, "head": HEAD_SHA})
        (run / "pr.diff").write_text("diff --git a/A b/A\n--- a/A\n+++ b/A\n@@\n-old\n+new\n")
        lock = None
        call(helper, "bind-context", "--run-dir", run, "--intake", run / "intake.json")
    else:
        write_json(run / "profile.json", {"branch": ref["branch"]})
        (run / "commits.tsv").write_text(f"{HEAD_SHA}\tИзменение\n")
        (run / "files.tsv").write_text("Sources/Wallet/Auth.swift\n")
        (run / "diff.patch").write_bytes(
            diff_patch or b"diff --git a/A b/A\n--- a/A\n+++ b/A\n@@\n-old\n+new\n"
        )
        lock = root / "state" / "locks" / f"{ref['routine_id']}.lock"
        lock.mkdir(parents=True)
        write_json(
            lock / "metadata.json",
            {
                "schema_version": 1,
                "issue_identifier": "UNS-123",
                "routine_id": ref["routine_id"],
                "from_sha": BASE_SHA,
                "to_sha": HEAD_SHA,
                "run_binding_sha256": None,
            },
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
    binding = read_json(run / "run-context.json")
    statuses = statuses or {}
    findings = findings or {}
    for stage, agent, filename in PAIRS[(kind, platform)]:
        status = statuses.get(stage, "complete")
        limitations = []
        block_reason = None
        if status == "partial":
            limitations = [{"text": "Runtime-сценарий не запускался полностью.", "material": True}]
        elif status == "blocked":
            block_reason = "Не удалось получить обязательный вход проверки."
        sidecar = {
            "schema_version": 1,
            "run_binding": binding,
            "stage": stage,
            "source_agent": agent,
            "audit_status": status,
            "findings": findings.get(stage, []),
            "limitations": limitations,
            "block_reason": block_reason,
        }
        path = run / filename
        write_json(path, sidecar)
        if validate:
            call(helper, "validate-stage", "--run-dir", run, "--sidecar", path)
    return {"helper": helper, "run": run, "lock": lock, "binding": binding}


def aggregate(fixture: dict, *, ok: bool = True) -> dict:
    return call(fixture["helper"], "aggregate", "--run-dir", fixture["run"], ok=ok)


def write_handoff(fixture: dict) -> Path:
    run = fixture["run"].resolve()
    binding = fixture["binding"]
    handoff = {
        "schema_version": 1,
        "delivery_contract": "uaudit-delivery/v1",
        "run_dir": str(run),
        "delivery_summary": str(run / "delivery-summary.json"),
        "issue_identifier": binding["issue_identifier"],
        "platform": binding["platform"],
        "audit_kind": binding["audit_kind"],
        "source_ref": binding["source_ref"],
    }
    path = run / "delivery-handoff.json"
    write_json(path, handoff)
    return path


def record(fixture: dict, mode: str, *, route: str = "UAudit", ok: bool = True) -> dict:
    if not (fixture["run"] / "delivery-handoff.json").exists():
        write_handoff(fixture)
    response = fixture["run"] / "delivery-plugin-response.json"
    write_json(
        response,
        {
            "data": {
                "content": [{"type": "text", "text": "Telegram delivery result"}],
                "data": {
                    "ok": True,
                    "mode": mode,
                    "routeSource": "file_route",
                    "routeName": route,
                    "issueIdentifier": "UNS-123",
                    "projectKey": "UNS",
                    "messageId": 321,
                    "chatId": "-100123",
                },
            }
        },
    )
    return call(
        fixture["helper"],
        "record-delivery",
        "--run-dir",
        fixture["run"],
        "--response",
        response,
        "--delivered-at",
        DELIVERED_AT,
        ok=ok,
    )


def test_install_manifest_is_mandatory_and_tamper_evident(tmp_path: Path):
    helper = install_helper(tmp_path)
    manifest = helper.with_name("uaudit_delivery_contract.manifest.json")
    verified = call(helper, "verify-install", "--manifest", manifest)
    assert verified["status"] == "installed"
    helper.chmod(0o644)
    failure = call(helper, "verify-install", "--manifest", manifest, ok=False)
    assert "read-only" in failure["error"]
    helper.write_bytes(helper.read_bytes() + b"\n# tampered\n")
    helper.chmod(0o444)
    failure = call(helper, "verify-install", "--manifest", manifest, ok=False)
    assert "digest mismatch" in failure["error"]
    manifest.unlink()
    failure = call(helper, "aggregate", "--run-dir", tmp_path / "missing", ok=False)
    assert "missing file" in failure["error"]


@pytest.mark.parametrize("mutation,error", [
    (lambda value: value.update({"unexpected": True}), "unknown fields"),
    (lambda value: value.update({"schema_version": 2}), "schema_version"),
    (lambda value: value.update({"source_agent": "UWISecurityAuditor"}), "unauthorized"),
    (lambda value: value["run_binding"]["source_ref"].update({"head_sha": "a" * 40}), "run_binding mismatch"),
])
def test_stage_schema_role_and_binding_fail_closed(tmp_path: Path, mutation, error: str):
    fixture = prepare_run(tmp_path, validate=False)
    path = fixture["run"] / "code.findings.json"
    value = read_json(path)
    mutation(value)
    write_json(path, value)
    failure = call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", path, ok=False)
    assert error in failure["error"]
    assert not (fixture["run"] / "status/code.done.json").exists()


def test_validate_stage_canonicalizes_valid_pretty_json_before_marking_done(tmp_path: Path):
    fixture = prepare_run(tmp_path, validate=False)
    path = fixture["run"] / "code.findings.json"
    value = read_json(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    result = call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", path)

    assert result["status"] == "validated"
    assert path.read_bytes() == canonical_bytes(value)
    assert (fixture["run"] / "status/code.done.json").is_file()


def test_pr_dedup_chooses_highest_severity_and_is_byte_deterministic(tmp_path: Path):
    findings = {
        "code": [finding("Important", title="Повторная   авторизация не проверяется")],
        "security": [finding("Block", title="повторная авторизация НЕ проверяется", runtime=True)],
        "bug": [finding("Observation", title="Состояние экрана не обновляется", file=None, line=None, area="Экран баланса")],
    }
    first = prepare_run(tmp_path / "first", findings=findings)
    second = prepare_run(tmp_path / "second", findings=findings)
    first_result = aggregate(first)
    second_result = aggregate(second)
    assert first_result["summary_sha256"] == second_result["summary_sha256"]
    for name in ("canonical-findings.json", "telegram-summary.txt", "audit.md", "delivery-summary.json"):
        assert (first["run"] / name).read_bytes() == (second["run"] / name).read_bytes()

    summary = read_json(first["run"] / "delivery-summary.json")
    assert summary["finding_count"] == 2
    assert summary["severity_counts"] == {"critical": 0, "block": 1, "important": 0, "observation": 1}
    assert summary["verdict"] == "block"
    canonical = read_json(first["run"] / "canonical-findings.json")
    duplicate = canonical["findings"][0]
    assert duplicate["severity"] == "Block"
    assert duplicate["source_agents"] == ["uaudit-security-auditor", "uaudit-swift-audit-specialist"]
    assert duplicate["stages"] == ["code", "security"]
    assert duplicate["needs_runtime_verification"] is True
    telegram = (first["run"] / "telegram-summary.txt").read_text()
    assert "Найдено замечаний: 2" in telegram
    assert "Критические: 0 · Блокирующие: 1 · Важные: 0 · Наблюдения: 1" in telegram
    assert len(telegram.encode()) < 900
    report = (first["run"] / "audit.md").read_text()
    assert report.index("## Замечания") < report.index("## Техническая информация")
    assert "run_binding" not in report
    assert report.rstrip().endswith("structured stage outputs, строгая привязка к diff и каноническая дедупликация.")


def test_complete_zero_removes_stale_reports_and_uses_message_receipt(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", platform="android")
    (fixture["run"] / "audit.md").write_text("stale")
    (fixture["run"] / "audit-final.md").write_text("stale")
    result = aggregate(fixture)
    assert result["finding_count"] == 0
    assert result["mode"] == "message"
    assert not (fixture["run"] / "audit.md").exists()
    assert not (fixture["run"] / "audit-final.md").exists()
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["report"] is None
    assert summary["verdict"] == "approve"
    assert "Итоговый отчёт не формировался" in (fixture["run"] / "telegram-summary.txt").read_text()

    handoff = write_handoff(fixture)
    payload = call(
        fixture["helper"],
        "verify-payload",
        "--run-dir",
        fixture["run"],
        "--handoff",
        handoff,
        "--expected-mode",
        "message",
    )
    assert payload["mode"] == "message"
    assert payload["route_name"] == "UAudit"
    assert payload["report_file"] is None
    receipt = record(fixture, "message")
    assert receipt["status"] == "recorded"
    stored = read_json(fixture["run"] / "delivery-result.json")
    assert stored["report_sha256"] is None
    assert stored["route_source"] == "file_route"


def test_daily_aggregate_streams_diff_larger_than_generic_file_limit(tmp_path: Path):
    diff = b"diff --git a/A b/A\n--- a/A\n+++ b/A\n" + (b"+new\n" * (17 * 1024 * 1024 // 5))
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        platform="android",
        statuses={"qa_verify": "partial"},
        diff_patch=diff,
    )

    result = aggregate(fixture)

    assert result["mode"] == "document"
    report = (fixture["run"] / "audit-final.md").read_text()
    assert "добавлений — 3565158" in report


def test_partial_zero_requires_document_and_allowlisted_human_approval(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", statuses={"qa_verify": "partial"})
    result = aggregate(fixture)
    assert result["audit_status"] == "partial"
    assert result["finding_count"] == 0
    assert result["mode"] == "document"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["verdict"] == "inconclusive"
    assert summary["report"]["file"] == "audit-final.md"
    report = (fixture["run"] / "audit-final.md").read_text()
    assert report.index("> Проверка выполнена частично") < report.index("## Замечания")
    assert "В проверенной части замечаний не найдено." in report
    record(fixture, "document")

    cursor = tmp_path / "state" / "ios-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": BASE_SHA})
    approvers = tmp_path / "state" / "partial-approvers.json"
    write_json(approvers, {"schema_version": 1, "approver_actor_ids": ["human-7"]})
    comments = fixture["run"] / "approval-comments.json"
    summary_sha = hashlib.sha256((fixture["run"] / "delivery-summary.json").read_bytes()).hexdigest()
    write_json(
        comments,
        {
            "schema_version": 1,
            "comments": [
                {
                    "id": "comment-1",
                    "text": f"partial audit approved {summary_sha}",
                    "actor": {"id": "human-7", "kind": "agent"},
                }
            ],
        },
    )
    before = cursor.read_bytes()
    failure = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir",
        fixture["run"],
        "--cursor",
        cursor,
        "--lock-dir",
        fixture["lock"],
        "--reconciled-at",
        RECONCILED_AT,
        "--approval-comments",
        comments,
        "--approvers",
        approvers,
        ok=False,
    )
    assert "allowlisted human" in failure["error"]
    assert cursor.read_bytes() == before

    approved = read_json(comments)
    approved["comments"][0]["actor"]["kind"] = "human"
    write_json(comments, approved)
    fake_approvers = tmp_path / "copied-approvers.json"
    shutil.copyfile(approvers, fake_approvers)
    failure = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir",
        fixture["run"],
        "--cursor",
        cursor,
        "--lock-dir",
        fixture["lock"],
        "--reconciled-at",
        RECONCILED_AT,
        "--approval-comments",
        comments,
        "--approvers",
        fake_approvers,
        ok=False,
    )
    assert "state/partial-approvers.json" in failure["error"]
    applied = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir",
        fixture["run"],
        "--cursor",
        cursor,
        "--lock-dir",
        fixture["lock"],
        "--reconciled-at",
        RECONCILED_AT,
        "--approval-comments",
        comments,
        "--approvers",
        approvers,
    )
    assert applied["status"] == "applied"
    assert applied["approval_comment_id"] == "comment-1"
    updated = read_json(cursor)
    assert updated["last_successfully_audited_sha"] == HEAD_SHA
    assert updated["last_delivery_summary_sha256"] == summary_sha
    resumed = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir",
        fixture["run"],
        "--cursor",
        cursor,
        "--lock-dir",
        fixture["lock"],
        "--reconciled-at",
        RECONCILED_AT,
        "--approval-comments",
        comments,
        "--approvers",
        approvers,
    )
    assert resumed["status"] == "already_applied"


@pytest.mark.parametrize("state", ["blocked", "missing_marker"])
def test_blocked_or_missing_required_stage_never_publishes_summary(tmp_path: Path, state: str):
    statuses = {"security": "blocked"} if state == "blocked" else None
    fixture = prepare_run(tmp_path, statuses=statuses)
    if state == "missing_marker":
        (fixture["run"] / "status/security.done.json").unlink()
    failure = aggregate(fixture, ok=False)
    assert "blocked required stages" in failure["error"] if state == "blocked" else "missing file" in failure["error"]
    assert not (fixture["run"] / "delivery-summary.json").exists()
    assert not (fixture["run"] / "telegram-summary.txt").exists()


def test_wrong_route_or_mode_never_creates_receipt(tmp_path: Path):
    fixture = prepare_run(tmp_path, findings={"security": [finding()]})
    aggregate(fixture)
    write_handoff(fixture)
    arbitrary = tmp_path / "outside-response.json"
    write_json(arbitrary, {"ok": True})
    failure = call(
        fixture["helper"],
        "record-delivery",
        "--run-dir",
        fixture["run"],
        "--response",
        arbitrary,
        "--delivered-at",
        DELIVERED_AT,
        ok=False,
    )
    assert "$RUN/delivery-plugin-response.json" in failure["error"]
    failure = record(fixture, "document", route="Wrong route", ok=False)
    assert "routeName" in failure["error"]
    assert not (fixture["run"] / "delivery-result.json").exists()
    assert not (fixture["run"] / "status/telegram.done").exists()
    failure = record(fixture, "message", ok=False)
    assert "mode" in failure["error"]
    assert not (fixture["run"] / "delivery-result.json").exists()


def test_cursor_cas_rejects_newer_and_conflicting_to_but_confirms_matching_to(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta")
    aggregate(fixture)
    record(fixture, "message")
    cursor = tmp_path / "state" / "ios-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": "c" * 40})
    fake_lock = tmp_path / "copied.lock"
    shutil.copytree(fixture["lock"], fake_lock)
    failure = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir",
        fixture["run"],
        "--cursor",
        cursor,
        "--lock-dir",
        fake_lock,
        "--reconciled-at",
        RECONCILED_AT,
        ok=False,
    )
    assert "state root and routine" in failure["error"]
    base_args = (
        "reconcile-daily", "--run-dir", fixture["run"], "--cursor", cursor,
        "--lock-dir", fixture["lock"], "--reconciled-at", RECONCILED_AT,
    )
    failure = call(fixture["helper"], *base_args, ok=False)
    assert "neither FROM nor matching TO" in failure["error"]
    write_json(
        cursor,
        {
            "last_successfully_audited_sha": HEAD_SHA,
            "last_successful_issue": "UNS-999",
            "last_successful_at": RECONCILED_AT,
            "last_delivery_summary_sha256": "a" * 64,
            "last_telegram_message_id": 999,
        },
    )
    failure = call(fixture["helper"], *base_args, ok=False)
    assert "different generation" in failure["error"]
    receipt = read_json(fixture["run"] / "delivery-result.json")
    write_json(
        cursor,
        {
            "last_successfully_audited_sha": HEAD_SHA,
            "last_successful_issue": "UNS-123",
            "last_successful_at": RECONCILED_AT,
            "last_delivery_summary_sha256": receipt["summary_sha256"],
            "last_telegram_message_id": receipt["message_id"],
        },
    )
    confirmed = call(fixture["helper"], *base_args)
    assert confirmed["status"] == "confirmed"
    assert (fixture["run"] / "status/cursor.done").is_file()


def test_existing_summary_is_immutable_and_tamper_blocks_resume(tmp_path: Path):
    fixture = prepare_run(tmp_path)
    first = aggregate(fixture)
    second = aggregate(fixture)
    assert second["status"] == "ready"
    assert second["summary_sha256"] == first["summary_sha256"]
    text_path = fixture["run"] / "telegram-summary.txt"
    text_path.write_text("подмена\n")
    failure = aggregate(fixture, ok=False)
    assert "digest mismatch" in failure["error"]
    assert text_path.read_text() == "подмена\n"


def test_handoff_path_and_binding_are_exact(tmp_path: Path):
    fixture = prepare_run(tmp_path)
    aggregate(fixture)
    handoff = write_handoff(fixture)
    wrong_path = fixture["run"] / "renamed-handoff.json"
    shutil.copyfile(handoff, wrong_path)
    failure = call(
        fixture["helper"],
        "verify-payload",
        "--run-dir",
        fixture["run"],
        "--handoff",
        wrong_path,
        "--expected-mode",
        "message",
        ok=False,
    )
    assert "$RUN/delivery-handoff.json" in failure["error"]
    value = read_json(handoff)
    value["source_ref"]["head_sha"] = "a" * 40
    write_json(handoff, value)
    failure = call(
        fixture["helper"],
        "verify-payload",
        "--run-dir",
        fixture["run"],
        "--handoff",
        handoff,
        "--expected-mode",
        "message",
        ok=False,
    )
    assert "source_ref" in failure["error"]


def test_routine_lock_cannot_be_reused_by_another_generation(tmp_path: Path):
    first = prepare_run(tmp_path / "first", kind="daily_delta")
    helper = install_helper(tmp_path / "second")
    run = tmp_path / "second" / "run"
    run.mkdir()
    ref = source_ref("daily_delta")
    write_json(
        run / "intake.json",
        {
            "schema_version": 1,
            "issue_identifier": "UNS-999",
            "platform": "ios",
            "audit_kind": "daily_delta",
            "generation_created_at": CREATED_AT,
            "source_ref": ref,
        },
    )
    write_json(run / "profile.json", {"branch": ref["branch"]})
    (run / "commits.tsv").write_text("commit\n")
    (run / "files.tsv").write_text("file\n")
    (run / "diff.patch").write_text("diff --git a/A b/A\n")
    failure = call(
        helper,
        "bind-context",
        "--run-dir",
        run,
        "--intake",
        run / "intake.json",
        "--lock-dir",
        first["lock"],
        ok=False,
    )
    assert "lock metadata mismatch" in failure["error"]
    assert not (run / "run-context.json").exists()


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda item: item.update({"file": "../Secrets.swift"}), "normalized POSIX relative path"),
        (lambda item: item.update({"title": "Опасный\nзаголовок"}), "control characters"),
        (lambda item: item.update({"evidence": "Session is unchecked"}), "Russian report-facing prose"),
        (lambda item: item.update({"line": True}), "positive integer"),
    ],
)
def test_finding_location_prose_and_types_are_strict(tmp_path: Path, mutation, error: str):
    fixture = prepare_run(tmp_path, findings={"code": [finding()]}, validate=False)
    path = fixture["run"] / "code.findings.json"
    value = read_json(path)
    mutation(value["findings"][0])
    write_json(path, value)
    failure = call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", path, ok=False)
    assert error in failure["error"]


def test_daily_research_is_explicit_and_partial_positive_never_approves(tmp_path: Path):
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        platform="android",
        statuses={"infra": "partial"},
        findings={"security": [finding("Critical")]},
    )
    research_path = fixture["run"] / "research-context.findings.json"
    write_json(
        research_path,
        {
            "schema_version": 1,
            "run_binding": fixture["binding"],
            "stage": "research_context",
            "source_agent": "UWAResearchAgent",
            "audit_status": "complete",
            "findings": [],
            "limitations": [{"text": "Внешний контекст проверен без существенных ограничений.", "material": False}],
            "block_reason": None,
        },
    )
    call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", research_path)
    failure = aggregate(fixture, ok=False)
    assert "--research-required" in failure["error"]
    result = call(
        fixture["helper"],
        "aggregate",
        "--run-dir",
        fixture["run"],
        "--research-required",
    )
    assert result["audit_status"] == "partial"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["finding_count"] == 1
    assert summary["severity_counts"]["critical"] == 1
    assert summary["verdict"] == "block"
    assert summary["report"]["file"] == "audit-final.md"
    text = (fixture["run"] / "telegram-summary.txt").read_text()
    assert "Вердикт: блокирует принятие" in text
    assert "Покрытие неполное" in text


def test_input_digest_change_and_summary_count_tamper_fail_closed(tmp_path: Path):
    fixture = prepare_run(tmp_path)
    (fixture["run"] / "pr.diff").write_text("changed after binding\n")
    failure = aggregate(fixture, ok=False)
    assert "input digest mismatch" in failure["error"]
    assert not (fixture["run"] / "delivery-summary.json").exists()

    # Restore the bound bytes, generate once, then prove that an attacker cannot
    # turn the committed count into free-form metadata and ask for regeneration.
    (fixture["run"] / "pr.diff").write_text("diff --git a/A b/A\n--- a/A\n+++ b/A\n@@\n-old\n+new\n")
    aggregate(fixture)
    summary_path = fixture["run"] / "delivery-summary.json"
    summary = read_json(summary_path)
    summary["finding_count"] = 7
    write_json(summary_path, summary)
    failure = aggregate(fixture, ok=False)
    assert "finding_count mismatch" in failure["error"]
    assert read_json(summary_path)["finding_count"] == 7


def test_summary_is_last_payload_and_receipt_crash_repairs_only_marker(tmp_path: Path):
    fixture = prepare_run(tmp_path, findings={"bug": [finding("Observation")]})
    aggregate(fixture)
    summary_mtime = (fixture["run"] / "delivery-summary.json").stat().st_mtime_ns
    for name in ("canonical-findings.json", "telegram-summary.txt", "audit.md"):
        assert (fixture["run"] / name).stat().st_mtime_ns <= summary_mtime
    record(fixture, "document")
    receipt_before = (fixture["run"] / "delivery-result.json").read_bytes()
    (fixture["run"] / "status/telegram.done").unlink()
    resumed = record(fixture, "document")
    assert resumed["status"] == "already_recorded"
    assert (fixture["run"] / "delivery-result.json").read_bytes() == receipt_before
    assert (fixture["run"] / "status/telegram.done").is_file()
