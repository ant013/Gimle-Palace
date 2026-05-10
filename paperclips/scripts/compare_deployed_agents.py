#!/usr/bin/env python3
"""Compare generated Paperclip bundles with deployed AGENTS.md files."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_COMPANY_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"


@dataclass(frozen=True)
class AgentRef:
    target: str
    name: str
    agent_id: str
    dist_path: Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_claude_agent_ids(deploy_script: Path) -> dict[str, str]:
    text = deploy_script.read_text()
    pattern = re.compile(r"^\s*([a-z][\w-]*)\)\s+echo\s+\"([0-9a-f-]{36})\"", re.MULTILINE)
    return {name: agent_id for name, agent_id in pattern.findall(text)}


def _codex_env_to_agent_name(key: str) -> str:
    if not key.endswith("_AGENT_ID"):
        return ""
    stem = key[: -len("_AGENT_ID")]
    return stem.lower().replace("_", "-")


def load_codex_agent_ids(env_file: Path) -> dict[str, str]:
    ids: dict[str, str] = {}
    if not env_file.is_file():
        return ids
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        name = _codex_env_to_agent_name(key.strip())
        agent_id = value.strip()
        if name and re.fullmatch(r"[0-9a-f-]{36}", agent_id):
            ids[name] = agent_id
    return ids


def collect_agent_refs(repo_root: Path, target: str, agent: str | None) -> list[AgentRef]:
    paperclips = repo_root / "paperclips"
    refs: list[AgentRef] = []

    if target in ("all", "claude"):
        ids = load_claude_agent_ids(paperclips / "deploy-agents.sh")
        for dist_path in sorted((paperclips / "dist").glob("*.md")):
            name = dist_path.stem
            if agent and name != agent:
                continue
            agent_id = ids.get(name)
            if agent_id:
                refs.append(AgentRef("claude", name, agent_id, dist_path))

    if target in ("all", "codex"):
        ids = load_codex_agent_ids(paperclips / "codex-agent-ids.env")
        for dist_path in sorted((paperclips / "dist" / "codex").glob("*.md")):
            name = dist_path.stem
            if agent and name != agent:
                continue
            agent_id = ids.get(name)
            if agent_id:
                refs.append(AgentRef("codex", name, agent_id, dist_path))

    return refs


def deployed_agents_path(paperclip_data_dir: Path, company_id: str, agent_id: str) -> Path:
    return paperclip_data_dir / "companies" / company_id / "agents" / agent_id / "instructions" / "AGENTS.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--target", choices=["all", "claude", "codex"], default="all")
    parser.add_argument("--agent", help="Optional role filename stem, e.g. cto or cx-cto")
    parser.add_argument(
        "--paperclip-data-dir",
        type=Path,
        default=Path.home() / ".paperclip" / "instances" / "default",
    )
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--show-diff", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    refs = collect_agent_refs(repo_root, args.target, args.agent)
    if not refs:
        print("ERROR: no comparable agents found", file=sys.stderr)
        return 1

    failures = 0
    for ref in refs:
        deployed_path = deployed_agents_path(args.paperclip_data_dir.expanduser(), args.company_id, ref.agent_id)
        label = f"{ref.target}:{ref.name}"
        if not deployed_path.is_file():
            message = f"{label}: missing deployed AGENTS.md at {deployed_path}"
            if args.allow_missing:
                print(f"SKIP {message}")
                continue
            print(f"ERROR {message}", file=sys.stderr)
            failures += 1
            continue

        generated = ref.dist_path.read_text()
        deployed = deployed_path.read_text()
        generated_hash = sha256_text(generated)
        deployed_hash = sha256_text(deployed)
        if generated_hash == deployed_hash:
            print(f"OK   {label} {generated_hash[:12]}")
            continue

        print(
            f"DIFF {label} generated={generated_hash[:12]} deployed={deployed_hash[:12]}",
            file=sys.stderr,
        )
        failures += 1
        if args.show_diff:
            diff = difflib.unified_diff(
                generated.splitlines(),
                deployed.splitlines(),
                fromfile=str(ref.dist_path),
                tofile=str(deployed_path),
                lineterm="",
            )
            for line in diff:
                print(line, file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
