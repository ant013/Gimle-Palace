#!/usr/bin/env python3
"""Gate C apply planning for UnstoppableAudit.

This script is deliberately conservative. The default `plan` command performs
no Paperclip mutations. It turns the approved Gate B2 preflight into an ordered
operation plan and rollback manifest that can be reviewed before live apply.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unstoppable_audit_team as team


DEFAULT_PREFLIGHT = Path("paperclips/manifests/unstoppable-audit/gate-b2-preflight.json")
DEFAULT_DRY_RUN = Path("paperclips/manifests/unstoppable-audit/gate-b1-dry-run.json")
DEFAULT_APPLY_PLAN = Path("paperclips/manifests/unstoppable-audit/gate-c-apply-plan.json")
DEFAULT_ROLLBACK = Path("paperclips/manifests/unstoppable-audit/rollback-gate-c.json")
LIVE_CONFIRMATION = "UNSTOPPABLE_AUDIT_LIVE_APPLY"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    if not plan.get("ok"):
        raise RuntimeError("apply plan is not ok")
    if not args.allow_live or args.confirm != LIVE_CONFIRMATION:
        raise RuntimeError(
            f"refusing live mutation; pass --allow-live --confirm {LIVE_CONFIRMATION} after review"
        )
    raise RuntimeError("live mutation transport is intentionally not enabled in this slice")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "plan":
        return command_plan(args)
    if args.command == "apply":
        return command_apply(args)
    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
