#!/usr/bin/env python3
"""Validate Paperclip instruction profile metadata without slimming bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

# Stable handoff markers required in every generated role bundle (per
# docs/superpowers/specs/2026-05-08-handoff-assign-rules-unification.md
# acceptance #3).
REQUIRED_HANDOFF_MARKERS = (
    "paperclip:handoff-contract:v2",
    "paperclip:handoff-exit-shapes:v1",
    "paperclip:handoff-verify-status-assignee:v1",
    "paperclip:team-local-roster:v1",
)

REQUIRED_PROJECT_MCP = (
    "codebase-memory",
    "context7",
    "serena",
    "github",
    "sequential-thinking",
)

REQUIRED_PROJECT_MANIFEST_SECTIONS = (
    "project",
    "domain",
    "evidence",
    "paths",
    "mcp",
    "skills",
    "subagents",
    "targets",
    "compatibility",
)

REQUIRED_PROJECT_MANIFEST_KEYS = {
    "project": ("key", "display_name", "issue_prefix", "company_id", "integration_branch", "specs_dir", "plans_dir"),
    "domain": ("wallet_target_short", "wallet_target_name", "wallet_target_slug"),
    "evidence": (
        "merge_without_smoke_issue",
        "graphiti_mock_issue",
        "release_reset_issue",
        "asyncmock_driver_issue",
        "worktree_discipline_issue_pair",
        "qa_worktree_discipline_issue",
        "mcp_wire_contract_issue",
        "qa_deploy_checklist_issue",
        "review_scope_drift_issue",
        "qa_to_cto_stall_issue",
        "handoff_flake_issue",
        "pre_slim_baseline_issue",
        "cr_to_pe_stall_issue",
        "handoff_misclassified_issue",
        "post_merge_stall_issue",
    ),
    "paths": (
        "project_root",
        "primary_repo_root",
        "primary_mcp_service_dir",
        "production_checkout",
        "codex_team_root",
        "operator_memory_dir",
        "overlay_root",
        "project_rules_file",
    ),
    "mcp": ("service_name", "package_name", "tool_namespace"),
}

REQUIRED_COMPATIBILITY_PATH_KEYS = (
    "claude_deploy_mapping",
    "codex_agent_ids_env",
    "workspace_update_script",
)

# Anti-pattern markers — a foreign-team UUID inside a section/line marked
# as anti-pattern (e.g., the routing-rule lookup table in agent-roster)
# is allowed; only actionable foreign UUIDs are flagged.
_ANTIPATTERN_LINE_TOKENS = ("❌", "WRONG", "NOT", "NEVER", "forbidden", "anti-pattern", "antipattern", "do not use")
_ANTIPATTERN_HEADER_TOKENS = ("not example", "wrong", "anti-pattern", "antipattern", "routing rule", "forbidden")

_UUID_RE = re.compile(r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b")
_UNRESOLVED_VARIABLE_RE = re.compile(r"\{\{[^}\n]+\}\}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_team_uuids(
    repo_root: Path,
    allowed_company_ids: "set[str] | None" = None,
) -> dict[str, set[str]]:
    """Return {'claude': {uuid, ...}, 'codex': {uuid, ...}}.

    Phase D dual-read sources:
      - Claude:  paperclips/deploy-agents.sh (case-statement uuids; legacy).
      - Codex:   paperclips/codex-agent-ids.env (legacy KEY=uuid env file)
                 + ~/.paperclip/projects/<key>/bindings.yaml (new — for every
                   project that has been bootstrapped). resolve_bindings handles
                   precedence + conflict warnings.

    D-fix C-2: when ``allowed_company_ids`` is provided, only include UUIDs from
    bindings whose ``company_id`` is in the set. This prevents watchdog from
    conflating UUIDs across trading/uaudit/gimle when running for a single
    company. When None (legacy behavior), iterate every project subdir.
    """
    teams: dict[str, set[str]] = {"claude": set(), "codex": set()}

    # --- Claude: legacy deploy-agents.sh (no bindings.yaml equivalent yet) ---
    deploy_sh = repo_root / "paperclips" / "deploy-agents.sh"
    if deploy_sh.is_file():
        case_re = re.compile(r'^\s*[a-z][\w-]*\)\s+echo\s+"([0-9a-f-]{36})"', re.MULTILINE)
        teams["claude"].update(case_re.findall(deploy_sh.read_text()))

    # --- Codex: dual-read via resolver -------------------------------------
    legacy_env = repo_root / "paperclips" / "codex-agent-ids.env"
    home_projects = Path.home() / ".paperclip" / "projects"

    # Import resolver via importlib (validate_instructions is itself loaded by
    # absolute path from the watchdog, so the surrounding `paperclips.scripts`
    # package may not be on sys.path). Resolve sibling-of-this-file, not
    # repo_root, so callers passing a synthetic repo_root (tests) still find it.
    import importlib.util

    resolver_path = Path(__file__).resolve().parent / "resolve_bindings.py"
    resolve_all = None
    if resolver_path.is_file():
        # D-fix I7: dedupe via sys.modules so repeated calls reuse the same
        # module object (prevents duplicate BindingsConflictWarning classes
        # under multi-tick watchdog runs).
        cached_mod = sys.modules.get("_phase_d_resolve_bindings")
        if cached_mod is not None:
            resolve_all = getattr(cached_mod, "resolve_all", None)
        else:
            spec = importlib.util.spec_from_file_location(
                "_phase_d_resolve_bindings", resolver_path
            )
            if spec is not None and spec.loader is not None:
                try:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules["_phase_d_resolve_bindings"] = mod
                    spec.loader.exec_module(mod)
                    resolve_all = mod.resolve_all
                except Exception:
                    sys.modules.pop("_phase_d_resolve_bindings", None)
                    resolve_all = None

    if resolve_all is None:
        # Fallback: legacy env only (preserves pre-Phase-D behavior).
        if legacy_env.is_file():
            for line in legacy_env.read_text().splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                _, val = stripped.split("=", 1)
                uuid_match = _UUID_RE.fullmatch(val.strip())
                if uuid_match:
                    teams["codex"].add(uuid_match.group(1))
        return teams

    # Resolver available: gather UUIDs from per-project bindings + legacy env.
    project_dirs: list[Path] = []
    if home_projects.is_dir():
        project_dirs = [p for p in home_projects.iterdir() if p.is_dir()]

    if not project_dirs and legacy_env.is_file():
        # Pre-Phase-E: no per-project bindings yet, only legacy env exists.
        try:
            data = resolve_all(legacy_env_path=legacy_env, bindings_yaml_path=None)
            for uuid in data["agents"].values():
                if _UUID_RE.fullmatch(uuid) or len(uuid) >= 8:
                    teams["codex"].add(uuid)
        except FileNotFoundError:
            pass
        return teams

    for project_dir in project_dirs:
        bindings = project_dir / "bindings.yaml"
        legacy_for_project = legacy_env if project_dir.name == "gimle" else None
        if not bindings.is_file() and legacy_for_project is None:
            continue
        try:
            data = resolve_all(
                legacy_env_path=legacy_for_project,
                bindings_yaml_path=bindings if bindings.is_file() else None,
            )
        except FileNotFoundError:
            continue
        # D-fix C-2: scope per company_id when caller supplied a filter, so a
        # gimle watchdog cannot accidentally allowlist trading/uaudit UUIDs.
        if allowed_company_ids is not None:
            this_company = data.get("company_id")
            # Pre-Phase-E gimle has no company_id in legacy-only mode; skip filter
            # only if we have NO id to compare (legacy-only path), otherwise enforce.
            if this_company is not None and this_company not in allowed_company_ids:
                continue
        # Codex bucket — Phase D treats every bindings UUID as codex by default,
        # because the only currently-migrated path is the codex env file. Phase
        # E/F will introduce per-agent target metadata.
        for uuid in data["agents"].values():
            # D-fix C-3: enforce full UUID format. The 'len >= 8' fallback
            # let any 8+ char string into the watchdog allowlist — security gap.
            if uuid and _UUID_RE.fullmatch(uuid):
                teams["codex"].add(uuid)

    return teams


def _is_antipattern_context(text: str, position: int) -> bool:
    """True if `position` is inside a section or line clearly labeled as
    anti-pattern (foreign-team examples allowed there).
    """
    line_start = text.rfind("\n", 0, position) + 1
    line_end_idx = text.find("\n", position)
    line_end = len(text) if line_end_idx == -1 else line_end_idx
    line = text[line_start:line_end].lower()
    for token in _ANTIPATTERN_LINE_TOKENS:
        if token.lower() in line:
            return True

    # Check headers in the recent 2 KB looking back — if the closest header
    # is anti-pattern flavored, the context is anti-pattern too.
    window_start = max(0, position - 2048)
    window = text[window_start:position]
    headers = list(re.finditer(r"^#{1,6} .*$", window, re.MULTILINE))
    if headers:
        last_header = headers[-1].group(0).lower()
        for token in _ANTIPATTERN_HEADER_TOKENS:
            if token in last_header:
                return True

    return False


def validate_handoff_markers(
    bundle_paths_by_role: dict[str, Path],
    repo_root: Path,
) -> list[str]:
    """Bundles that include the phase-handoff fragment must contain all 4 stable markers.

    Trigger: presence of the heading `## Phase handoff discipline (iron rule)`.
    Roles that don't participate in plan-phase handoffs (writers, research) skip the check.
    """
    errors: list[str] = []
    trigger = "## Phase handoff discipline (iron rule)"
    for role_id, bundle_path in bundle_paths_by_role.items():
        try:
            text = bundle_path.read_text()
        except OSError:
            continue
        if trigger not in text:
            continue
        for marker in REQUIRED_HANDOFF_MARKERS:
            if marker not in text:
                errors.append(
                    f"handoff marker missing for {role_id} ({bundle_path.relative_to(repo_root)}): {marker}"
                )
    return errors


def validate_project_capability_manifests(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifests = sorted((repo_root / "paperclips" / "projects").glob("*/paperclip-agent-assembly.yaml"))
    if not manifests:
        return errors

    for manifest in manifests:
        text = manifest.read_text()
        rel = manifest.relative_to(repo_root)
        is_template = "_template" in manifest.parts
        for section in REQUIRED_PROJECT_MANIFEST_SECTIONS:
            if not re.search(rf"^{re.escape(section)}:\s*$", text, re.MULTILINE):
                errors.append(f"project manifest missing {section} section: {rel}")
        if not is_template and re.search(r"<[^>\n]+>", text):
            errors.append(f"project manifest contains unresolved placeholder: {rel}")
        for section, keys in REQUIRED_PROJECT_MANIFEST_KEYS.items():
            if not re.search(rf"^{re.escape(section)}:\s*$", text, re.MULTILINE):
                continue
            for key in keys:
                if not re.search(rf"^\s{{2}}{re.escape(key)}:\s+\S", text, re.MULTILINE):
                    errors.append(f"project manifest missing {section}.{key}: {rel}")
        if "mcp:" not in text:
            errors.append(f"project manifest missing mcp section: {rel}")
            continue
        if "base_required:" not in text:
            errors.append(f"project manifest missing mcp.base_required: {rel}")
            continue
        if not re.search(r"^\s{4}primary:\s+\S", text, re.MULTILINE):
            errors.append(f"project manifest missing mcp.codebase_memory_projects.primary: {rel}")
        for marker in REQUIRED_PROJECT_MCP:
            if not re.search(rf"^\s*-\s+{re.escape(marker)}\s*$", text, re.MULTILINE):
                errors.append(f"project manifest missing base MCP {marker}: {rel}")
        for section in ("mcp", "skills", "subagents"):
            if f"{section}:" not in text:
                continue
            if not re.search(rf"^{re.escape(section)}:\n(?:^[ \t].*\n)*?^\s{{2}}additions:\s*$", text, re.MULTILINE):
                errors.append(f"project manifest missing {section}.additions: {rel}")
            if not re.search(rf"^{re.escape(section)}:\n(?:^[ \t].*\n)*?^\s{{4}}project:\s*(?:\[\])?\s*$", text, re.MULTILINE):
                errors.append(f"project manifest missing {section}.additions.project: {rel}")
            if not re.search(rf"^{re.escape(section)}:\n(?:^[ \t].*\n)*?^\s{{4}}by_role:\s*(?:\{{\}})?\s*$", text, re.MULTILINE):
                errors.append(f"project manifest missing {section}.additions.by_role: {rel}")
        declared_target_count = 0
        for target, adapter_type in [("claude", "claude_local"), ("codex", "codex_local")]:
            if not re.search(rf"^\s{{2}}{target}:\s*$", text, re.MULTILINE):
                continue
            declared_target_count += 1
            if not re.search(
                rf"^\s{{2}}{target}:\s*$\n(?:^\s{{4}}.*\n)*?^\s{{4}}adapter_type:\s+{adapter_type}\s*$",
                text,
                re.MULTILINE,
            ):
                errors.append(f"project manifest missing targets.{target}.adapter_type={adapter_type}: {rel}")
            if not re.search(
                rf"^\s{{2}}{target}:\s*$\n(?:^\s{{4}}.*\n)*?^\s{{4}}instruction_entry_file:\s+AGENTS\.md\s*$",
                text,
                re.MULTILINE,
            ):
                errors.append(f"project manifest missing targets.{target}.instruction_entry_file=AGENTS.md: {rel}")
        if declared_target_count == 0:
            errors.append(f"project manifest declares no supported targets: {rel}")
        if not is_template:
            for key in REQUIRED_COMPATIBILITY_PATH_KEYS:
                match = re.search(rf"^\s{{2}}{re.escape(key)}:\s+(.+?)\s*$", text, re.MULTILINE)
                if not match:
                    errors.append(f"project manifest missing compatibility.{key}: {rel}")
                    continue
                compatibility_path = repo_root / match.group(1)
                if not compatibility_path.exists():
                    errors.append(
                        f"project manifest compatibility path missing for {key}: "
                        f"{compatibility_path.relative_to(repo_root)}"
                    )
    return errors


def validate_project_literal_leakage(repo_root: Path) -> list[str]:
    errors: list[str] = []
    inventory_path = repo_root / "paperclips" / "assembly-inventory.json"
    if not inventory_path.is_file():
        return [f"missing project literal inventory: {inventory_path.relative_to(repo_root)}"]

    try:
        inventory = json.loads(inventory_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"invalid project literal inventory JSON: {exc}"]

    roots = inventory.get("projectLiteralScanRoots", [])
    literals = inventory.get("projectLiterals", [])
    if not isinstance(roots, list) or not isinstance(literals, list):
        return ["invalid project literal inventory shape"]

    for literal in literals:
        if not isinstance(literal, dict):
            continue
        literal_id = str(literal.get("id", "<unknown>"))
        pattern = literal.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            errors.append(f"project literal inventory missing pattern for {literal_id}")
            continue
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            errors.append(f"project literal inventory invalid pattern for {literal_id}: {exc}")
            continue

        occurrence_count = 0
        paths: set[str] = set()
        for root in roots:
            if not isinstance(root, str):
                continue
            scan_root = repo_root / root
            if scan_root.is_file():
                candidates = [scan_root]
            elif scan_root.is_dir():
                candidates = [path for path in scan_root.rglob("*") if path.is_file()]
            else:
                continue
            for path in candidates:
                try:
                    text = path.read_text()
                except UnicodeDecodeError:
                    continue
                matches = regex.findall(text)
                if matches:
                    occurrence_count += len(matches)
                    paths.add(str(path.relative_to(repo_root)))
        if occurrence_count:
            sample_paths = ", ".join(sorted(paths)[:5])
            if len(paths) > 5:
                sample_paths += ", ..."
            errors.append(
                f"project literal leak {literal_id}: {occurrence_count} occurrence(s) in {sample_paths}"
            )
    return errors


def validate_resolved_assembly_manifests(repo_root: Path) -> list[str]:
    errors: list[str] = []
    manifests = sorted((repo_root / "paperclips" / "projects").glob("*/paperclip-agent-assembly.yaml"))
    for manifest in manifests:
        if "_template" in manifest.parts:
            continue
        project = manifest.parent.name
        manifest_text = manifest.read_text()
        resolved_path = repo_root / "paperclips" / "dist" / f"{project}.resolved-assembly.json"
        if not resolved_path.is_file():
            errors.append(f"missing resolved assembly manifest: {resolved_path.relative_to(repo_root)}")
            continue
        try:
            resolved = json.loads(resolved_path.read_text())
        except json.JSONDecodeError as exc:
            errors.append(f"invalid resolved assembly manifest JSON: {resolved_path.relative_to(repo_root)}: {exc}")
            continue

        if resolved.get("schemaVersion") != 1:
            errors.append(f"resolved assembly manifest schemaVersion must be 1: {resolved_path.relative_to(repo_root)}")
        if resolved.get("project") != project:
            errors.append(
                f"resolved assembly manifest project mismatch for {resolved_path.relative_to(repo_root)}: "
                f"{resolved.get('project')} != {project}"
            )
        source_manifest = resolved.get("sourceManifest")
        if source_manifest != str(manifest.relative_to(repo_root)):
            errors.append(f"resolved assembly manifest sourceManifest mismatch: {resolved_path.relative_to(repo_root)}")
        source_sha = resolved.get("sourceManifestSha256")
        if source_sha != sha256_text(manifest_text):
            errors.append(f"resolved assembly manifest sourceManifestSha256 stale: {resolved_path.relative_to(repo_root)}")
        manifest_company_match = re.search(r"^\s{2}company_id:\s+(.+?)\s*$", manifest_text, re.MULTILINE)
        manifest_company_id = manifest_company_match.group(1).strip("\"'") if manifest_company_match else ""
        resolved_company_id = resolved.get("parameters", {}).get("project", {}).get("companyId")
        if resolved_company_id != manifest_company_id:
            errors.append(
                f"resolved assembly manifest project.companyId mismatch for "
                f"{resolved_path.relative_to(repo_root)}: {resolved_company_id} != {manifest_company_id}"
            )

        compatibility = resolved.get("compatibility", {})
        compatibility_inputs = compatibility.get("inputs", {}) if isinstance(compatibility, dict) else {}
        if not isinstance(compatibility_inputs, dict) or not compatibility_inputs:
            errors.append(f"resolved assembly manifest missing compatibility inputs: {resolved_path.relative_to(repo_root)}")
        else:
            for input_name in ["claudeDeployMapping", "codexAgentIdsEnv", "workspaceUpdateScript"]:
                input_data = compatibility_inputs.get(input_name)
                if not isinstance(input_data, dict):
                    errors.append(f"resolved assembly manifest missing compatibility input {input_name}: {resolved_path.relative_to(repo_root)}")
                    continue
                input_path = input_data.get("path")
                input_sha = input_data.get("sha256")
                if not isinstance(input_path, str) or not input_path:
                    errors.append(f"resolved assembly manifest compatibility input {input_name} missing path")
                    continue
                source_path = repo_root / input_path
                if not source_path.is_file():
                    errors.append(f"resolved assembly manifest compatibility input missing: {input_path}")
                    continue
                if input_sha != sha256_text(source_path.read_text()):
                    errors.append(f"resolved assembly manifest compatibility input stale: {input_path}")

        mcp = resolved.get("capabilities", {}).get("mcp", {})
        base_required = set(mcp.get("baseRequired", []))
        for marker in REQUIRED_PROJECT_MCP:
            if marker not in base_required:
                errors.append(f"resolved assembly manifest missing base MCP {marker}: {resolved_path.relative_to(repo_root)}")

        targets = resolved.get("targets", {})
        if not isinstance(targets, dict) or not targets:
            errors.append(f"resolved assembly manifest missing targets: {resolved_path.relative_to(repo_root)}")
            continue
        for target, target_data in targets.items():
            roles = target_data.get("roles", []) if isinstance(target_data, dict) else []
            if not roles:
                errors.append(f"resolved assembly manifest target has no roles: {project}:{target}")
                continue
            for role in roles:
                if not isinstance(role, dict):
                    continue
                output = role.get("output")
                role_id = role.get("roleId", "<unknown>")
                agent_name = role.get("agentName")
                agent_id = role.get("agentId")
                if not isinstance(output, str):
                    errors.append(f"resolved assembly manifest role missing output: {project}:{target}:{role_id}")
                    continue
                expected_agent_name = Path(output).stem
                if agent_name != expected_agent_name:
                    errors.append(
                        f"resolved assembly manifest agentName mismatch: "
                        f"{project}:{target}:{role_id}: {agent_name} != {expected_agent_name}"
                    )
                if not isinstance(agent_id, str) or not agent_id:
                    errors.append(f"resolved assembly manifest role missing agentId: {project}:{target}:{role_id}")
                elif not _UUID_RE.fullmatch(agent_id):
                    errors.append(f"resolved assembly manifest agentId invalid: {project}:{target}:{role_id}")
                output_path = repo_root / output
                if not output_path.is_file():
                    errors.append(f"resolved assembly manifest output missing: {output}")
                    continue
                if role.get("sha256") != sha256_text(output_path.read_text()):
                    errors.append(f"resolved assembly manifest bundle sha stale: {output}")
    return errors


def validate_cross_team_targets(
    bundle_paths_by_role: dict[str, Path],
    role_meta_by_id: dict[str, "RoleMeta"],
    repo_root: Path,
) -> list[str]:
    """A bundle whose role target is `<my>` must not contain any
    `<other>`-team UUID outside of anti-pattern sections / lines.
    """
    errors: list[str] = []
    teams = load_team_uuids(repo_root)
    if not teams["claude"] or not teams["codex"]:
        # No source-of-truth data → cannot validate, skip silently
        return errors

    for role_id, bundle_path in bundle_paths_by_role.items():
        meta = role_meta_by_id.get(role_id)
        if not meta or meta.target not in ("claude", "codex"):
            continue
        foreign_team = "codex" if meta.target == "claude" else "claude"
        foreign_uuids = teams[foreign_team]
        try:
            text = bundle_path.read_text()
        except OSError:
            continue
        rel = bundle_path.relative_to(repo_root)
        for foreign_uuid in foreign_uuids:
            for match in re.finditer(re.escape(foreign_uuid), text):
                if not _is_antipattern_context(text, match.start()):
                    line_no = text[: match.start()].count("\n") + 1
                    errors.append(
                        f"cross-team UUID in active section: {rel}:{line_no} "
                        f"contains {foreign_team} UUID {foreign_uuid[:8]}… "
                        f"in {meta.target} bundle"
                    )
                    break  # one error per foreign UUID per bundle is enough
    return errors


@dataclass
class RoleMeta:
    target: str
    role_id: str
    family: str
    profiles: list[str]


def parse_scalar_or_inline_list(value: str) -> str | list[str]:
    value = value.strip()
    if not value.startswith("[") or not value.endswith("]"):
        return value.strip("\"'")
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

    data: dict[str, str | list[str]] = {}
    end_index = None
    current_list_key: str | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end_index = index
            break
        cleaned = clean_line(line)
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        text = cleaned.strip()
        if indent == 2 and text.startswith("- ") and current_list_key:
            existing = data.setdefault(current_list_key, [])
            if isinstance(existing, list):
                existing.append(text[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        key, value = text.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = []
            current_list_key = key
        else:
            data[key] = parse_scalar_or_inline_list(value)
            current_list_key = None

    if end_index is None:
        raise ValueError(f"{path}: unterminated YAML front matter")

    required = ["target", "role_id", "family", "profiles"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{path}: missing front matter keys: {', '.join(missing)}")

    return RoleMeta(
        target=str(data["target"]),
        role_id=str(data["role_id"]),
        family=str(data["family"]),
        profiles=(
            list(data["profiles"])
            if isinstance(data["profiles"], list)
            else [str(data["profiles"])]
        ),
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
                matrix[section][current_item][key] = parse_scalar_or_inline_list(value)
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


def allowlisted(allowlist: dict, role_id: str, path: str, rule: str) -> bool:
    for entry in allowlist.get("entries", []):
        if entry.get("rule") != rule:
            continue
        if entry.get("roleId") != role_id:
            continue
        if entry.get("path") != path:
            continue
        if not all(
            [
                entry.get("reason"),
                entry.get("owner"),
                entry.get("reviewAfter") or entry.get("expiresAt"),
            ]
        ):
            continue
        return True
    return False


def target_allowlisted(allowlist: dict, target: str, rule: str) -> bool:
    for entry in allowlist.get("entries", []):
        if entry.get("rule") != rule:
            continue
        if entry.get("target") != target:
            continue
        if not all(
            [
                entry.get("reason"),
                entry.get("owner"),
                entry.get("reviewAfter") or entry.get("expiresAt"),
            ]
        ):
            continue
        return True
    return False


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
    role_profiles_by_id: dict[str, set[str]] = {}
    role_meta_by_id: dict[str, RoleMeta] = {}
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
        role_meta_by_id[role_id] = metadata
        if metadata.role_id != role_id:
            errors.append(f"{source}: role_id {metadata.role_id} != matrix id {role_id}")
        if metadata.target != role.get("target"):
            errors.append(f"{source}: target mismatch with matrix")
        if metadata.family != role.get("family"):
            errors.append(f"{source}: family mismatch with matrix")
        if metadata.profiles != role.get("profiles"):
            errors.append(f"{source}: profiles mismatch with matrix")
        role_profiles_by_id[role_id] = set(metadata.profiles)
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
    for index, entry in enumerate(allowlist.get("entries", [])):
        for key in ["rule", "reason", "owner"]:
            if not entry.get(key):
                errors.append(f"allowlist entry {index} missing {key}")
        if entry.get("rule") == "bundle-size-growth":
            for key in ["roleId", "path"]:
                if not entry.get(key):
                    errors.append(f"allowlist entry {index} missing {key}")
        if entry.get("rule") == "bundle-target-size-growth" and not entry.get("target"):
            errors.append(f"allowlist entry {index} missing target")
        if not (entry.get("reviewAfter") or entry.get("expiresAt")):
            errors.append(f"allowlist entry {index} missing reviewAfter or expiresAt")
    if "measurementCommit" not in baseline:
        errors.append("bundle-size-baseline.json missing measurementCommit")
    policy = baseline.get("policy", {})
    max_growth_percent = int(policy.get("maxGrowthPercent", 0))
    if max_growth_percent != 0:
        errors.append(
            "bundle-size-baseline.json policy.maxGrowthPercent must be 0; "
            "use bundle-size-allowlist.json for reviewed exceptions"
        )

    bundle_paths_by_role: dict[str, Path] = {}
    totals_by_target: dict[str, dict[str, int]] = {}
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
        unresolved = _UNRESOLVED_VARIABLE_RE.search(text)
        if unresolved:
            errors.append(f"generated bundle contains unresolved variable: {path}: {unresolved.group(0)}")
        byte_count = len(text.encode("utf-8"))
        baseline_bytes = bundle.get("bytes")
        if not isinstance(baseline_bytes, int):
            errors.append(f"baseline byte count missing for {path}")
            continue
        target = str(bundle.get("target", ""))
        if not target:
            errors.append(f"baseline bundle missing target for {path}")
        else:
            totals = totals_by_target.setdefault(target, {"baseline": 0, "actual": 0})
            totals["baseline"] += baseline_bytes
            totals["actual"] += byte_count
        growth_allowance = (baseline_bytes * max_growth_percent + 99) // 100
        max_allowed_bytes = baseline_bytes + growth_allowance
        if byte_count > max_allowed_bytes and not allowlisted(
            allowlist, str(role_id), str(path), "bundle-size-growth"
        ):
            errors.append(
                f"bundle grew without reviewed allowlist for {path}: "
                f"{byte_count} > {max_allowed_bytes}"
            )

    for target, totals in sorted(totals_by_target.items()):
        if totals["actual"] > totals["baseline"] and not target_allowlisted(
            allowlist, target, "bundle-target-size-growth"
        ):
            errors.append(
                f"target bundle total grew without reviewed allowlist for {target}: "
                f"{totals['actual']} > {totals['baseline']}"
            )

    for rule_id, rule in matrix.get("rules", {}).items():
        rule_role_ids = role_ids if rule.get("role_ids") == "all" else set(rule.get("role_ids", []))
        required_profiles = set(rule.get("required_profiles", []))
        markers = [str(marker).lower() for marker in rule.get("markers", [])]
        for role_id in rule_role_ids:
            missing_profiles = required_profiles - role_profiles_by_id.get(role_id, set())
            for profile in sorted(missing_profiles):
                errors.append(f"rule {rule_id} requires profile {profile} for role {role_id}")
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

    errors.extend(validate_handoff_markers(bundle_paths_by_role, repo_root))
    errors.extend(validate_project_capability_manifests(repo_root))
    errors.extend(validate_project_literal_leakage(repo_root))
    errors.extend(validate_resolved_assembly_manifests(repo_root))
    errors.extend(
        validate_cross_team_targets(bundle_paths_by_role, role_meta_by_id, repo_root)
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
