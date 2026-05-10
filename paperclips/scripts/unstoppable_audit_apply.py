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

import unstoppable_audit_team as team


DEFAULT_PREFLIGHT = Path("paperclips/manifests/unstoppable-audit/gate-b2-preflight.json")
DEFAULT_DRY_RUN = Path("paperclips/manifests/unstoppable-audit/gate-b1-dry-run.json")
DEFAULT_APPLY_PLAN = Path("paperclips/manifests/unstoppable-audit/gate-c-apply-plan.json")
DEFAULT_ROLLBACK = Path("paperclips/manifests/unstoppable-audit/rollback-gate-c.json")
DEFAULT_LIVE_RESULT = Path("paperclips/manifests/unstoppable-audit/gate-c-live-result.json")
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
        "code-audit": "search-code",
        "security-audit": "shield",
        "crypto-audit": "key-round",
        "infra": "wrench",
        "research": "search",
        "qa": "bug",
        "writer": "file-text",
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
    stop_on_pending_approval: bool = True,
) -> dict[str, Any]:
    created_agent_ids: dict[str, str] = {}
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
    apply.add_argument("--continue-after-pending-approval", action="store_true")
    apply.add_argument("--allow-live", action="store_true")
    apply.add_argument("--confirm", default="")
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
    result = execute_operations(
        plan,
        args.api_base,
        token,
        company_id,
        replacements,
        stop_on_pending_approval=not args.continue_after_pending_approval,
    )
    write_json(args.result_manifest, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "plan":
        return command_plan(args)
    if args.command == "apply":
        return command_apply(args)
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
