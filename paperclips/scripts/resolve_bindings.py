"""UAA Phase D: dual-read resolver — bindings.yaml (new) + codex-agent-ids.env (legacy).

Precedence: new (bindings.yaml) > legacy (env). Conflicts emit BindingsConflictWarning.
"""
from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path
from typing import Any

import yaml

# D-fix IMP-D1: parity with shell-side validate_project_key (lib/_common.sh).
_PROJECT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class BindingsConflictWarning(UserWarning):
    """Emitted when same agent has different UUID in legacy vs new source."""

    pass


def _load_acronyms() -> frozenset[str]:
    """Read shared canonical-acronyms list from lib/canonical_acronyms.txt.

    Same source-of-truth consumed by migrate-bindings.sh; prevents drift between
    Python normalization and bash camelization (Phase D deep-review CRIT-C-4).
    """
    p = Path(__file__).resolve().parent / "lib" / "canonical_acronyms.txt"
    if not p.is_file():
        # Fallback to embedded list if file removed/missing — keeps unit-test
        # discoverability and never silently produces wrong names.
        return frozenset({"CTO", "CEO", "QA", "MCP", "CR", "API", "URL", "UUID"})
    return frozenset(
        line.strip() for line in p.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


_PRESERVED_ACRONYMS = _load_acronyms()


def _normalize_legacy_name(env_var: str) -> str:
    """CX_PYTHON_ENGINEER_AGENT_ID → CXPythonEngineer.

    Output MUST match canonical names in services/watchdog/src/gimle_watchdog/role_taxonomy.py
    (entries like CXCTO, CXMCPEngineer, CXQAEngineer preserve acronym case; entries
    like CXPythonEngineer, CXCodeReviewer use PascalCase).
    """
    name = env_var
    if name.endswith("_AGENT_ID"):
        name = name[: -len("_AGENT_ID")]
    parts = name.split("_")
    if not parts:
        return name

    prefix = ""
    rest = parts
    if parts[0] == "CX":
        prefix = "CX"
        rest = parts[1:]
    elif parts[0] == "CODEX":
        prefix = "Codex"
        rest = parts[1:]

    out_parts: list[str] = []
    for p in rest:
        if p in _PRESERVED_ACRONYMS:
            out_parts.append(p)
        else:
            out_parts.append(p.capitalize())
    return prefix + "".join(out_parts)


def _read_legacy_env(path: Path) -> dict[str, str]:
    """Parse legacy KEY=VALUE env file → {canonical_agent_name: uuid}."""
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key.endswith("_AGENT_ID"):
            continue
        if not value:
            continue
        canonical = _normalize_legacy_name(key)
        out[canonical] = value
    return out


def _read_bindings_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: root must be mapping")
    agents = raw.get("agents", {})
    if not isinstance(agents, dict):
        raise ValueError(f"{path}: agents must be mapping")
    return {"company_id": raw.get("company_id"), "agents": agents}


def resolve_all(
    *,
    legacy_env_path: Path | None,
    bindings_yaml_path: Path | None,
) -> dict[str, Any]:
    """Merge sources. Bindings precedence > legacy. Conflicts warned but bindings wins.

    Returns dict with keys: company_id, agents, sources_used, conflicts.
    """
    sources_used: list[str] = []
    conflicts: list[dict[str, str]] = []

    legacy: dict[str, str] = {}
    if legacy_env_path is not None and legacy_env_path.is_file():
        legacy = _read_legacy_env(legacy_env_path)
        sources_used.append("legacy")

    bindings: dict[str, Any] = {"company_id": None, "agents": {}}
    if bindings_yaml_path is not None and bindings_yaml_path.is_file():
        bindings = _read_bindings_yaml(bindings_yaml_path)
        sources_used.append("bindings")

    if not sources_used:
        raise FileNotFoundError(
            f"no sources available (legacy={legacy_env_path}, bindings={bindings_yaml_path})"
        )

    merged: dict[str, str] = dict(legacy)
    for name, uuid in bindings["agents"].items():
        if name in merged and merged[name] != uuid:
            conflicts.append(
                {"agent": name, "legacy": merged[name], "bindings": uuid}
            )
            warnings.warn(
                f"conflict for agent {name!r}: legacy={merged[name]!r}, bindings={uuid!r}; "
                f"using bindings value (resolve via cleanup gate per spec §10.5)",
                BindingsConflictWarning,
                stacklevel=2,
            )
        merged[name] = uuid

    return {
        "company_id": bindings.get("company_id"),
        "agents": merged,
        "sources_used": sources_used,
        "conflicts": conflicts,
    }


def resolve_one(
    *,
    agent_name: str,
    legacy_env_path: Path | None = None,
    bindings_yaml_path: Path | None = None,
) -> str | None:
    """Return UUID for agent_name, or None if not found in any source."""
    try:
        result = resolve_all(legacy_env_path=legacy_env_path, bindings_yaml_path=bindings_yaml_path)
    except FileNotFoundError:
        return None
    return result["agents"].get(agent_name)


def main() -> int:
    """CLI: print UUID for agent_name, or full JSON if --agent-name omitted."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="UAA dual-read bindings resolver")
    parser.add_argument("project_key")
    parser.add_argument("--agent-name", required=False, help="single-agent lookup")
    parser.add_argument("--legacy-env", help="path to legacy codex-agent-ids.env")
    parser.add_argument("--bindings", help="path to ~/.paperclip/projects/<key>/bindings.yaml")
    args = parser.parse_args()

    # D-fix IMP-D1: reject path-traversal / non-canonical project keys before
    # any filesystem use. Matches shell-side validate_project_key in _common.sh.
    if not _PROJECT_KEY_RE.fullmatch(args.project_key):
        parser.error(
            f"invalid project_key: {args.project_key!r} "
            f"(must match {_PROJECT_KEY_RE.pattern})"
        )

    repo_root = Path.cwd()
    home = Path.home()

    legacy: Path | None
    if args.legacy_env:
        legacy = Path(args.legacy_env)
    elif args.project_key == "gimle":
        legacy = repo_root / "paperclips" / "codex-agent-ids.env"
    else:
        legacy = None

    bindings = Path(args.bindings) if args.bindings else (
        home / ".paperclip" / "projects" / args.project_key / "bindings.yaml"
    )

    try:
        result = resolve_all(legacy_env_path=legacy, bindings_yaml_path=bindings)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.agent_name:
        uuid = result["agents"].get(args.agent_name)
        if uuid is None:
            print(f"ERROR: agent {args.agent_name!r} not found", file=sys.stderr)
            return 1
        print(uuid)
    else:
        print(json.dumps(result, indent=2, default=str))

    if result["conflicts"]:
        print(
            f"WARNING: {len(result['conflicts'])} bindings conflicts (see stderr)",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
