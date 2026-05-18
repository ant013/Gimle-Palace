#!/usr/bin/env python3
"""Validate generated Codex bundles against the Codex runtime capability map."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


CAPABILITY_RE = re.compile(
    r"\b("
    r"superpowers:[A-Za-z0-9_-]+"
    r"|pr-review-toolkit:[A-Za-z0-9_*-]+"
    r"|claude-api"
    r")\b"
)

HARD_FORBIDDEN_RE = re.compile(
    r"Claude Code|Claude CLI|claude CLI|CLAUDE\.md|OpusArchitectReviewer|\bOpus\b"
)

VALID_CAPABILITY_STATUSES = {"confirmed", "partial", "instruction_equivalent"}


@dataclass(frozen=True)
class Finding:
    path: Path
    line_no: int
    text: str
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line_no}: {self.message}\n  {self.text}"


def _is_antipattern_line(line: str) -> bool:
    lowered = line.lower()
    return "❌" in line or "anti-pattern" in lowered or "do not use" in lowered


def _load_concepts(runtime_map: Path) -> list[dict[str, object]]:
    data = json.loads(runtime_map.read_text())
    return list(data.get("concepts", []))


def _matching_concept(ref: str, concepts: list[dict[str, object]]) -> dict[str, object] | None:
    for concept in concepts:
        claude_ref = str(concept.get("claude", ""))
        if claude_ref == ref:
            return concept
        if claude_ref.startswith(ref + " "):
            return concept
        if claude_ref.endswith(":*") and ref.startswith(claude_ref[:-1]):
            return concept
    return None


def validate_codex_runtime_refs(codex_dist: Path, runtime_map: Path) -> list[Finding]:
    concepts = _load_concepts(runtime_map)
    findings: list[Finding] = []

    for bundle in sorted(codex_dist.glob("*.md")):
        for idx, line in enumerate(bundle.read_text().splitlines(), start=1):
            if _is_antipattern_line(line):
                continue

            hard_match = HARD_FORBIDDEN_RE.search(line)
            if hard_match:
                findings.append(
                    Finding(
                        bundle,
                        idx,
                        line,
                        f"hard-forbidden Claude runtime reference: {hard_match.group(0)}",
                    )
                )

            for match in CAPABILITY_RE.finditer(line):
                ref = match.group(1)
                concept = _matching_concept(ref, concepts)
                if concept is None:
                    findings.append(
                        Finding(bundle, idx, line, f"unmapped Codex runtime capability reference: {ref}")
                    )
                    continue

                status = str(concept.get("status", ""))
                if status == "gap":
                    findings.append(
                        Finding(bundle, idx, line, f"runtime capability gap is referenced in Codex bundle: {ref}")
                    )
                elif status not in VALID_CAPABILITY_STATUSES:
                    findings.append(
                        Finding(
                            bundle,
                            idx,
                            line,
                            f"invalid runtime-map status {status!r} for capability reference: {ref}",
                        )
                    )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-dist", type=Path, required=True)
    parser.add_argument("--runtime-map", type=Path, required=True)
    args = parser.parse_args()

    if not args.codex_dist.is_dir():
        print(f"ERROR: Codex dist not found: {args.codex_dist}", file=sys.stderr)
        return 1
    if not args.runtime_map.is_file():
        print(f"ERROR: Codex runtime map not found: {args.runtime_map}", file=sys.stderr)
        return 1

    findings = validate_codex_runtime_refs(args.codex_dist, args.runtime_map)
    if findings:
        print("ERROR: Codex output contains unsupported runtime references", file=sys.stderr)
        for finding in findings:
            print(finding.format(), file=sys.stderr)
        return 1

    print(f"Codex runtime references OK: {args.codex_dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
