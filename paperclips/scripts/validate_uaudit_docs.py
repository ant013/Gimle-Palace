#!/usr/bin/env python3
"""Validate UAudit dispatcher/routine documentation stays consistent."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_uaudit_routines import load_config, required_agent_names, resolve_agent_ids  # noqa: E402

DOC_PATHS = [
    Path("docs/paperclip-operations/telegram-report-delivery.md"),
    Path("docs/superpowers/specs/2026-05-12-uaudit-infra-incremental-orchestrator.md"),
    Path("docs/superpowers/specs/2026-05-11-uaudit-report-delivery-owner.md"),
    Path("docs/superpowers/plans/2026-05-15-uaa-phase-F-uaudit-migration.md"),
    Path("paperclips/scripts/imac-agents-deploy.README.md"),
]

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
STALE_PATTERNS = (
    "UAudit daily version-branch audits are owned end-to-end by infra agents",
    "Android assignee: `UWAInfraEngineer`",
    "iOS assignee: `UWIInfraEngineer`",
    "If the cursor file is missing, create it",
)


def iter_existing_docs(paths: Iterable[Path]) -> Iterable[Path]:
    for rel in paths:
        path = REPO_ROOT / rel
        if path.is_file():
            yield path


def validate_links(path: Path, errors: list[str]) -> None:
    text = path.read_text()
    for match in MD_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(REPO_ROOT.resolve())
        except ValueError:
            errors.append(f"{path.relative_to(REPO_ROOT)}: link escapes repo: {target}")
            continue
        if not resolved.exists():
            errors.append(f"{path.relative_to(REPO_ROOT)}: broken link: {target}")


def validate_stale_language(path: Path, errors: list[str]) -> None:
    text = path.read_text()
    doc_marked_superseded = "SUPERSEDED" in text[:700]
    for stale in STALE_PATTERNS:
        if stale in text and not doc_marked_superseded:
            errors.append(f"{path.relative_to(REPO_ROOT)}: stale UAudit ownership text lacks SUPERSEDED marker: {stale}")


def validate_config(errors: list[str]) -> None:
    config = load_config()
    agents = resolve_agent_ids("uaudit", None)
    missing = sorted(required_agent_names(config) - set(agents))
    if missing:
        errors.append(f"routine config references unknown agents: {missing}")
    raw = (REPO_ROOT / "paperclips/projects/uaudit/daily-version-branch-routines.yaml").read_text()
    if UUID_RE.search(raw):
        errors.append("daily-version-branch-routines.yaml must use agent names, not UUIDs")
    if "required_subagents" in raw or "uaudit-" in raw:
        errors.append("daily version-branch routines must use Paperclip agents, not Codex subagent rosters")
    limits = config.get("limits", {})
    if limits.get("max_files") != 300:
        errors.append("daily routine max_files must be 300")
    dispatchers = {r.get("platform"): r.get("dispatcher") for r in config.get("routines", [])}
    if dispatchers.get("android") != "UWACTO" or dispatchers.get("ios") != "UWICTO":
        errors.append(f"daily routines must point to platform CTO dispatchers, got {dispatchers}")


def main() -> int:
    errors: list[str] = []
    validate_config(errors)
    for path in iter_existing_docs(DOC_PATHS):
        validate_links(path, errors)
        validate_stale_language(path, errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("UAudit docs validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
