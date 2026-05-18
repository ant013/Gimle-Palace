"""Semgrep runner for loc-a11y rules (GIM-355: migrated to foundation runner).

Thin wrapper around foundation.semgrep_runner that adds normalise_findings()
and the SemgrepFinding dataclass. Error classes are re-exported from foundation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from palace_mcp.extractors.foundation.semgrep_runner import (  # noqa: F401 — re-export
    SemgrepConfigInvalidError,
    SemgrepInternalError,
    SemgrepTargetError,
    run_semgrep as _foundation_run_semgrep,
)

logger = logging.getLogger(__name__)

_SEMGREP_SEVERITY_MAP: dict[str, str] = {
    "CRITICAL": "critical",
    "ERROR": "high",
    "WARNING": "medium",
    "INFO": "low",
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


_SEMGREP_EXTENSIONS = frozenset((".swift", ".kt", ".kts"))

# Relative path components that identify test code (LA-D3)
_TEST_PATH_PARTS = frozenset(
    {
        "Tests",
        "Test",
        "UnitTests",
        "UITests",
        "test",
        "androidTest",
        "AndroidTest",
    }
)


async def run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    timeout_s: int = 120,
    extra_args: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Invoke semgrep with stop-list-aware enumeration, return raw results.

    Delegates to foundation.semgrep_runner with skip_test_paths=True and
    the loc-a11y extension set. Never passes a bare directory to semgrep.
    """
    return await _foundation_run_semgrep(
        rules_dir=rules_dir,
        target=target,
        suffixes=_SEMGREP_EXTENSIONS,
        timeout_s=timeout_s,
        extra_args=extra_args,
        skip_test_paths=True,
        test_path_parts=_TEST_PATH_PARTS,
    )


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
        end_line = (
            int(end.get("line", start_line)) if isinstance(end, dict) else start_line
        )

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
