#!/usr/bin/env python3
"""Project-aware Paperclip deploy dry-run from resolved assembly metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import compare_deployed_agents


def load_resolved(repo_root: Path, project: str) -> dict:
    path = compare_deployed_agents.resolved_assembly_path(repo_root, project)
    if not path.is_file():
        raise FileNotFoundError(f"missing resolved assembly manifest: {path.relative_to(repo_root)}")
    return json.loads(path.read_text())


def agent_ids(repo_root: Path, target: str) -> dict[str, str]:
    paperclips = repo_root / "paperclips"
    if target == "claude":
        return compare_deployed_agents.load_claude_agent_ids(paperclips / "deploy-agents.sh")
    if target == "codex":
        return compare_deployed_agents.load_codex_agent_ids(paperclips / "codex-agent-ids.env")
    raise ValueError(f"unsupported target: {target}")


def selected_targets(resolved: dict, target: str) -> list[str]:
    targets = resolved.get("targets", {})
    if target == "all":
        return sorted(str(key) for key in targets.keys())
    return [target]


def dry_run(repo_root: Path, project: str, target: str, agent: str | None) -> int:
    resolved = load_resolved(repo_root, project)
    failures = 0
    selected = selected_targets(resolved, target)

    print(f"DRY-RUN project={project}")
    print(f"sourceManifest={resolved.get('sourceManifest', '')}")
    print(f"sourceManifestSha256={str(resolved.get('sourceManifestSha256', ''))[:12]}")

    for target_name in selected:
        target_data = resolved.get("targets", {}).get(target_name)
        if not isinstance(target_data, dict):
            print(f"ERROR missing target in resolved assembly: {target_name}", file=sys.stderr)
            failures += 1
            continue
        ids = agent_ids(repo_root, target_name)
        expected_adapter = target_data.get("adapterType", "")
        print(f"\nTarget: {target_name} adapter={expected_adapter}")

        roles = target_data.get("roles", [])
        for role in roles:
            if not isinstance(role, dict):
                continue
            output = role.get("output", "")
            name = Path(str(output)).stem
            if agent and name != agent:
                continue
            output_path = repo_root / str(output)
            aid = ids.get(name, "")
            if not output_path.is_file():
                print(f"  ERROR {name}: missing output {output}", file=sys.stderr)
                failures += 1
                continue
            if not aid:
                print(f"  PENDING {name}: no {target_name} agent id")
                failures += 1
                continue
            sha = role.get("sha256", "")
            size = role.get("bytes", "")
            print(f"  WOULD DEPLOY {name} -> {aid}")
            print(f"    source: {output}")
            print(f"    sha256: {str(sha)[:12]} bytes={size}")
        if agent and not any(Path(str(role.get("output", ""))).stem == agent for role in roles if isinstance(role, dict)):
            print(f"  ERROR unknown agent for {target_name}: {agent}", file=sys.stderr)
            failures += 1

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--project", default="gimle")
    parser.add_argument("--target", choices=["all", "claude", "codex"], default="all")
    parser.add_argument("--agent", help="Optional role filename stem, e.g. cto or cx-cto")
    parser.add_argument("--dry-run", action="store_true", help="Required; live deploy is intentionally out of scope")
    args = parser.parse_args()

    if not args.dry_run:
        print("ERROR: only --dry-run is supported by this project-aware wrapper", file=sys.stderr)
        return 2

    try:
        return dry_run(args.repo_root.resolve(), args.project, args.target, args.agent)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
