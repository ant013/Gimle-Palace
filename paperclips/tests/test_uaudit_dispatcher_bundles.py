from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "paperclips" / "scripts"
CONFIG = REPO / "paperclips/projects/uaudit/daily-version-branch-routines.yaml"
MANIFEST = REPO / "paperclips/projects/uaudit/paperclip-agent-assembly.yaml"
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

sys.path.insert(0, str(SCRIPTS))

from reconcile_uaudit_routines import (  # noqa: E402
    build_plan,
    load_config,
    normalize_current_routines,
    required_agent_names,
    resolve_agent_ids,
    validate_config_agents,
)


def load_manifest():
    return yaml.safe_load(MANIFEST.read_text())


def test_daily_routine_config_uses_names_not_uuids_and_resolves_agents():
    raw = CONFIG.read_text()
    assert not UUID_RE.search(raw)
    config = load_config(CONFIG)
    assert config["limits"] == {"max_commits": 30, "max_files": 300, "max_diff_lines": 3000}
    assert {r["platform"] for r in config["routines"]} == {"android", "ios"}
    agents = resolve_agent_ids("uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml")
    validate_config_agents(config, agents)
    assert {"AUCEO", "UWACTO", "UWICTO", "UWAInfraEngineer", "UWIInfraEngineer"} <= required_agent_names(config)


def test_uaudit_platform_ctos_use_custom_project_dispatcher_roles():
    data = load_manifest()
    by_name = {agent["agent_name"]: agent for agent in data["agents"]}
    assert by_name["UWACTO"]["profile"] == "custom"
    assert by_name["UWACTO"]["role_source"] == "paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md"
    assert by_name["UWICTO"]["profile"] == "custom"
    assert by_name["UWICTO"]["role_source"] == "paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md"
    assert by_name["AUCEO"]["profile"] == "cto"


def test_generated_dispatcher_bundles_are_slim_and_decision_only():
    forbidden = [
        "CTO profile",
        "Merge gate",
        "merge readiness",
        "APPROVE",
        "git merge",
        "Direct push",
    ]
    for name in ("UWACTO", "UWICTO"):
        path = REPO / f"paperclips/dist/uaudit/codex/{name}.md"
        assert path.is_file(), f"missing generated bundle {path}"
        text = path.read_text()
        assert text.count("\n") <= 100
        assert len(text.encode()) <= 4096
        for phrase in forbidden:
            assert phrase not in text, f"{name} contains forbidden phrase {phrase!r}"
        assert "daily-version-branch-routines.yaml" in text
        assert "assigneeAgentId=00000000-0000-0000-0000-000000000010" in text
        assert "Do not assign infra, create `$RUN`, write status files, send Telegram, or update the cursor." in text
        assert "max_files=300" in text


def test_infra_bundles_no_longer_own_daily_intake_decisions():
    forbidden = [
        "If the cursor file is missing, create it",
        "noop.done",
        "If `FROM == TO`",
        "No new commits for",
    ]
    for name, cto in (("UWAInfraEngineer", "UWACTO"), ("UWIInfraEngineer", "UWICTO")):
        path = REPO / f"paperclips/dist/uaudit/codex/{name}.md"
        text = path.read_text()
        for phrase in forbidden:
            assert phrase not in text, f"{name} still contains intake phrase {phrase!r}"
        assert f"Run this path only after `{cto}` PATCHes this issue" in text
        assert "mode=initialize_cursor" in text
        assert "mode=audit_delta" in text
        assert "Never advance the cursor before successful Telegram delivery" in text
        assert "more than 300 files" in text
        assert "Persist each completed subagent JSON immediately" in text
        assert "$RUN/recovery.json" in text
        assert "resume by spawning only missing reviewers" in text


def test_reconcile_plan_is_dry_run_and_uses_dispatcher_assignments():
    config = load_config(CONFIG)
    agents = resolve_agent_ids("uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml")
    current = normalize_current_routines({
        "routines": [
            {"id": "daily-android-version-0.49", "assigneeAgentId": "old-android"},
            {"id": "daily-ios-version-0.49", "assigneeAgentId": agents["UWICTO"]},
        ]
    })
    plan = build_plan(config, agents, current)
    by_id = {item["routine_id"]: item for item in plan}
    assert by_id["daily-android-version-0.49"]["dispatcher"] == "UWACTO"
    assert by_id["daily-android-version-0.49"]["desired_assigneeAgentId"] == agents["UWACTO"]
    assert by_id["daily-android-version-0.49"]["needs_update"] is True
    assert by_id["daily-ios-version-0.49"]["needs_update"] is False


def test_reconcile_plan_matches_live_uuid_routine_and_detects_cursor_drift():
    config = load_config(CONFIG)
    agents = resolve_agent_ids("uaudit", REPO / "paperclips/projects/uaudit/bindings.local-example.yaml")
    current = normalize_current_routines({
        "routines": [
            {
                "id": "6f14f50f-4834-4812-b9e0-aee857397c7c",
                "title": "UAudit daily Android version delta audit",
                "description": (
                    "UAudit daily version-branch delta audit\n"
                    "platform: android\n"
                    "cursor: /Users/Shared/UnstoppableAudit/artifacts/UWAInfraEngineer/cursor.json\n"
                ),
                "assigneeAgentId": agents["UWACTO"],
            },
            {
                "id": "12cf9f8d-0000-4000-9000-000000000000",
                "title": "UAudit daily iOS version delta audit",
                "description": (
                    "UAudit daily version-branch delta audit\n"
                    "platform: ios\n"
                    "cursor: /Users/Shared/UnstoppableAudit/state/ios-version-audit.json\n"
                ),
                "assigneeAgentId": agents["UWICTO"],
            },
        ]
    })
    plan = build_plan(config, agents, current, {"project_root": "/Users/Shared/UnstoppableAudit"})
    by_id = {item["routine_id"]: item for item in plan}

    android = by_id["daily-android-version-0.49"]
    assert android["current_routine_id"] == "6f14f50f-4834-4812-b9e0-aee857397c7c"
    assert android["matched_by"] == "title"
    assert android["needs_assignee_update"] is False
    assert android["needs_cursor_update"] is True
    assert android["desired_cursor_path"] == "/Users/Shared/UnstoppableAudit/state/android-version-audit.json"
    assert android["desired_description"] is not None
    assert "/Users/Shared/UnstoppableAudit/state/android-version-audit.json" in android["desired_description"]
    assert "/artifacts/UWAInfraEngineer/cursor.json" not in android["desired_description"]

    ios = by_id["daily-ios-version-0.49"]
    assert ios["needs_update"] is False


def test_validate_uaudit_docs_script_passes():
    spec = importlib.util.spec_from_file_location("validate_uaudit_docs", SCRIPTS / "validate_uaudit_docs.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0
