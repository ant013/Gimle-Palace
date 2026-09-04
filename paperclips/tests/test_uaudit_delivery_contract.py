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
    ("forced_full", "ios"): (
        ("code", "UWISwiftAuditor", "code.findings.json"),
        ("security", "UWISecurityAuditor", "security.findings.json"),
        ("crypto", "UWICryptoAuditor", "crypto.findings.json"),
        ("infra", "UWIInfraEngineer", "infra.findings.json"),
        ("qa_verify", "UWIQAEngineer", "qa-verify.findings.json"),
    ),
    ("forced_full", "android"): (
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


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_helper(root: Path) -> Path:
    tools = root / ".uaudit-tools"
    tools.mkdir(parents=True, exist_ok=True)
    helper = tools / "uaudit_delivery_contract.py"
    if helper.exists():
        return helper
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


def prepare_daily_status(root: Path, *, outcome: str = "no_change") -> tuple[Path, dict]:
    helper = install_helper(root)
    descriptor = root / "descriptor.json"
    write_json(descriptor, {
        "schema_version": "uaudit-daily-slot-status/v1",
        "app_id": "unstoppable_wallet",
        "routine_key": "uaudit-daily-ios",
        "platform": "ios",
        "config_sha256": "a" * 64,
    })
    proof = root / "slot-proof.json"
    write_json(proof, {
        "schema_version": "uaudit-daily-slot-status/v1",
        "routine_key": "uaudit-daily-ios",
        "platform": "ios",
        "scheduled_utc_slot": CREATED_AT,
        "descriptor_sha256": sha256_path(descriptor),
        "source": "paperclip_scheduled",
    })
    result = call(
        helper, "prepare-daily-status", "--state-root", root / "state", "--descriptor", descriptor,
        "--slot-proof", proof, "--issue-identifier", "UNS-123", "--outcome", outcome,
        "--selected-head", HEAD_SHA, "--reason", "No new commits.", "--attempt-id", "attempt-1",
        "--created-at", CREATED_AT,
    )
    return helper, result


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
    routine_id: str | None = None,
    lock_routine_id: str | None = None,
    statuses: dict[str, str] | None = None,
    findings: dict[str, list[dict]] | None = None,
    limitations: dict[str, list[dict]] | None = None,
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
    if kind != "pr" and routine_id is not None:
        ref["routine_id"] = routine_id
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
        lock_name = lock_routine_id or ref["routine_id"]
        lock = root / "state" / "locks" / f"{lock_name}.lock"
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
    limitations = limitations or {}
    for stage, agent, filename in PAIRS[(kind, platform)]:
        status = statuses.get(stage, "complete")
        stage_limitations = limitations.get(stage, [])
        block_reason = None
        if status == "partial" and not stage_limitations:
            stage_limitations = [{"text": "Runtime-сценарий не запускался полностью.", "material": True}]
        elif status == "blocked":
            block_reason = "Не удалось получить обязательный вход проверки."
        sidecar = {
            "schema_version": 1,
            "run_binding": binding,
            "stage": stage,
            "source_agent": agent,
            "audit_status": status,
            "findings": findings.get(stage, []),
            "limitations": stage_limitations,
            "block_reason": block_reason,
        }
        path = run / filename
        write_json(path, sidecar)
        if validate:
            call(helper, "validate-stage", "--run-dir", run, "--sidecar", path)
    return {"helper": helper, "run": run, "lock": lock, "binding": binding}


def finalize_translation(fixture: dict) -> dict:
    run = fixture["run"]
    translation = read_json(run / "translation-input.json")
    english = "# English audit\n\nThis is the complete English translation of the attached Russian audit.\n"
    (run / "audit-final.en.md").write_text(english)
    write_json(
        run / "translation-result.json",
        {
            "schema_version": 1,
            "run_binding_sha256": translation["run_binding_sha256"],
            "source_sha256": translation["source_sha256"],
            "target_file": "audit-final.en.md",
            "target_sha256": sha256_path(run / "audit-final.en.md"),
        },
    )
    return call(fixture["helper"], "finalize-translation", "--run-dir", run)


def aggregate(fixture: dict, *, ok: bool = True, research_required: bool = False) -> dict:
    args: list[object] = ["aggregate", "--run-dir", fixture["run"]]
    if research_required:
        args.append("--research-required")
    result = call(fixture["helper"], *args, ok=ok)
    if ok and result["status"] == "translation_required":
        return finalize_translation(fixture)
    return result


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
    args: list[object] = [
        "record-delivery", "--run-dir", fixture["run"], "--response", response,
    ]
    if read_json(fixture["run"] / "delivery-summary.json").get("english_report") is not None:
        english_response = fixture["run"] / "delivery-plugin-response.en.json"
        value = read_json(response)
        value["data"]["data"]["messageId"] = 322
        write_json(english_response, value)
        args.extend(("--english-response", english_response))
    args.extend(("--delivered-at", DELIVERED_AT))
    return call(fixture["helper"], *args, ok=ok)


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


def test_validate_stage_repairs_known_severity_aliases_as_non_material_warnings(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", platform="ios", validate=False)
    path = fixture["run"] / "security.findings.json"
    value = read_json(path)
    aliases = (
        ("Suggestion", "Observation"),
        ("HIGH", "Important"),
        ("blocker", "Block"),
        ("informational", "Observation"),
        ("important", "Important"),
    )
    value["findings"] = [
        finding(alias, line=42 + index, title=f"Неканоническая важность {index}")
        for index, (alias, _) in enumerate(aliases)
    ]
    value["findings"].append(finding("Critical", line=100, title="Каноническая важность"))
    write_json(path, value)

    result = call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", path)

    assert result["status"] == "validated"
    repaired = read_json(path)
    assert [item["severity"] for item in repaired["findings"]] == [
        *(canonical for _, canonical in aliases),
        "Critical",
    ]
    assert len(repaired["limitations"]) == len(aliases)
    assert all(item["material"] is False for item in repaired["limitations"])
    for alias, canonical in aliases:
        assert any(alias in item["text"] and canonical in item["text"] for item in repaired["limitations"])
    assert not any("Critical" in item["text"] for item in repaired["limitations"])
    assert (fixture["run"] / "status/security.done.json").is_file()


def test_validate_stage_rejects_severity_without_deterministic_mapping(tmp_path: Path):
    fixture = prepare_run(tmp_path, validate=False)
    path = fixture["run"] / "code.findings.json"
    value = read_json(path)
    value["findings"] = [finding("Possibly serious")]
    write_json(path, value)

    failure = call(fixture["helper"], "validate-stage", "--run-dir", fixture["run"], "--sidecar", path, ok=False)

    assert "severity is unsupported" in failure["error"]
    assert not (fixture["run"] / "status/code.done.json").exists()


def test_operational_warning_is_idempotent_and_delivered_without_partial_status(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", platform="ios")
    warning = "Paperclip временно не принял комментарий QA; передача продолжена по валидному маркеру."

    first = call(
        fixture["helper"],
        "record-operational-warning",
        "--run-dir",
        fixture["run"],
        "--code",
        "paperclip-comment",
        "--text",
        warning,
    )
    second = call(
        fixture["helper"],
        "record-operational-warning",
        "--run-dir",
        fixture["run"],
        "--code",
        "paperclip-comment",
        "--text",
        warning,
    )

    assert first["status"] == "recorded"
    assert second["status"] == "already_recorded"
    journal = read_json(fixture["run"] / "operational-warnings.json")
    assert journal["run_binding_sha256"] == sha256_path(fixture["run"] / "run-context.json")
    assert journal["warnings"] == [{"code": "paperclip-comment", "text": warning}]

    result = aggregate(fixture)

    assert result["audit_status"] == "complete"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["warning_count"] == 1
    canonical = read_json(fixture["run"] / "canonical-findings.json")
    assert canonical["limitations"] == [
        {
            "material": False,
            "source_agents": ["UAuditControlPlane"],
            "stages": ["control_plane"],
            "text": warning,
        }
    ]
    assert warning in (fixture["run"] / "audit-final.ru.md").read_text()


@pytest.mark.parametrize(
    ("code", "text", "error"),
    (
        ("Paperclip comment", "Paperclip не принял комментарий.", "code"),
        ("paperclip-comment", "Comment failed.", "Russian"),
    ),
)
def test_operational_warning_rejects_invalid_input(
    tmp_path: Path, code: str, text: str, error: str
):
    fixture = prepare_run(tmp_path, kind="daily_delta", platform="ios")
    failure = call(
        fixture["helper"],
        "record-operational-warning",
        "--run-dir",
        fixture["run"],
        "--code",
        code,
        "--text",
        text,
        ok=False,
    )

    assert error in failure["error"]
    assert not (fixture["run"] / "operational-warnings.json").exists()


def test_post_aggregation_warning_does_not_invalidate_translation_snapshot(tmp_path: Path):
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        platform="ios",
        findings={"security": [finding("Important")]},
    )
    pending = call(fixture["helper"], "aggregate", "--run-dir", fixture["run"])
    assert pending["status"] == "translation_required"

    call(
        fixture["helper"],
        "record-operational-warning",
        "--run-dir",
        fixture["run"],
        "--code",
        "paperclip-comment",
        "--text",
        "Paperclip не принял комментарий после агрегации; payload оставлен неизменным.",
    )
    ready = finalize_translation(fixture)

    assert ready["status"] == "ready"
    assert read_json(fixture["run"] / "delivery-summary.json")["warning_count"] == 0
    assert read_json(fixture["run"] / "operational-warnings.json")["warnings"]


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
    (fixture["run"] / "audit-final.ru.md").write_text("stale")
    (fixture["run"] / "audit-final.en.md").write_text("stale")
    result = aggregate(fixture)
    assert result["finding_count"] == 0
    assert result["mode"] == "message"
    assert not (fixture["run"] / "audit.md").exists()
    assert not (fixture["run"] / "audit-final.md").exists()
    assert not (fixture["run"] / "audit-final.ru.md").exists()
    assert not (fixture["run"] / "audit-final.en.md").exists()
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


def test_ios_non_material_runtime_warning_is_delivered_and_advances_cursor(tmp_path: Path):
    warning = "На старом iMac недоступны полный Xcode и проверка на устройстве."
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        limitations={
            "qa_verify": [
                {
                    "text": warning,
                    "material": False,
                }
            ]
        },
    )

    result = aggregate(fixture)
    assert result["audit_status"] == "complete"
    assert result["finding_count"] == 0
    assert result["mode"] == "document"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["warning_count"] == 1
    telegram = (fixture["run"] / "telegram-summary.txt").read_text()
    assert "Предупреждения: 1" in telegram
    assert "Итоговый отчёт не формировался" not in telegram
    report = (fixture["run"] / "audit-final.ru.md").read_text()
    assert "## Предупреждения" in report
    assert warning in report
    record(fixture, "document")

    cursor = tmp_path / "state" / "ios-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": BASE_SHA})
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
    )
    assert applied["status"] == "applied"
    assert read_json(cursor)["last_successfully_audited_sha"] == HEAD_SHA
    assert (fixture["run"] / "status/cursor.done").is_file()

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
    )
    assert resumed["status"] == "already_applied"


