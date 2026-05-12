"""Shared semgrep subprocess runner for loc-a11y rules.

Follows the error_handling_policy pattern:
  semgrep --config <rules_dir> --json <target_dir> → parse JSON → map to findings.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from palace_mcp.extractors.base import ExtractorConfigError

logger = logging.getLogger(__name__)

_SEMGREP_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
}

# Contexts matched by rule metadata.context field
_CONTEXT_MAP: dict[str, str] = {
    "swiftui_text": "swiftui_text",
    "uikit_label": "uikit_label",
    "compose_text": "compose_text",
    "view_xml": "view_xml",
}


@dataclass(frozen=True)
class SemgrepFinding:
    """Normalised finding from semgrep JSON output."""

    file: str
    start_line: int
    end_line: int
    rule_id: str
    check_kind: str  # "hardcoded_string" | "a11y_missing"
    context: str  # surface context from rule metadata
    severity: str
    literal: str  # the matched text (truncated to 100 chars)
    message: str


async def run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    timeout_s: int = 120,
    extra_args: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Invoke semgrep as async subprocess, return raw results list."""
    if not rules_dir.exists():
        raise ExtractorConfigError(f"semgrep rules directory not found: {rules_dir}")

    cmd = [
        "semgrep",
        "--config",
        str(rules_dir),
        "--json",
        "--quiet",
        *(extra_args or []),
        str(target),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise ExtractorConfigError(f"semgrep timed out after {timeout_s}s on {target}")

    # semgrep exits 0 on no findings, 1 on findings found — both are fine
    if proc.returncode not in (0, 1):
        stderr_text = stderr_b.decode("utf-8", errors="replace")[:500]
        raise ExtractorConfigError(
            f"semgrep exited {proc.returncode}: {stderr_text}"
        )

    try:
        output = json.loads(stdout_b.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ExtractorConfigError(f"semgrep output not valid JSON: {exc}") from exc

    results = output.get("results", [])
    if not isinstance(results, list):
        raise ExtractorConfigError("semgrep output missing results list")
    return [item for item in results if isinstance(item, dict)]


def normalise_findings(
    raw: list[dict[str, Any]],
    *,
    repo_root: Path,
) -> list[SemgrepFinding]:
    """Map raw semgrep JSON results to SemgrepFinding records."""
    findings: list[SemgrepFinding] = []
    for result in raw:
        extra = result.get("extra", {}) or {}
        metadata = extra.get("metadata", {}) or {}
        start = result.get("start", {}) or {}
        end = result.get("end", {}) or {}

        path_str = str(result.get("path", ""))
        file = _relative_path(repo_root, path_str)
        start_line = int(start.get("line", 1)) if isinstance(start, dict) else 1
        end_line = int(end.get("line", start_line)) if isinstance(end, dict) else start_line

        rule_id = str(result.get("check_id", "unknown"))
        severity = _SEMGREP_SEVERITY_MAP.get(
            str(extra.get("severity", "INFO")).upper(), "low"
        )
        context = str(metadata.get("context", "other"))
        check_kind = str(metadata.get("kind", "hardcoded_string"))
        message = str(extra.get("message", ""))

        # matched text — truncated to 100 chars per spec
        matched = str(extra.get("lines", "")).strip()[:100]

        findings.append(
            SemgrepFinding(
                file=file,
                start_line=start_line,
                end_line=end_line,
                rule_id=rule_id,
                check_kind=check_kind,
                context=context,
                severity=severity,
                literal=matched,
                message=message,
            )
        )
    return findings


def _relative_path(repo_root: Path, path_str: str) -> str:
    raw = Path(path_str)
    if raw.is_absolute():
        try:
            return raw.relative_to(repo_root).as_posix()
        except ValueError:
            return raw.as_posix()
    return raw.as_posix()
