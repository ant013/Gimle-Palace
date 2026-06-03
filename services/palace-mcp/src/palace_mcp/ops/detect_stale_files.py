"""Detect stale Swift ingest files by comparing mtimes to :IngestRun.finished_at."""

from __future__ import annotations

import argparse
import asyncio
import fnmatch
import hashlib
import json
import logging
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver
from neo4j import AsyncGraphDatabase

from palace_mcp.cache import hydration_semaphore
from palace_mcp.config import Settings
from palace_mcp.memory.project_tools import list_projects
from palace_mcp.memory.schema import ProjectInfo

logger = logging.getLogger(__name__)

_READ_LATEST_INGEST_RUN = """
MATCH (r:IngestRun {project: $project, extractor_name: 'symbol_index_swift'})
RETURN r.run_id AS run_id,
       r.started_at AS started_at,
       r.finished_at AS finished_at
ORDER BY r.started_at DESC
LIMIT 1
"""

_READ_PROJECT_FILES = """
MATCH (f:File {project_id: $project})
RETURN f.path AS path, f.body_hash AS body_hash
ORDER BY f.path
"""


@dataclass(frozen=True)
class FileDecision:
    path: str
    bucket: str
    reason: str
    mtime: str | None = None
    finished_at: str | None = None
    previous_body_hash: str | None = None
    current_body_hash: str | None = None


@dataclass(frozen=True)
class ProjectReport:
    project: str
    repo_path: str
    language_profile: str | None
    run_id: str | None
    finished_at: str | None
    requires_reingest: bool
    project_reason: str | None
    stale_files: list[dict[str, Any]]
    metadata_only_files: list[dict[str, Any]]
    ignored_files: list[dict[str, Any]]
    errors: list[str]


def _finished_at_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _should_ignore(path: str, ignore_globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in ignore_globs)


def _repo_path_for_project(project: ProjectInfo, workspace_root: Path) -> Path | None:
    relative = project.relative_path or project.slug
    if not relative:
        return None
    if project.parent_mount:
        return Path(f"/repos-{project.parent_mount}") / relative
    return workspace_root / relative


async def _classify_file(
    *,
    repo_path: Path,
    relative_path: str,
    previous_body_hash: str,
    finished_at: str | None,
    ignore_globs: list[str],
) -> FileDecision:
    if _should_ignore(relative_path, ignore_globs):
        return FileDecision(
            path=relative_path,
            bucket="ignored",
            reason="ignore_glob_match",
            finished_at=finished_at,
        )

    file_path = repo_path / relative_path
    if finished_at is None:
        return FileDecision(
            path=relative_path,
            bucket="stale",
            reason="ingest_run_unfinished",
            previous_body_hash=previous_body_hash or None,
        )

    try:
        stat_result = await asyncio.to_thread(file_path.stat)
    except FileNotFoundError:
        return FileDecision(
            path=relative_path,
            bucket="stale",
            reason="missing_on_disk",
            finished_at=finished_at,
            previous_body_hash=previous_body_hash or None,
        )

    mtime_iso = _iso_from_epoch(stat_result.st_mtime)
    finished_at_dt = _finished_at_dt(finished_at)
    if finished_at_dt is None:
        return FileDecision(
            path=relative_path,
            bucket="stale",
            reason="ingest_run_unfinished",
            previous_body_hash=previous_body_hash or None,
        )
    if stat_result.st_mtime <= finished_at_dt.timestamp():
        return FileDecision(
            path=relative_path,
            bucket="fresh",
            reason="mtime_not_newer_than_finished_at",
            mtime=mtime_iso,
            finished_at=finished_at,
        )

    current_body_hash = await asyncio.to_thread(_file_hash, file_path)
    if previous_body_hash and current_body_hash == previous_body_hash:
        logger.info(
            "periodic_reingest.metadata_only_change project=%s path=%s",
            repo_path.name,
            relative_path,
        )
        return FileDecision(
            path=relative_path,
            bucket="metadata_only",
            reason="mtime_newer_but_body_hash_unchanged",
            mtime=mtime_iso,
            finished_at=finished_at,
            previous_body_hash=previous_body_hash,
            current_body_hash=current_body_hash,
        )

    return FileDecision(
        path=relative_path,
        bucket="stale",
        reason="mtime_newer_than_finished_at",
        mtime=mtime_iso,
        finished_at=finished_at,
        previous_body_hash=previous_body_hash or None,
        current_body_hash=current_body_hash,
    )