def test_legacy_complete_zero_warning_summary_remains_verifiable(tmp_path: Path):
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        limitations={
            "qa_verify": [
                {
                    "text": "На старом iMac недоступна проверка на устройстве.",
                    "material": False,
                }
            ]
        },
    )
    aggregate(fixture)
    run = fixture["run"]
    summary = read_json(run / "delivery-summary.json")
    summary.pop("warning_count")
    summary["report"] = None
    summary["english_report"] = None
    for name in (
        "audit-final.ru.md",
        "audit-final.en.md",
        "translation-input.json",
        "translation-result.json",
    ):
        (run / name).unlink(missing_ok=True)
    branch = fixture["binding"]["source_ref"]["branch"]
    legacy_telegram = (
        f"Аудит iOS {branch} {BASE_SHA[:7]}..{HEAD_SHA[:7]} завершён\n"
        "Найдено замечаний: 0\n"
        "Критические: 0 · Блокирующие: 0 · Важные: 0 · Наблюдения: 0\n"
        "Вердикт: можно принимать\n"
        "Итоговый отчёт не формировался\n"
    )
    (run / "telegram-summary.txt").write_text(legacy_telegram)
    summary["telegram_text"]["sha256"] = sha256_path(run / "telegram-summary.txt")
    write_json(run / "delivery-summary.json", summary)
    write_json(
        run / "status/aggregate.done",
        {
            "schema_version": 1,
            "summary_sha256": sha256_path(run / "delivery-summary.json"),
            "run_binding_sha256": summary["run_binding_sha256"],
        },
    )

    handoff = write_handoff(fixture)
    payload = call(
        fixture["helper"],
        "verify-payload",
        "--run-dir",
        run,
        "--handoff",
        handoff,
        "--expected-mode",
        "message",
    )
    assert payload["mode"] == "message"


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
    report = (fixture["run"] / "audit-final.ru.md").read_text()
    assert "добавлений — 3565158" in report


