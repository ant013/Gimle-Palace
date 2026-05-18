#!/usr/bin/env python3
"""Project-aware Paperclip deploy helpers from resolved assembly metadata."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import compare_deployed_agents


def load_resolved(repo_root: Path, project: str) -> dict:
    path = compare_deployed_agents.resolved_assembly_path(repo_root, project)
    if not path.is_file():
        raise FileNotFoundError(f"missing resolved assembly manifest: {path.relative_to(repo_root)}")
    return json.loads(path.read_text())


def selected_targets(resolved: dict, target: str) -> list[str]:
    targets = resolved.get("targets", {})
    if target == "all":
        return sorted(str(key) for key in targets.keys())
    return [target]


def role_agent_name(role: dict) -> str:
    output = role.get("output", "")
    name = role.get("agentName")
    if isinstance(name, str) and name:
        return name
    return Path(str(output)).stem


def find_role(resolved: dict, target: str, agent: str) -> tuple[str, dict, dict]:
    for target_name in selected_targets(resolved, target):
        target_data = resolved.get("targets", {}).get(target_name)
        if not isinstance(target_data, dict):
            continue
        for role in target_data.get("roles", []):
            if isinstance(role, dict) and role_agent_name(role) == agent:
                return target_name, target_data, role
    raise ValueError(f"unknown agent for {target}: {agent}")


def verify_source_bundle(repo_root: Path, role: dict) -> Path:
    output = role.get("output")
    if not isinstance(output, str) or not output:
        raise ValueError(f"resolved role missing output: {role_agent_name(role)}")
    source = repo_root / output
    if not source.is_file():
        raise FileNotFoundError(f"missing source bundle: {output}")
    expected_sha = role.get("sha256")
    actual_sha = compare_deployed_agents.sha256_text(source.read_text())
    if expected_sha != actual_sha:
        raise ValueError(f"source bundle sha mismatch for {output}: {actual_sha[:12]} != {expected_sha}")
    return source


def workspace_agents_path(role: dict) -> Path:
    workspace = role.get("workspaceCwd")
    name = role_agent_name(role)
    if not isinstance(workspace, str) or not workspace:
        raise ValueError(f"resolved role missing workspaceCwd: {name}")
    if workspace.startswith(("~", "$")):
        raise ValueError(f"unsafe workspaceCwd for {name}: {workspace}")
    workspace_path = Path(workspace)
    if not workspace_path.is_absolute() or ".." in workspace_path.parts:
        raise ValueError(f"workspaceCwd must be absolute and normalized for {name}: {workspace}")
    if not workspace_path.is_dir():
        raise FileNotFoundError(f"workspaceCwd missing for {name}: {workspace}")
    return workspace_path / "AGENTS.md"


def backup_path(backup_dir: Path, project: str, target: str, agent: str) -> Path:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_agent = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in agent)
    return backup_dir / project / target / f"{safe_agent}.AGENTS.{timestamp}.bak.md"


def ensure_backup_under_dir(backup: Path, backup_dir: Path) -> Path:
    resolved_backup = backup.resolve()
    resolved_dir = backup_dir.resolve()
    try:
        resolved_backup.relative_to(resolved_dir)
    except ValueError as exc:
        raise ValueError(f"backup path is outside backup-dir: {resolved_backup}") from exc
    return resolved_backup


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
        expected_adapter = target_data.get("adapterType", "")
        print(f"\nTarget: {target_name} adapter={expected_adapter}")

        roles = target_data.get("roles", [])
        for role in roles:
            if not isinstance(role, dict):
                continue
            output = role.get("output", "")
            name = role.get("agentName")
            if not isinstance(name, str) or not name:
                name = Path(str(output)).stem
            if agent and name != agent:
                continue
            output_path = repo_root / str(output)
            aid = role.get("agentId", "")
            if not output_path.is_file():
                print(f"  ERROR {name}: missing output {output}", file=sys.stderr)
                failures += 1
                continue
            if not isinstance(aid, str) or not aid:
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


def live_local(repo_root: Path, project: str, target: str, agent: str, backup_dir: Path) -> int:
    resolved = load_resolved(repo_root, project)
    if target == "all":
        raise ValueError("--live-local requires a concrete --target")
    target_name, target_data, role = find_role(resolved, target, agent)
    adapter = target_data.get("adapterType", "")
    if adapter not in {"codex_local", "claude_local"}:
        raise ValueError(f"live-local refuses non-local adapter for {agent}: {adapter}")

    source = verify_source_bundle(repo_root, role)
    destination = workspace_agents_path(role)
    if not destination.is_file():
        raise FileNotFoundError(f"live AGENTS.md missing for {agent}: {destination}")

    backup = backup_path(backup_dir, project, target_name, agent)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, backup)
    backup.with_suffix(".json").write_text(
        json.dumps(
            {
                "project": project,
                "target": target_name,
                "agent": agent,
                "destination": str(destination),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    shutil.copy2(source, destination)

    deployed_sha = compare_deployed_agents.sha256_text(destination.read_text())
    expected_sha = role.get("sha256")
    if deployed_sha != expected_sha:
        shutil.copy2(backup, destination)
        raise ValueError(f"post-deploy sha mismatch for {agent}; restored backup {backup}")

    print(f"LIVE-LOCAL DEPLOYED {agent}")
    print(f"  source: {source.relative_to(repo_root)}")
    print(f"  target: {destination}")
    print(f"  backup: {backup}")
    print(f"  rollbackMetadata: {backup.with_suffix('.json')}")
    print(f"  sha256: {deployed_sha[:12]}")
    return 0


def fetch_adapter_type(api_base: str, api_key: str, agent_id: str) -> str:
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/agents/{agent_id}/configuration",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "paperclip-project-agent-deploy/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    adapter = data.get("adapterType", "")
    return adapter if isinstance(adapter, str) else ""


def put_instruction_bundle(api_base: str, api_key: str, agent_id: str, content: str) -> int:
    body = json.dumps({"path": "AGENTS.md", "content": content}).encode("utf-8")
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/agents/{agent_id}/instructions-bundle/file",
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "paperclip-project-agent-deploy/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return int(response.status)


def live_api(
    repo_root: Path,
    project: str,
    target: str,
    agent: str,
    api_base: str,
    api_key: str,
) -> int:
    resolved = load_resolved(repo_root, project)
    if target == "all":
        raise ValueError("--api requires a concrete --target")
    target_name, target_data, role = find_role(resolved, target, agent)
    adapter = target_data.get("adapterType", "")
    if adapter != "codex_local":
        raise ValueError(f"--api refuses non-codex_local adapter for {agent}: {adapter}")
    source = verify_source_bundle(repo_root, role)
    agent_id = role.get("agentId")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError(f"missing agentId for {agent}")
    live_adapter = fetch_adapter_type(api_base, api_key, agent_id)
    if live_adapter != adapter:
        raise ValueError(f"refusing upload to {agent_id}; expected {adapter}, got {live_adapter!r}")
    content = source.read_text()
    status = put_instruction_bundle(api_base, api_key, agent_id, content)
    if status not in {200, 204}:
        raise ValueError(f"upload failed for {agent}: HTTP {status}")
    print(f"API DEPLOYED {agent}")
    print(f"  project: {project} target: {target_name}")
    print(f"  source: {source.relative_to(repo_root)}")
    print(f"  agentId: {agent_id}")
    print(f"  adapterType: {live_adapter}")
    print(f"  sha256: {role.get('sha256', '')[:12]}")
    return 0


def rollback(backup: Path, backup_dir: Path) -> int:
    backup_file = ensure_backup_under_dir(backup, backup_dir)
    if not backup_file.is_file():
        raise FileNotFoundError(f"backup file missing: {backup_file}")
    metadata_path = ensure_backup_under_dir(backup_file.with_suffix(".json"), backup_dir)
    if not metadata_path.is_file():
        raise FileNotFoundError(f"rollback metadata missing: {metadata_path}")
    metadata = json.loads(metadata_path.read_text())
    project = str(metadata.get("project", ""))
    target = str(metadata.get("target", ""))
    agent = str(metadata.get("agent", ""))
    destination = Path(str(metadata.get("destination", "")))
    if not destination.is_absolute() or destination.name != "AGENTS.md":
        raise ValueError(f"rollback destination invalid for {backup_file}: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"rollback workspace missing: {destination.parent}")
    shutil.copy2(backup_file, destination)
    print(f"ROLLBACK RESTORED {agent}")
    print(f"  project: {project} target: {target}")
    print(f"  source: {backup_file}")
    print(f"  target: {destination}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--project", default="gimle")
    parser.add_argument("--target", choices=["all", "claude", "codex"], default="all")
    parser.add_argument("--agent", help="Optional role filename stem, e.g. cto or cx-cto")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved deploy actions without writing")
    parser.add_argument("--live-local", action="store_true", help="Write one resolved bundle to its local workspace")
    parser.add_argument("--api", action="store_true", help="Upload one resolved Codex bundle through Paperclip API")
    parser.add_argument("--api-base", default=os.environ.get("PAPERCLIP_API_URL", "https://paperclip.ant013.work"))
    parser.add_argument("--backup-dir", type=Path, help="Directory for live-local backups and rollback guard")
    parser.add_argument("--rollback", type=Path, help="Restore one backup file created by --live-local")
    args = parser.parse_args()

    selected_modes = sum(bool(mode) for mode in [args.dry_run, args.live_local, args.api, args.rollback])
    if selected_modes != 1:
        print("ERROR: choose exactly one of --dry-run, --live-local, --api, or --rollback", file=sys.stderr)
        return 2
    if (args.live_local or args.api) and not args.agent:
        print("ERROR: --live-local/--api require --agent", file=sys.stderr)
        return 2
    if (args.live_local or args.rollback) and not args.backup_dir:
        print("ERROR: --live-local/--rollback require --backup-dir", file=sys.stderr)
        return 2
    if args.api and not os.environ.get("PAPERCLIP_API_KEY"):
        print("ERROR: --api requires PAPERCLIP_API_KEY", file=sys.stderr)
        return 2

    try:
        repo_root = args.repo_root.resolve()
        if args.dry_run:
            return dry_run(repo_root, args.project, args.target, args.agent)
        if args.live_local:
            return live_local(repo_root, args.project, args.target, args.agent or "", args.backup_dir)
        if args.api:
            return live_api(
                repo_root,
                args.project,
                args.target,
                args.agent or "",
                args.api_base,
                os.environ["PAPERCLIP_API_KEY"],
            )
        return rollback(args.rollback, args.backup_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
