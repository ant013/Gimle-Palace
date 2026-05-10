#!/usr/bin/env python3
"""Unauthenticated team renderer for UnstoppableAudit Gate B1."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unstoppable_audit_prereq as prereq


TEAM_SLUG = "unstoppable-audit"
DEFAULT_MANIFEST = Path("paperclips/manifests/unstoppable-audit/gate-b1-dry-run.json")
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


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


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
        validate_agent_plan(agent)
        agents.append(agent)
    return agents


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
        "agents": agents,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config = load_config(args.config)
    bundle_dir = args.bundle_dir if args.bundle_dir.is_absolute() else args.bundle_dir
    agents = build_agent_plan(config, args.repo_root, bundle_dir)
    if args.render_bundles:
        render_bundles(agents, config, args.repo_root)
    manifest = build_manifest(config, agents, args.config)
    if args.write_manifest:
        write_json(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
