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


class SemgrepConfigInvalidError(ExtractorConfigError):
    error_code = "semgrep_config_invalid"


class SemgrepTargetError(ExtractorConfigError):
    error_code = "semgrep_target_error"


class SemgrepInternalError(ExtractorConfigError):
    error_code = "semgrep_internal_error"


_SEMGREP_EXTENSIONS = frozenset((".swift", ".kt", ".kts"))
_GENERATED_CHECKOUT_PATH = (".build", "checkouts")
# Relative path components (within the target repo) that identify test code (LA-D3)
_TEST_PATH_PARTS = frozenset(
    {
        "Tests",  # iOS XCTest directories
        "Test",  # iOS XCTest (singular)
        "UnitTests",  # iOS unit test directories
        "UITests",  # iOS UI test directories
        "test",  # Kotlin/Android src/test/
        "androidTest",  # Android instrumented test src
        "AndroidTest",  # Android instrumented test src (uppercase variant)
    }
)


def _is_test_path(path: Path, *, relative_to: Path) -> bool:
    """Return True if path (relative to repo root) looks like a test file."""
    if ".test." in path.stem.lower():
        return True
    try:
        rel_parts = path.relative_to(relative_to).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in _TEST_PATH_PARTS for part in rel_parts)


def _is_generated_checkout_path(path: Path, *, relative_to: Path) -> bool:
    try:
        rel_parts = path.relative_to(relative_to).parts
    except ValueError:
        rel_parts = path.parts
    return rel_parts[: len(_GENERATED_CHECKOUT_PATH)] == _GENERATED_CHECKOUT_PATH


async def run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    timeout_s: int = 120,
    extra_args: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Invoke semgrep as async subprocess, return raw results list.

    Semgrep OSS does not reliably discover Swift/Kotlin files when scanning
    a directory (``paths.scanned`` is empty even with ``--include``).  When
    given a directory we therefore enumerate eligible files ourselves and pass
    them as individual path arguments, skipping test files per LA-D3.
    """
    if not rules_dir.exists():
        raise ExtractorConfigError(f"semgrep rules directory not found: {rules_dir}")

    if target.is_dir():
        file_targets = sorted(
            p
            for p in target.rglob("*")
            if p.is_file()
            and p.suffix in _SEMGREP_EXTENSIONS
            and not _is_generated_checkout_path(p, relative_to=target)
            and not _is_test_path(p, relative_to=target)
        )
        if not file_targets:
            return []
        if len(file_targets) > 5000:
            logger.warning(
                "localization_accessibility: %d source files collected; "
                "command line may be very long (followup: batching)",
                len(file_targets),
            )
        target_strs = [str(p) for p in file_targets]
    else:
        target_strs = [str(target)]

    cmd = [
        "semgrep",
        "--config",
        str(rules_dir),
        "--json",
        "--quiet",
        *(extra_args or []),
        *target_strs,
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
        raise SemgrepInternalError(f"semgrep timed out after {timeout_s}s on {target}")

    # semgrep exits 0 on no findings, 1 on findings found — both are fine
    returncode = proc.returncode
    assert returncode is not None
    if returncode not in (0, 1):
        raise _classify_semgrep_failure(
            returncode,
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
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


def _classify_semgrep_failure(
    returncode: int,
    stdout_text: str,
    stderr_text: str,
) -> ExtractorConfigError:
    detail = _semgrep_failure_detail(stdout_text, stderr_text)
    lowered = detail.lower()
    if any(
        marker in lowered
        for marker in (
            "invalid scanning root",
            "invalid configuration",
            "invalid rule",
            "parse error",
        )
    ):
        error_cls: type[ExtractorConfigError] = SemgrepConfigInvalidError
    elif any(
        marker in lowered
        for marker in (
            "no such file",
            "not found",
            "permission denied",
            "unreadable",
            "unable to read",
        )
    ):
        error_cls = SemgrepTargetError
    else:
        error_cls = SemgrepInternalError
    return error_cls(f"semgrep exited {returncode}: {detail}")


def _semgrep_failure_detail(stdout_text: str, stderr_text: str) -> str:
    stderr_detail = stderr_text.strip()
    stdout_detail = _semgrep_stdout_error(stdout_text) or stdout_text.strip()
    if stderr_detail and stdout_detail:
        return f"{stderr_detail}\n{stdout_detail}"
    if stderr_detail or stdout_detail:
        return stderr_detail or stdout_detail
    return "no diagnostic output"


def _semgrep_stdout_error(stdout_text: str) -> str:
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return ""
    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        return ""
    messages = [
        str(item.get("message", "")).strip()
        for item in errors
        if isinstance(item, dict) and str(item.get("message", "")).strip()
    ]
    return "\n".join(messages)
