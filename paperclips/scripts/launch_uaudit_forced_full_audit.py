#!/usr/bin/env python3
"""Create explicitly confirmed, cursorless UAudit full-range audit issues."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_uaudit_routines import (  # noqa: E402
    DEFAULT_CONFIG,
    load_config,
    load_paths,
    request_json,
    resolve_agent_ids,
    resolve_token,
)
from resolve_template_sources import resolve  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MARKER = "UAudit forced full-range audit"


def sha(value: str, name: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 40-hex SHA")
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True)
    if result.returncode:
        raise ValueError(f"git {' '.join(args)} failed for {repo}: {result.stderr.strip()}")
    return result.stdout.strip()


def selected(config: dict[str, Any], platform: str) -> list[dict[str, Any]]:
    choices = config["routines"] if platform == "all" else [r for r in config["routines"] if r["platform"] == platform]
    if not choices or len(choices) != (2 if platform == "all" else 1):
        raise ValueError(f"missing routine for platform {platform}")
    return choices


def build_payloads(config: dict[str, Any], paths: dict[str, Any], agents: dict[str, str], platform: str, from_sha: str, to_sha: str) -> list[dict[str, Any]]:
    from_sha, to_sha = sha(from_sha, "from_sha"), sha(to_sha, "to_sha")
    payloads: list[dict[str, Any]] = []
    for routine in selected(config, platform):
        repo = Path(resolve(routine["repo_local_path_template"], {"paths": paths}))
        if not repo.is_dir():
            raise ValueError(f"declared checkout does not exist: {repo}")
        git(repo, "cat-file", "-e", f"{from_sha}^{{commit}}")
        git(repo, "cat-file", "-e", f"{to_sha}^{{commit}}")
        git(repo, "merge-base", "--is-ancestor", from_sha, to_sha)
        dispatcher = agents[routine["dispatcher"]]
        description = "\n".join((
            MARKER,
            "mode: forced_full_range",
            "audit_kind: forced_full",
            "daily_limits_bypassed: true",
            f"platform: {routine['platform']}",
            f"routine_id: {routine['id']}",
            f"branch: {routine['branch']}",
            f"repo: {repo}",
            f"from_sha: {from_sha}",
            f"to_sha: {to_sha}",
            "cursor_mutation: forbidden",
            "schedule_mutation: forbidden",
        ))
        payloads.append({
            "title": f"UAudit forced full-range {routine['platform']} audit",
            "description": description,
            "status": "todo",
            "priority": "high",
            "assigneeAgentId": dispatcher,
        })
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    parser.add_argument("--from-sha", required=True)
    parser.add_argument("--to-sha", required=True)
    parser.add_argument("--confirm-unbounded", action="store_true")
    parser.add_argument("--apply", action="store_true", help="POST issues; dry-run is the default")
    parser.add_argument("--company-id")
    parser.add_argument("--api-url", default="https://paperclip.ant013.work")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--paths", type=Path)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--auth-json", type=Path)
    args = parser.parse_args()
    try:
        if not args.confirm_unbounded:
            raise ValueError("--confirm-unbounded is required")
        config, paths = load_config(args.config), load_paths("uaudit", args.paths)
        payloads = build_payloads(config, paths, resolve_agent_ids("uaudit", args.bindings), args.platform, args.from_sha, args.to_sha)
        result: dict[str, Any] = {"mode": "apply" if args.apply else "dry-run", "issues": payloads}
        if args.apply:
            if not args.company_id:
                raise ValueError("--company-id is required with --apply")
            token = resolve_token(args.api_url, args.auth_json)
            result["created"] = [request_json("POST", f"{args.api_url.rstrip('/')}/api/companies/{args.company_id}/issues", token, body) for body in payloads]
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
