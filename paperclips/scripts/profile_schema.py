"""Profile YAML schema for UAA Phase B.

Stdlib-only + pyyaml. Validates the 8 profiles in
paperclips/fragments/profiles/*.yaml per spec §5.2.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed; run `pip install pyyaml`", file=sys.stderr)
    raise

ALLOWED_KEYS = {
    "schemaVersion", "name", "inheritsUniversal", "extends", "includes",
    "description",  # documentation; not used by builder
    "empty_allowed",  # compat with legacy instruction-profiles.yaml format
    "fragments",  # compat with legacy format (alternative to includes)
}
SUPPORTED_SCHEMA_VERSION = 2


class ProfileSchemaError(Exception):
    pass


def load_profile(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ProfileSchemaError(f"{path}: root must be a mapping")
    return validate_profile(raw)


def validate_profile(raw: dict[str, Any]) -> dict[str, Any]:
    if "name" not in raw:
        raise ProfileSchemaError("missing required key: name")
    if not isinstance(raw["name"], str) or not raw["name"]:
        raise ProfileSchemaError("name must be non-empty string")
    if raw.get("schemaVersion") != SUPPORTED_SCHEMA_VERSION:
        raise ProfileSchemaError(
            f"schemaVersion must be {SUPPORTED_SCHEMA_VERSION}, got {raw.get('schemaVersion')!r}"
        )
    unknown = set(raw.keys()) - ALLOWED_KEYS
    if unknown:
        raise ProfileSchemaError(f"unknown keys: {sorted(unknown)}")

    out: dict[str, Any] = dict(raw)
    out.setdefault("inheritsUniversal", True)
    out.setdefault("extends", None)
    out.setdefault("includes", [])

    if not isinstance(out["inheritsUniversal"], bool):
        raise ProfileSchemaError("inheritsUniversal must be bool")
    if out["extends"] is not None and not isinstance(out["extends"], str):
        raise ProfileSchemaError("extends must be string (profile name) or null")
    if not isinstance(out["includes"], list):
        raise ProfileSchemaError("includes must be a list")
    for inc in out["includes"]:
        if not isinstance(inc, str):
            raise ProfileSchemaError(f"includes entry must be string, got {type(inc).__name__}")
        if "/" not in inc:
            raise ProfileSchemaError(f"includes entry must be subdir/file.md form, got {inc!r}")

    return out


def resolve_extends_chain(
    profile: dict[str, Any], all_profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return list of profiles in extends-resolution order: [base, ..., this].

    Raises ProfileSchemaError on cycles or unknown parent.
    """
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur: dict[str, Any] | None = profile
    while cur is not None:
        if cur["name"] in seen:
            raise ProfileSchemaError(f"extends cycle detected: {cur['name']}")
        seen.add(cur["name"])
        chain.append(cur)
        parent_name = cur.get("extends")
        if parent_name is None:
            break
        if parent_name not in all_profiles:
            raise ProfileSchemaError(
                f"profile {cur['name']!r} extends unknown profile {parent_name!r}",
            )
        cur = all_profiles[parent_name]
    return list(reversed(chain))


def load_all_profiles(profiles_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all *.yaml files in profiles_dir as validated profile dicts."""
    return {p.stem: load_profile(p) for p in profiles_dir.glob("*.yaml")}
