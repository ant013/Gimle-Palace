#!/usr/bin/env python3
"""Generate the Paperclip assembly inventory used by layered build migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import validate_instructions


DEFAULT_OUTPUT = Path("paperclips/assembly-inventory.json")

PROJECT_LITERAL_PATTERNS = (
    {
        "id": "gimle-name",
        "pattern": r"\bGimle\b|Gimle-Palace",
        "classification": "project-owned",
    },
    {
        "id": "gimle-issue-prefix",
        "pattern": r"\bGIM-\d+\b|\bGIM-NN?\b",
        "classification": "project-owned",
    },
    {
        "id": "gimle-codebase-memory-project",
        "pattern": r"\brepos-gimle\b",
        "classification": "project-owned",
    },
    {
        "id": "gimle-shared-worktree-path",
        "pattern": r"/Users/Shared/Ios/[A-Za-z0-9_./-]*Gimle-Palace",
        "classification": "project-owned",
    },
    {
        "id": "palace-service-name",
        "pattern": r"\bpalace[-_.][A-Za-z0-9_.-]+|\bpalace\.[A-Za-z0-9_.-]+",
        "classification": "project-owned",
    },
    {
        "id": "unstoppable-domain-reference",
        "pattern": r"\bUnstoppable\b",
        "classification": "project-owned",
    },
)

LITERAL_SCAN_ROOTS = (
    "paperclips/roles",
    "paperclips/roles-codex",
    "paperclips/fragments/local",
    "paperclips/fragments/codex",
    "paperclips/fragments/shared/fragments",
    "paperclips/fragments/shared/templates",
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dist_path_for_role(repo_root: Path, meta: validate_instructions.RoleMeta) -> Path:
    name = meta.role_id.split(":", 1)[1]
    if meta.target == "codex":
        return repo_root / "paperclips" / "dist" / "codex" / f"{name}.md"
    return repo_root / "paperclips" / "dist" / f"{name}.md"


def role_entry(
    repo_root: Path,
    role_id: str,
    role_data: dict,
) -> dict:
    source = repo_root / str(role_data["source"])
    meta = validate_instructions.load_role_front_matter(source)
    dist_path = dist_path_for_role(repo_root, meta)
    text = dist_path.read_text()

    return {
        "roleId": role_id,
        "family": meta.family,
        "profiles": meta.profiles,
        "source": str(source.relative_to(repo_root)),
        "dist": str(dist_path.relative_to(repo_root)),
        "bytes": len(text.encode("utf-8")),
        "lines": text.count("\n"),
        "tokenEstimate": validate_instructions.token_estimate(len(text.encode("utf-8"))),
        "sha256": sha256_text(text),
        "handoffMarkers": {
            marker: marker in text
            for marker in validate_instructions.REQUIRED_HANDOFF_MARKERS
        },
    }


def collect_roles(repo_root: Path) -> dict[str, dict]:
    matrix = validate_instructions.load_coverage_matrix(
        repo_root / "paperclips" / "instruction-coverage.matrix.yaml"
    )
    targets: dict[str, dict] = {
        "claude": {"roles": [], "totalBytes": 0},
        "codex": {"roles": [], "totalBytes": 0},
    }

    for role_id, role_data in sorted(matrix["roles"].items()):
        entry = role_entry(repo_root, role_id, role_data)
        target = str(role_data["target"])
        targets[target]["roles"].append(entry)
        targets[target]["totalBytes"] += int(entry["bytes"])

    return targets


def iter_scan_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root in LITERAL_SCAN_ROOTS:
        path = repo_root / root
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
    return sorted(set(files))


def scan_project_literals(repo_root: Path) -> list[dict]:
    files = iter_scan_files(repo_root)
    inventory: list[dict] = []

    for pattern in PROJECT_LITERAL_PATTERNS:
        regex = re.compile(str(pattern["pattern"]))
        occurrences = 0
        paths: set[str] = set()
        for path in files:
            text = path.read_text(errors="ignore")
            matches = list(regex.finditer(text))
            if not matches:
                continue
            occurrences += len(matches)
            paths.add(str(path.relative_to(repo_root)))
        inventory.append(
            {
                "id": pattern["id"],
                "pattern": pattern["pattern"],
                "classification": pattern["classification"],
                "occurrenceCount": occurrences,
                "paths": sorted(paths),
            }
        )

    return inventory


def build_inventory(repo_root: Path) -> dict:
    return {
        "schemaVersion": 1,
        "project": "gimle",
        "sourceFiles": {
            "coverageMatrix": "paperclips/instruction-coverage.matrix.yaml",
            "projectManifest": "paperclips/projects/gimle/paperclip-agent-assembly.yaml",
            "bundleSizeBaseline": "paperclips/bundle-size-baseline.json",
        },
        "requiredProjectMcp": list(validate_instructions.REQUIRED_PROJECT_MCP),
        "mandatoryHandoffMarkers": list(validate_instructions.REQUIRED_HANDOFF_MARKERS),
        "targets": collect_roles(repo_root),
        "projectLiteralScanRoots": list(LITERAL_SCAN_ROOTS),
        "projectLiterals": scan_project_literals(repo_root),
        "legacyCompatibilityInputs": [
            "paperclips/codex-agent-ids.env",
            "paperclips/deploy-agents.sh",
            "paperclips/deploy-codex-agents.sh",
            "paperclips/update-agent-workspaces.sh",
        ],
    }


def canonical_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo_root / args.output
    generated = canonical_json(build_inventory(repo_root))

    if args.check:
        if not output.is_file():
            print(f"ERROR: missing assembly inventory: {output.relative_to(repo_root)}", file=sys.stderr)
            return 1
        current = output.read_text()
        if current != generated:
            print(f"ERROR: stale assembly inventory: {output.relative_to(repo_root)}", file=sys.stderr)
            print("Run: python3 paperclips/scripts/generate_assembly_inventory.py", file=sys.stderr)
            return 1
        print("Paperclip assembly inventory OK")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated)
    print(f"wrote {output.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
