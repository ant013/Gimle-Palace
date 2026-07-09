"""Durable per-extractor baseline state stored in Neo4j."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from neo4j import AsyncDriver


BASELINE_STATUS_VALID = "valid"


@dataclass(frozen=True)
class ExtractorBaseline:
    project_id: str
    project_slug: str
    extractor: str
    baseline_kind: str
    state_version: int
    commit_sha: str
    indexed_commit: str | None
    scip_digest: str | None
    scip_path: str | None
    scip_document_count: int | None
    scip_occurrence_count: int | None
    body_hash_manifest_digest: str | None
    file_count: int | None
    successful_run_id: str
    status: str
    invalid_reason: str | None
    updated_at: datetime


_LOAD_BASELINE_CYPHER = """
MATCH (b:ExtractorBaseline {
  project_id: $project_id,
  extractor: $extractor,
  baseline_kind: $baseline_kind
})
RETURN b.project_id AS project_id,
       b.project_slug AS project_slug,
       b.extractor AS extractor,
       b.baseline_kind AS baseline_kind,
       b.state_version AS state_version,
       b.commit_sha AS commit_sha,
       b.indexed_commit AS indexed_commit,
       b.scip_digest AS scip_digest,
       b.scip_path AS scip_path,
       b.scip_document_count AS scip_document_count,
       b.scip_occurrence_count AS scip_occurrence_count,
       b.body_hash_manifest_digest AS body_hash_manifest_digest,
       b.file_count AS file_count,
       b.successful_run_id AS successful_run_id,
       b.status AS status,
       b.invalid_reason AS invalid_reason,
       b.updated_at AS updated_at
"""

_UPSERT_BASELINE_CYPHER = """
MERGE (b:ExtractorBaseline {
  project_id: $project_id,
  extractor: $extractor,
  baseline_kind: $baseline_kind
})
SET b.project_slug = $project_slug,
    b.state_version = $state_version,
    b.commit_sha = $commit_sha,
    b.indexed_commit = $indexed_commit,
    b.scip_digest = $scip_digest,
    b.scip_path = $scip_path,
    b.scip_document_count = $scip_document_count,
    b.scip_occurrence_count = $scip_occurrence_count,
    b.body_hash_manifest_digest = $body_hash_manifest_digest,
    b.file_count = $file_count,
    b.successful_run_id = $successful_run_id,
    b.status = $status,
    b.invalid_reason = $invalid_reason,
    b.updated_at = $updated_at
"""

_DELETE_BASELINE_CYPHER = """
MATCH (b:ExtractorBaseline {
  project_id: $project_id,
  extractor: $extractor,
  baseline_kind: $baseline_kind
})
DELETE b
"""


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if hasattr(value, "to_native"):
        native = value.to_native()
        if isinstance(native, datetime):
            return native
    raise TypeError(f"cannot coerce Neo4j datetime value: {value!r}")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"cannot coerce Neo4j integer value: {value!r}")


async def load_extractor_baseline(
    driver: AsyncDriver,
    *,
    project_id: str,
    extractor: str,
    baseline_kind: str,
) -> ExtractorBaseline | None:
    async with driver.session() as session:
        result = await session.run(
            _LOAD_BASELINE_CYPHER,
            project_id=project_id,
            extractor=extractor,
            baseline_kind=baseline_kind,
        )
        record = await result.single()
    if record is None:
        return None
    return ExtractorBaseline(
        project_id=str(record["project_id"]),
        project_slug=str(record["project_slug"]),
        extractor=str(record["extractor"]),
        baseline_kind=str(record["baseline_kind"]),
        state_version=int(record["state_version"]),
        commit_sha=str(record["commit_sha"]),
        indexed_commit=(
            str(record["indexed_commit"])
            if record.get("indexed_commit") is not None
            else None
        ),
        scip_digest=(
            str(record["scip_digest"])
            if record.get("scip_digest") is not None
            else None
        ),
        scip_path=str(record["scip_path"])
        if record.get("scip_path") is not None
        else None,
        scip_document_count=_optional_int(record.get("scip_document_count")),
        scip_occurrence_count=_optional_int(record.get("scip_occurrence_count")),
        body_hash_manifest_digest=(
            str(record["body_hash_manifest_digest"])
            if record.get("body_hash_manifest_digest") is not None
            else None
        ),
        file_count=_optional_int(record.get("file_count")),
        successful_run_id=str(record["successful_run_id"]),
        status=str(record["status"]),
        invalid_reason=(
            str(record["invalid_reason"])
            if record.get("invalid_reason") is not None
            else None
        ),
        updated_at=_coerce_datetime(record["updated_at"]),
    )


async def upsert_extractor_baseline(
    driver: AsyncDriver,
    *,
    baseline: ExtractorBaseline,
) -> None:
    async with driver.session() as session:
        await session.run(
            _UPSERT_BASELINE_CYPHER,
            project_id=baseline.project_id,
            project_slug=baseline.project_slug,
            extractor=baseline.extractor,
            baseline_kind=baseline.baseline_kind,
            state_version=baseline.state_version,
            commit_sha=baseline.commit_sha,
            indexed_commit=baseline.indexed_commit,
            scip_digest=baseline.scip_digest,
            scip_path=baseline.scip_path,
            scip_document_count=baseline.scip_document_count,
            scip_occurrence_count=baseline.scip_occurrence_count,
            body_hash_manifest_digest=baseline.body_hash_manifest_digest,
            file_count=baseline.file_count,
            successful_run_id=baseline.successful_run_id,
            status=baseline.status,
            invalid_reason=baseline.invalid_reason,
            updated_at=baseline.updated_at.isoformat(),
        )


async def delete_extractor_baseline(
    driver: AsyncDriver,
    *,
    project_id: str,
    extractor: str,
    baseline_kind: str,
) -> None:
    async with driver.session() as session:
        await session.run(
            _DELETE_BASELINE_CYPHER,
            project_id=project_id,
            extractor=extractor,
            baseline_kind=baseline_kind,
        )


def build_valid_extractor_baseline(
    *,
    project_id: str,
    project_slug: str,
    extractor: str,
    baseline_kind: str,
    state_version: int,
    commit_sha: str,
    run_id: str,
    indexed_commit: str | None = None,
    scip_digest: str | None = None,
    scip_path: str | None = None,
    scip_document_count: int | None = None,
    scip_occurrence_count: int | None = None,
    body_hash_manifest_digest: str | None = None,
    file_count: int | None = None,
) -> ExtractorBaseline:
    return ExtractorBaseline(
        project_id=project_id,
        project_slug=project_slug,
        extractor=extractor,
        baseline_kind=baseline_kind,
        state_version=state_version,
        commit_sha=commit_sha,
        indexed_commit=indexed_commit,
        scip_digest=scip_digest,
        scip_path=scip_path,
        scip_document_count=scip_document_count,
        scip_occurrence_count=scip_occurrence_count,
        body_hash_manifest_digest=body_hash_manifest_digest,
        file_count=file_count,
        successful_run_id=run_id,
        status=BASELINE_STATUS_VALID,
        invalid_reason=None,
        updated_at=datetime.now(tz=timezone.utc),
    )
