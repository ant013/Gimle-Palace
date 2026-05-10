#!/usr/bin/env python3
"""Unauthenticated team renderer for UnstoppableAudit Gate B1."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unstoppable_audit_prereq as prereq


TEAM_SLUG = "unstoppable-audit"
DEFAULT_MANIFEST = Path("paperclips/manifests/unstoppable-audit/gate-b1-dry-run.json")
DEFAULT_PREFLIGHT_MANIFEST = Path("paperclips/manifests/unstoppable-audit/gate-b2-preflight.json")
DEFAULT_BUNDLE_DIR = Path("paperclips/dist/codex/unstoppable-audit")
FORBIDDEN_ENV_KEYS = {
    "PAPERCLIP_API_KEY",
    "PAPERCLIP_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_WRITE_TOKEN",
    "NEO4J_PASSWORD",
    "BOOTSTRAP_ADMIN_TOKEN",
    "DEPLOY_UPDATE_TOKEN",
}
RUNTIME_ENV_KEYS = [
    "CODEBASE_MEMORY_PROJECT",
    "SERENA_PROJECT",
    "TELEGRAM_REDACTED_REPORTS_CHAT_ID",
    "TELEGRAM_OPS_CHAT_ID",
]
PREFLIGHT_REQUIRED_FIELDS = [
    "adapterType",
    "model",
    "reasoningEffort",
    "instructionsFilePath",
    "instructionsBundleMode",
    "sandboxBypass",
    "runtimeEnvKeys",
    "workspacePath",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def load_config(config_path: Path) -> dict[str, Any]:
    config = prereq.parse_simple_yaml(config_path)
    if prereq.get_path(config, "team") != "UnstoppableAudit":
        raise ValueError("config team must be UnstoppableAudit")
    roster = prereq.get_path(config, "roster")
    if not isinstance(roster, dict) or not roster:
        raise ValueError("config roster must be a non-empty mapping")
    return config


def platform_repo(config: dict[str, Any], platform: str) -> dict[str, str]:
    if platform == "ios":
        return {
            "codebase_memory_project": str(prereq.get_path(config, "codebase_memory.ios_project")),
            "repo_url": str(prereq.get_path(config, "repositories.ios.url")),
            "mirror_path": str(prereq.get_path(config, "repositories.ios.mirror_path")),
        }
    if platform == "android":
        return {
            "codebase_memory_project": str(prereq.get_path(config, "codebase_memory.android_project")),
            "repo_url": str(prereq.get_path(config, "repositories.android.url")),
            "mirror_path": str(prereq.get_path(config, "repositories.android.mirror_path")),
        }
    return {
        "codebase_memory_project": "unstoppable-audit",
        "repo_url": "multiple",
        "mirror_path": str(prereq.get_path(config, "roots.stable_mirror_root")),
    }


def render_bundle(agent: dict[str, Any], config: dict[str, Any]) -> str:
    repo = agent["repository"]
    return "\n".join(
        [
            f"# {agent['name']} - {agent['title']}",
            "",
            "You are a Codex local audit agent for the UnstoppableAudit team.",
            "",
            "## Role",
            "",
            f"- Team: UnstoppableAudit",
            f"- Agent: {agent['name']}",
            f"- Platform scope: {agent['platform']}",
            f"- Family: {agent['family']}",
            f"- Reports to: {agent['reports_to']}",
            "",
            "## Audit-Only Runtime Policy",
            "",
            "- Adapter must be `codex_local`.",
            "- Instructions are managed and loaded from `AGENTS.md`.",
            "- Sandbox bypass must remain false.",
            "- Product repositories are read-only audit inputs.",
            "- Write only to the assigned artifact root or scratch root.",
            "- Runtime env must not contain bootstrap-admin, deploy-update, or GitHub write credentials.",
            "- Phase 1 does not write structured audit findings to Neo4j.",
            "",
            "## Required Tools And Context",
            "",
            "- Use `codebase-memory` first for indexed architecture, code search, symbols, and cross-file context.",
            "- Use Serena for project activation, symbol navigation, references, diagnostics, and targeted code reading.",
            "- Use Paperclip one-issue handoff: update the current issue with status, evidence, blockers, and next owner instead of spawning unrelated child work.",
            "",
            "## Repository Scope",
            "",
            f"- Repository URL: `{repo['repo_url']}`",
            f"- Stable mirror path: `{repo['mirror_path']}`",
            f"- codebase-memory project: `{repo['codebase_memory_project']}`",
            "",
            "## Telegram Delivery Policy",
            "",
            "- Telegram receives redacted artifacts and ops signals only.",
            "- Full internal reports and evidence manifests stay on disk/Paperclip.",
            f"- Redacted report chat ID: `{prereq.get_path(config, 'telegram.redacted_reports_chat_id')}`",
            f"- Ops chat ID: `{prereq.get_path(config, 'telegram.ops_chat_id')}`",
            "- Never send secrets, seed phrases, auth headers, private keys, full exploit payloads, or local absolute paths.",
            "",
            "## Handoff Contract",
            "",
            "- Keep work attached to one Paperclip issue unless a concrete blocker requires escalation.",
            "- Handoff comments must include status, exact evidence paths, validation commands, known blockers, and the next owner.",
            "- Positive handoff smoke must not create child issues.",
            "",
        ]
    )


def build_agent_plan(config: dict[str, Any], repo_root: Path, bundle_dir: Path) -> list[dict[str, Any]]:
    roster = prereq.get_path(config, "roster")
    artifact_root = str(prereq.get_path(config, "roots.artifact_root"))
    run_root = str(prereq.get_path(config, "roots.run_root"))
    agents: list[dict[str, Any]] = []

    for name, raw in roster.items():
        if not isinstance(raw, dict):
            raise ValueError(f"roster entry must be a mapping: {name}")
        platform = str(raw.get("platform", "umbrella"))
        bundle_path = bundle_dir / f"{slugify(name)}.md"
        scratch_root = f"{run_root}/{name}/scratch"
        agent_artifact_root = f"{artifact_root}/{name}"
        agent = {
            "name": name,
            "title": str(raw.get("title", name)),
            "platform": platform,
            "family": str(raw.get("family", "audit")),
            "reports_to": str(raw.get("reports_to", "AUCEO")),
            "adapterType": "codex_local",
            "instructionsBundleMode": "managed",
            "instructionsFilePath": "AGENTS.md",
            "model": str(prereq.get_path(config, "models.default_model")),
            "reasoningEffort": str(prereq.get_path(config, "models.default_reasoning_effort")),
            "sandboxBypass": False,
            "plannedOperation": "create",
            "workspacePath": f"{run_root}/{name}/workspace",
            "bundlePath": str(bundle_path),
            "writableRoots": [agent_artifact_root, scratch_root],
            "sourceRootsReadOnly": [
                str(prereq.get_path(config, "repositories.ios.mirror_path")),
                str(prereq.get_path(config, "repositories.android.mirror_path")),
            ],
            "runtimeEnvKeys": RUNTIME_ENV_KEYS,
            "forbiddenRuntimeEnvKeys": sorted(FORBIDDEN_ENV_KEYS),
            "repository": platform_repo(config, platform),
        }
        agent["expectedConfig"] = expected_config(agent)
        agent["expectedConfigHash"] = sha256_json(agent["expectedConfig"])
        validate_agent_plan(agent)
        agents.append(agent)
    return agents


def expected_config(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapterType": agent["adapterType"],
        "adapterConfig": {
            "cwd": agent["workspacePath"],
            "model": agent["model"],
            "modelReasoningEffort": agent["reasoningEffort"],
            "instructionsFilePath": agent["instructionsFilePath"],
            "instructionsEntryFile": agent["instructionsFilePath"],
            "instructionsBundleMode": agent["instructionsBundleMode"],
            "dangerouslyBypassApprovalsAndSandbox": agent["sandboxBypass"],
            "envKeys": sorted(agent["runtimeEnvKeys"]),
            "writableRoots": sorted(agent["writableRoots"]),
            "sourceRootsReadOnly": sorted(agent["sourceRootsReadOnly"]),
        },
    }


def validate_agent_plan(agent: dict[str, Any]) -> None:
    if agent["adapterType"] != "codex_local":
        raise ValueError(f"{agent['name']}: adapterType must be codex_local")
    if agent["instructionsBundleMode"] != "managed":
        raise ValueError(f"{agent['name']}: instructionsBundleMode must be managed")
    if agent["instructionsFilePath"] != "AGENTS.md":
        raise ValueError(f"{agent['name']}: instructionsFilePath must be AGENTS.md")
    if agent["sandboxBypass"] is not False:
        raise ValueError(f"{agent['name']}: sandboxBypass must be false")
    leaked = FORBIDDEN_ENV_KEYS.intersection(agent["runtimeEnvKeys"])
    if leaked:
        raise ValueError(f"{agent['name']}: forbidden runtime env keys present: {sorted(leaked)}")
    for root in agent["writableRoots"]:
        if "/repos/" in root or root.endswith("/repos"):
            raise ValueError(f"{agent['name']}: writable roots must not include product repo paths")


def render_bundles(agents: list[dict[str, Any]], config: dict[str, Any], repo_root: Path) -> None:
    for agent in agents:
        path = repo_root / agent["bundlePath"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_bundle(agent, config), encoding="utf-8")


def build_manifest(config: dict[str, Any], agents: list[dict[str, Any]], config_path: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "gate": "B1",
        "mode": "unauthenticated-dry-run",
        "checked_at": now_iso(),
        "team": "UnstoppableAudit",
        "config_path": str(config_path),
        "paperclip": {
            "company_id": prereq.get_path(config, "paperclip.company_id"),
            "project_id": prereq.get_path(config, "paperclip.onboarding_project_id"),
        },
        "live_readback": {
            "checked": False,
            "reason": "Gate B1 is intentionally unauthenticated and performs no Paperclip API mutation.",
        },
        "apply_policy": {
            "default_operation": "create-only",
            "live_apply_allowed": False,
            "requires_authenticated_preflight": True,
        },
        "dry_run_config_hash": sha256_json({"agents": agents}),
        "agents": agents,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_auth_token(api_base: str, auth_path: Path) -> str | None:
    if os.environ.get("PAPERCLIP_API_KEY"):
        return os.environ["PAPERCLIP_API_KEY"]
    if not auth_path.exists():
        return None
    data = read_json(auth_path)
    credentials = data.get("credentials", {})
    if not isinstance(credentials, dict):
        return None
    candidates = [api_base.rstrip("/")]
    candidates.extend(str(key).rstrip("/") for key in credentials)
    for candidate in candidates:
        entry = credentials.get(candidate)
        if isinstance(entry, dict) and entry.get("token"):
            return str(entry["token"])
    return None


def http_get_json(api_base: str, token: str, path: str) -> Any:
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            api_base.rstrip("/") + path,
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Accept: application/json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"GET {path} failed: {result.stderr.strip()}")
    if "\n" not in result.stdout:
        raise RuntimeError(f"GET {path} returned malformed curl output")
    body, http_code = result.stdout.rsplit("\n", 1)
    if http_code not in {"200", "204"}:
        raise RuntimeError(f"GET {path} failed with HTTP {http_code}: {body[:300]}")
    return json.loads(body) if body else None


def index_live_agents(live_agents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for agent in live_agents:
        name = str(agent.get("name", ""))
        if not name:
            continue
        by_name.setdefault(name, []).append(agent)
    return by_name


def sanitized_agent(agent: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "id",
        "name",
        "title",
        "role",
        "status",
        "adapterType",
        "sourceIssueId",
        "projectId",
        "companyId",
    ]
    return {key: agent.get(key) for key in keys if key in agent}


def sanitized_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    adapter_config = config.get("adapterConfig") or {}
    if not isinstance(adapter_config, dict):
        adapter_config = {}
    env = adapter_config.get("env") or {}
    env_keys = sorted(env.keys()) if isinstance(env, dict) else []
    return {
        "adapterType": config.get("adapterType"),
        "adapterConfig": {
            "cwd": adapter_config.get("cwd"),
            "model": adapter_config.get("model"),
            "modelReasoningEffort": adapter_config.get("modelReasoningEffort"),
            "instructionsFilePath": adapter_config.get("instructionsFilePath"),
            "instructionsEntryFile": adapter_config.get("instructionsEntryFile"),
            "instructionsBundleMode": adapter_config.get("instructionsBundleMode"),
            "dangerouslyBypassApprovalsAndSandbox": adapter_config.get(
                "dangerouslyBypassApprovalsAndSandbox"
            ),
            "envKeys": env_keys,
            "writableRoots": adapter_config.get("writableRoots"),
            "sourceRootsReadOnly": adapter_config.get("sourceRootsReadOnly"),
        },
    }


def config_readback(config: dict[str, Any] | None) -> dict[str, Any]:
    sanitized = sanitized_config(config)
    adapter_config = sanitized.get("adapterConfig", {})
    return {
        "adapterType": sanitized.get("adapterType"),
        "model": adapter_config.get("model"),
        "reasoningEffort": adapter_config.get("modelReasoningEffort"),
        "instructionsFilePath": adapter_config.get("instructionsFilePath"),
        "instructionsBundleMode": adapter_config.get("instructionsBundleMode"),
        "sandboxBypass": adapter_config.get("dangerouslyBypassApprovalsAndSandbox"),
        "runtimeEnvKeys": sorted(adapter_config.get("envKeys") or []),
        "workspacePath": adapter_config.get("cwd"),
        "writableRoots": adapter_config.get("writableRoots"),
        "sourceRootsReadOnly": adapter_config.get("sourceRootsReadOnly"),
    }


def compare_readback(agent: dict[str, Any], config: dict[str, Any] | None) -> list[str]:
    readback = config_readback(config)
    expected = {
        "adapterType": agent["adapterType"],
        "model": agent["model"],
        "reasoningEffort": agent["reasoningEffort"],
        "instructionsFilePath": agent["instructionsFilePath"],
        "instructionsBundleMode": agent["instructionsBundleMode"],
        "sandboxBypass": agent["sandboxBypass"],
        "runtimeEnvKeys": sorted(agent["runtimeEnvKeys"]),
        "workspacePath": agent["workspacePath"],
    }
    divergences: list[str] = []
    for key in PREFLIGHT_REQUIRED_FIELDS:
        if readback.get(key) != expected.get(key):
            divergences.append(f"{key}: expected {expected.get(key)!r}, got {readback.get(key)!r}")

    env_keys = set(readback.get("runtimeEnvKeys") or [])
    forbidden = sorted(FORBIDDEN_ENV_KEYS.intersection(env_keys))
    if forbidden:
        divergences.append(f"runtimeEnvKeys contain forbidden keys: {forbidden}")
    return divergences


def decide_agent(
    agent: dict[str, Any],
    live_matches: list[dict[str, Any]],
    live_config: dict[str, Any] | None,
    existing_early_ceo_agent_id: str,
    auceo_policy: str = "refuse",
) -> dict[str, Any]:
    decision = {
        "name": agent["name"],
        "plannedOperation": agent["plannedOperation"],
        "decision": "create",
        "ok": True,
        "blockers": [],
        "live": {"found": False},
        "readback": {"checked": False},
        "expectedConfigHash": agent["expectedConfigHash"],
    }

    if not live_matches:
        return decision
    if len(live_matches) > 1:
        decision["decision"] = "refuse"
        decision["ok"] = False
        decision["blockers"].append("duplicate live agents with same planned name")
        decision["live"] = {"found": True, "matches": [sanitized_agent(match) for match in live_matches]}
        return decision

    live_agent = live_matches[0]
    live_id = str(live_agent.get("id", ""))
    live_status = str(live_agent.get("status", "")).lower()
    decision["live"] = {"found": True, "agent": sanitized_agent(live_agent)}
    decision["readback"] = {
        "checked": True,
        "fields": config_readback(live_config),
        "configHash": sha256_json(sanitized_config(live_config)),
    }
    decision["rollbackSnapshot"] = {
        "agent": sanitized_agent(live_agent),
        "configuration": sanitized_config(live_config),
    }

    divergences = compare_readback(agent, live_config)
    if agent["name"] == "AUCEO":
        if live_id != existing_early_ceo_agent_id:
            decision["blockers"].append(
                f"AUCEO live id {live_id} does not match expected early CEO id {existing_early_ceo_agent_id}"
            )
        status_blocker = live_status in {"paused", "failed", "terminated", "unknown"}
        if status_blocker and auceo_policy != "recreate":
            decision["blockers"].append(f"AUCEO live status is {live_status}; operator recreate/update decision required")
        if divergences and auceo_policy != "recreate":
            decision["blockers"].append("AUCEO readback diverges: " + "; ".join(divergences))
        if decision["blockers"]:
            decision["decision"] = "refuse"
            decision["ok"] = False
        elif auceo_policy == "recreate":
            decision["decision"] = "recreate"
            decision["ok"] = True
            decision["operatorPolicy"] = "recreate"
            decision["recreatePlan"] = {
                "terminate_existing_agent_id": live_id,
                "create_replacement_name": agent["name"],
                "requires_rollback_snapshot": True,
                "requires_operator_approval": True,
            }
            reasons = []
            if status_blocker:
                reasons.append(f"live status is {live_status}")
            if divergences:
                reasons.append("readback diverges: " + "; ".join(divergences))
            decision["warnings"] = reasons
        else:
            decision["decision"] = "skip"
        return decision

    if divergences:
        decision["decision"] = "update"
        decision["ok"] = True
        decision["readback"]["divergences"] = divergences
    else:
        decision["decision"] = "skip"
    return decision


def assert_fresh_dry_run(dry_run_manifest: dict[str, Any], current_manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if dry_run_manifest.get("gate") != "B1":
        errors.append("dry-run manifest gate is not B1")
    if dry_run_manifest.get("mode") != "unauthenticated-dry-run":
        errors.append("dry-run manifest mode is not unauthenticated-dry-run")
    if dry_run_manifest.get("team") != "UnstoppableAudit":
        errors.append("dry-run manifest team is not UnstoppableAudit")
    if dry_run_manifest.get("dry_run_config_hash") != current_manifest.get("dry_run_config_hash"):
        errors.append("dry-run manifest is stale against current team config")
    return errors


def build_preflight_manifest(
    config: dict[str, Any],
    current_manifest: dict[str, Any],
    dry_run_manifest: dict[str, Any],
    live_agents: list[dict[str, Any]],
    live_configs_by_id: dict[str, dict[str, Any]],
    config_path: Path,
    dry_run_path: Path,
    api_base: str,
    auceo_policy: str = "refuse",
) -> dict[str, Any]:
    errors = assert_fresh_dry_run(dry_run_manifest, current_manifest)
    live_by_name = index_live_agents(live_agents)
    existing_early_ceo_agent_id = str(prereq.get_path(config, "paperclip.existing_early_ceo_agent_id"))
    decisions = []
    if not errors:
        for agent in current_manifest["agents"]:
            matches = live_by_name.get(agent["name"], [])
            live_config = None
            if len(matches) == 1 and matches[0].get("id"):
                live_config = live_configs_by_id.get(str(matches[0]["id"]))
            decisions.append(decide_agent(agent, matches, live_config, existing_early_ceo_agent_id, auceo_policy))

    blockers = list(errors)
    blockers.extend(
        f"{decision['name']}: {blocker}"
        for decision in decisions
        for blocker in decision.get("blockers", [])
    )
    return {
        "ok": not blockers,
        "gate": "B2",
        "mode": "authenticated-preflight",
        "checked_at": now_iso(),
        "team": "UnstoppableAudit",
        "config_path": str(config_path),
        "dry_run_manifest_path": str(dry_run_path),
        "dry_run_manifest_hash": sha256_json(dry_run_manifest),
        "api_base": api_base.rstrip("/"),
        "paperclip": {
            "company_id": prereq.get_path(config, "paperclip.company_id"),
            "project_id": prereq.get_path(config, "paperclip.onboarding_project_id"),
        },
        "apply_policy": {
            "live_apply_allowed": False,
            "requires_operator_approval": True,
            "requires_rollback_snapshot_before_mutation": True,
            "stop_on_first_failure": True,
        },
        "operator_policy": {
            "auceo": auceo_policy,
        },
        "blockers": blockers,
        "live_agent_count": len(live_agents),
        "decisions": decisions,
    }


def fetch_live_state(api_base: str, token: str, company_id: str, planned_agents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    agents = http_get_json(api_base, token, f"/api/companies/{company_id}/agents")
    if not isinstance(agents, list):
        raise RuntimeError("company agents endpoint returned non-list payload")
    planned_names = {agent["name"] for agent in planned_agents}
    configs: dict[str, dict[str, Any]] = {}
    for live_agent in agents:
        if live_agent.get("name") not in planned_names:
            continue
        live_id = str(live_agent.get("id", ""))
        if not live_id:
            continue
        config = http_get_json(api_base, token, f"/api/agents/{live_id}/configuration")
        if isinstance(config, dict):
            configs[live_id] = config
    return agents, configs


def parse_args(argv: list[str]) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Render UnstoppableAudit team dry-run manifests")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--repo-root", type=Path, default=repo_root)
    dry_run.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    dry_run.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_MANIFEST)
    dry_run.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    dry_run.add_argument("--write-manifest", action="store_true")
    dry_run.add_argument("--render-bundles", action="store_true")

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repo-root", type=Path, default=repo_root)
    preflight.add_argument("--config", type=Path, default=repo_root / "paperclips/teams/unstoppable-audit.yaml")
    preflight.add_argument("--dry-run-manifest", type=Path, default=repo_root / DEFAULT_MANIFEST)
    preflight.add_argument("--manifest", type=Path, default=repo_root / DEFAULT_PREFLIGHT_MANIFEST)
    preflight.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    preflight.add_argument("--auth-path", type=Path, default=Path.home() / ".paperclip" / "auth.json")
    preflight.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    preflight.add_argument(
        "--auceo-policy",
        choices=["refuse", "recreate"],
        default="refuse",
        help="explicit operator policy for existing AUCEO divergence",
    )
    preflight.add_argument("--write-manifest", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = load_config(args.config)
    bundle_dir = args.bundle_dir if args.bundle_dir.is_absolute() else args.bundle_dir
    agents = build_agent_plan(config, args.repo_root, bundle_dir)
    if getattr(args, "render_bundles", False):
        render_bundles(agents, config, args.repo_root)
    current_manifest = build_manifest(config, agents, args.config)
    if args.command == "dry-run":
        manifest = current_manifest
    else:
        dry_run_manifest = read_json(args.dry_run_manifest)
        token = load_auth_token(args.api_base, args.auth_path)
        if not token:
            raise RuntimeError("PAPERCLIP_API_KEY or ~/.paperclip/auth.json token is required for preflight")
        live_agents, live_configs_by_id = fetch_live_state(
            args.api_base,
            token,
            str(prereq.get_path(config, "paperclip.company_id")),
            current_manifest["agents"],
        )
        manifest = build_preflight_manifest(
            config,
            current_manifest,
            dry_run_manifest,
            live_agents,
            live_configs_by_id,
            args.config,
            args.dry_run_manifest,
            args.api_base,
            args.auceo_policy,
        )
    if args.write_manifest:
        write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
