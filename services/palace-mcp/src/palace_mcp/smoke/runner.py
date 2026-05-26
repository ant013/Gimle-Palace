"""Runtime smoke runner — deterministic stage pipeline.

Orchestrates preflight → prepare → build_scip → register_project →
run_extractors → report.  Separate ``semantic_probe`` mode runs after
a successful smoke and is *not* part of the smoke pass/fail gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from palace_mcp.smoke import mcp_caller
from palace_mcp.smoke.preflight import run_preflight
from palace_mcp.smoke.recipe import Recipe
from palace_mcp.smoke.runtime_binding import RuntimeBinding
from palace_mcp.smoke.swift_package import build_swift_package_invocation
from palace_mcp.smoke.xcode_workspace import (
    apply_prepare_steps,
    build_xcode_workspace_invocation,
)

logger = logging.getLogger(__name__)


class _StageFailure(Exception):
    """Internal: a stage failed but produced partial details to preserve."""

    def __init__(self, message: str, details: dict[str, Any]) -> None:
        super().__init__(message)
        self.details = details


class _StageSkipped(Exception):
    """Internal: a stage intentionally skipped itself (e.g. skip_build_reason)."""

    def __init__(self, reason: str, details: dict[str, Any]) -> None:
        super().__init__(reason)
        self.details = details


# ---------------------------------------------------------------------------
# Stage models
# ---------------------------------------------------------------------------

SMOKE_STAGES: tuple[str, ...] = (
    "preflight",
    "prepare",
    "build_scip",
    "register_project",
    "run_extractors",
    "report",
)


class StageStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageResult(BaseModel, frozen=True):
    stage: str
    status: StageStatus
    duration_ms: int = 0
    error: str | None = None
    details: dict[str, Any] = {}


class RunReport(BaseModel, frozen=True):
    recipe_slug: str
    mode: str
    dry_run: bool
    started_at: str
    finished_at: str
    stages: list[StageResult]
    passed: bool
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class SmokeRunner:
    """Deterministic stage runner for palace runtime smoke."""

    def __init__(
        self,
        recipe: Recipe,
        binding: RuntimeBinding,
        *,
        dry_run: bool = False,
    ) -> None:
        self._recipe = recipe
        self._binding = binding
        self._dry_run = dry_run
        self._warnings: list[str] = []

    async def run_smoke(self) -> RunReport:
        return await self._run_pipeline("smoke")

    async def run_semantic_probe(self) -> RunReport:
        return await self._run_pipeline("semantic_probe")

    # -- pipeline orchestration ---------------------------------------------

    async def _run_pipeline(self, mode: str) -> RunReport:
        started_at = _now_iso()
        results: list[StageResult] = []
        failed = False

        stage_methods = {
            "preflight": self._stage_preflight,
            "prepare": self._stage_prepare,
            "build_scip": self._stage_build_scip,
            "register_project": self._stage_register_project,
            "run_extractors": self._stage_run_extractors,
        }

        for stage_name in SMOKE_STAGES:
            if stage_name == "report":
                break

            if failed:
                results.append(
                    StageResult(stage=stage_name, status=StageStatus.SKIPPED)
                )
                logger.info("[%s] SKIPPED (prior failure)", stage_name)
                continue

            mutating = stage_name in (
                "build_scip",
                "register_project",
                "run_extractors",
            )
            if self._dry_run and mutating:
                results.append(
                    StageResult(stage=stage_name, status=StageStatus.SKIPPED)
                )
                logger.info("[%s] SKIPPED (dry-run)", stage_name)
                continue

            method = stage_methods[stage_name]
            result = await self._execute_stage(stage_name, method)
            results.append(result)

            if result.status == StageStatus.FAILED:
                failed = True

        report_result = self._build_report_stage(results)
        results.append(report_result)

        finished_at = _now_iso()
        overall_passed = all(r.status != StageStatus.FAILED for r in results)
        return RunReport(
            recipe_slug=self._recipe.slug,
            mode=mode,
            dry_run=self._dry_run,
            started_at=started_at,
            finished_at=finished_at,
            stages=results,
            passed=overall_passed,
            warnings=list(self._warnings),
        )

    async def _execute_stage(self, name: str, method: Any) -> StageResult:
        logger.info("[%s] START", name)
        t0 = time.monotonic()
        try:
            details = await method()
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info("[%s] PASSED (%dms)", name, duration_ms)
            return StageResult(
                stage=name,
                status=StageStatus.PASSED,
                duration_ms=duration_ms,
                details=details or {},
            )
        except _StageSkipped as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info("[%s] SKIPPED (%dms): %s", name, duration_ms, str(exc))
            return StageResult(
                stage=name,
                status=StageStatus.SKIPPED,
                duration_ms=duration_ms,
                details=exc.details,
            )
        except _StageFailure as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = str(exc)
            logger.error("[%s] FAILED (%dms): %s", name, duration_ms, error_msg)
            return StageResult(
                stage=name,
                status=StageStatus.FAILED,
                duration_ms=duration_ms,
                error=error_msg,
                details=exc.details,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            error_msg = str(exc)
            logger.error("[%s] FAILED (%dms): %s", name, duration_ms, error_msg)
            return StageResult(
                stage=name,
                status=StageStatus.FAILED,
                duration_ms=duration_ms,
                error=error_msg,
            )

    # -- stage implementations ---------------------------------------------

    async def _stage_preflight(self) -> dict[str, Any]:
        report = await run_preflight(self._recipe, self._binding)
        if not report.passed:
            raise _StageFailure(
                "; ".join(report.actionable_failures[:5]),
                {
                    "checks": [c.model_dump() for c in report.checks],
                    "actionable_failures": report.actionable_failures,
                },
            )

        scip_parent = (self._binding.repo_path / self._recipe.scip_path).parent
        if not scip_parent.is_dir():
            scip_parent.mkdir(parents=True, exist_ok=True)

        return {
            "checks": [c.model_dump() for c in report.checks],
            "all_passed": True,
        }

    async def _stage_prepare(self) -> dict[str, Any]:
        apply_prepare_steps(self._recipe, self._binding)
        return {"steps_applied": len(self._recipe.prepare_steps)}

    async def _stage_build_scip(self) -> dict[str, Any]:
        # Bug 4: honour skip_build_reason before attempting any build
        if self._recipe.build.skip_build_reason is not None:
            raise _StageSkipped(
                self._recipe.build.skip_build_reason,
                {"skip_reason": self._recipe.build.skip_build_reason},
            )

        if self._recipe.build_system == "xcode_workspace":
            invocation = build_xcode_workspace_invocation(self._recipe, self._binding)
            proc = await asyncio.create_subprocess_exec(
                *invocation.command,
                cwd=invocation.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await proc.communicate()
            if proc.returncode != 0:
                tail = (stdout_bytes or b"").decode(errors="replace")[-2000:]
                raise RuntimeError(f"xcodebuild exited {proc.returncode}\n{tail}")
            scip_path = self._binding.repo_path / self._recipe.scip_path
            scip_size = scip_path.stat().st_size if scip_path.exists() else 0
            # Bug 3: fail explicitly when SCIP is missing or empty
            if scip_size == 0:
                raise _StageFailure(
                    "SCIP file missing or empty after xcodebuild",
                    {
                        "build_system": self._recipe.build_system,
                        "scip_path": str(scip_path),
                    },
                )
            return {
                "build_system": self._recipe.build_system,
                "scip_size_bytes": scip_size,
            }

        if self._recipe.build_system == "swift_package":
            spm_invocation = build_swift_package_invocation(self._recipe, self._binding)
            if spm_invocation.scip_reused:
                scip_path = self._binding.repo_path / self._recipe.scip_path
                return {
                    "build_system": self._recipe.build_system,
                    "scip_reused": True,
                    "scip_size_bytes": scip_path.stat().st_size,
                }
            proc = await asyncio.create_subprocess_exec(
                *spm_invocation.command,
                cwd=spm_invocation.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await proc.communicate()
            if proc.returncode != 0:
                tail = (stdout_bytes or b"").decode(errors="replace")[-2000:]
                raise RuntimeError(f"swift build exited {proc.returncode}\n{tail}")
            scip_path = self._binding.repo_path / self._recipe.scip_path
            scip_size = scip_path.stat().st_size if scip_path.exists() else 0
            # Bug 3: fail explicitly when SCIP is missing or empty
            if scip_size == 0:
                raise _StageFailure(
                    "SCIP file missing or empty after swift build",
                    {
                        "build_system": self._recipe.build_system,
                        "scip_path": str(scip_path),
                    },
                )
            return {
                "build_system": self._recipe.build_system,
                "scip_reused": False,
                "scip_size_bytes": scip_size,
            }

        raise RuntimeError(f"no adapter for build_system={self._recipe.build_system!r}")

    async def _stage_register_project(self) -> dict[str, Any]:
        result = await mcp_caller.register_project(
            self._binding.mcp_url,
            slug=self._recipe.slug,
            name=self._recipe.name,
            language=self._recipe.language,
            parent_mount=self._binding.mount_name,  # Bug 2a: use mount_name not path
            relative_path=str(
                self._binding.repo_path.relative_to(self._binding.parent_mount)
            ),
        )
        # Bug 2b: treat explicit ok=false as a hard failure
        if result.get("ok") is False:
            raise _StageFailure(
                result.get("message", "register_project returned ok=false"),
                {
                    "error_code": result.get("error_code"),
                    "message": result.get("message"),
                },
            )
        return {"register_response": result}

    async def _stage_run_extractors(self) -> dict[str, Any]:
        extractor_results: list[dict[str, Any]] = []
        any_failed = False

        for ext_name in self._recipe.extractors:
            logger.info("[run_extractors] running %s", ext_name)
            try:
                result = await mcp_caller.run_extractor(
                    self._binding.mcp_url,
                    extractor_name=ext_name,
                    project=self._recipe.slug,
                )
                extractor_results.append(result.model_dump())
                if not result.ok:
                    any_failed = True
                    self._warnings.append(
                        f"extractor {ext_name} returned ok=false: {result.message}"
                    )
                    logger.warning(
                        "[run_extractors] %s failed: %s", ext_name, result.message
                    )
                else:
                    logger.info("[run_extractors] %s ok", ext_name)
            except Exception as exc:
                any_failed = True
                extractor_results.append(
                    {
                        "ok": False,
                        "extractor_name": ext_name,
                        "error_code": "call_failed",
                        "message": str(exc),
                    }
                )
                self._warnings.append(f"extractor {ext_name} call failed: {exc}")
                logger.warning("[run_extractors] %s call failed: %s", ext_name, exc)

        details: dict[str, Any] = {"extractors": extractor_results}
        if any_failed:
            raise _StageFailure("one or more extractors failed", details)
        return details

    # -- report stage -------------------------------------------------------

    def _build_report_stage(self, prior_results: list[StageResult]) -> StageResult:
        t0 = time.monotonic()
        try:
            report_data = {
                "recipe_slug": self._recipe.slug,
                "dry_run": self._dry_run,
                "stages": [r.model_dump() for r in prior_results],
                "warnings": list(self._warnings),
            }
            logger.info("[report] --- smoke report ---")
            logger.info(json.dumps(report_data, indent=2))
            duration_ms = int((time.monotonic() - t0) * 1000)
            return StageResult(
                stage="report",
                status=StageStatus.PASSED,
                duration_ms=duration_ms,
                details=report_data,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.error("[report] FAILED: %s", exc)
            return StageResult(
                stage="report",
                status=StageStatus.FAILED,
                duration_ms=duration_ms,
                error=str(exc),
            )


def write_report_json(report: RunReport, path: Path) -> None:
    """Write a RunReport to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), indent=2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
