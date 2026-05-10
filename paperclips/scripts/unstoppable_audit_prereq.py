#!/usr/bin/env python3
"""Gate A prerequisite verifier for the UnstoppableAudit bootstrap.

The verifier is intentionally local and read-only by default. It validates the
team-scoped bootstrap config, checks filesystem safety expectations, and can
record a manifest for later live Paperclip steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
TELEGRAM_PRIVATE_SUPERGROUP_RE = re.compile(r"^-100\d{7,}$")

EXPECTED_REPOS = {
    "ios": "https://github.com/horizontalsystems/unstoppable-wallet-ios",
    "android": "https://github.com/horizontalsystems/unstoppable-wallet-android",
}


@dataclass
class Check:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        data = {"name": self.name, "status": self.status, "message": self.message}
        if self.details:
            data["details"] = self.details
        return data


class ConfigError(ValueError):
    pass


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise ConfigError(f"{path}:{line_number}: tabs are not supported")

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            raise ConfigError(f"{path}:{line_number}: lists are not supported")
        if ":" not in stripped:
            raise ConfigError(f"{path}:{line_number}: expected 'key: value'")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"{path}:{line_number}: empty key")

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        value = raw_value.strip()
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_scalar(value)

    return root


def get_path(config: dict[str, Any], dotted: str) -> Any:
    current: Any = config
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ConfigError(f"missing required config key: {dotted}")
        current = current[part]
    return current


def validate_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(UUID_RE.match(value))


def validate_chat_id(value: Any) -> bool:
    return isinstance(value, str) and bool(TELEGRAM_PRIVATE_SUPERGROUP_RE.match(value))


def owner_only_mode(path: Path) -> bool:
    mode = stat.S_IMODE(path.stat().st_mode)
    return (mode & 0o077) == 0


def git_mirror_head(mirror_path: Path) -> str | None:
    if not mirror_path.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "--git-dir", str(mirror_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = result.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", sha):
        return sha
    return None


def add_check(checks: list[Check], name: str, status: str, message: str, **details: Any) -> None:
    checks.append(Check(name=name, status=status, message=message, details=details))


def verify(config_path: Path, repo_root: Path) -> dict[str, Any]:
    checks: list[Check] = []

    try:
        config = parse_simple_yaml(config_path)
    except (OSError, ConfigError) as exc:
        return {
            "ok": False,
            "checked_at": now_iso(),
            "config_path": str(config_path),
            "checks": [
                Check("config.parse", "blocker", str(exc)).to_json(),
            ],
        }

    required_keys = [
        "team",
        "paperclip.company_id",
        "paperclip.onboarding_project_id",
        "paperclip.existing_early_ceo_agent_id",
        "repositories.ios.url",
        "repositories.ios.mirror_path",
        "repositories.android.url",
        "repositories.android.mirror_path",
        "telegram.redacted_reports_chat_id",
        "telegram.ops_chat_id",
        "codex.home_root",
        "codex.path",
        "models.default_model",
        "roots.stable_mirror_root",
        "roots.run_root",
        "roots.artifact_root",
        "codebase_memory.ios_project",
        "codebase_memory.android_project",
        "neo4j.audit_storage_phase1",
    ]
    missing: list[str] = []
    for key in required_keys:
        try:
            get_path(config, key)
        except ConfigError:
            missing.append(key)
    if missing:
        add_check(
            checks,
            "config.required_keys",
            "blocker",
            "config is missing required keys",
            missing=missing,
        )
        return {
            "ok": False,
            "checked_at": now_iso(),
            "team": config.get("team"),
            "config_path": str(config_path),
            "checks": [check.to_json() for check in checks],
        }
    else:
        add_check(checks, "config.required_keys", "pass", "all required keys are present")

    if get_path(config, "team") != "UnstoppableAudit":
        add_check(checks, "config.team", "blocker", "team must be UnstoppableAudit")
    else:
        add_check(checks, "config.team", "pass", "team is UnstoppableAudit")

    for key in [
        "paperclip.company_id",
        "paperclip.onboarding_project_id",
        "paperclip.existing_early_ceo_agent_id",
    ]:
        value = get_path(config, key)
        if validate_uuid(value):
            add_check(checks, key, "pass", "valid UUID")
        else:
            add_check(checks, key, "blocker", "expected UUID", value=str(value))

    for platform, expected_url in EXPECTED_REPOS.items():
        url = get_path(config, f"repositories.{platform}.url")
        if url == expected_url:
            add_check(checks, f"repositories.{platform}.url", "pass", "repository URL matches")
        else:
            add_check(
                checks,
                f"repositories.{platform}.url",
                "blocker",
                "unexpected repository URL",
                expected=expected_url,
                actual=str(url),
            )

        mirror = Path(str(get_path(config, f"repositories.{platform}.mirror_path")))
        if not mirror.is_absolute():
            add_check(checks, f"repositories.{platform}.mirror_path", "blocker", "path must be absolute")
            continue
        sha = git_mirror_head(mirror)
        if sha:
            add_check(
                checks,
                f"repositories.{platform}.mirror_sha",
                "pass",
                "mirror HEAD resolved",
                mirror_path=str(mirror),
                sha=sha,
            )
        else:
            add_check(
                checks,
                f"repositories.{platform}.mirror_sha",
                "blocker",
                "stable mirror is missing or HEAD cannot be resolved",
                mirror_path=str(mirror),
            )

    for key in ["telegram.redacted_reports_chat_id", "telegram.ops_chat_id"]:
        value = str(get_path(config, key))
        if validate_chat_id(value):
            add_check(checks, key, "pass", "valid private supergroup chat id")
        else:
            add_check(checks, key, "blocker", "expected Telegram id derived from t.me/c link")

    for key in ["roots.stable_mirror_root", "roots.run_root", "roots.artifact_root"]:
        root_path = Path(str(get_path(config, key)))
        if not root_path.is_absolute():
            add_check(checks, key, "blocker", "path must be absolute")
            continue
        if not root_path.exists():
            add_check(checks, key, "blocker", "path does not exist yet", path=str(root_path))
            continue
        if owner_only_mode(root_path):
            add_check(checks, key, "pass", "path exists with owner-only permissions", path=str(root_path))
        else:
            add_check(
                checks,
                key,
                "blocker",
                "path must not be group/world accessible",
                path=str(root_path),
                mode=oct(stat.S_IMODE(root_path.stat().st_mode)),
            )

    for rel in [
        "paperclips/build.sh",
        "paperclips/validate-codex-target.sh",
        "paperclips/scripts/validate_instructions.py",
    ]:
        path = repo_root / rel
        if path.exists():
            add_check(checks, f"repo.{rel}", "pass", "required local substrate file exists")
        else:
            add_check(checks, f"repo.{rel}", "blocker", "required local substrate file is missing")

    neo_phase = str(get_path(config, "neo4j.audit_storage_phase1"))
    if neo_phase == "skipped":
        add_check(checks, "neo4j.phase1", "pass", "Neo4j audit storage is disabled for phase 1")
    else:
        add_check(checks, "neo4j.phase1", "blocker", "phase 1 must not write audit storage to Neo4j")

    codebase_memory_inputs = {
        "ios_project": get_path(config, "codebase_memory.ios_project"),
        "android_project": get_path(config, "codebase_memory.android_project"),
        "audit_storage_phase1": get_path(config, "codebase_memory.audit_storage_phase1"),
    }

    failing = [check for check in checks if check.status in {"fail", "blocker"}]
    return {
        "ok": not failing,
        "checked_at": now_iso(),
        "team": get_path(config, "team"),
        "config_path": str(config_path),
        "inputs": {
            "paperclip_company_id": get_path(config, "paperclip.company_id"),
            "onboarding_project_id": get_path(config, "paperclip.onboarding_project_id"),
            "early_ceo_agent_id": get_path(config, "paperclip.existing_early_ceo_agent_id"),
            "repositories": {
                platform: {
                    "url": get_path(config, f"repositories.{platform}.url"),
                    "mirror_path": get_path(config, f"repositories.{platform}.mirror_path"),
                }
                for platform in EXPECTED_REPOS
            },
            "telegram": {
                "redacted_reports_chat_id": str(get_path(config, "telegram.redacted_reports_chat_id")),
                "ops_chat_id": str(get_path(config, "telegram.ops_chat_id")),
            },
            "codebase_memory": codebase_memory_inputs,
        },
        "decisions": {
            "default_model": get_path(config, "models.default_model"),
            "default_reasoning_effort": get_path(config, "models.default_reasoning_effort"),
            "neo4j_audit_storage_phase1": neo_phase,
        },
        "checks": [check.to_json() for check in checks],
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Verify UnstoppableAudit Gate A prerequisites")
    parser.add_argument("--repo-root", type=Path, default=repo_root)
    parser.add_argument(
        "--config",
        type=Path,
        default=repo_root / "paperclips" / "teams" / "unstoppable-audit.yaml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=repo_root / "paperclips" / "manifests" / "unstoppable-audit" / "gate-a-prereq.json",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="write the JSON manifest to --manifest in addition to stdout",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    manifest = verify(args.config, args.repo_root)
    if args.write_manifest:
        write_manifest(args.manifest, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
