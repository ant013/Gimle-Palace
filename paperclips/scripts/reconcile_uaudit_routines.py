#!/usr/bin/env python3
"""Dry-run or apply UAudit daily routine assignee reconciliation."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from resolve_bindings import resolve_all  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "paperclips/projects/uaudit/daily-version-branch-routines.yaml"
DEFAULT_PATHS = REPO_ROOT / "paperclips/projects/uaudit/paths.local-example.yaml"
DEFAULT_AUTH_PATHS = (
    Path.home() / ".paperclip/auth.json",
    Path("/Users/anton/.paperclip/auth.json"),
)
CURSOR_PATH_RE = re.compile(r"/[^\s`\"']+/(?:state/(?:android|ios)-version-audit\.json|artifacts/[^\s/]+/cursor\.json)")


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be mapping")
    if data.get("schemaVersion") != 1:
        raise ValueError(f"{path}: schemaVersion must be 1")
    limits = data.get("limits")
    routines = data.get("routines")
    if not isinstance(limits, dict) or not isinstance(routines, list):
        raise ValueError(f"{path}: expected limits mapping and routines list")
    for key in ("max_commits", "max_files", "max_diff_lines"):
        if not isinstance(limits.get(key), int) or limits[key] <= 0:
            raise ValueError(f"{path}: limits.{key} must be positive integer")
    return data


def resolve_agent_ids(project_key: str, bindings_path: Path | None) -> dict[str, str]:
    fallback = REPO_ROOT / "paperclips" / "projects" / project_key / "bindings.local-example.yaml"
    chosen = bindings_path or (Path.home() / ".paperclip" / "projects" / project_key / "bindings.yaml")
    if not chosen.is_file() and fallback.is_file():
        chosen = fallback
    merged = resolve_all(legacy_env_path=None, bindings_yaml_path=chosen)
    agents = merged.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("bindings source did not resolve agents mapping")
    return {str(k): str(v) for k, v in agents.items()}


def load_project_paths(project_key: str, paths_path: Path | None) -> dict[str, str]:
    fallback = REPO_ROOT / "paperclips" / "projects" / project_key / "paths.local-example.yaml"
    chosen = paths_path or (Path.home() / ".paperclip" / "projects" / project_key / "paths.yaml")
    if not chosen.is_file() and fallback.is_file():
        chosen = fallback
    if not chosen.is_file():
        return {}
    data = yaml.safe_load(chosen.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{chosen}: paths source must be mapping")
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def render_path_template(template: str, paths: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if not key.startswith("paths."):
            raise ValueError(f"unsupported path template reference: {key}")
        path_key = key.split(".", 1)[1]
        value = paths.get(path_key)
        if not value:
            raise ValueError(f"missing paths.{path_key} needed to render {template!r}")
        return value

    return re.sub(r"\{\{\s*([^}\s]+)\s*\}\}", replace, template)


def routine_title(routine: dict[str, Any]) -> str:
    platform = str(routine.get("platform", "")).strip()
    if not platform:
        return str(routine.get("id", ""))
    return f"UAudit daily {platform.capitalize()} version delta audit"


def required_agent_names(config: dict[str, Any]) -> set[str]:
    names: set[str] = {"AUCEO"}
    for routine in config.get("routines", []):
        for key in ("dispatcher", "infra_executor", "pr_audit_coordinator"):
            value = routine.get(key)
            if isinstance(value, str):
                names.add(value)
    return names


def validate_config_agents(config: dict[str, Any], agent_ids: dict[str, str]) -> None:
    missing = sorted(required_agent_names(config) - set(agent_ids))
    if missing:
        raise ValueError(f"routine config references unknown agents: {', '.join(missing)}")


def normalize_current_routines(payload: Any) -> dict[str, dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("routines"), list):
        items = payload["routines"]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("routines API response must be list or contain routines/data list")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = item.get("id") or item.get("key") or item.get("name")
        if isinstance(rid, str):
            result[rid] = item
    return result


def _routine_text(item: dict[str, Any]) -> str:
    parts = []
    for key in ("title", "name", "description", "body", "instructions"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _find_current_routine(
    routine: dict[str, Any],
    current: dict[str, dict[str, Any]],
    marker: str,
) -> tuple[str, dict[str, Any], str]:
    rid = routine["id"]
    direct = current.get(rid)
    if direct is not None:
        return rid, direct, "id"

    expected_title = routine_title(routine)
    for current_id, item in current.items():
        if item.get("title") == expected_title or item.get("name") == expected_title:
            return current_id, item, "title"

    platform = str(routine.get("platform", ""))
    for current_id, item in current.items():
        text = _routine_text(item).lower()
        if marker.lower() in text and platform.lower() in text:
            return current_id, item, "marker_platform"

    raise ValueError(f"routine {rid!r} not found; creation is not implicit")


def _description_with_cursor(description: str, desired_cursor_path: str) -> str:
    if desired_cursor_path in description:
        return description
    if CURSOR_PATH_RE.search(description):
        return CURSOR_PATH_RE.sub(desired_cursor_path, description)
    suffix = f"\ncursor: {desired_cursor_path}"
    return description.rstrip() + suffix if description else suffix.lstrip()


def _cursor_paths_in_item(item: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ("description", "body", "instructions"):
        value = item.get(key)
        if isinstance(value, str):
            paths.extend(CURSOR_PATH_RE.findall(value))
    return sorted(set(paths))


def build_plan(
    config: dict[str, Any],
    agent_ids: dict[str, str],
    current: dict[str, dict[str, Any]],
    paths: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    marker = str(config.get("marker", ""))
    for routine in config["routines"]:
        rid = routine["id"]
        current_id, current_item, matched_by = _find_current_routine(routine, current, marker)
        dispatcher = routine["dispatcher"]
        desired = agent_ids[dispatcher]
        current_assignee = current_item.get("assigneeAgentId") or current_item.get("assignee_agent_id")
        desired_cursor_path = None
        current_cursor_paths: list[str] = []
        needs_cursor_update = False
        desired_description = None
        if paths is not None:
            desired_cursor_path = render_path_template(routine["cursor_path_template"], paths)
            current_cursor_paths = _cursor_paths_in_item(current_item)
            needs_cursor_update = desired_cursor_path not in current_cursor_paths
            description = current_item.get("description")
            if needs_cursor_update and isinstance(description, str):
                desired_description = _description_with_cursor(description, desired_cursor_path)
        plan.append({
            "routine_id": rid,
            "current_routine_id": current_id,
            "matched_by": matched_by,
            "platform": routine.get("platform"),
            "dispatcher": dispatcher,
            "desired_assigneeAgentId": desired,
            "current_assigneeAgentId": current_assignee,
            "desired_cursor_path": desired_cursor_path,
            "current_cursor_paths": current_cursor_paths,
            "needs_assignee_update": current_assignee != desired,
            "needs_cursor_update": needs_cursor_update,
            "desired_description": desired_description,
            "needs_update": current_assignee != desired or needs_cursor_update,
        })
    return plan


def token_from_auth_json(path: Path, api_url: str) -> str | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    credentials = data.get("credentials") if isinstance(data, dict) else None
    if not isinstance(credentials, dict):
        return None
    candidates = [api_url.rstrip("/"), "http://localhost:3100", "https://paperclip.ant013.work"]
    for candidate in candidates:
        entry = credentials.get(candidate)
        if isinstance(entry, dict) and isinstance(entry.get("token"), str) and entry["token"]:
            return entry["token"]
    return None


def resolve_token(api_url: str, auth_json: Path | None) -> str:
    env_token = os.environ.get("PAPERCLIP_API_KEY") or os.environ.get("PAPERCLIP_API_TOKEN")
    if env_token:
        return env_token
    paths = (auth_json,) if auth_json else DEFAULT_AUTH_PATHS
    for path in paths:
        if path is None:
            continue
        token = token_from_auth_json(path, api_url)
        if token:
            return token
    raise ValueError("missing Paperclip token; set PAPERCLIP_API_KEY or provide --auth-json")


def request_json(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "uaudit-routine-reconcile/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{method} {url} failed HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc
    return json.loads(raw) if raw else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--project-key", default="uaudit")
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--paths", type=Path)
    parser.add_argument("--company-id")
    parser.add_argument("--api-url", default=os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100"))
    parser.add_argument("--auth-json", type=Path)
    parser.add_argument("--current-routines-json", type=Path, help="fixture/input for deterministic dry-runs")
    parser.add_argument("--apply", action="store_true", help="PATCH live routines; default is dry-run only")
    parser.add_argument("--create", action="store_true", help="reserved; routine creation is intentionally not implemented")
    args = parser.parse_args()

    try:
        if args.create:
            raise ValueError("--create is not implemented; missing routines require a separate reviewed change")
        config = load_config(args.config)
        agent_ids = resolve_agent_ids(args.project_key, args.bindings)
        paths = load_project_paths(args.project_key, args.paths)
        validate_config_agents(config, agent_ids)

        company_id = args.company_id
        token = None
        if args.current_routines_json:
            current_payload = json.loads(args.current_routines_json.read_text())
        else:
            if not company_id:
                fallback_bindings = yaml.safe_load((REPO_ROOT / "paperclips/projects/uaudit/bindings.local-example.yaml").read_text())
                company_id = fallback_bindings.get("company_id") if isinstance(fallback_bindings, dict) else None
            if not company_id:
                raise ValueError("--company-id is required when reading live routines")
            token = resolve_token(args.api_url, args.auth_json)
            current_payload = request_json("GET", f"{args.api_url.rstrip('/')}/api/companies/{company_id}/routines", token)

        current = normalize_current_routines(current_payload)
        plan = build_plan(config, agent_ids, current, paths)
        result = {"mode": "apply" if args.apply else "dry-run", "company_id": company_id, "updates": plan}

        if args.apply:
            if args.current_routines_json:
                raise ValueError("--apply cannot be used with --current-routines-json")
            if token is None:
                token = resolve_token(args.api_url, args.auth_json)
            for item in plan:
                if item["needs_update"]:
                    body: dict[str, Any] = {}
                    if item["needs_assignee_update"]:
                        body["assigneeAgentId"] = item["desired_assigneeAgentId"]
                    if item["needs_cursor_update"] and item["desired_description"] is not None:
                        body["description"] = item["desired_description"]
                    if not body:
                        raise ValueError(
                            f"routine {item['routine_id']} has cursor drift but no editable description field",
                        )
                    request_json(
                        "PATCH",
                        f"{args.api_url.rstrip('/')}/api/companies/{company_id}/routines/{item['current_routine_id']}",
                        token,
                        body,
                    )

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
