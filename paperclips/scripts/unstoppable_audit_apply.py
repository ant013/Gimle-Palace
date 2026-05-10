#!/usr/bin/env python3
"""Gate C apply planning for UnstoppableAudit.

This script is deliberately conservative. The default `plan` command performs
no Paperclip mutations. It turns the approved Gate B2 preflight into an ordered
operation plan and rollback manifest that can be reviewed before live apply.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import unstoppable_audit_team as team


DEFAULT_PREFLIGHT = Path("paperclips/manifests/unstoppable-audit/gate-b2-preflight.json")
DEFAULT_DRY_RUN = Path("paperclips/manifests/unstoppable-audit/gate-b1-dry-run.json")
DEFAULT_APPLY_PLAN = Path("paperclips/manifests/unstoppable-audit/gate-c-apply-plan.json")
DEFAULT_ROLLBACK = Path("paperclips/manifests/unstoppable-audit/rollback-gate-c.json")
DEFAULT_READINESS = Path("paperclips/manifests/unstoppable-audit/gate-c-readiness.json")
DEFAULT_SOURCE_ISSUE = Path("paperclips/manifests/unstoppable-audit/gate-c-source-issue.json")
DEFAULT_SOURCE_ISSUE_CREATE = Path("paperclips/manifests/unstoppable-audit/gate-c-source-issue-create.json")
DEFAULT_LIVE_RESULT = Path("paperclips/manifests/unstoppable-audit/gate-c-live-result.json")
DEFAULT_RUNTIME_FIX = Path("paperclips/manifests/unstoppable-audit/gate-d-runtime-fix.json")
LIVE_CONFIRMATION = "UNSTOPPABLE_AUDIT_LIVE_APPLY"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def http_post_json(api_base: str, token: str, path: str, payload: dict[str, Any]) -> Any:
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            "-w",
            "\n%{http_code}",
            api_base.rstrip("/") + path,
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Accept: application/json",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        input=json.dumps(payload, sort_keys=True),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"POST {path} failed: {result.stderr.strip()}")
    if "\n" not in result.stdout:
        raise RuntimeError(f"POST {path} returned malformed curl output")
    body, http_code = result.stdout.rsplit("\n", 1)
    if http_code not in {"200", "201", "202", "204"}:
        raise RuntimeError(f"POST {path} failed with HTTP {http_code}: {body[:300]}")
    return json.loads(body) if body else None


def http_patch_json(api_base: str, token: str, path: str, payload: dict[str, Any]) -> Any:
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "PATCH",
            "-w",
            "\n%{http_code}",
            api_base.rstrip("/") + path,
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Accept: application/json",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        input=json.dumps(payload, sort_keys=True),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"PATCH {path} failed: {result.stderr.strip()}")
    if "\n" not in result.stdout:
        raise RuntimeError(f"PATCH {path} returned malformed curl output")
    body, http_code = result.stdout.rsplit("\n", 1)
    if http_code not in {"200", "201", "202", "204"}:
        raise RuntimeError(f"PATCH {path} failed with HTTP {http_code}: {body[:300]}")
    return json.loads(body) if body else None


def validate_preflight(preflight: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if preflight.get("gate") != "B2":
        errors.append("preflight gate must be B2")
    if preflight.get("mode") != "authenticated-preflight":
        errors.append("preflight mode must be authenticated-preflight")
    if preflight.get("team") != "UnstoppableAudit":
        errors.append("preflight team must be UnstoppableAudit")
    if not preflight.get("ok"):
        errors.append("preflight ok must be true")
    if preflight.get("blockers"):
        errors.append("preflight blockers must be empty")
    operator_policy = preflight.get("operator_policy") or {}
    if operator_policy.get("auceo") != "recreate":
        errors.append("operator_policy.auceo must be recreate before Gate C plan")
    for decision in preflight.get("decisions", []):
        if not decision.get("ok"):
            errors.append(f"{decision.get('name')}: decision ok must be true")
        if decision.get("blockers"):
            errors.append(f"{decision.get('name')}: decision blockers must be empty")
    return errors


def validate_apply_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not plan.get("ok"):
        errors.append("apply plan ok must be true")
    if plan.get("gate") != "C-apply-plan":
        errors.append("apply plan gate must be C-apply-plan")
    if plan.get("mode") != "dry-run":
        errors.append("apply plan mode must be dry-run")
    if plan.get("team") != "UnstoppableAudit":
        errors.append("apply plan team must be UnstoppableAudit")
    if plan.get("live_mutation"):
        errors.append("apply plan must be generated as non-mutating dry-run")
    if not isinstance(plan.get("operations"), list) or not plan.get("operations"):
        errors.append("apply plan operations must be a non-empty list")
    return errors


def agents_by_name(dry_run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(agent["name"]): agent for agent in dry_run.get("agents", [])}


def role_for_agent(agent: dict[str, Any]) -> str:
    family = str(agent.get("family", "general"))
    if agent["name"] == "AUCEO":
        return "ceo"
    if family == "coordination":
        return "cto"
    if family == "infra":
        return "devops"
    if family == "qa":
        return "qa"
    if family == "research":
        return "researcher"
    if family == "writer":
        return "general"
    return "engineer"


def icon_for_agent(agent: dict[str, Any]) -> str:
    family = str(agent.get("family", "general"))
    if agent["name"] == "AUCEO":
        return "crown"
    return {
        "coordination": "crown",
        "code-audit": "file-code",
        "security-audit": "shield",
        "crypto-audit": "fingerprint",
        "infra": "wrench",
        "research": "search",
        "qa": "bug",
        "writer": "message-square",
    }.get(family, "bot")


def hire_payload_template(agent: dict[str, Any]) -> dict[str, Any]:
    expected = agent["expectedConfig"]["adapterConfig"]
    runtime_env = {
        "CODEBASE_MEMORY_PROJECT": agent["repository"]["codebase_memory_project"],
        "SERENA_PROJECT": agent["repository"]["codebase_memory_project"],
        "TELEGRAM_REDACTED_REPORTS_CHAT_ID": "${TELEGRAM_REDACTED_REPORTS_CHAT_ID}",
        "TELEGRAM_OPS_CHAT_ID": "${TELEGRAM_OPS_CHAT_ID}",
    }
    return {
        "name": agent["name"],
        "role": role_for_agent(agent),
        "title": agent["title"],
        "icon": icon_for_agent(agent),
        "reportsTo": None if agent["reports_to"] == "Board" else {"agentName": agent["reports_to"]},
        "capabilities": (
            f"UnstoppableAudit {agent['platform']} {agent['family']} role. "
            "Performs audit-only work with read-only product source and writes only to artifact/scratch roots."
        ),
        "adapterType": "codex_local",
        "adapterConfig": {
            "cwd": expected["cwd"],
            "model": expected["model"],
            "modelReasoningEffort": expected["modelReasoningEffort"],
            "instructionsFilePath": expected["instructionsFilePath"],
            "instructionsEntryFile": expected["instructionsEntryFile"],
            "instructionsBundleMode": expected["instructionsBundleMode"],
            "dangerouslyBypassApprovalsAndSandbox": False,
            "extraArgs": expected["extraArgs"],
            "env": runtime_env,
            "writableRoots": expected["writableRoots"],
            "sourceRootsReadOnly": expected["sourceRootsReadOnly"],
        },
        "runtimeConfig": {
            "heartbeat": {
                "enabled": False,
                "intervalSec": 14400,
                "wakeOnDemand": True,
                "maxConcurrentRuns": 1,
                "cooldownSec": 10,
            }
        },
        "budgetMonthlyCents": 0,
        "sourceIssueId": "${UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID}",
    }


def dependency_names(agent: dict[str, Any]) -> list[str]:
    reports_to = agent.get("reports_to")
    if reports_to and reports_to != "Board":
        return [str(reports_to)]
    return []


def operation_sort_key(operation: dict[str, Any]) -> tuple[int, str]:
    kind = operation["kind"]
    name = operation.get("agentName", "")
    if kind == "terminate_agent":
        return (0, name)
    if name == "AUCEO":
        return (1, name)
    if name in {"UWICTO", "UWACTO"}:
        return (2, name)
    if kind == "hire_agent":
        return (3, name)
    return (4, name)


def build_operations(preflight: dict[str, Any], dry_run: dict[str, Any]) -> list[dict[str, Any]]:
    agents = agents_by_name(dry_run)
    operations: list[dict[str, Any]] = []
    for decision in preflight.get("decisions", []):
        name = decision["name"]
        agent = agents[name]
        if decision["decision"] == "recreate":
            terminate_id = decision["recreatePlan"]["terminate_existing_agent_id"]
            operations.append(
                {
                    "kind": "terminate_agent",
                    "agentName": name,
                    "agentId": terminate_id,
                    "stopOnFailure": True,
                    "rollbackSnapshotRef": f"agents.{name}",
                }
            )
            operations.append(
                {
                    "kind": "hire_agent",
                    "agentName": name,
                    "dependsOn": dependency_names(agent),
                    "payloadTemplate": hire_payload_template(agent),
                    "expectedConfigHash": decision["expectedConfigHash"],
                    "stopOnFailure": True,
                    "requiresReadback": True,
                }
            )
        elif decision["decision"] == "create":
            operations.append(
                {
                    "kind": "hire_agent",
                    "agentName": name,
                    "dependsOn": dependency_names(agent),
                    "payloadTemplate": hire_payload_template(agent),
                    "expectedConfigHash": decision["expectedConfigHash"],
                    "stopOnFailure": True,
                    "requiresReadback": True,
                }
            )
        elif decision["decision"] == "skip":
            operations.append(
                {
                    "kind": "skip_agent",
                    "agentName": name,
                    "reason": "live readback already matches expected config",
                }
            )
        else:
            raise ValueError(f"{name}: unsupported preflight decision {decision['decision']!r}")
    return sorted(operations, key=operation_sort_key)


def build_rollback_manifest(preflight: dict[str, Any]) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for decision in preflight.get("decisions", []):
        if "rollbackSnapshot" in decision:
            snapshots[decision["name"]] = decision["rollbackSnapshot"]
    return {
        "ok": True,
        "mode": "rollback-snapshot",
        "team": "UnstoppableAudit",
        "created_at": now_iso(),
        "source_preflight_hash": team.sha256_json(preflight),
        "snapshots": snapshots,
        "rollback_policy": {
            "restore_only_mutated_agents": True,
            "run_before_bundle_deploy": True,
            "operator_approval_required": True,
        },
    }


def build_apply_plan(preflight: dict[str, Any], dry_run: dict[str, Any], rollback_path: Path) -> dict[str, Any]:
    errors = validate_preflight(preflight)
    operations = [] if errors else build_operations(preflight, dry_run)
    return {
        "ok": not errors,
        "gate": "C-apply-plan",
        "mode": "dry-run",
        "team": "UnstoppableAudit",
        "created_at": now_iso(),
        "preflight_hash": team.sha256_json(preflight),
        "dry_run_hash": team.sha256_json(dry_run),
        "rollback_manifest_path": str(rollback_path),
        "live_mutation": False,
        "live_apply_guard": {
            "required_flag": "--allow-live",
            "required_confirmation": LIVE_CONFIRMATION,
        },
        "errors": errors,
        "operation_count": len(operations),
        "operations": operations,
    }


def replacement_value(cli_value: str | None, *env_names: str) -> str | None:
    if cli_value:
        return cli_value
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def runtime_replacements(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, str]:
    source_issue_id = replacement_value(
        args.source_issue_id,
        "UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID",
        "PAPERCLIP_SOURCE_ISSUE_ID",
    )
    if not source_issue_id:
        raise RuntimeError(
            "source issue id is required; pass --source-issue-id or set "
            "UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID/PAPERCLIP_SOURCE_ISSUE_ID"
        )
    reports_chat = replacement_value(
        args.redacted_reports_chat_id,
        "TELEGRAM_REDACTED_REPORTS_CHAT_ID",
    ) or str(team.prereq.get_path(config, "telegram.redacted_reports_chat_id"))
    ops_chat = replacement_value(
        args.ops_chat_id,
        "TELEGRAM_OPS_CHAT_ID",
    ) or str(team.prereq.get_path(config, "telegram.ops_chat_id"))
    return {
        "${UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID}": source_issue_id,
        "${TELEGRAM_REDACTED_REPORTS_CHAT_ID}": reports_chat,
        "${TELEGRAM_OPS_CHAT_ID}": ops_chat,
    }


def substitute_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for placeholder, replacement in replacements.items():
            result = result.replace(placeholder, replacement)
        return result
    if isinstance(value, list):
        return [substitute_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: substitute_placeholders(item, replacements) for key, item in value.items()}
    return value


def materialize_hire_payload(
    operation: dict[str, Any],
    created_agent_ids: dict[str, str],
    replacements: dict[str, str],
) -> dict[str, Any]:
    payload = substitute_placeholders(copy.deepcopy(operation["payloadTemplate"]), replacements)
    reports_to = payload.get("reportsTo")
    if isinstance(reports_to, dict) and reports_to.get("agentName"):
        manager_name = str(reports_to["agentName"])
        manager_id = created_agent_ids.get(manager_name)
        if not manager_id:
            raise RuntimeError(f"{operation['agentName']}: missing created manager id for {manager_name}")
        payload["reportsTo"] = manager_id
    return payload


def response_summary(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {"responseType": type(response).__name__}
    agent = response.get("agent") if isinstance(response.get("agent"), dict) else response
    approval = response.get("approval") if isinstance(response.get("approval"), dict) else {}
    return {
        "agentId": agent.get("id"),
        "agentName": agent.get("name"),
        "agentStatus": agent.get("status"),
        "approvalId": approval.get("id"),
        "approvalStatus": approval.get("status"),
    }


def extract_agent_id(response: Any) -> str:
    if isinstance(response, dict) and isinstance(response.get("agent"), dict):
        agent_id = response["agent"].get("id")
        if agent_id:
            return str(agent_id)
    if isinstance(response, dict) and response.get("id"):
        return str(response["id"])
    raise RuntimeError("hire response did not include agent id")


def is_pending_approval(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    agent = response.get("agent") if isinstance(response.get("agent"), dict) else response
    approval = response.get("approval") if isinstance(response.get("approval"), dict) else {}
    return agent.get("status") == "pending_approval" or approval.get("status") == "pending"


def compare_config_subset(expected_payload: dict[str, Any], live_config: dict[str, Any]) -> list[str]:
    divergences: list[str] = []
    expected_adapter = expected_payload.get("adapterConfig", {})
    live_adapter = live_config.get("adapterConfig", {}) if isinstance(live_config, dict) else {}
    if live_config.get("adapterType") != expected_payload.get("adapterType"):
        divergences.append("adapterType mismatch")
    for key in [
        "cwd",
        "model",
        "modelReasoningEffort",
        "instructionsFilePath",
        "instructionsEntryFile",
        "instructionsBundleMode",
        "dangerouslyBypassApprovalsAndSandbox",
        "extraArgs",
        "writableRoots",
        "sourceRootsReadOnly",
    ]:
        if live_adapter.get(key) != expected_adapter.get(key):
            divergences.append(f"adapterConfig.{key} mismatch")
    expected_env_keys = sorted((expected_adapter.get("env") or {}).keys())
    live_env = live_adapter.get("env") or {}
    live_env_keys = sorted(live_env.keys()) if isinstance(live_env, dict) else []
    live_env_key_list = sorted(live_adapter.get("envKeys") or [])
    if expected_env_keys and live_env_keys != expected_env_keys and live_env_key_list != expected_env_keys:
        divergences.append("adapterConfig.env keys mismatch")
    return divergences


def execute_operations(
    plan: dict[str, Any],
    api_base: str,
    token: str,
    company_id: str,
    replacements: dict[str, str],
    *,
    initial_created_agent_ids: dict[str, str] | None = None,
    stop_on_pending_approval: bool = True,
) -> dict[str, Any]:
    created_agent_ids: dict[str, str] = dict(initial_created_agent_ids or {})
    results: list[dict[str, Any]] = []
    ok = True
    stopped_reason = None
    for index, operation in enumerate(plan["operations"], start=1):
        result: dict[str, Any] = {
            "index": index,
            "kind": operation["kind"],
            "agentName": operation.get("agentName"),
            "ok": False,
        }
        try:
            if operation["kind"] == "terminate_agent":
                response = http_post_json(api_base, token, f"/api/agents/{operation['agentId']}/terminate", {})
                result.update({"ok": True, "response": response_summary(response)})
            elif operation["kind"] == "hire_agent":
                payload = materialize_hire_payload(operation, created_agent_ids, replacements)
                response = http_post_json(api_base, token, f"/api/companies/{company_id}/agent-hires", payload)
                agent_id = extract_agent_id(response)
                created_agent_ids[str(operation["agentName"])] = agent_id
                result.update(
                    {
                        "ok": True,
                        "agentId": agent_id,
                        "payloadHash": team.sha256_json(payload),
                        "response": response_summary(response),
                    }
                )
                if is_pending_approval(response) and stop_on_pending_approval:
                    result["readbackSkipped"] = "pending approval"
                    stopped_reason = f"{operation['agentName']}: pending approval"
                    results.append(result)
                    break
                if operation.get("requiresReadback"):
                    live_config = team.http_get_json(api_base, token, f"/api/agents/{agent_id}/configuration")
                    divergences = compare_config_subset(payload, live_config if isinstance(live_config, dict) else {})
                    result["readback"] = {
                        "checked": True,
                        "ok": not divergences,
                        "divergences": divergences,
                    }
                    if divergences:
                        ok = False
                        result["ok"] = False
                        stopped_reason = f"{operation['agentName']}: readback divergence"
            elif operation["kind"] == "skip_agent":
                result.update({"ok": True, "skipped": True, "reason": operation.get("reason")})
            else:
                raise RuntimeError(f"unsupported operation kind {operation['kind']!r}")
        except Exception as exc:
            ok = False
            result["ok"] = False
            result["error"] = str(exc)
        results.append(result)
        if not result["ok"] or (operation.get("stopOnFailure") and not ok):
            stopped_reason = stopped_reason or f"{operation.get('agentName')}: operation failed"
            break
    return {
        "ok": ok and stopped_reason is None,
        "gate": "C-live-apply",
        "mode": "live",
        "team": "UnstoppableAudit",
        "created_at": now_iso(),
        "source_plan_hash": team.sha256_json(plan),
        "operation_count": len(plan["operations"]),
        "executed_count": len(results),
        "created_agent_ids": created_agent_ids,
        "stopped_reason": stopped_reason,
        "results": results,
    }


def resume_plan(plan: dict[str, Any], previous_result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    completed_indexes = {
        int(result["index"])
        for result in previous_result.get("results", [])
        if result.get("ok") and isinstance(result.get("index"), int)
    }
    resumed_plan = copy.deepcopy(plan)
    resumed_plan["operations"] = [
        operation
        for index, operation in enumerate(plan.get("operations", []), start=1)
        if index not in completed_indexes
    ]
    resumed_plan["operation_count"] = len(resumed_plan["operations"])
    created_agent_ids = {
        str(name): str(agent_id)
        for name, agent_id in (previous_result.get("created_agent_ids") or {}).items()
        if agent_id
    }
    resume_meta = {
        "source_result_hash": team.sha256_json(previous_result),
        "completed_indexes": sorted(completed_indexes),
        "remaining_count": len(resumed_plan["operations"]),
        "created_agent_ids": created_agent_ids,
    }
    return resumed_plan, created_agent_ids, resume_meta


def find_agent_by_id(live_agents: list[dict[str, Any]], agent_id: str) -> dict[str, Any] | None:
    for agent in live_agents:
        if str(agent.get("id", "")) == agent_id:
            return agent
    return None


def build_readiness_manifest(
    plan: dict[str, Any],
    api_base: str,
    token: str | None,
    company_id: str,
    source_issue_id_present: bool,
) -> dict[str, Any]:
    blockers = validate_apply_plan(plan)
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    if not token:
        blockers.append("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required")
    if not source_issue_id_present:
        blockers.append(
            "source issue id is required; pass --source-issue-id or set "
            "UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID/PAPERCLIP_SOURCE_ISSUE_ID"
        )

    live_agents: list[dict[str, Any]] = []
    if token and not validate_apply_plan(plan):
        try:
            me = team.http_get_json(api_base, token, "/api/agents/me")
            checks.append(
                {
                    "name": "identity",
                    "ok": True,
                    "agentId": me.get("id") if isinstance(me, dict) else None,
                    "agentName": me.get("name") if isinstance(me, dict) else None,
                }
            )
        except Exception as exc:
            warnings.append(f"identity check failed: {exc}")
            checks.append({"name": "identity", "ok": False, "error": str(exc)})
        try:
            agents = team.http_get_json(api_base, token, f"/api/companies/{company_id}/agents")
            if not isinstance(agents, list):
                raise RuntimeError("company agents endpoint returned non-list payload")
            live_agents = agents
            checks.append({"name": "company_agents", "ok": True, "count": len(live_agents)})
        except Exception as exc:
            blockers.append(f"company agents check failed: {exc}")
            checks.append({"name": "company_agents", "ok": False, "error": str(exc)})

        for operation in plan.get("operations", []):
            if operation.get("kind") != "terminate_agent":
                continue
            agent_id = str(operation.get("agentId", ""))
            live_agent = find_agent_by_id(live_agents, agent_id)
            terminate_check: dict[str, Any] = {
                "name": "terminate_target",
                "ok": bool(live_agent),
                "agentName": operation.get("agentName"),
                "agentId": agent_id,
            }
            if live_agent:
                terminate_check["status"] = live_agent.get("status")
                if live_agent.get("status") == "terminated":
                    terminate_check["ok"] = False
                    blockers.append(f"{operation.get('agentName')}: terminate target is already terminated")
            else:
                blockers.append(f"{operation.get('agentName')}: terminate target {agent_id} was not found")
            checks.append(terminate_check)
            try:
                config = team.http_get_json(api_base, token, f"/api/agents/{agent_id}/configuration")
                checks.append(
                    {
                        "name": "rollback_config_readback",
                        "ok": isinstance(config, dict),
                        "agentName": operation.get("agentName"),
                        "agentId": agent_id,
                    }
                )
                if not isinstance(config, dict):
                    blockers.append(f"{operation.get('agentName')}: rollback config readback returned non-object")
            except Exception as exc:
                blockers.append(f"{operation.get('agentName')}: rollback config readback failed: {exc}")
                checks.append(
                    {
                        "name": "rollback_config_readback",
                        "ok": False,
                        "agentName": operation.get("agentName"),
                        "agentId": agent_id,
                        "error": str(exc),
                    }
                )

    return {
        "ok": not blockers,
        "gate": "C-readiness",
        "mode": "safe-read-only",
        "team": "UnstoppableAudit",
        "checked_at": now_iso(),
        "api_base": api_base.rstrip("/"),
        "company_id": company_id,
        "source_plan_hash": team.sha256_json(plan),
        "operation_count": len(plan.get("operations", [])),
        "token_present": bool(token),
        "source_issue_id_present": source_issue_id_present,
        "live_mutation": False,
        "safe_methods_only": True,
        "next_live_guard": {
            "required_flag": "--allow-live",
            "required_confirmation": LIVE_CONFIRMATION,
        },
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }


def issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        key: issue.get(key)
        for key in [
            "id",
            "key",
            "number",
            "title",
            "status",
            "priority",
            "projectId",
            "assigneeAgentId",
            "createdAt",
            "updatedAt",
        ]
        if key in issue
    }


def score_source_issue(issue: dict[str, Any]) -> int:
    text = " ".join(str(issue.get(key, "")) for key in ["title", "description", "key"]).lower()
    score = 0
    if "unstoppableaudit" in text:
        score += 5
    if "unstoppable audit" in text:
        score += 5
    if "bootstrap" in text:
        score += 3
    if "audit" in text:
        score += 1
    if issue.get("status") not in {"done", "closed", "cancelled"}:
        score += 1
    return score


def discover_source_issue(
    api_base: str,
    token: str,
    company_id: str,
    queries: list[str],
    project_id: str | None = None,
) -> dict[str, Any]:
    seen: dict[str, dict[str, Any]] = {}
    query_results: list[dict[str, Any]] = []
    for query in queries:
        path = f"/api/companies/{company_id}/issues?q={quote(query)}"
        issues = team.http_get_json(api_base, token, path)
        if not isinstance(issues, list):
            raise RuntimeError(f"issues search for {query!r} returned non-list payload")
        filtered = [
            issue
            for issue in issues
            if isinstance(issue, dict) and (not project_id or str(issue.get("projectId", "")) == project_id)
        ]
        for issue in filtered:
            issue_id = str(issue.get("id", ""))
            if issue_id:
                seen[issue_id] = issue
        query_results.append(
            {
                "query": query,
                "result_count": len(issues),
                "filtered_count": len(filtered),
            }
        )
    ranked = sorted(
        (issue_summary(issue) | {"score": score_source_issue(issue)} for issue in seen.values()),
        key=lambda item: (-int(item["score"]), str(item.get("updatedAt", "")), str(item.get("id", ""))),
    )
    selected = ranked[0] if ranked and int(ranked[0]["score"]) > 0 else None
    blockers: list[str] = []
    if not selected:
        blockers.append("no plausible UnstoppableAudit source issue found")
    return {
        "ok": not blockers,
        "gate": "C-source-issue-discovery",
        "mode": "safe-read-only",
        "team": "UnstoppableAudit",
        "checked_at": now_iso(),
        "api_base": api_base.rstrip("/"),
        "company_id": company_id,
        "project_id": project_id,
        "live_mutation": False,
        "queries": query_results,
        "blockers": blockers,
        "selected": selected,
        "candidates": ranked[:10],
    }


def source_issue_payload(company_id: str, project_id: str, title: str, body: str) -> dict[str, Any]:
    return {
        "title": title,
        "body": body,
        "companyId": company_id,
        "projectId": project_id,
    }


def create_source_issue(
    api_base: str,
    token: str,
    company_id: str,
    project_id: str,
    title: str,
    body: str,
) -> dict[str, Any]:
    payload = source_issue_payload(company_id, project_id, title, body)
    response = http_post_json(api_base, token, f"/api/companies/{company_id}/issues", payload)
    if not isinstance(response, dict) or not response.get("id"):
        raise RuntimeError("source issue create response did not include issue id")
    return {
        "ok": True,
        "gate": "C-source-issue-create",
        "mode": "live",
        "team": "UnstoppableAudit",
        "created_at": now_iso(),
        "api_base": api_base.rstrip("/"),
        "company_id": company_id,
        "project_id": project_id,
        "live_mutation": True,
        "payloadHash": team.sha256_json(payload),
        "issue": issue_summary(response),
    }


def runtime_extra_args_fix(
    dry_run: dict[str, Any],
    api_base: str,
    token: str,
    company_id: str,
    *,
    apply_live: bool,
) -> dict[str, Any]:
    planned_agents = agents_by_name(dry_run)
    live_agents = team.http_get_json(api_base, token, f"/api/companies/{company_id}/agents")
    if not isinstance(live_agents, list):
        raise RuntimeError("company agents response must be a list")
    live_by_name = team.index_live_agents(live_agents)
    results: list[dict[str, Any]] = []
    blockers: list[str] = []

    for name in sorted(planned_agents):
        agent = planned_agents[name]
        expected_extra_args = sorted(agent["expectedConfig"]["adapterConfig"].get("extraArgs") or [])
        matches = live_by_name.get(name, [])
        result: dict[str, Any] = {
            "agentName": name,
            "expectedExtraArgs": expected_extra_args,
            "ok": False,
            "patched": False,
        }
        if not matches:
            result["blocker"] = "live agent not found"
            blockers.append(f"{name}: live agent not found")
            results.append(result)
            continue
        if len(matches) > 1:
            result["blocker"] = "duplicate live agents found"
            result["matches"] = [team.sanitized_agent(match) for match in matches]
            blockers.append(f"{name}: duplicate live agents found")
            results.append(result)
            continue

        live_agent = matches[0]
        agent_id = str(live_agent.get("id") or "")
        if not agent_id:
            result["blocker"] = "live agent id missing"
            blockers.append(f"{name}: live agent id missing")
            results.append(result)
            continue

        live_config = team.http_get_json(api_base, token, f"/api/agents/{agent_id}/configuration")
        adapter_config = (live_config or {}).get("adapterConfig") if isinstance(live_config, dict) else None
        if not isinstance(adapter_config, dict):
            result["blocker"] = "adapterConfig missing"
            blockers.append(f"{name}: adapterConfig missing")
            results.append(result)
            continue

        current_extra_args = sorted(adapter_config.get("extraArgs") or [])
        target_extra_args = sorted(set(current_extra_args).union(expected_extra_args))
        result.update(
            {
                "ok": True,
                "agentId": agent_id,
                "currentExtraArgs": current_extra_args,
                "targetExtraArgs": target_extra_args,
                "configHashBefore": team.sha256_json(team.sanitized_config(live_config)),
            }
        )
        if current_extra_args != target_extra_args:
            result["patched"] = apply_live
            result["wouldPatch"] = not apply_live
            if apply_live:
                patched_adapter_config = copy.deepcopy(adapter_config)
                patched_adapter_config["extraArgs"] = target_extra_args
                response = http_patch_json(
                    api_base,
                    token,
                    f"/api/agents/{agent_id}",
                    {"adapterConfig": patched_adapter_config},
                )
                result["response"] = response_summary(response)
                readback = team.http_get_json(api_base, token, f"/api/agents/{agent_id}/configuration")
                result["configHashAfter"] = team.sha256_json(team.sanitized_config(readback))
                result["readbackExtraArgs"] = sorted(
                    ((readback or {}).get("adapterConfig") or {}).get("extraArgs") or []
                )
                if result["readbackExtraArgs"] != target_extra_args:
                    result["ok"] = False
                    result["blocker"] = "readback extraArgs mismatch"
                    blockers.append(f"{name}: readback extraArgs mismatch")
        else:
            result["wouldPatch"] = False
        results.append(result)

    return {
        "ok": not blockers,
        "gate": "D-runtime-fix",
        "mode": "live" if apply_live else "dry-run",
        "team": "UnstoppableAudit",
        "created_at": now_iso(),
        "api_base": api_base.rstrip("/"),
        "company_id": company_id,
        "live_mutation": apply_live,
        "source_dry_run_hash": team.sha256_json(dry_run),
        "blockers": blockers,
        "results": results,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Plan or apply UnstoppableAudit live bootstrap")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--preflight", type=Path, default=repo_root / DEFAULT_PREFLIGHT)
    plan.add_argument("--dry-run", type=Path, default=repo_root / DEFAULT_DRY_RUN)
    plan.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_APPLY_PLAN)
    plan.add_argument("--rollback-manifest", type=Path, default=repo_root / DEFAULT_ROLLBACK)
    plan.add_argument("--write-manifest", action="store_true")

    readiness = subparsers.add_parser("readiness")
    readiness.add_argument("--plan", type=Path, default=repo_root / DEFAULT_APPLY_PLAN)
    readiness.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    readiness.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_READINESS)
    readiness.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    readiness.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    readiness.add_argument("--company-id", default="")
    readiness.add_argument("--source-issue-id", default="")
    readiness.add_argument("--write-manifest", action="store_true")

    source_issue = subparsers.add_parser("discover-source-issue")
    source_issue.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    source_issue.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_SOURCE_ISSUE)
    source_issue.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    source_issue.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    source_issue.add_argument("--company-id", default="")
    source_issue.add_argument("--project-id", default="")
    source_issue.add_argument(
        "--query",
        action="append",
        default=[],
        help="Issue search query. Can be repeated.",
    )
    source_issue.add_argument("--write-manifest", action="store_true")

    create_source = subparsers.add_parser("create-source-issue")
    create_source.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    create_source.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_SOURCE_ISSUE_CREATE)
    create_source.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    create_source.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    create_source.add_argument("--company-id", default="")
    create_source.add_argument("--project-id", default="")
    create_source.add_argument("--title", default="UnstoppableAudit bootstrap")
    create_source.add_argument(
        "--body",
        default=(
            "Bootstrap source issue for the UnstoppableAudit Paperclip team. "
            "Tracks gated creation of AUCEO plus iOS/Android audit roles, with read-only repository access, "
            "team-scoped artifact roots, and explicit approval gates."
        ),
    )
    create_source.add_argument("--allow-live", action="store_true")
    create_source.add_argument("--confirm", default="")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--plan", type=Path, default=repo_root / DEFAULT_APPLY_PLAN)
    apply.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    apply.add_argument("--result-manifest", type=Path, default=repo_root / DEFAULT_LIVE_RESULT)
    apply.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    apply.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    apply.add_argument("--company-id", default="")
    apply.add_argument("--source-issue-id", default="")
    apply.add_argument("--redacted-reports-chat-id", default="")
    apply.add_argument("--ops-chat-id", default="")
    apply.add_argument("--resume-result", type=Path)
    apply.add_argument("--continue-after-pending-approval", action="store_true")
    apply.add_argument("--allow-live", action="store_true")
    apply.add_argument("--confirm", default="")

    runtime_fix = subparsers.add_parser("patch-runtime-extra-args")
    runtime_fix.add_argument("--dry-run", type=Path, default=repo_root / DEFAULT_DRY_RUN)
    runtime_fix.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    runtime_fix.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_RUNTIME_FIX)
    runtime_fix.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    runtime_fix.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    runtime_fix.add_argument("--company-id", default="")
    runtime_fix.add_argument("--write-manifest", action="store_true")
    runtime_fix.add_argument("--allow-live", action="store_true")
    runtime_fix.add_argument("--confirm", default="")
    return parser.parse_args(argv)


def command_plan(args: argparse.Namespace) -> int:
    preflight = read_json(args.preflight)
    dry_run = read_json(args.dry_run)
    rollback = build_rollback_manifest(preflight)
    plan = build_apply_plan(preflight, dry_run, args.rollback_manifest)
    if args.write_manifest:
        write_json(args.rollback_manifest, rollback)
        write_json(args.manifest, plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0 if plan["ok"] else 1


def command_readiness(args: argparse.Namespace) -> int:
    plan = read_json(args.plan)
    config = team.load_config(args.config)
    company_id = args.company_id or str(team.prereq.get_path(config, "paperclip.company_id"))
    token = team.load_auth_token(args.api_base, args.auth_path)
    source_issue_id = replacement_value(
        args.source_issue_id,
        "UNSTOPPABLE_AUDIT_SOURCE_ISSUE_ID",
        "PAPERCLIP_SOURCE_ISSUE_ID",
    )
    manifest = build_readiness_manifest(
        plan,
        args.api_base,
        token,
        company_id,
        bool(source_issue_id),
    )
    if args.write_manifest:
        write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["ok"] else 1


def command_discover_source_issue(args: argparse.Namespace) -> int:
    config = team.load_config(args.config)
    company_id = args.company_id or str(team.prereq.get_path(config, "paperclip.company_id"))
    project_id = args.project_id or str(team.prereq.get_path(config, "paperclip.onboarding_project_id"))
    token = team.load_auth_token(args.api_base, args.auth_path)
    if not token:
        raise RuntimeError("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required for source issue discovery")
    queries = args.query or [
        "UnstoppableAudit",
        "Unstoppable Audit",
        "unstoppable wallet audit bootstrap",
        "audit bootstrap",
    ]
    manifest = discover_source_issue(args.api_base, token, company_id, queries, project_id)
    if args.write_manifest:
        write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["ok"] else 1


def command_create_source_issue(args: argparse.Namespace) -> int:
    if not args.allow_live or args.confirm != LIVE_CONFIRMATION:
        raise RuntimeError(
            f"refusing source issue creation; pass --allow-live --confirm {LIVE_CONFIRMATION} after review"
        )
    config = team.load_config(args.config)
    company_id = args.company_id or str(team.prereq.get_path(config, "paperclip.company_id"))
    project_id = args.project_id or str(team.prereq.get_path(config, "paperclip.onboarding_project_id"))
    token = team.load_auth_token(args.api_base, args.auth_path)
    if not token:
        raise RuntimeError("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required for source issue creation")
    manifest = create_source_issue(args.api_base, token, company_id, project_id, args.title, args.body)
    write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def command_apply(args: argparse.Namespace) -> int:
    plan = read_json(args.plan)
    errors = validate_apply_plan(plan)
    if errors:
        raise RuntimeError("invalid apply plan: " + "; ".join(errors))
    if not args.allow_live or args.confirm != LIVE_CONFIRMATION:
        raise RuntimeError(
            f"refusing live mutation; pass --allow-live --confirm {LIVE_CONFIRMATION} after review"
        )
    token = team.load_auth_token(args.api_base, args.auth_path)
    if not token:
        raise RuntimeError("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required for apply")
    config = team.load_config(args.config)
    company_id = args.company_id or str(team.prereq.get_path(config, "paperclip.company_id"))
    replacements = runtime_replacements(args, config)
    initial_created_agent_ids: dict[str, str] | None = None
    if args.resume_result:
        previous_result = read_json(args.resume_result)
        plan, initial_created_agent_ids, resume_meta = resume_plan(plan, previous_result)
    else:
        resume_meta = None
    result = execute_operations(
        plan,
        args.api_base,
        token,
        company_id,
        replacements,
        initial_created_agent_ids=initial_created_agent_ids,
        stop_on_pending_approval=not args.continue_after_pending_approval,
    )
    if resume_meta:
        result["resumed_from"] = resume_meta
    write_json(args.result_manifest, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def command_patch_runtime_extra_args(args: argparse.Namespace) -> int:
    if args.allow_live and args.confirm != LIVE_CONFIRMATION:
        raise RuntimeError(
            f"refusing live runtime patch; pass --allow-live --confirm {LIVE_CONFIRMATION} after review"
        )
    dry_run = read_json(args.dry_run)
    config = team.load_config(args.config)
    company_id = args.company_id or str(team.prereq.get_path(config, "paperclip.company_id"))
    token = team.load_auth_token(args.api_base, args.auth_path)
    if not token:
        raise RuntimeError("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required for runtime patch")
    manifest = runtime_extra_args_fix(
        dry_run,
        args.api_base,
        token,
        company_id,
        apply_live=args.allow_live,
    )
    if args.write_manifest or args.allow_live:
        write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "plan":
        return command_plan(args)
    if args.command == "readiness":
        return command_readiness(args)
    if args.command == "discover-source-issue":
        return command_discover_source_issue(args)
    if args.command == "create-source-issue":
        return command_create_source_issue(args)
    if args.command == "apply":
        return command_apply(args)
    if args.command == "patch-runtime-extra-args":
        return command_patch_runtime_extra_args(args)
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
