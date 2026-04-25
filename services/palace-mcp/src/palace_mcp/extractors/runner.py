"""Extractor runner — lifecycle orchestration.

Split into _precheck / _execute / _finalize + run_extractor orchestrator.
Each helper is independently testable.

Runner keeps direct driver access for :IngestRun ops-log writes (per spec §3.9).
Product-layer entities flow through Graphiti only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union
from uuid import uuid4

from graphiti_core import Graphiti
from neo4j import AsyncDriver

from palace_mcp.extractors import registry
from palace_mcp.extractors.base import (
    BaseExtractor,
    ExtractorError,
    ExtractorRunContext,
    ExtractorStats,
)
from palace_mcp.extractors.cypher import CREATE_INGEST_RUN, FINALIZE_INGEST_RUN
from palace_mcp.extractors.schemas import (
    ExtractorErrorResponse,
    ExtractorRunResponse,
)
from palace_mcp.memory.projects import InvalidSlug, validate_slug

REPOS_ROOT = Path("/repos")
EXTRACTOR_TIMEOUT_S = 300.0

GET_PROJECT = "MATCH (p:Project {slug: $slug}) RETURN p"


# --- precheck ---


@dataclass(frozen=True)
class _PrecheckOk:
    extractor: BaseExtractor
    repo_path: Path
    group_id: str


@dataclass(frozen=True)
class _PrecheckError:
    error_code: str
    message: str
    extractor: str | None = None


_PrecheckResult = Union[_PrecheckOk, _PrecheckError]


async def _precheck(
    *, name: str, project: str, driver: AsyncDriver, repos_root: Path
) -> _PrecheckResult:
    """Validate slug, look up extractor, verify :Project + repo mount."""
    try:
        validate_slug(project)
    except InvalidSlug as e:
        return _PrecheckError(error_code="invalid_slug", message=str(e))

    extractor = registry.get(name)
    if extractor is None:
        return _PrecheckError(
            error_code="unknown_extractor",
            message=f"no extractor named {name!r}",
        )

    async with driver.session() as session:
        result = await session.run(GET_PROJECT, slug=project)
        row = await result.single()
    if row is None:
        return _PrecheckError(
            error_code="project_not_registered",
            message=f"no :Project {{name: {project!r}}}",
            extractor=name,
        )

    repo_path = repos_root / project
    if not repo_path.is_dir() or not (repo_path / ".git").exists():
        return _PrecheckError(
            error_code="repo_not_mounted",
            message=f"no mounted git repo at {repo_path}",
            extractor=name,
        )

    group_id = f"project/{project}"
    return _PrecheckOk(extractor=extractor, repo_path=repo_path, group_id=group_id)


# --- execute ---


@dataclass(frozen=True)
class _ExecuteOk:
    stats: ExtractorStats


@dataclass(frozen=True)
class _ExecuteError:
    error_code: str
    errors: list[str]


_ExecuteResult = Union[_ExecuteOk, _ExecuteError]


async def _execute(
    *,
    extractor: BaseExtractor,
    graphiti: Graphiti,
    ctx: ExtractorRunContext,
    timeout_s: float,
) -> _ExecuteResult:
    """Wrap run() in timeout + Exception handling. Never raises."""
    logger = ctx.logger
    try:
        stats = await asyncio.wait_for(
            extractor.run(graphiti=graphiti, ctx=ctx), timeout=timeout_s
        )
        return _ExecuteOk(stats=stats)
    except asyncio.TimeoutError:
        msg = f"timeout after {timeout_s}s"
        logger.error("extractor.execute.timeout", extra={"run_id": ctx.run_id})
        return _ExecuteError(error_code="extractor_runtime_error", errors=[msg])
    except ExtractorError as e:
        logger.error(
            "extractor.execute.extractor_error",
            extra={"run_id": ctx.run_id, "error_code": e.error_code},
        )
        return _ExecuteError(error_code=e.error_code, errors=[str(e)[:200]])
    except Exception as e:  # noqa: BLE001 — unexpected, structured response
        logger.exception("extractor.execute.unhandled")
        return _ExecuteError(
            error_code="unknown",
            errors=[f"{type(e).__name__}: {str(e)[:200]}"],
        )


# --- finalize ---


async def _finalize(
    *,
    driver: AsyncDriver,
    run_id: str,
    result: _ExecuteResult,
    finished_at: str,
    duration_ms: int,
) -> tuple[int, int, list[str], bool]:
    """Write FINALIZE_INGEST_RUN. Returns (nodes, edges, errors, success)."""
    if isinstance(result, _ExecuteOk):
        nodes, edges, errors, success = (
            result.stats.nodes_written,
            result.stats.edges_written,
            [],
            True,
        )
    else:
        nodes, edges, errors, success = 0, 0, result.errors, False

    async with driver.session() as session:
        await session.run(
            FINALIZE_INGEST_RUN,
            id=run_id,
            finished_at=finished_at,
            duration_ms=duration_ms,
            nodes_written=nodes,
            edges_written=edges,
            errors=errors,
            success=success,
        )
    return nodes, edges, errors, success


# --- orchestrator ---


async def run_extractor(
    name: str,
    project: str,
    *,
    driver: AsyncDriver,
    graphiti: Graphiti,
    timeout_s: float = EXTRACTOR_TIMEOUT_S,
) -> dict[str, Any]:
    """Full lifecycle: precheck → create :IngestRun → execute → finalize."""
    # 1. Precheck (driver used for :Project lookup)
    pre = await _precheck(
        name=name, project=project, driver=driver, repos_root=REPOS_ROOT
    )
    if isinstance(pre, _PrecheckError):
        return ExtractorErrorResponse(
            error_code=pre.error_code,
            message=pre.message,
            extractor=pre.extractor,
            project=project,
        ).model_dump()

    # 2. Create :IngestRun (driver — ops-log, not Graphiti product layer)
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    source = f"extractor.{name}"

    async with driver.session() as session:
        await session.run(
            CREATE_INGEST_RUN,
            id=run_id,
            source=source,
            group_id=pre.group_id,
            started_at=started_at,
        )

    # 3. Execute
    logger = logging.getLogger(f"palace_mcp.extractors.{name}")
    logger.info(
        "extractor.run.start",
        extra={
            "extractor": name,
            "project": project,
            "run_id": run_id,
            "group_id": pre.group_id,
        },
    )
    start_mono = time.monotonic()
    ctx = ExtractorRunContext(
        project_slug=project,
        group_id=pre.group_id,
        repo_path=pre.repo_path,
        run_id=run_id,
        duration_ms=0,  # placeholder; extractor may use ctx.duration_ms for metadata
        logger=logger,
    )
    exec_result = await _execute(
        extractor=pre.extractor, graphiti=graphiti, ctx=ctx, timeout_s=timeout_s
    )
    duration_ms = int((time.monotonic() - start_mono) * 1000)
    finished_at = datetime.now(timezone.utc).isoformat()

    # 4. Finalize (driver — ops-log)
    nodes, edges, errors, success = await _finalize(
        driver=driver,
        run_id=run_id,
        result=exec_result,
        finished_at=finished_at,
        duration_ms=duration_ms,
    )

    # 5. Return response
    if success:
        logger.info(
            "extractor.run.finish",
            extra={
                "extractor": name,
                "project": project,
                "run_id": run_id,
                "duration_ms": duration_ms,
                "nodes_written": nodes,
                "edges_written": edges,
                "success": True,
            },
        )
        return ExtractorRunResponse(
            run_id=run_id,
            extractor=name,
            project=project,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            nodes_written=nodes,
            edges_written=edges,
        ).model_dump()

    assert isinstance(exec_result, _ExecuteError)
    logger.error(
        "extractor.run.error",
        extra={
            "extractor": name,
            "project": project,
            "run_id": run_id,
            "duration_ms": duration_ms,
            "error_code": exec_result.error_code,
            "error_head": errors[0] if errors else "",
        },
    )
    return ExtractorErrorResponse(
        error_code=exec_result.error_code,
        message=errors[0] if errors else "",
        extractor=name,
        project=project,
        run_id=run_id,
    ).model_dump()
