#!/usr/bin/env python3
"""Manifest-driven compatibility builder for Paperclip project bundles."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import generate_assembly_inventory
import validate_instructions


SUPPORTED_TARGETS = ("claude", "codex")


def project_manifest_path(repo_root: Path, project: str) -> Path:
    return repo_root / "paperclips" / "projects" / project / "paperclip-agent-assembly.yaml"


def declared_targets(manifest_text: str) -> list[str]:
    targets: list[str] = []
    for target in SUPPORTED_TARGETS:
        if re.search(rf"^\s{{2}}{re.escape(target)}:\s*$", manifest_text, re.MULTILINE):
            targets.append(target)
    return targets


def run_build(repo_root: Path, target: str) -> None:
    build_script = repo_root / "paperclips" / "build.sh"
    subprocess.run(["bash", str(build_script), "--target", target], cwd=repo_root, check=True)


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
        targets = declared_targets(manifest.read_text())
        if args.target != "all":
            targets = [target for target in targets if target == args.target]
        if not targets:
            raise ValueError(f"project {args.project} declares no build targets for {args.target}")
        for target in targets:
            run_build(repo_root, target)
        run_inventory(repo_root, args.inventory)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Paperclip project build OK: {args.project} ({', '.join(targets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
