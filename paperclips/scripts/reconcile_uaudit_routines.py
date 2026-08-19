#!/usr/bin/env python3
"""Dry-run or revision-safely reconcile repository-owned UAudit routines."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from resolve_bindings import resolve_all  # noqa: E402
from resolve_template_sources import resolve  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "paperclips/projects/uaudit/daily-version-branch-routines.yaml"
DEFAULT_AUTH_PATHS = (
    Path.home() / ".paperclip/auth.json",
    Path("/Users/anton/.paperclip/auth.json"),
)
DAILY_CHAIN_KEYS = {
    "intake",
    "code_auditor",
    "security_auditor",
    "crypto_auditor",
    "infra_auditor",
    "research_agent",
    "qa_agent",
    "aggregator",
    "delivery_agent",
}
ROUTINE_REQUIRED_STRINGS = (
    "id",
    "app_id",
    "routine_key",
    "title",
    "platform",
    "branch",
    "repo_local_path_template",
    "cursor_path_template",
    "dispatcher",
    "infra_executor",
    "pr_audit_coordinator",
)
IDENTITY_FIELDS = ("app_id", "routine_key", "platform")


def _single_line(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{where} must be a non-empty trimmed string")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{where} must be single-line")
    return value


def _require_unique(values: list[str], where: str) -> None:
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"{where} must be unique; duplicates: {', '.join(duplicates)}")


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be mapping")
    if data.get("schemaVersion") != 2:
        raise ValueError(f"{path}: schemaVersion must be 2")
    marker = _single_line(data.get("marker"), f"{path}: marker")
    routines = data.get("routines")
    apps = data.get("apps")
    if not isinstance(routines, list) or not routines or not isinstance(apps, list) or not apps:
        raise ValueError(f"{path}: expected apps and non-empty routines lists")
    app_ids: set[str] = set()
    for index, app in enumerate(apps):
        if not isinstance(app, dict):
            raise ValueError(f"{path}: apps[{index}] must be a mapping")
        app_id = _single_line(app.get("id"), f"{path}: apps[{index}].id")
        if app_id in app_ids:
            raise ValueError(f"{path}: app ids must be unique")
        if not isinstance(app.get("enabled"), bool):
            raise ValueError(f"{path}: apps[{index}].enabled must be boolean")
        _single_line(app.get("display_name"), f"{path}: apps[{index}].display_name")
        _single_line(app.get("report_route"), f"{path}: apps[{index}].report_route")
        app_ids.add(app_id)
    validated: list[dict[str, Any]] = []
    for index, routine in enumerate(routines):
        if not isinstance(routine, dict):
            raise ValueError(f"{path}: routines[{index}] must be a mapping")
        for key in ROUTINE_REQUIRED_STRINGS:
            _single_line(routine.get(key), f"{path}: routines[{index}].{key}")
        if routine["app_id"] not in app_ids:
            raise ValueError(f"{path}: routines[{index}].app_id is not registered")
        if routine["platform"] not in {"android", "ios"}:
            raise ValueError(f"{path}: routines[{index}].platform must be android or ios")
        if not routine["branch"].startswith("version/"):
            raise ValueError(f"{path}: routines[{index}].branch must start with version/")
        if "required_subagents" in routine:
            raise ValueError(f"{path}: daily routines must use daily_chain, not required_subagents")
        chain = routine.get("daily_chain")
        if not isinstance(chain, dict):
            raise ValueError(f"{path}: routine {routine['id']!r} missing daily_chain mapping")
        missing_chain = sorted(DAILY_CHAIN_KEYS - set(chain))
        if missing_chain:
            raise ValueError(
                f"{path}: routine {routine['id']!r} missing daily_chain keys: "
                f"{', '.join(missing_chain)}"
            )
        non_string_chain = sorted(
            key
            for key in DAILY_CHAIN_KEYS
            if not isinstance(chain.get(key), str) or not chain[key].strip()
        )
        if non_string_chain:
            raise ValueError(
                f"{path}: routine {routine['id']!r} daily_chain keys must be agent names: "
                f"{', '.join(non_string_chain)}"
            )
        validated.append(routine)

    for key in ("id", "title"):
        _require_unique([routine[key] for routine in validated], f"{path}: routine {key} values")
    _require_unique([f"{routine['app_id']}:{routine['routine_key']}" for routine in validated], f"{path}: app-scoped routine keys")
    _require_unique([f"{routine['app_id']}:{routine['platform']}" for routine in validated], f"{path}: app-scoped platforms")
    data["marker"] = marker
    return data


def _choose_local_source(project_key: str, filename: str, explicit: Path | None) -> Path:
    fallback = REPO_ROOT / "paperclips" / "projects" / project_key / filename
    if explicit is not None:
        if not explicit.is_file():
            raise ValueError(f"missing explicit {filename} source: {explicit}")
        return explicit
    operator = (
        Path.home()
        / ".paperclip"
        / "projects"
        / project_key
        / filename.replace(".local-example", "")
    )
    if operator.is_file():
        return operator
    if fallback.is_file():
        return fallback
    raise ValueError(f"missing {filename} source: {operator}")


def load_paths(project_key: str, paths_path: Path | None = None) -> dict[str, Any]:
    chosen = _choose_local_source(project_key, "paths.local-example.yaml", paths_path)
    data = yaml.safe_load(chosen.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{chosen}: paths source must be a mapping")
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
    return {str(key): str(value) for key, value in agents.items()}


def required_agent_names(config: dict[str, Any]) -> set[str]:
    names: set[str] = {"AUCEO"}
    for routine in config.get("routines", []):
        for key in ("dispatcher", "infra_executor", "pr_audit_coordinator"):
            value = routine.get(key)
            if isinstance(value, str):
                names.add(value)
        chain = routine.get("daily_chain")
        if isinstance(chain, dict):
            names.update(str(value) for value in chain.values() if isinstance(value, str))
    return names


def validate_config_agents(config: dict[str, Any], agent_ids: dict[str, str]) -> None:
    missing = sorted(required_agent_names(config) - set(agent_ids))
    if missing:
        raise ValueError(f"routine config references unknown agents: {', '.join(missing)}")


def normalize_current_routines(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("routines"), list):
        items = payload["routines"]
    elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload["data"]
    elif isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("id"), str):
        items = [payload]
    else:
        raise ValueError("routines API response must be a routine, list, or contain routines/data list")
    result = [item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)]
    live_ids = [str(item["id"]) for item in result]
    _require_unique(live_ids, "live routine ids")
    return result


def _description_identity(item: dict[str, Any], marker: str) -> dict[str, str]:
    description = item.get("description")
    if description is None:
        description = ""
    if not isinstance(description, str):
        raise ValueError(f"live routine {item.get('id')!r} description must be a string")
    lines = description.splitlines()
    values: dict[str, str] = {}
    relevant = marker in lines or any(line.startswith("routine_key") for line in lines)
    if not relevant:
        return values
    for field in IDENTITY_FIELDS:
        prefix = f"{field}: "
        malformed = [line for line in lines if line.startswith(field) and not line.startswith(prefix)]
        if malformed:
            raise ValueError(f"live routine {item.get('id')!r} has malformed {field} line")
        matches = [line[len(prefix):] for line in lines if line.startswith(prefix)]
        if len(matches) > 1:
            raise ValueError(f"live routine {item.get('id')!r} has duplicate {field} lines")
        if matches:
            values[field] = _single_line(matches[0], f"live routine {item.get('id')!r} {field}")
    return values


def render_description(config: dict[str, Any], routine: dict[str, Any], paths: dict[str, Any]) -> str:
    sources = {"paths": paths}
    repo_path = resolve(routine["repo_local_path_template"], sources)
    cursor_path = resolve(routine["cursor_path_template"], sources)
    return "\n".join(
        (
            config["marker"],
            f"app_id: {routine['app_id']}",
            f"routine_key: {routine['routine_key']}",
            f"platform: {routine['platform']}",
            f"branch: {routine['branch']}",
            f"repo: {repo_path}",
            f"cursor: {cursor_path}",
        )
    )


def _match_live_routine(
    config: dict[str, Any],
    routine: dict[str, Any],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    marker = config["marker"]
    identities = [(item, _description_identity(item, marker)) for item in current]
    by_key = [item for item, identity in identities if identity.get("routine_key") == routine["routine_key"] and identity.get("app_id") in (None, routine["app_id"])]
    if len(by_key) > 1:
        raise ValueError(f"routine key {routine['routine_key']!r} matches multiple live routines")
    if by_key:
        identity = next(identity for item, identity in identities if item is by_key[0])
        if identity.get("app_id") not in (None, routine["app_id"]) or identity.get("platform") != routine["platform"]:
            raise ValueError(
                f"routine key {routine['routine_key']!r} has conflicting platform identity"
            )
        return by_key[0]

    fallback_base: list[tuple[dict[str, Any], dict[str, str]]] = []
    for item, identity in identities:
        description = item.get("description") or ""
        lines = description.splitlines() if isinstance(description, str) else []
        if (
            item.get("title") == routine["title"]
            and marker in lines
            and identity.get("platform") == routine["platform"]
        ):
            fallback_base.append((item, identity))
    conflicting = [
        item
        for item, identity in fallback_base
        if identity.get("routine_key") not in (None, routine["routine_key"])
    ]
    if conflicting:
        raise ValueError(
            f"routine {routine['id']!r} fallback candidate has conflicting routine_key"
        )
    fallback = [item for item, identity in fallback_base if "routine_key" not in identity]
    if not fallback:
        raise ValueError(f"routine {routine['id']!r} not found; creation is not implicit")
    if len(fallback) > 1:
        raise ValueError(f"routine {routine['id']!r} fallback is ambiguous")
    return fallback[0]


def _plan_one(
    config: dict[str, Any],
    routine: dict[str, Any],
    agent_ids: dict[str, str],
    paths: dict[str, Any],
    current: list[dict[str, Any]],
) -> dict[str, Any]:
    current_item = _match_live_routine(config, routine, current)
    live_uuid = _single_line(current_item.get("id"), f"routine {routine['id']!r} live id")
    live_revision = _single_line(
        current_item.get("latestRevisionId") or current_item.get("latest_revision_id"),
        f"routine {routine['id']!r} latestRevisionId",
    )
    dispatcher = routine["dispatcher"]
    desired_assignee = agent_ids[dispatcher]
    current_assignee = current_item.get("assigneeAgentId") or current_item.get("assignee_agent_id")
    desired_description = render_description(config, routine, paths)
    current_description = current_item.get("description") or ""
    patch: dict[str, Any] = {}
    if current_assignee != desired_assignee:
        patch["assigneeAgentId"] = desired_assignee
    if current_description != desired_description:
        patch["description"] = desired_description
    if patch:
        patch["baseRevisionId"] = live_revision
    return {
        "routine_id": routine["id"],
        "app_id": routine["app_id"],
        "routine_key": routine["routine_key"],
        "platform": routine["platform"],
        "dispatcher": dispatcher,
        "live_uuid": live_uuid,
        "live_revision_id": live_revision,
        "current_assigneeAgentId": current_assignee,
        "desired_assigneeAgentId": desired_assignee,
        "current_description": current_description,
        "desired_description": desired_description,
        "patch": patch,
        "needs_update": bool(patch),
    }


def build_plan(
    config: dict[str, Any],
    agent_ids: dict[str, str],
    current: list[dict[str, Any]],
    paths: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chosen_paths = paths if paths is not None else load_paths(str(config.get("project") or "uaudit"))
    plan = [
        _plan_one(config, routine, agent_ids, chosen_paths, current)
        for routine in config["routines"]
    ]
    _require_unique([item["live_uuid"] for item in plan], "matched live routine ids")
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
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "uaudit-routine-reconcile/2.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"{method} {url} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw) if raw else {}


def _config_for_routine(config: dict[str, Any], routine_id: str) -> dict[str, Any]:
    routine = next(item for item in config["routines"] if item["id"] == routine_id)
    return {**config, "routines": [routine]}


def apply_plan(
    api_url: str,
    token: str,
    config: dict[str, Any],
    agent_ids: dict[str, str],
    paths: dict[str, Any],
    plan: list[dict[str, Any]],
    request: Callable[[str, str, str, dict[str, Any] | None], Any] = request_json,
) -> tuple[dict[str, Any], bool]:
    result: dict[str, list[dict[str, Any]]] = {
        "updated": [],
        "unchanged": [],
        "failed": [],
        "not_attempted": [],
    }
    pending = [item for item in plan if item["needs_update"]]
    result["unchanged"].extend(
        {"routine_id": item["routine_id"], "live_uuid": item["live_uuid"]}
        for item in plan
        if not item["needs_update"]
    )
    base_url = api_url.rstrip("/")
    for index, initial in enumerate(pending):
        endpoint = f"{base_url}/api/routines/{initial['live_uuid']}"
        try:
            fresh_payload = request("GET", endpoint, token, None)
            fresh = normalize_current_routines(fresh_payload)
            one_config = _config_for_routine(config, initial["routine_id"])
            fresh_item = build_plan(one_config, agent_ids, fresh, paths)[0]
            if fresh_item["live_uuid"] != initial["live_uuid"]:
                raise ValueError("fresh routine identity resolved to a different live UUID")
            if not fresh_item["needs_update"]:
                result["unchanged"].append(
                    {"routine_id": fresh_item["routine_id"], "live_uuid": fresh_item["live_uuid"]}
                )
                continue
            request("PATCH", endpoint, token, fresh_item["patch"])
            verified_payload = request("GET", endpoint, token, None)
            verified = build_plan(
                one_config,
                agent_ids,
                normalize_current_routines(verified_payload),
                paths,
            )[0]
            if verified["needs_update"]:
                raise RuntimeError("post-write GET still reports routine drift")
            result["updated"].append(
                {
                    "routine_id": verified["routine_id"],
                    "live_uuid": verified["live_uuid"],
                    "revision_id": verified["live_revision_id"],
                }
            )
        except Exception as exc:
            result["failed"].append(
                {
                    "routine_id": initial["routine_id"],
                    "live_uuid": initial["live_uuid"],
                    "error": str(exc),
                }
            )
            result["not_attempted"].extend(
                {
                    "routine_id": remaining["routine_id"],
                    "live_uuid": remaining["live_uuid"],
                }
                for remaining in pending[index + 1:]
            )
            return result, False
    return result, True


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
        validate_config_agents(config, agent_ids)
        paths = load_paths(args.project_key, args.paths)

        company_id = args.company_id
        token = None
        if args.current_routines_json:
            current_payload = json.loads(args.current_routines_json.read_text())
        else:
            if not company_id:
                fallback_bindings = yaml.safe_load(
                    (REPO_ROOT / "paperclips/projects/uaudit/bindings.local-example.yaml").read_text()
                )
                company_id = (
                    fallback_bindings.get("company_id")
                    if isinstance(fallback_bindings, dict)
                    else None
                )
            if not company_id:
                raise ValueError("--company-id is required when reading live routines")
            token = resolve_token(args.api_url, args.auth_json)
            current_payload = request_json(
                "GET",
                f"{args.api_url.rstrip('/')}/api/companies/{company_id}/routines",
                token,
            )

        current = normalize_current_routines(current_payload)
        plan = build_plan(config, agent_ids, current, paths)
        result: dict[str, Any] = {
            "mode": "apply" if args.apply else "dry-run",
            "company_id": company_id,
            "updates": plan,
        }

        success = True
        if args.apply:
            if args.current_routines_json:
                raise ValueError("--apply cannot be used with --current-routines-json")
            if token is None:
                token = resolve_token(args.api_url, args.auth_json)
            result["apply"], success = apply_plan(
                args.api_url,
                token,
                config,
                agent_ids,
                paths,
                plan,
            )

        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if success else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
