#!/usr/bin/env python3
"""Manifest-driven compatibility builder for Paperclip project bundles."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import generate_assembly_inventory
import validate_instructions


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


def include_fragment_path(repo_root: Path, target: str, include_line: str) -> Path:
    match = INCLUDE_RE.search(include_line)
    if not match:
        raise ValueError(f"include marker missing fragment path: {include_line}")
    fragment_rel = match.group(0)[len("fragments/") :]
    fragments_root = repo_root / "paperclips" / "fragments"
    target_fragment = fragments_root / "targets" / target / fragment_rel
    if target_fragment.is_file():
        return target_fragment
    return fragments_root / fragment_rel


def expand_includes(repo_root: Path, target: str, text: str) -> str:
    rendered: list[str] = []
    for line in text.splitlines():
        if "<!-- @include fragments/" not in line:
            rendered.append(line)
            continue
        fragment_path = include_fragment_path(repo_root, target, line)
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
    overlay_path = repo_root / overlay_root / target / role_name
    if not overlay_path.is_file():
        return text
    separator = "" if text.endswith("\n") else "\n"
    return f"{text}{separator}{overlay_path.read_text()}"


def render_role(
    repo_root: Path,
    target: str,
    role_file: Path,
    manifest_values: dict[str, str],
) -> str:
    text = strip_front_matter(role_file.read_text())
    text = expand_includes(repo_root, target, text)
    text = apply_overlay(repo_root, manifest_values, target, role_file.name, text)
    text = substitute_variables(text, manifest_values)
    unresolved = UNRESOLVED_VARIABLE_RE.search(text)
    if unresolved:
        raise ValueError(
            f"unresolved variable in {role_file.relative_to(repo_root)}: "
            f"{unresolved.group(0)}"
        )
    return text


def render_target(repo_root: Path, target: str, manifest_values: dict[str, str]) -> None:
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
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    try:
        manifest = check_project_manifest(repo_root, args.project)
        manifest_text = manifest.read_text()
        manifest_values = flatten_manifest_scalars(manifest_text)
        targets = declared_targets(manifest_text)
        if args.target != "all":
            targets = [target for target in targets if target == args.target]
        if not targets:
            raise ValueError(f"project {args.project} declares no build targets for {args.target}")
        for target in targets:
            render_target(repo_root, target, manifest_values)
        run_inventory(repo_root, args.inventory)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Paperclip project build OK: {args.project} ({', '.join(targets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