def test_daily_document_requires_bound_english_translation_before_delivery(tmp_path: Path):
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        findings={"security": [finding("Important")]},
    )

    pending = call(fixture["helper"], "aggregate", "--run-dir", fixture["run"])

    assert pending == {
        "ok": True,
        "status": "translation_required",
        "audit_status": "complete",
        "finding_count": 1,
        "translation_input": "translation-input.json",
    }
    assert not (fixture["run"] / "delivery-summary.json").exists()
    translation = read_json(fixture["run"] / "translation-input.json")
    assert translation["source_file"] == "audit-final.ru.md"
    assert translation["target_file"] == "audit-final.en.md"

    ready = finalize_translation(fixture)

    assert ready["mode"] == "document"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["report"]["file"] == "audit-final.ru.md"
    assert summary["english_report"]["file"] == "audit-final.en.md"
    payload = call(
        fixture["helper"], "verify-payload", "--run-dir", fixture["run"],
        "--handoff", write_handoff(fixture), "--expected-mode", "document",
    )
    assert payload["english_report_file"].endswith("audit-final.en.md")


def test_bilingual_delivery_records_russian_then_recovers_english_only(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", findings={"code": [finding()]})
    aggregate(fixture)
    write_handoff(fixture)
    response = fixture["run"] / "delivery-plugin-response.json"
    write_json(response, {
        "ok": True, "mode": "document", "routeSource": "file_route", "routeName": "UAudit",
        "issueIdentifier": "UNS-123", "projectKey": "UNS", "messageId": 321,
    })

    pending = call(
        fixture["helper"], "record-delivery", "--run-dir", fixture["run"], "--response", response,
        "--delivered-at", DELIVERED_AT,
    )

    assert pending["status"] == "english_pending"
    assert not (fixture["run"] / "delivery-result.json").exists()
    assert read_json(fixture["run"] / "delivery-progress.json")["message_id"] == 321
    receipt = record(fixture, "document")
    stored = read_json(fixture["run"] / "delivery-result.json")
    assert receipt["english_message_id"] == 322
    assert stored["english_message_id"] == 322
    assert stored["english_report_sha256"] == read_json(fixture["run"] / "delivery-summary.json")["english_report"]["sha256"]
    assert not (fixture["run"] / "delivery-progress.json").exists()


def test_existing_single_language_daily_summary_remains_reconcilable(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", findings={"code": [finding()]})
    aggregate(fixture)
    run = fixture["run"]
    summary = read_json(run / "delivery-summary.json")
    (run / "audit-final.ru.md").replace(run / "audit-final.md")
    (run / "audit-final.en.md").unlink()
    (run / "translation-input.json").unlink()
    (run / "translation-result.json").unlink()
    summary.pop("english_report")
    summary.pop("warning_count")
    summary["report"] = {"file": "audit-final.md", "sha256": sha256_path(run / "audit-final.md")}
    write_json(run / "delivery-summary.json", summary)
    summary_sha = sha256_path(run / "delivery-summary.json")
    write_json(run / "status/aggregate.done", {
        "schema_version": 1,
        "summary_sha256": summary_sha,
        "run_binding_sha256": summary["run_binding_sha256"],
    })

    resumed = aggregate(fixture)

    assert resumed["status"] == "ready"
    assert resumed["summary_sha256"] == summary_sha
    record(fixture, "document")
    assert "english_message_id" not in read_json(run / "delivery-result.json")


@pytest.mark.parametrize("platform", ("android", "ios"))
def test_forced_full_uses_russian_v1_delivery_without_daily_cursor(tmp_path: Path, platform: str):
    fixture = prepare_run(
        tmp_path,
        kind="forced_full",
        platform=platform,
        statuses={"qa_verify": "partial"},
        findings={"code": [finding(title="Проверка полного диапазона")]},
    )

    result = aggregate(fixture)

    assert result["mode"] == "document"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["audit_kind"] == "forced_full"
    report = (fixture["run"] / "audit-final.ru.md").read_text()
    assert "# Аудит изменений" in report
    assert "Проверка полного диапазона" in report
    assert "Аудит " in (fixture["run"] / "telegram-summary.txt").read_text()
    failure = call(
        fixture["helper"],
        "reconcile-daily",
        "--run-dir", fixture["run"],
        "--cursor", tmp_path / f"{platform}-version-audit.json",
        "--lock-dir", fixture["lock"],
        "--reconciled-at", RECONCILED_AT,
        ok=False,
    )
    assert "requires a daily summary" in failure["error"]


def test_partial_zero_delivers_and_advances_cursor_without_human_approval(tmp_path: Path):
    fixture = prepare_run(tmp_path, kind="daily_delta", statuses={"qa_verify": "partial"})
    result = aggregate(fixture)
    assert result["audit_status"] == "partial"
    assert result["finding_count"] == 0
    assert result["mode"] == "document"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["verdict"] == "inconclusive"
    assert summary["report"]["file"] == "audit-final.ru.md"
    assert summary["english_report"]["file"] == "audit-final.en.md"
    report = (fixture["run"] / "audit-final.ru.md").read_text()
    assert report.index("> Проверка выполнена частично") < report.index("## Замечания")
    assert "В проверенной части замечаний не найдено." in report
    record(fixture, "document")

    cursor = tmp_path / "state" / "ios-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": BASE_SHA})
    summary_sha = hashlib.sha256((fixture["run"] / "delivery-summary.json").read_bytes()).hexdigest()
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
    )
    assert applied["status"] == "applied"
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
    )
    assert resumed["status"] == "already_applied"