async def detect_project_stale_files(
    driver: AsyncDriver,
    *,
    project: ProjectInfo,
    workspace_root: Path,
    ignore_globs: list[str],
) -> ProjectReport:
    repo_path = _repo_path_for_project(project, workspace_root)
    if repo_path is None:
        return ProjectReport(
            project=project.slug,
            repo_path="",
            language_profile=project.language_profile,
            run_id=None,
            finished_at=None,
            requires_reingest=False,
            project_reason=None,
            stale_files=[],
            metadata_only_files=[],
            ignored_files=[],
            errors=["relative_path unavailable"],
        )
    if not repo_path.exists():
        return ProjectReport(
            project=project.slug,
            repo_path=str(repo_path),
            language_profile=project.language_profile,
            run_id=None,
            finished_at=None,
            requires_reingest=False,
            project_reason=None,
            stale_files=[],
            metadata_only_files=[],
            ignored_files=[],
            errors=[f"repo path missing: {repo_path}"],
        )

    async with driver.session() as session:
        run_row = await (
            await session.run(_READ_LATEST_INGEST_RUN, project=project.slug)
        ).single()
        files = await (
            await session.run(_READ_PROJECT_FILES, project=project.slug)
        ).data()

    run_id = str(run_row["run_id"]) if run_row and run_row["run_id"] is not None else None
    finished_at = (
        str(run_row["finished_at"]) if run_row and run_row["finished_at"] is not None else None
    )
    project_reason: str | None = None
    if run_row is None:
        project_reason = "ingest_run_missing"
    elif finished_at is None:
        project_reason = "ingest_run_unfinished"

    stale: list[dict[str, Any]] = []
    metadata_only: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    errors: list[str] = []

    async with hydration_semaphore("palace.ops.detect_stale_files"):
        for row in files:
            path = str(row["path"])
            previous_body_hash = str(row.get("body_hash") or "")
            try:
                decision = await _classify_file(
                    repo_path=repo_path,
                    relative_path=path,
                    previous_body_hash=previous_body_hash,
                    finished_at=finished_at,
                    ignore_globs=ignore_globs,
                )
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            payload = asdict(decision)
            if decision.bucket == "stale":
                stale.append(payload)
            elif decision.bucket == "metadata_only":
                metadata_only.append(payload)
            elif decision.bucket == "ignored":
                ignored.append(payload)

    return ProjectReport(
        project=project.slug,
        repo_path=str(repo_path),
        language_profile=project.language_profile,
        run_id=run_id,
        finished_at=finished_at,
        requires_reingest=bool(stale) or project_reason in {"ingest_run_missing", "ingest_run_unfinished"},
        project_reason=project_reason,
        stale_files=stale,
        metadata_only_files=metadata_only,
        ignored_files=ignored,
        errors=errors,
    )


async def detect_stale_files(
    driver: AsyncDriver,
    *,
    settings: Settings,
    selected_projects: list[str] | None = None,
    workspace_root: Path | None = None,
) -> list[ProjectReport]:
    workspace = workspace_root or Path(settings.palace_git_workspace)
    ignore_globs = settings.palace_periodic_reingest_ignore_globs
    requested = set(selected_projects or [])
    reports: list[ProjectReport] = []

    projects = await list_projects(driver)
    for project in projects:
        if requested and project.slug not in requested:
            continue
        if not requested and project.language_profile != "swift_kit":
            continue
        reports.append(
            await detect_project_stale_files(
                driver,
                project=project,
                workspace_root=workspace,
                ignore_globs=ignore_globs,
            )
        )

    if requested:
        found = {report.project for report in reports}
        for missing in sorted(requested - found):
            reports.append(
                ProjectReport(
                    project=missing,
                    repo_path="",
                    language_profile=None,
                    run_id=None,
                    finished_at=None,
                    requires_reingest=False,
                    project_reason=None,
                    stale_files=[],
                    metadata_only_files=[],
                    ignored_files=[],
                    errors=["project not registered"],
                )
            )

    return reports


async def _run_cli(args: argparse.Namespace) -> int:
    settings = Settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        reports = await detect_stale_files(
            driver,
            settings=settings,
            selected_projects=args.projects,
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
    finally:
        await driver.close()

    payload = {"projects": [asdict(report) for report in reports]}
    print(json.dumps(payload, indent=2))
    return 1 if any(report.errors for report in reports) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare project file mtimes against the latest symbol_index_swift "
            ":IngestRun.finished_at and report stale files."
        )
    )
    parser.add_argument(
        "--project",
        dest="projects",
        action="append",
        help="Project slug to scan. Repeat to target multiple projects.",
    )
    parser.add_argument(
        "--workspace-root",
        help="Override PALACE_GIT_WORKSPACE for projects without parent_mount.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run_cli(args)))


if __name__ == "__main__":
    main()
