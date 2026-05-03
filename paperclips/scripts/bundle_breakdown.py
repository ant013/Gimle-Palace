#!/usr/bin/env python3
"""Report expanded Paperclip bundle size by inline role text and fragments."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

ROLE_SPECS = [
    (
        "claude:blockchain-engineer",
        "claude",
        "paperclips/roles/blockchain-engineer.md",
        "paperclips/dist/blockchain-engineer.md",
    ),
    (
        "claude:code-reviewer",
        "claude",
        "paperclips/roles/code-reviewer.md",
        "paperclips/dist/code-reviewer.md",
    ),
    (
        "claude:python-engineer",
        "claude",
        "paperclips/roles/python-engineer.md",
        "paperclips/dist/python-engineer.md",
    ),
    (
        "claude:mcp-engineer",
        "claude",
        "paperclips/roles/mcp-engineer.md",
        "paperclips/dist/mcp-engineer.md",
    ),
    ("claude:cto", "claude", "paperclips/roles/cto.md", "paperclips/dist/cto.md"),
    (
        "codex:cx-mcp-engineer",
        "codex",
        "paperclips/roles-codex/cx-mcp-engineer.md",
        "paperclips/dist/codex/cx-mcp-engineer.md",
    ),
    (
        "codex:cx-python-engineer",
        "codex",
        "paperclips/roles-codex/cx-python-engineer.md",
        "paperclips/dist/codex/cx-python-engineer.md",
    ),
]


@dataclass
class Component:
    kind: str
    path: str
    bytes: int
    lines: int
    token_estimate: int
    include_count: int = 1


def token_estimate(byte_count: int) -> int:
    return (byte_count + 3) // 4


def codex_transform(text: str) -> str:
    replacements = [
        ("CLAUDE.md", "AGENTS.md"),
        ("claude CLI cache", "session cache"),
        ("Claude CLI cache", "session cache"),
        ("claude CLI", "session cache"),
        ("Claude CLI", "session cache"),
        ("OpusArchitectReviewer", "CodexArchitectReviewer"),
        ("Opus adversarial", "Codex adversarial"),
        ("superpowers:writing-plans", "create-plan"),
        ("superpowers:", "codex-discipline:"),
        ("pr-review-toolkit:", "codex-review:"),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    return text


def strip_front_matter(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return text

    start = end_index + 1
    if start < len(lines) and lines[start].strip() == "":
        start += 1
    return "".join(lines[start:])


def metric(text: str) -> tuple[int, int, int]:
    byte_count = len(text.encode("utf-8"))
    line_count = text.count("\n")
    return byte_count, line_count, token_estimate(byte_count)


def add_component(
    components: dict[tuple[str, str], Component], kind: str, path: str, text: str
) -> None:
    if not text:
        return
    byte_count, line_count, tokens = metric(text)
    key = (kind, path)
    if key in components:
        existing = components[key]
        existing.bytes += byte_count
        existing.lines += line_count
        existing.token_estimate = token_estimate(existing.bytes)
        existing.include_count += 1
        return
    components[key] = Component(kind, path, byte_count, line_count, tokens)


def analyze_role(role_id: str, target: str, source_path: str, dist_path: str) -> dict:
    source_abs = REPO_ROOT / source_path
    dist_abs = REPO_ROOT / dist_path
    role_text = strip_front_matter(source_abs.read_text())
    components: dict[tuple[str, str], Component] = {}
    inline_buffer: list[str] = []
    expanded_parts: list[str] = []

    def flush_inline() -> None:
        if not inline_buffer:
            return
        text = "".join(inline_buffer)
        if target == "codex":
            text = codex_transform(text)
        add_component(components, "inline-role-text", source_path, text)
        expanded_parts.append(text)
        inline_buffer.clear()

    for line in role_text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("<!-- @include fragments/") and stripped.endswith("-->"):
            flush_inline()
            fragment_rel = stripped.split("fragments/", 1)[1].split(".md", 1)[0] + ".md"
            fragment_path = f"paperclips/fragments/{fragment_rel}"
            fragment_text = (REPO_ROOT / fragment_path).read_text()
            if target == "codex":
                fragment_text = codex_transform(fragment_text)
            add_component(components, "fragment", fragment_path, fragment_text)
            expanded_parts.append(fragment_text)
        else:
            inline_buffer.append(line)
    flush_inline()

    expanded = "".join(expanded_parts)
    actual = dist_abs.read_text()
    if expanded != actual:
        raise SystemExit(f"expanded output mismatch for {role_id}: {dist_path}")

    total_bytes, total_lines, total_tokens = metric(actual)
    ordered_components = sorted(
        components.values(), key=lambda item: item.bytes, reverse=True
    )

    return {
        "roleId": role_id,
        "target": target,
        "source": source_path,
        "dist": dist_path,
        "total": {
            "bytes": total_bytes,
            "lines": total_lines,
            "tokenEstimate": total_tokens,
        },
        "components": [
            {
                "kind": component.kind,
                "path": component.path,
                "bytes": component.bytes,
                "lines": component.lines,
                "tokenEstimate": component.token_estimate,
                "includeCount": component.include_count,
            }
            for component in ordered_components
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="paperclips/bundle-size-breakdown.json",
        help="Path to write JSON report, relative to repo root.",
    )
    args = parser.parse_args()

    roles = [analyze_role(*spec) for spec in ROLE_SPECS]
    report = {
        "schemaVersion": 1,
        "generatedAt": date.today().isoformat(),
        "tokenEstimate": "ceil(bytes / 4)",
        "scope": "Task 1.5 heavy-bundle sample before slimming",
        "roles": roles,
    }
    output_path = REPO_ROOT / args.output
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