def test_reconcile_daily_accepts_metadata_bound_versioned_lock_for_stable_routine_id(tmp_path: Path):
    fixture = prepare_run(
        tmp_path,
        kind="daily_delta",
        platform="android",
        routine_id="uaudit-daily-android",
        lock_routine_id="daily-android-version-0.50",
    )
    aggregate(fixture)
    record(fixture, "message")
    cursor = tmp_path / "state" / "android-version-audit.json"
    write_json(cursor, {"last_successfully_audited_sha": BASE_SHA})

    result = call(
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
    )

    assert result["status"] == "applied"
    assert read_json(cursor)["last_successfully_audited_sha"] == HEAD_SHA


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
    result = aggregate(fixture, research_required=True)
    assert result["audit_status"] == "partial"
    summary = read_json(fixture["run"] / "delivery-summary.json")
    assert summary["finding_count"] == 1
    assert summary["severity_counts"]["critical"] == 1
    assert summary["verdict"] == "block"
    assert summary["report"]["file"] == "audit-final.ru.md"
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


def test_daily_no_change_status_is_idempotent_and_never_creates_a_cursor(tmp_path: Path):
    helper, prepared = prepare_daily_status(tmp_path)
    run = Path(prepared["run_dir"])
    assert prepared["status"] == "ready"
    assert "no_change" in (run / "telegram-summary.txt").read_text()
    assert not (tmp_path / "state/ios-version-audit.json").exists()

    _, duplicate = prepare_daily_status(tmp_path)
    assert duplicate["status"] == "already_prepared"
    response = tmp_path / "response.json"
    write_json(response, {
        "ok": True, "mode": "message", "routeName": "UAudit", "issueIdentifier": "UNS-123", "messageId": 77,
    })
    result = call(helper, "record-daily-status", "--run-dir", run, "--response", response, "--delivered-at", DELIVERED_AT)
    assert result["message_id"] == 77
    resumed = call(helper, "record-daily-status", "--run-dir", run, "--response", response, "--delivered-at", DELIVERED_AT)
    assert resumed["status"] == "already_recorded"
    assert not (tmp_path / "state/ios-version-audit.json").exists()


def test_daily_status_rejects_slot_proof_for_a_different_descriptor(tmp_path: Path):
    helper = install_helper(tmp_path)
    descriptor = tmp_path / "descriptor.json"
    write_json(descriptor, {
        "schema_version": "uaudit-daily-slot-status/v1", "app_id": "unstoppable_wallet",
        "routine_key": "uaudit-daily-ios", "platform": "ios", "config_sha256": "a" * 64,
    })
    proof = tmp_path / "slot-proof.json"
    write_json(proof, {
        "schema_version": "uaudit-daily-slot-status/v1", "routine_key": "uaudit-daily-ios", "platform": "ios",
        "scheduled_utc_slot": CREATED_AT, "descriptor_sha256": "b" * 64, "source": "paperclip_scheduled",
    })
    failure = call(
        helper, "prepare-daily-status", "--state-root", tmp_path / "state", "--descriptor", descriptor,
        "--slot-proof", proof, "--issue-identifier", "UNS-123", "--outcome", "no_change",
        "--reason", "No new commits.", "--attempt-id", "attempt-1", "--created-at", CREATED_AT, ok=False,
    )
    assert "descriptor digest mismatch" in failure["error"]
