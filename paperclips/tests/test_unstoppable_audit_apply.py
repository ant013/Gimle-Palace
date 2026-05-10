import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import unstoppable_audit_apply as apply


def fixture_path(name):
    return Path(__file__).resolve().parents[1] / "manifests" / "unstoppable-audit" / name


def load_manifests():
    preflight = apply.read_json(fixture_path("gate-b2-preflight.json"))
    dry_run = apply.read_json(fixture_path("gate-b1-dry-run.json"))
    return preflight, dry_run


def test_validate_preflight_accepts_recreate_policy():
    preflight, _ = load_manifests()

    assert apply.validate_preflight(preflight) == []


def test_build_operations_orders_recreate_before_hires():
    preflight, dry_run = load_manifests()

    operations = apply.build_operations(preflight, dry_run)

    assert operations[0]["kind"] == "terminate_agent"
    assert operations[0]["agentName"] == "AUCEO"
    assert operations[1]["kind"] == "hire_agent"
    assert operations[1]["agentName"] == "AUCEO"
    assert operations[2]["agentName"] in {"UWACTO", "UWICTO"}
    assert all(operation.get("stopOnFailure", True) for operation in operations if operation["kind"] != "skip_agent")


def test_rollback_manifest_contains_existing_auceo_snapshot_only():
    preflight, _ = load_manifests()

    rollback = apply.build_rollback_manifest(preflight)

    assert rollback["snapshots"]["AUCEO"]["agent"]["id"] == "dcdd8871-5b44-4563-bb00-f8cca292a69e"
    assert "UWICTO" not in rollback["snapshots"]
    assert "PAPERCLIP_API_KEY" not in str(rollback)


def test_apply_plan_uses_symbolic_reports_to_dependencies():
    preflight, dry_run = load_manifests()

    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))
    by_name = {operation["agentName"]: operation for operation in plan["operations"] if operation["kind"] == "hire_agent"}

    assert plan["ok"] is True
    assert by_name["AUCEO"]["dependsOn"] == []
    assert by_name["UWICTO"]["dependsOn"] == ["AUCEO"]
    assert by_name["UWISwiftAuditor"]["dependsOn"] == ["UWICTO"]
    assert by_name["UWAKotlinAuditor"]["dependsOn"] == ["UWACTO"]


def test_apply_refuses_without_live_confirmation(tmp_path):
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))
    plan_path = tmp_path / "plan.json"
    apply.write_json(plan_path, plan)

    args = apply.parse_args(["apply", "--plan", str(plan_path)])

    with pytest.raises(RuntimeError, match="refusing live mutation"):
        apply.command_apply(args)


def test_validate_preflight_rejects_blockers():
    preflight, _ = load_manifests()
    broken = dict(preflight)
    broken["ok"] = False
    broken["blockers"] = ["blocked"]

    errors = apply.validate_preflight(broken)

    assert "preflight ok must be true" in errors
    assert "preflight blockers must be empty" in errors


def test_materialize_hire_payload_resolves_placeholders_and_manager_id():
    preflight, dry_run = load_manifests()
    operations = apply.build_operations(preflight, dry_run)
    uwicto = next(operation for operation in operations if operation["agentName"] == "UWICTO")

    payload = apply.materialize_hire_payload(
        uwicto,
        {"AUCEO": "auceo-id"},
        {
            "${UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID}": "issue-id",
            "${TELEGRAM_REDACTED_REPORTS_CHAT_ID}": "-100reports",
            "${TELEGRAM_OPS_CHAT_ID}": "-100ops",
        },
    )

    assert payload["reportsTo"] == "auceo-id"
    assert payload["sourceIssueId"] == "issue-id"
    assert payload["adapterConfig"]["env"]["TELEGRAM_OPS_CHAT_ID"] == "-100ops"


def test_runtime_replacements_require_source_issue_id(monkeypatch):
    monkeypatch.delenv("UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID", raising=False)
    monkeypatch.delenv("PAPERCLIP_SOURCE_ISSUE_ID", raising=False)
    args = apply.parse_args(
        [
            "apply",
            "--allow-live",
            "--confirm",
            apply.LIVE_CONFIRMATION,
        ]
    )
    config = {
        "telegram": {
            "redacted_reports_chat_id": "-100reports",
            "ops_chat_id": "-100ops",
        }
    }

    with pytest.raises(RuntimeError, match="source issue id is required"):
        apply.runtime_replacements(args, config)


def test_readiness_manifest_reports_missing_source_issue_without_network():
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))

    manifest = apply.build_readiness_manifest(
        plan,
        "https://paperclip.example",
        None,
        "company-id",
        False,
    )

    assert manifest["ok"] is False
    assert manifest["live_mutation"] is False
    assert manifest["safe_methods_only"] is True
    assert any("source issue id is required" in blocker for blocker in manifest["blockers"])
    assert any("token is required" in blocker for blocker in manifest["blockers"])
    assert manifest["warnings"] == []
    assert manifest["checks"] == []


