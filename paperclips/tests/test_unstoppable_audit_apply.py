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
