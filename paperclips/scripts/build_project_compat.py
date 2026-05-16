#!/usr/bin/env python3
"""Manifest-driven compatibility builder for Paperclip project bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import generate_assembly_inventory
import validate_instructions
from compose_agent_prompt import compose as _compose_agent_prompt
from resolve_bindings import (
    BindingsConflictWarning,
    resolve_all as _resolve_bindings_all,
)
from resolve_template_sources import (
    UnresolvedTemplateError,
    resolve as _resolve_template,
)
from validate_manifest import (
    ManifestValidationError,
    validate_manifest as _validate_manifest,
)


SUPPORTED_TARGETS = ("claude", "codex")
INCLUDE_RE = re.compile(r"fragments/[^ ]+\.md")
UNRESOLVED_VARIABLE_RE = re.compile(r"\{\{[^}\n]+\}\}")


def project_manifest_path(repo_root: Path, project: str) -> Path:
    return repo_root / "paperclips" / "projects" / project / "paperclip-agent-assembly.yaml"


def declared_targets(manifest_text: str) -> list[str]:
    targets: list[str] = []
    for target in SUPPORTED_TARGETS:
        if re.search(rf"^\s{{2}}{re.escape(target)}:\s*$", manifest_text, re.MULTILINE):
            targets.append(target)
    return targets


def target_paths(repo_root: Path, target: str) -> tuple[Path, Path]:
    paperclips = repo_root / "paperclips"
    if target == "claude":
        return paperclips / "roles", paperclips / "dist"
    if target == "codex":
        return paperclips / "roles-codex", paperclips / "dist" / "codex"
    raise ValueError(f"unsupported target: {target}")


def strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return "\n".join(lines) + "\n"

    end_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            end_index = index
            break
    if end_index is None:
        raise ValueError("unterminated front matter")

    body = lines[end_index + 1 :]
    if body and body[0] == "":
        body = body[1:]
    return "\n".join(body) + "\n"


def include_fragment_path(
    repo_root: Path,
    target: str,
    include_line: str,
    manifest_values: dict[str, str] | None = None,
) -> Path:
    match = INCLUDE_RE.search(include_line)
    if not match:
        raise ValueError(f"include marker missing fragment path: {include_line}")
    fragment_rel = match.group(0)[len("fragments/") :]
    fragments_root = repo_root / "paperclips" / "fragments"
    if manifest_values:
        project_key = manifest_values.get("project.key", "")
        if project_key:
            project_fragments_root = (
                repo_root / "paperclips" / "projects" / project_key / "fragments"
            )
            project_target_fragment = project_fragments_root / "targets" / target / fragment_rel
            if project_target_fragment.is_file():
                print(
                    f"  override applied: {project_target_fragment.relative_to(repo_root)} "
                    f"(was: paperclips/fragments/targets/{target}/{fragment_rel})",
                    file=sys.stderr,
                )
                return project_target_fragment
            project_shared_fragment = project_fragments_root / fragment_rel
            if project_shared_fragment.is_file():
                print(
                    f"  override applied: {project_shared_fragment.relative_to(repo_root)} "
                    f"(was: paperclips/fragments/{fragment_rel})",
                    file=sys.stderr,
                )
                return project_shared_fragment
    target_fragment = fragments_root / "targets" / target / fragment_rel
    if target_fragment.is_file():
        return target_fragment
    return fragments_root / fragment_rel


def expand_includes(
    repo_root: Path,
    target: str,
    text: str,
    manifest_values: dict[str, str] | None = None,
) -> str:
    rendered: list[str] = []
    for line in text.splitlines():
        if "<!-- @include fragments/" not in line:
            rendered.append(line)
            continue
        fragment_path = include_fragment_path(repo_root, target, line, manifest_values)
        if not fragment_path.is_file():
            raise FileNotFoundError(f"include fragment not readable: {fragment_path}")
        rendered.extend(fragment_path.read_text().splitlines())
    return "\n".join(rendered) + "\n"


def flatten_manifest_scalars(manifest_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    for raw_line in manifest_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if ":" not in text:
            continue
        key, raw_value = text.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip("\"'")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([item[1] for item in stack] + [key])
        if value and value not in {"[]", "{}"}:
            values[path] = value
        else:
            stack.append((indent, key))

    aliases = {
        "PROJECT": values.get("project.display_name", ""),
        "PROJECT_KEY": values.get("project.key", ""),
        "ISSUE_PREFIX": values.get("project.issue_prefix", ""),
        "CODEBASE_MEMORY_PROJECT": values.get("mcp.codebase_memory_projects.primary", ""),
    }
    for key, value in aliases.items():
        if value:
            values[key] = value
    return values


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return sha256_text(path.read_text())


def load_claude_agent_ids(deploy_script: Path) -> dict[str, str]:
    text = deploy_script.read_text()
    pattern = re.compile(r"^\s*([a-z][\w-]*)\)\s+echo\s+\"([0-9a-f-]{36})\"", re.MULTILINE)
    return {name: agent_id for name, agent_id in pattern.findall(text)}


def _codex_env_to_agent_name(key: str) -> str:
    if not key.endswith("_AGENT_ID"):
        return ""
    stem = key[: -len("_AGENT_ID")]
    return stem.lower().replace("_", "-")


def load_codex_agent_ids(env_file: Path) -> dict[str, str]:
    ids: dict[str, str] = {}
    if not env_file.is_file():
        return ids
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        name = _codex_env_to_agent_name(key.strip())
        agent_id = value.strip()
        if name and re.fullmatch(r"[0-9a-f-]{36}", agent_id):
            ids[name] = agent_id
    return ids


def compatibility_agent_ids(repo_root: Path, manifest_values: dict[str, str], target: str) -> dict[str, str]:
    if target == "claude":
        mapping = manifest_values.get("compatibility.claude_deploy_mapping", "paperclips/deploy-agents.sh")
        return load_claude_agent_ids(repo_root / mapping)
    if target == "codex":
        env_file = manifest_values.get("compatibility.codex_agent_ids_env", "paperclips/codex-agent-ids.env")
        return load_codex_agent_ids(repo_root / env_file)
    return {}


def manifest_entries(manifest_text: str) -> list[tuple[int, str, str, str]]:
    entries: list[tuple[int, str, str, str]] = []
    stack: list[tuple[int, str]] = []
    for raw_line in manifest_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if ":" not in text:
            continue
        key, raw_value = text.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip("\"'")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([item[1] for item in stack] + [key])
        entries.append((indent, path, key, value))
        if not value or value in {"[]", "{}"}:
            stack.append((indent, key))
    return entries


def manifest_path_entry(manifest_text: str, path: str) -> tuple[int, int, str] | None:
    for index, (indent, entry_path, _key, value) in enumerate(manifest_entries(manifest_text)):
        if entry_path == path:
            return index, indent, value
    return None


def manifest_list(manifest_text: str, path: str) -> list[str]:
    entry = manifest_path_entry(manifest_text, path)
    if entry is None:
        return []
    index, indent, value = entry
    if value == "[]":
        return []
    items: list[str] = []
    lines = manifest_text.splitlines()
    entry_line = 0
    current_entry = -1
    for line_index, raw_line in enumerate(lines):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        current_entry += 1
        if current_entry == index:
            entry_line = line_index
            break
    for raw_line in lines[entry_line + 1 :]:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if line_indent <= indent:
            break
        if line_indent == indent + 2 and stripped.startswith("- "):
            items.append(stripped[2:].strip().strip("\"'"))
    return items


def manifest_mapping_of_lists(manifest_text: str, path: str) -> dict[str, list[str]]:
    entry = manifest_path_entry(manifest_text, path)
    if entry is None:
        return {}
    index, indent, value = entry
    if value == "{}":
        return {}
    lines = manifest_text.splitlines()
    entry_line = 0
    current_entry = -1
    for line_index, raw_line in enumerate(lines):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        current_entry += 1
        if current_entry == index:
            entry_line = line_index
            break

    result: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in lines[entry_line + 1 :]:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if line_indent <= indent:
            break
        if line_indent == indent + 2 and stripped.endswith(":"):
            current_key = stripped[:-1].strip()
            result[current_key] = []
            continue
        if current_key and line_indent == indent + 4 and stripped.startswith("- "):
            result[current_key].append(stripped[2:].strip().strip("\"'"))
    return result


def manifest_mapping_scalars(manifest_text: str, path: str) -> dict[str, str]:
    prefix = f"{path}."
    values = flatten_manifest_scalars(manifest_text)
    return {
        key[len(prefix) :]: value
        for key, value in values.items()
        if key.startswith(prefix)
    }


def manifest_object_list(manifest_text: str, path: str) -> list[dict[str, str]]:
    entry = manifest_path_entry(manifest_text, path)
    if entry is None:
        return []
    index, indent, value = entry
    if value == "[]":
        return []

    lines = manifest_text.splitlines()
    entry_line = 0
    current_entry = -1
    for line_index, raw_line in enumerate(lines):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("- "):
            continue
        current_entry += 1
        if current_entry == index:
            entry_line = line_index
            break

    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in lines[entry_line + 1 :]:
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        line_indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if line_indent <= indent:
            break
        if line_indent == indent + 2 and stripped.startswith("- "):
            current = {}
            items.append(current)
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if current is None or ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        value = raw_value.strip().strip("\"'")
        if value and value not in {"[]", "{}"}:
            current[key.strip()] = value
    return items


def manifest_agents(manifest_text: str, target: str | None = None) -> list[dict[str, str]]:
    agents = manifest_object_list(manifest_text, "agents")
    if target is None:
        return agents
    return [agent for agent in agents if agent.get("target") == target]


def target_manifest_data(manifest_values: dict[str, str], target: str) -> dict[str, str]:
    prefix = f"targets.{target}."
    return {
        "instructionEntryFile": manifest_values.get(f"{prefix}instruction_entry_file", ""),
        "adapterType": manifest_values.get(f"{prefix}adapter_type", ""),
        "deployMode": manifest_values.get(f"{prefix}deploy_mode", ""),
        "instructionsBundleMode": manifest_values.get(f"{prefix}instructions_bundle_mode", ""),
    }


def substitute_variables(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(0)[2:-2].strip()
        return values.get(key, match.group(0))

    return UNRESOLVED_VARIABLE_RE.sub(replace, text)


def apply_overlay(
    repo_root: Path,
    manifest_values: dict[str, str],
    target: str,
    role_name: str,
    text: str,
) -> str:
    overlay_root = manifest_values.get("paths.overlay_root")
    if not overlay_root:
        return text
    overlay_names = ["_common.md", role_name]
    agent_name = manifest_values.get("agent.agent_name", "")
    if agent_name:
        overlay_names.append(f"{agent_name}.md")
    for overlay_name in overlay_names:
        overlay_path = repo_root / overlay_root / target / overlay_name
        if not overlay_path.is_file():
            continue
        separator = "" if text.endswith("\n") else "\n"
        text = f"{text}{separator}{overlay_path.read_text()}"
    return text


def _load_host_local_sources(project_key: str, repo_root: Path | None = None) -> dict:
    """Load ~/.paperclip/projects/<key>/{bindings,paths,plugins}.yaml if present.

    Returns nested dict for resolve_template_sources.resolve():
      {"bindings": {...}, "paths": {...}, "plugins": {...}}

    Returns empty dict if no host-local files exist (pre-migration state).

    Phase D: bindings.yaml is resolved via resolve_bindings.resolve_all so
    legacy paperclips/codex-agent-ids.env still contributes UUIDs alongside
    the new bindings.yaml (with bindings winning on conflict, plus a
    BindingsConflictWarning to surface drift).
    """
    import os
    home = Path(os.path.expanduser("~/.paperclip/projects")) / project_key
    sources: dict = {}

    # --- bindings: dual-read via resolver -------------------------------------
    bindings_yaml = home / "bindings.yaml"
    legacy_env = (
        repo_root / "paperclips" / "codex-agent-ids.env"
        if (repo_root is not None and project_key == "gimle")
        else None
    )
    try:
        merged = _resolve_bindings_all(
            legacy_env_path=legacy_env,
            bindings_yaml_path=bindings_yaml,
        )
        sources["bindings"] = {
            "company_id": merged.get("company_id"),
            "agents": merged.get("agents", {}),
        }
    except FileNotFoundError:
        pass  # pre-migration: no host-local + no legacy → silently skip

    # --- paths/plugins: direct read (no legacy equivalent) -------------------
    if not home.is_dir():
        return sources
    try:
        import yaml
    except ImportError:
        return sources  # pyyaml missing — silently skip remaining host-local
    for fname in ("paths.yaml", "plugins.yaml"):
        p = home / fname
        if not p.is_file():
            continue
        try:
            raw = yaml.safe_load(p.read_text()) or {}
        except Exception:
            continue
        if isinstance(raw, dict):
            key = fname.replace(".yaml", "")
            sources[key] = raw
    return sources


def _collect_overlay_blocks(
    repo_root: Path,
    manifest_values: dict[str, str],
    target: str,
    role_name: str,
    agent_name: str,
) -> list[str]:
    """Return overlay file contents per spec §6.7 (Phase B compose path).

    Same lookup logic as apply_overlay, but returns blocks separately instead of
    concatenating into role text — so compose() can place them last.
    """
    overlay_root = manifest_values.get("paths.overlay_root")
    if not overlay_root:
        return []
    blocks: list[str] = []
    overlay_names = ["_common.md", role_name]
    if agent_name:
        overlay_names.append(f"{agent_name}.md")
    for overlay_name in overlay_names:
        overlay_path = repo_root / overlay_root / target / overlay_name
        if overlay_path.is_file():
            blocks.append(overlay_path.read_text())
    return blocks


def render_role(
    repo_root: Path,
    target: str,
    role_file: Path,
    manifest_values: dict[str, str],
    agent_values: dict[str, str] | None = None,
) -> str:
    values = dict(manifest_values)
    if agent_values:
        values.update({f"agent.{key}": value for key, value in agent_values.items()})
    text = strip_front_matter(role_file.read_text())

    # UAA Phase B: detect slim crafts (no <!-- @include --> directives) and route
    # to compose_agent_prompt() instead of legacy expand_includes.
    if "<!-- @include fragments/" not in text:
        # Compose path: profile-driven composition per spec §3, §5.2.1.
        # Profile lookup order:
        # 1. agent_values["profile"] (explicit per-agent manifest entry)
        # 2. role file frontmatter profiles[0] (single-profile contract per Phase A)
        # 3. fallback "minimal"
        # rev4 fix B-2: agent_values is flat dict; key is 'profile', NOT 'agent.profile'.
        profile_name = (agent_values or {}).get("profile")
        if not profile_name:
            # rev2 Architect C-2: narrow except — don't swallow KeyboardInterrupt,
            # MemoryError, etc. Only legitimate "frontmatter unreadable" cases.
            try:
                meta = validate_instructions.load_role_front_matter(role_file)
                if meta.profiles:
                    profile_name = meta.profiles[0]
            except (FileNotFoundError, ValueError, KeyError) as exc:
                print(
                    f"  WARN: frontmatter unreadable for {role_file.name} "
                    f"({type(exc).__name__}: {exc}); falling back to profile lookup chain",
                    file=sys.stderr,
                )
        if not profile_name:
            profile_name = "minimal"
        profiles_dir = repo_root / "paperclips" / "fragments" / "profiles"
        fragments_dir = repo_root / "paperclips" / "fragments" / "shared" / "fragments"
        custom_includes = (agent_values or {}).get("custom_includes", [])
        if isinstance(custom_includes, str):
            custom_includes = []  # back-compat / defensive
        # rev2 Security C-3: validate custom_includes shape + reject traversal.
        if not isinstance(custom_includes, list):
            raise ValueError(
                f"custom_includes must be list, got {type(custom_includes).__name__} "
                f"for agent {(agent_values or {}).get('agent_name', '<unknown>')}",
            )
        for inc in custom_includes:
            if not isinstance(inc, str):
                raise ValueError(f"custom_includes entry must be string, got {type(inc).__name__}")
            if inc.startswith("/") or any(p in ("..", "") for p in inc.split("/")):
                raise ValueError(f"custom_includes entry contains traversal: {inc!r}")
        # rev4 fix B-2: same key-naming fix — flat 'agent_name', not 'agent.agent_name'.
        agent_name = (agent_values or {}).get("agent_name", "")
        overlay_blocks = _collect_overlay_blocks(
            repo_root, values, target, role_file.name, agent_name,
        )
        text = _compose_agent_prompt(
            profile_name=profile_name,
            profiles_dir=profiles_dir,
            fragments_dir=fragments_dir,
            role_source_text=text,
            custom_includes=custom_includes,
            overlay_blocks=overlay_blocks,
        )
    else:
        # Legacy path: existing @include expansion + overlay merge (unchanged).
        text = expand_includes(repo_root, target, text, values)
        text = apply_overlay(repo_root, values, target, role_file.name, text)

    text = substitute_variables(text, values)

    # UAA Phase B rev2: host-local resolver per spec §6.5. If
    # ~/.paperclip/projects/<key>/{bindings,paths,plugins}.yaml exist,
    # resolve any remaining {{bindings.X}}/{{paths.X}}/{{plugins.X}} refs.
    # Phase D/E/F/G migrations populate these files; pre-migration they're
    # absent and host_sources is {} — refs stay unresolved and the
    # UNRESOLVED_VARIABLE_RE check below catches them as build error.
    project_key = manifest_values.get("project.key", "")
    if project_key:
        host_sources = _load_host_local_sources(project_key, repo_root=repo_root)
        if host_sources:
            # Build nested sources dict expected by resolve():
            #   {"manifest": {project: {...}, domain: {...}, mcp: {...}},
            #    "bindings": {...}, "paths": {...}, "plugins": {...}, "agent": {...}}
            manifest_nested: dict = {"project": {}, "domain": {}, "mcp": {}}
            for k, v in manifest_values.items():
                for top in ("project", "domain", "mcp"):
                    if k.startswith(f"{top}."):
                        manifest_nested[top][k[len(top) + 1:]] = v
            full_sources = {
                "manifest": manifest_nested,
                "agent": agent_values or {},
                **host_sources,  # bindings / paths / plugins
            }
            try:
                text = _resolve_template(text, full_sources)
            except UnresolvedTemplateError as exc:
                raise ValueError(
                    f"unresolved host-local variable in {role_file.relative_to(repo_root)}: {exc}",
                ) from exc

    unresolved = UNRESOLVED_VARIABLE_RE.search(text)
    if unresolved:
        raise ValueError(
            f"unresolved variable in {role_file.relative_to(repo_root)}: "
            f"{unresolved.group(0)}",
        )
    return text


def render_target(
    repo_root: Path,
    target: str,
    manifest_values: dict[str, str],
    manifest_text: str = "",
) -> None:
    explicit_agents = manifest_agents(manifest_text, target) if manifest_text else []
    if explicit_agents:
        for agent in explicit_agents:
            role_source = agent.get("role_source", "")
            output_path = agent.get("output_path", "")
            agent_name = agent.get("agent_name", "")
            if not role_source:
                raise ValueError(
                    f"manifest agent missing role_source for target {target}: {agent}",
                )
            # UAA Phase B (rev4 fix B-1): derive output_path from
            # (project.key, target, agent_name) when manifest omits it.
            # Post-migration manifests are path-free per spec §6.1.
            if not output_path:
                if not agent_name:
                    raise ValueError(
                        f"manifest agent missing agent_name AND output_path for target {target}: {agent}",
                    )
                project_key = manifest_values.get("project.key", "")
                if not project_key:
                    raise ValueError(
                        f"manifest missing project.key; cannot derive output_path for {agent_name}",
                    )
                output_path = f"paperclips/dist/{project_key}/{target}/{agent_name}.md"
            role_file = repo_root / role_source
            if not role_file.is_file():
                raise FileNotFoundError(f"agent role source missing: {role_source}")
            out_file = repo_root / output_path
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(render_role(repo_root, target, role_file, manifest_values, agent))
            print(f"built {out_file}")
        return

    roles_dir, out_dir = target_paths(repo_root, target)
    if not roles_dir.is_dir():
        raise FileNotFoundError(f"roles directory not found for target '{target}': {roles_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    if target == "codex":
        for path in out_dir.glob("*.md"):
            path.unlink()

    role_files = sorted(roles_dir.glob("*.md"))
    if not role_files:
        raise FileNotFoundError(f"no role files found for target '{target}' in {roles_dir}")

    for role_file in role_files:
        out_file = out_dir / role_file.name
        out_file.write_text(render_role(repo_root, target, role_file, manifest_values))
        print(f"built {out_file}")


def role_output_entry(repo_root: Path, target: str, role_file: Path, ids: dict[str, str]) -> dict[str, object]:
    _roles_dir, out_dir = target_paths(repo_root, target)
    out_file = out_dir / role_file.name
    meta = validate_instructions.load_role_front_matter(role_file)
    text = out_file.read_text()
    name = out_file.stem
    return {
        "roleId": meta.role_id,
        "agentName": name,
        "agentId": ids.get(name, ""),
        "family": meta.family,
        "profiles": meta.profiles,
        "source": str(role_file.relative_to(repo_root)),
        "output": str(out_file.relative_to(repo_root)),
        "sha256": sha256_text(text),
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n"),
    }


def agent_output_entry(
    repo_root: Path,
    target: str,
    agent: dict[str, str],
    ids: dict[str, str],
    manifest_values: dict[str, str] | None = None,
) -> dict[str, object]:
    role_source = agent.get("role_source", "")
    output = agent.get("output_path", "")
    agent_name = agent.get("agent_name", "")
    if not role_source:
        raise ValueError(
            f"manifest agent missing role_source for target {target}: {agent}",
        )
    # UAA Phase B (rev4 fix B-1): same derivation as render_target.
    if not output:
        if not agent_name:
            raise ValueError(
                f"manifest agent missing agent_name AND output_path for target {target}: {agent}",
            )
        project_key = (manifest_values or {}).get("project.key", "")
        if not project_key:
            raise ValueError(
                f"manifest missing project.key; cannot derive output_path for {agent_name}",
            )
        output = f"paperclips/dist/{project_key}/{target}/{agent_name}.md"
    role_file = repo_root / role_source
    out_file = repo_root / output
    meta = validate_instructions.load_role_front_matter(role_file)
    text = out_file.read_text()
    name = agent.get("agent_name") or out_file.stem
    return {
        "roleId": meta.role_id,
        "agentName": name,
        "agentId": agent.get("agent_id") or ids.get(name, ""),
        "family": meta.family,
        "profiles": meta.profiles,
        "source": str(role_file.relative_to(repo_root)),
        "output": str(out_file.relative_to(repo_root)),
        "workspaceCwd": agent.get("workspace_cwd", ""),
        "platform": agent.get("platform", ""),
        "sha256": sha256_text(text),
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n"),
    }


def target_output_entry(
    repo_root: Path,
    target: str,
    manifest_values: dict[str, str],
    manifest_text: str = "",
) -> dict[str, object]:
    ids = compatibility_agent_ids(repo_root, manifest_values, target)
    explicit_agents = manifest_agents(manifest_text, target) if manifest_text else []
    if explicit_agents:
        return {
            **target_manifest_data(manifest_values, target),
            "roles": [
                agent_output_entry(repo_root, target, agent, ids, manifest_values)
                for agent in explicit_agents
            ],
        }
    role_files = sorted(target_paths(repo_root, target)[0].glob("*.md"))
    return {
        **target_manifest_data(manifest_values, target),
        "roles": [
            role_output_entry(repo_root, target, role_file, ids)
            for role_file in role_files
        ],
    }


def compatibility_input_entry(repo_root: Path, relative_path: str) -> dict[str, str]:
    path = repo_root / relative_path
    return {
        "path": relative_path,
        "sha256": sha256_file(path),
    }


def resolved_assembly(
    repo_root: Path,
    project: str,
    manifest: Path,
    manifest_text: str,
    manifest_values: dict[str, str],
    targets: list[str],
) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "project": project,
        "sourceManifest": str(manifest.relative_to(repo_root)),
        "sourceManifestSha256": sha256_text(manifest_text),
        "parameters": {
            "project": {
                "key": manifest_values.get("project.key", ""),
                "displayName": manifest_values.get("project.display_name", ""),
                "systemName": manifest_values.get("project.system_name", ""),
                "issuePrefix": manifest_values.get("project.issue_prefix", ""),
                "companyId": manifest_values.get("project.company_id", ""),
                "integrationBranch": manifest_values.get("project.integration_branch", ""),
            },
            "paths": {
                "projectRoot": manifest_values.get("paths.project_root", ""),
                "primaryRepoRoot": manifest_values.get("paths.primary_repo_root", ""),
                "primaryMcpServiceDir": manifest_values.get("paths.primary_mcp_service_dir", ""),
                "productionCheckout": manifest_values.get("paths.production_checkout", ""),
                "codexTeamRoot": manifest_values.get("paths.codex_team_root", ""),
                "operatorMemoryDir": manifest_values.get("paths.operator_memory_dir", ""),
                "overlayRoot": manifest_values.get("paths.overlay_root", ""),
                "projectRulesFile": manifest_values.get("paths.project_rules_file", ""),
            },
        },
        "capabilities": {
            "mcp": {
                "serviceName": manifest_values.get("mcp.service_name", ""),
                "packageName": manifest_values.get("mcp.package_name", ""),
                "toolNamespace": manifest_values.get("mcp.tool_namespace", ""),
                "baseRequired": manifest_list(manifest_text, "mcp.base_required"),
                "codebaseMemoryProjects": {
                    **manifest_mapping_scalars(manifest_text, "mcp.codebase_memory_projects"),
                },
                "additions": {
                    "project": manifest_list(manifest_text, "mcp.additions.project"),
                    "byRole": manifest_mapping_of_lists(manifest_text, "mcp.additions.by_role"),
                },
            },
            "skills": {
                "additions": {
                    "project": manifest_list(manifest_text, "skills.additions.project"),
                    "byRole": manifest_mapping_of_lists(manifest_text, "skills.additions.by_role"),
                },
            },
            "subagents": {
                "additions": {
                    "project": manifest_list(manifest_text, "subagents.additions.project"),
                    "byRole": manifest_mapping_of_lists(manifest_text, "subagents.additions.by_role"),
                },
            },
        },
        "compatibility": {
            "legacyOutputPaths": manifest_values.get("compatibility.legacy_output_paths", ""),
            "claudeDeployMapping": manifest_values.get("compatibility.claude_deploy_mapping", ""),
            "codexAgentIdsEnv": manifest_values.get("compatibility.codex_agent_ids_env", ""),
            "workspaceUpdateScript": manifest_values.get("compatibility.workspace_update_script", ""),
            "inputs": {
                "claudeDeployMapping": compatibility_input_entry(
                    repo_root,
                    manifest_values.get("compatibility.claude_deploy_mapping", ""),
                ),
                "codexAgentIdsEnv": compatibility_input_entry(
                    repo_root,
                    manifest_values.get("compatibility.codex_agent_ids_env", ""),
                ),
                "workspaceUpdateScript": compatibility_input_entry(
                    repo_root,
                    manifest_values.get("compatibility.workspace_update_script", ""),
                ),
            },
        },
        "targets": {
            target: target_output_entry(repo_root, target, manifest_values, manifest_text)
            for target in targets
        },
    }


def write_resolved_assembly(
    repo_root: Path,
    project: str,
    manifest: Path,
    manifest_text: str,
    manifest_values: dict[str, str],
    targets: list[str],
) -> None:
    output = repo_root / "paperclips" / "dist" / f"{project}.resolved-assembly.json"
    data = resolved_assembly(repo_root, project, manifest, manifest_text, manifest_values, targets)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output.relative_to(repo_root)}")


def check_project_manifest(repo_root: Path, project: str) -> Path:
    manifest = project_manifest_path(repo_root, project)
    if not manifest.is_file():
        raise FileNotFoundError(f"missing project manifest: {manifest.relative_to(repo_root)}")
    errors = validate_instructions.validate_project_capability_manifests(repo_root)
    if errors:
        raise ValueError("\n".join(errors))
    return manifest


def run_inventory(repo_root: Path, mode: str) -> None:
    if mode == "skip":
        return
    inventory = generate_assembly_inventory.canonical_json(
        generate_assembly_inventory.build_inventory(repo_root)
    )
    output = repo_root / generate_assembly_inventory.DEFAULT_OUTPUT
    if mode == "update":
        output.write_text(inventory)
        print(f"wrote {output.relative_to(repo_root)}")
        return
    if not output.is_file() or output.read_text() != inventory:
        raise ValueError(
            "stale assembly inventory; run: "
            "python3 paperclips/scripts/generate_assembly_inventory.py"
        )
    print("Paperclip assembly inventory OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--project", default="gimle")
    parser.add_argument("--target", choices=[*SUPPORTED_TARGETS, "all"], default="all")
    parser.add_argument("--inventory", choices=["check", "update", "skip"], default="check")
    parser.add_argument(
        "--validate-strict",
        action="store_true",
        help="reject manifest with literal UUIDs / abs paths / forbidden host-local keys (UAA §6.2)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    try:
        manifest = check_project_manifest(repo_root, args.project)
        # UAA Phase B rev2: --validate-strict enforces spec §6.2 (path-free + UUID-free
        # committed manifests). Trading/uaudit/gimle pre-Phase-D/E/F/G still have UUIDs +
        # abs paths inline; --validate-strict is opt-in until those migrations land.
        if args.validate_strict:
            try:
                _validate_manifest(manifest)
            except ManifestValidationError as exc:
                print(f"ERROR: manifest validation (strict) failed: {exc}", file=sys.stderr)
                return 1
        manifest_text = manifest.read_text()
        manifest_values = flatten_manifest_scalars(manifest_text)
        targets = declared_targets(manifest_text)
        if args.target != "all":
            targets = [target for target in targets if target == args.target]
        if not targets:
            raise ValueError(f"project {args.project} declares no build targets for {args.target}")
        for target in targets:
            render_target(repo_root, target, manifest_values, manifest_text)
        write_resolved_assembly(repo_root, args.project, manifest, manifest_text, manifest_values, targets)
        run_inventory(repo_root, args.inventory)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # rev2 DevOps #9: catch yaml.YAMLError + any other unanticipated parse error
        # with clean diagnostic instead of raw Python traceback.
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"Paperclip project build OK: {args.project} ({', '.join(targets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
