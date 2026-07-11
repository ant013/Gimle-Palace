"""Shared semgrep subprocess runner for palace-mcp extractors (GIM-355).

Wraps semgrep subprocess invocation with stop-list-aware file enumeration
via walk_repo(). Individual file paths are always passed to semgrep; a bare
directory is never passed (prevents semgrep's own walker from escaping the
stop-list).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from palace_mcp.extractors.base import ExtractorConfigError
from palace_mcp.extractors.foundation.walk import walk_repo

logger = logging.getLogger(__name__)

_DEFAULT_SUFFIXES: frozenset[str] = frozenset({".swift"})
_DEFAULT_BATCH_SIZE = 64

_DEFAULT_TEST_PATH_PARTS: frozenset[str] = frozenset(
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


class SemgrepConfigInvalidError(ExtractorConfigError):
    error_code = "semgrep_config_invalid"


class SemgrepTargetError(ExtractorConfigError):
    error_code = "semgrep_target_error"


class SemgrepInternalError(ExtractorConfigError):
    error_code = "semgrep_internal_error"


async def run_semgrep(
    *,
    rules_dir: Path,
    target: Path,
    target_paths: list[Path] | None = None,
    suffixes: frozenset[str] = _DEFAULT_SUFFIXES,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    timeout_s: int = 120,
    extra_args: list[str] | None = None,
    skip_test_paths: bool = False,
    test_path_parts: frozenset[str] | None = None,
    extra_excludes: frozenset[str] = frozenset(),
    exclude_globs: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """Invoke semgrep with stop-list-aware file enumeration.

    Uses walk_repo() for file discovery (never passes a bare directory to semgrep),
    splits files into batches, and returns merged raw results.
    """
    if not rules_dir.exists():
        raise ExtractorConfigError(f"semgrep rules directory not found: {rules_dir}")

    if target_paths is not None:
        file_targets = sorted(path for path in target_paths if path.is_file())
    elif target.is_file():
        file_targets = [target]
    else:
        parts = (
            test_path_parts if test_path_parts is not None else _DEFAULT_TEST_PATH_PARTS
        )
        file_targets = sorted(
            p
            for p in walk_repo(
                target,
                suffixes=suffixes,
                extra_excludes=extra_excludes,
                exclude_globs=exclude_globs,
            )
            if not skip_test_paths
            or not _is_test_path(p, relative_to=target, test_parts=parts)
        )

    if not file_targets:
        return []

    results: list[dict[str, Any]] = []
    for batch in _batches(file_targets, batch_size):
        results.extend(
            await _run_batch(
                rules_dir=rules_dir,
                targets=batch,
                timeout_s=timeout_s,
                extra_args=extra_args,
            )
        )
    return results


def _batches(files: list[Path], size: int) -> list[list[Path]]:
    return [files[i : i + size] for i in range(0, len(files), size)]


async def _run_batch(
    *,
    rules_dir: Path,
    targets: list[Path],
    timeout_s: int,
    extra_args: list[str] | None,
) -> list[dict[str, Any]]:
    cmd = [
        "semgrep",
        "--config",
        str(rules_dir),
        "--json",
        "--quiet",
        *(extra_args or []),
        *(str(t) for t in targets),
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
        raise SemgrepInternalError(
            f"semgrep timed out after {timeout_s}s on {targets[0]}"
        )

    assert proc.returncode is not None
    if proc.returncode not in (0, 1):
        raise _classify_failure(
            proc.returncode,
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


def _is_test_path(path: Path, *, relative_to: Path, test_parts: frozenset[str]) -> bool:
    if ".test." in path.stem.lower():
        return True
    try:
        rel_parts = path.relative_to(relative_to).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in test_parts for part in rel_parts)


def _classify_failure(
    returncode: int, stdout_text: str, stderr_text: str
) -> ExtractorConfigError:
    detail = _failure_detail(stdout_text, stderr_text)
    lowered = detail.lower()
    if any(
        m in lowered
        for m in (
            "invalid scanning root",
            "invalid configuration",
            "invalid rule",
            "parse error",
        )
    ):
        cls: type[ExtractorConfigError] = SemgrepConfigInvalidError
    elif any(
        m in lowered
        for m in (
            "no such file",
            "not found",
            "permission denied",
            "unreadable",
            "unable to read",
        )
    ):
        cls = SemgrepTargetError
    else:
        cls = SemgrepInternalError
    return cls(f"semgrep exited {returncode}: {detail}")


def _failure_detail(stdout_text: str, stderr_text: str) -> str:
    stderr_detail = stderr_text.strip()
    stdout_detail = _stdout_error(stdout_text) or stdout_text.strip()
    if stderr_detail and stdout_detail:
        return f"{stderr_detail}\n{stdout_detail}"
    return stderr_detail or stdout_detail or "no diagnostic output"


def _stdout_error(stdout_text: str) -> str:
    try:
        payload = json.loads(stdout_text)
    except json.JSONDecodeError:
        return ""
    errors = payload.get("errors", [])
    if not isinstance(errors, list):
        return ""
    return "\n".join(
        str(item.get("message", "")).strip()
        for item in errors
        if isinstance(item, dict) and str(item.get("message", "")).strip()
    )
