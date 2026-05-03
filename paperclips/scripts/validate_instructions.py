#!/usr/bin/env python3
"""Validate Paperclip instruction profile metadata without slimming bundles."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class RoleMeta:
    target: str
    role_id: str
    family: str
    profiles: list[str]


def parse_inline_list(value: str) -> list[str]:
    value = value.strip()
    if not value.startswith("[") or not value.endswith("]"):
        return [value] if value else []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("\"'") for item in inner.split(",")]


def clean_line(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def load_role_front_matter(path: Path) -> RoleMeta:
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: missing YAML front matter")

    data: dict[str, str] = {}
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end_index = index
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()

    if end_index is None:
        raise ValueError(f"{path}: unterminated YAML front matter")

    required = ["target", "role_id", "family", "profiles"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path}: missing front matter keys: {', '.join(missing)}")

    return RoleMeta(
        target=data["target"],
        role_id=data["role_id"],
        family=data["family"],
        profiles=parse_inline_list(data["profiles"]),
    )


def load_profiles_manifest(path: Path) -> dict[str, dict[str, list[str]]]:
    profiles: dict[str, dict[str, list[str]]] = {}
    current_profile: str | None = None
    current_key: str | None = None

    for raw_line in path.read_text().splitlines():
        line = clean_line(raw_line)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if text == "profiles:":
            continue
        if indent == 2 and text.endswith(":"):
            current_profile = text[:-1]
            profiles[current_profile] = {}
            current_key = None
            continue
        if current_profile is None:
            continue
        if indent == 4 and text.endswith(":"):
            current_key = text[:-1]
            profiles[current_profile][current_key] = []
            continue
        if indent == 4 and ":" in text:
            key, value = text.split(":", 1)
            profiles[current_profile][key.strip()] = value.strip().strip("\"'")
            current_key = None
            continue
        if indent == 6 and text.startswith("- ") and current_key:
            profiles[current_profile][current_key].append(text[2:].strip())

    return profiles


def load_coverage_matrix(path: Path) -> dict[str, dict]:
    matrix: dict[str, dict] = {"roles": {}, "rules": {}}
    section: str | None = None
    current_item: str | None = None
    current_list_key: str | None = None

    for raw_line in path.read_text().splitlines():
        line = clean_line(raw_line)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()

        if indent == 0 and text in {"roles:", "rules:"}:
            section = text[:-1]
            current_item = None
            current_list_key = None
            continue
        if section is None:
            continue
        if indent == 2 and text.endswith(":"):
            current_item = text[:-1]
            matrix[section][current_item] = {}
            current_list_key = None
            continue
        if current_item is None:
            continue
        if indent == 4 and ":" in text:
            key, value = text.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                matrix[section][current_item][key] = []
                current_list_key = key
            elif value.startswith("["):
                matrix[section][current_item][key] = parse_inline_list(value)
                current_list_key = None
            else:
                matrix[section][current_item][key] = value.strip("\"'")
                current_list_key = None
            continue
        if indent == 6 and text.startswith("- ") and current_list_key:
            matrix[section][current_item][current_list_key].append(text[2:].strip())

    return matrix


def token_estimate(byte_count: int) -> int:
    return (byte_count + 3) // 4


def validate(repo_root: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []
    paperclips = repo_root / "paperclips"
    profiles_path = paperclips / "instruction-profiles.yaml"
    matrix_path = paperclips / "instruction-coverage.matrix.yaml"
    baseline_path = paperclips / "bundle-size-baseline.json"
    allowlist_path = paperclips / "bundle-size-allowlist.json"

    for required_path in [profiles_path, matrix_path, baseline_path, allowlist_path]:
        if not required_path.is_file():
            errors.append(f"missing required file: {required_path.relative_to(repo_root)}")
    if errors:
        return errors

    profiles = load_profiles_manifest(profiles_path)
    matrix = load_coverage_matrix(matrix_path)

    if not profiles:
        errors.append("instruction-profiles.yaml has no profiles")

    for profile_name, profile_data in profiles.items():
        fragments = profile_data.get("fragments", [])
        empty_allowed = profile_data.get("empty_allowed") == "true"
        if not fragments and not empty_allowed:
            errors.append(f"profile has no fragments: {profile_name}")
        for fragment in fragments:
            fragment_path = repo_root / fragment
            if not fragment_path.is_file():
                errors.append(f"profile {profile_name} references missing fragment: {fragment}")
        runbooks = profile_data.get("runbooks", [])
        if runbooks and profile_data.get("inline_rule_required") != "true":
            errors.append(
                f"profile {profile_name} has runbooks but does not require inline rules"
            )
        for runbook in runbooks:
            runbook_path = repo_root / runbook
            if not runbook_path.is_file():
                errors.append(f"profile {profile_name} references missing runbook: {runbook}")

    role_sources_seen: set[Path] = set()
    for role_id, role in matrix.get("roles", {}).items():
        source = role.get("source")
        if not source:
            errors.append(f"matrix role missing source: {role_id}")
            continue
        source_path = repo_root / source
        if not source_path.is_file():
            errors.append(f"matrix role {role_id} source missing: {source}")
            continue
        role_sources_seen.add(source_path)
        try:
            metadata = load_role_front_matter(source_path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if metadata.role_id != role_id:
            errors.append(f"{source}: role_id {metadata.role_id} != matrix id {role_id}")
        if metadata.target != role.get("target"):
            errors.append(f"{source}: target mismatch with matrix")
        if metadata.family != role.get("family"):
            errors.append(f"{source}: family mismatch with matrix")
        if metadata.profiles != role.get("profiles"):
            errors.append(f"{source}: profiles mismatch with matrix")
        expected_prefix = f"{metadata.target}:"
        if not metadata.role_id.startswith(expected_prefix):
            errors.append(f"{source}: role_id must start with {expected_prefix}")
        for profile in metadata.profiles:
            if profile not in profiles:
                errors.append(f"{source}: unknown profile {profile}")

    for role_dir in [paperclips / "roles", paperclips / "roles-codex"]:
        for source_path in sorted(role_dir.glob("*.md")):
            if source_path not in role_sources_seen:
                errors.append(f"role file missing from matrix: {source_path.relative_to(repo_root)}")

    role_ids = set(matrix.get("roles", {}))
    for rule_id, rule in matrix.get("rules", {}).items():
        for profile in rule.get("required_profiles", []):
            if profile not in profiles:
                errors.append(f"rule {rule_id} references unknown profile: {profile}")
        rule_role_ids = rule.get("role_ids")
        if rule_role_ids != "all":
            for role_id in rule_role_ids or []:
                if role_id not in role_ids:
                    errors.append(f"rule {rule_id} references unknown role: {role_id}")
        if not rule.get("markers"):
            errors.append(f"rule {rule_id} has no validation markers")

    try:
        baseline = json.loads(baseline_path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"invalid bundle-size-baseline.json: {exc}")
        baseline = {"bundles": []}

    try:
        allowlist = json.loads(allowlist_path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"invalid bundle-size-allowlist.json: {exc}")
        allowlist = {"entries": []}
    if "entries" not in allowlist:
        errors.append("bundle-size-allowlist.json missing entries")

    bundle_paths_by_role: dict[str, Path] = {}
    for bundle in baseline.get("bundles", []):
        role_id = bundle.get("roleId")
        if role_id not in role_ids:
            errors.append(f"baseline references unknown role: {role_id}")
        path = bundle.get("path")
        if not path:
            errors.append(f"baseline bundle missing path for role: {role_id}")
            continue
        bundle_path = repo_root / path
        if not bundle_path.is_file():
            errors.append(f"baseline bundle missing generated file: {path}")
            continue
        if role_id:
            bundle_paths_by_role[role_id] = bundle_path
        text = bundle_path.read_text()
        if text.startswith("---\n"):
            errors.append(f"generated bundle contains front matter: {path}")
        byte_count = len(text.encode("utf-8"))
        line_count = text.count("\n")
        bundle_tokens = token_estimate(byte_count)
        if bundle.get("bytes") != byte_count:
            errors.append(f"baseline byte mismatch for {path}: {bundle.get('bytes')} != {byte_count}")
        if bundle.get("lines") != line_count:
            errors.append(f"baseline line mismatch for {path}: {bundle.get('lines')} != {line_count}")
        if bundle.get("tokenEstimate") != bundle_tokens:
            errors.append(
                f"baseline token mismatch for {path}: {bundle.get('tokenEstimate')} != {bundle_tokens}"
            )

    for rule_id, rule in matrix.get("rules", {}).items():
        rule_role_ids = role_ids if rule.get("role_ids") == "all" else set(rule.get("role_ids", []))
        markers = [str(marker).lower() for marker in rule.get("markers", [])]
        for role_id in rule_role_ids:
            bundle_path = bundle_paths_by_role.get(role_id)
            if bundle_path is None:
                errors.append(f"rule {rule_id} cannot find generated bundle for role: {role_id}")
                continue
            bundle_text = bundle_path.read_text().lower()
            for marker in markers:
                if marker not in bundle_text:
                    errors.append(
                        f"rule {rule_id} marker missing for {role_id}: {marker}"
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args()

    errors = validate(Path(args.repo_root).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Paperclip instruction validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