def test_readiness_manifest_checks_identity_company_and_rollback_config(monkeypatch):
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))
    calls = []

    def fake_get(api_base, token, path):
        calls.append(path)
        if path == "/api/agents/me":
            return {"id": "operator-id", "name": "Operator"}
        if path == "/api/companies/company-id/agents":
            return [
                {
                    "id": "dcdd8871-5b44-4563-bb00-f8cca292a69e",
                    "name": "AUCEO",
                    "status": "paused",
                }
            ]
        if path == "/api/agents/dcdd8871-5b44-4563-bb00-f8cca292a69e/configuration":
            return {"adapterType": "codex_local", "adapterConfig": {}}
        raise AssertionError(path)

    monkeypatch.setattr(apply.team, "http_get_json", fake_get)

    manifest = apply.build_readiness_manifest(
        plan,
        "https://paperclip.example",
        "token",
        "company-id",
        True,
    )

    assert manifest["ok"] is True
    assert manifest["blockers"] == []
    assert calls == [
        "/api/agents/me",
        "/api/companies/company-id/agents",
        "/api/agents/dcdd8871-5b44-4563-bb00-f8cca292a69e/configuration",
    ]
    assert {check["name"] for check in manifest["checks"]} == {
        "identity",
        "company_agents",
        "terminate_target",
        "rollback_config_readback",
    }


def test_readiness_identity_failure_is_warning_when_company_checks_pass(monkeypatch):
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))

    def fake_get(api_base, token, path):
        if path == "/api/agents/me":
            raise RuntimeError("HTTP 401")
        if path == "/api/companies/company-id/agents":
            return [
                {
                    "id": "dcdd8871-5b44-4563-bb00-f8cca292a69e",
                    "name": "AUCEO",
                    "status": "paused",
                }
            ]
        if path == "/api/agents/dcdd8871-5b44-4563-bb00-f8cca292a69e/configuration":
            return {"adapterType": "codex_local", "adapterConfig": {}}
        raise AssertionError(path)

    monkeypatch.setattr(apply.team, "http_get_json", fake_get)

    manifest = apply.build_readiness_manifest(
        plan,
        "https://paperclip.example",
        "token",
        "company-id",
        True,
    )

    assert manifest["ok"] is True
    assert manifest["blockers"] == []
    assert manifest["warnings"] == ["identity check failed: HTTP 401"]


def test_execute_operations_stops_on_pending_approval(monkeypatch):
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))
    calls = []

    def fake_post(api_base, token, path, payload):
        calls.append((path, payload))
        if path.endswith("/terminate"):
            return {"agent": {"id": "old-auceo", "name": "AUCEO", "status": "terminated"}}
        return {
            "agent": {"id": "new-auceo", "name": "AUCEO", "status": "pending_approval"},
            "approval": {"id": "approval-id", "status": "pending"},
        }

    monkeypatch.setattr(apply, "http_post_json", fake_post)

    result = apply.execute_operations(
        plan,
        "https://paperclip.example",
        "token",
        "company-id",
        {
            "${UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID}": "issue-id",
            "${TELEGRAM_REDACTED_REPORTS_CHAT_ID}": "-100reports",
            "${TELEGRAM_OPS_CHAT_ID}": "-100ops",
        },
    )

    assert result["ok"] is False
    assert result["executed_count"] == 2
    assert result["created_agent_ids"] == {"AUCEO": "new-auceo"}
    assert result["stopped_reason"] == "AUCEO: pending approval"
    assert calls[0][0] == "/api/agents/dcdd8871-5b44-4563-bb00-f8cca292a69e/terminate"
    assert calls[1][0] == "/api/companies/company-id/agent-hires"


def test_execute_operations_resolves_reports_to_after_created_manager(monkeypatch):
    preflight, dry_run = load_manifests()
    plan = apply.build_apply_plan(preflight, dry_run, Path("rollback.json"))
    plan["operations"] = [
        operation
        for operation in plan["operations"]
        if operation["kind"] == "hire_agent" and operation["agentName"] in {"AUCEO", "UWICTO"}
    ]
    post_payloads = []

    def fake_post(api_base, token, path, payload):
        post_payloads.append(payload)
        name = payload["name"]
        return {"agent": {"id": f"{name}-id", "name": name, "status": "active"}}

    def fake_get(api_base, token, path):
        agent_id = path.rsplit("/", 2)[-2]
        payload = next(payload for payload in post_payloads if payload["name"] == agent_id.removesuffix("-id"))
        return {"adapterType": payload["adapterType"], "adapterConfig": payload["adapterConfig"]}

    monkeypatch.setattr(apply, "http_post_json", fake_post)
    monkeypatch.setattr(apply.team, "http_get_json", fake_get)

    result = apply.execute_operations(
        plan,
        "https://paperclip.example",
        "token",
        "company-id",
        {
            "${UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID}": "issue-id",
            "${TELEGRAM_REDACTED_REPORTS_CHAT_ID}": "-100reports",
            "${TELEGRAM_OPS_CHAT_ID}": "-100ops",
        },
        stop_on_pending_approval=False,
    )

    assert result["ok"] is True
    assert post_payloads[0]["reportsTo"] is None
    assert post_payloads[1]["reportsTo"] == "AUCEO-id"
    assert result["created_agent_ids"] == {"AUCEO": "AUCEO-id", "UWICTO": "UWICTO-id"}
