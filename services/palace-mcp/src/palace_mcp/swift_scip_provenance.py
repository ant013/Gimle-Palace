"""Swift SCIP artifact provenance and durable-baseline parity checks."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from neo4j import AsyncDriver

from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    ExtractorBaseline,
    load_extractor_baseline,
)

SWIFT_SCIP_EMITTER_NAME = "palace-swift-scip-emit-cli"
SWIFT_SCIP_EMITTER_VERSION = "2026-05-15"
SWIFT_SYMBOL_BASELINE_KIND = "swift_symbol_scope"
SWIFT_SYMBOL_BASELINE_STATE_VERSION = 1
SWIFT_SYMBOL_EXTRACTOR = "symbol_index_swift"


class SwiftScipProvenancePolicy(StrEnum):
    """Validation policy for host preparation versus mounted consumption."""

    PREPARATION = "preparation"
    CONSUMPTION = "consumption"


@dataclass(frozen=True)
class SwiftScipProvenance:
    current: bool
    reason: str
    repo_head_sha: str | None
    artifact_commit_sha: str | None
    scip_digest: str | None
    metadata_path: Path
    metadata: dict[str, Any] | None


@dataclass(frozen=True)
class SwiftScipIndexState:
    current: bool
    reason: str
    stale: bool | None
    provenance: SwiftScipProvenance
    baseline: ExtractorBaseline | None


def swift_scip_metadata_path(scip_path: Path) -> Path:
    return Path(f"{scip_path}.meta.json")


def load_swift_scip_metadata(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.is_file():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def swift_scip_file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


def git_head_sha(repo_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if value else None


def validate_swift_scip_metadata(
    *,
    repo_path: Path,
    repo_head_sha: str,
    metadata: dict[str, Any] | None,
    project_slug: str | None = None,
    policy: SwiftScipProvenancePolicy = SwiftScipProvenancePolicy.PREPARATION,
) -> tuple[bool, str]:
    """Return whether metadata must be rejected and a stable reason."""
    if metadata is None:
        return True, "metadata_missing_or_invalid"

    expected_package_path = (
        "Wallet.xcworkspace"
        if (project_slug or metadata.get("slug")) == "uw-ios-app"
        else "Package.swift"
    )
    required: dict[str, object] = {
        "repo_head_sha": repo_head_sha,
        "emitter_name": SWIFT_SCIP_EMITTER_NAME,
        "emitter_version": SWIFT_SCIP_EMITTER_VERSION,
        "package_path": expected_package_path,
    }
    if project_slug is not None:
        required["slug"] = project_slug
    if policy is SwiftScipProvenancePolicy.PREPARATION:
        required["destination_repo_path"] = str(repo_path.resolve())

    for key, expected in required.items():
        if metadata.get(key) != expected:
            return True, f"{key}_mismatch"

    source_repo_path = metadata.get("source_repo_path")
    destination_repo_path = metadata.get("destination_repo_path")
    generator_host = metadata.get("generator_host")
    if not isinstance(source_repo_path, str) or not source_repo_path:
        return True, "source_repo_path_missing"
    if not isinstance(destination_repo_path, str) or not destination_repo_path:
        return True, "destination_repo_path_missing"
    if not isinstance(generator_host, str) or not generator_host:
        return True, "generator_host_missing"

    if policy is SwiftScipProvenancePolicy.CONSUMPTION:
        return False, "metadata_current"
    if metadata.get("artifact_origin") == "remote_copy":
        return False, "metadata_current_remote_copy"
    if source_repo_path != str(repo_path.resolve()):
        return True, "source_repo_path_mismatch"
    if generator_host != socket.gethostname():
        return True, "generator_host_mismatch"
    return False, "metadata_current"


def inspect_swift_scip_provenance(
    *,
    repo_path: Path,
    project_slug: str,
    scip_path: Path,
    policy: SwiftScipProvenancePolicy,
) -> SwiftScipProvenance:
    metadata_path = swift_scip_metadata_path(scip_path)
    metadata = load_swift_scip_metadata(metadata_path)
    repo_head = git_head_sha(repo_path)
    artifact_commit = (
        str(metadata["repo_head_sha"])
        if metadata is not None and metadata.get("repo_head_sha")
        else None
    )

    if not scip_path.is_file():
        return SwiftScipProvenance(
            False,
            "scip_artifact_missing",
            repo_head,
            artifact_commit,
            None,
            metadata_path,
            metadata,
        )
    try:
        if scip_path.stat().st_size == 0:
            return SwiftScipProvenance(
                False,
                "scip_artifact_empty",
                repo_head,
                artifact_commit,
                None,
                metadata_path,
                metadata,
            )
    except OSError:
        return SwiftScipProvenance(
            False,
            "scip_artifact_unreadable",
            repo_head,
            artifact_commit,
            None,
            metadata_path,
            metadata,
        )
    if repo_head is None:
        return SwiftScipProvenance(
            False,
            "repo_head_unavailable",
            None,
            artifact_commit,
            None,
            metadata_path,
            metadata,
        )

    stale, reason = validate_swift_scip_metadata(
        repo_path=repo_path,
        repo_head_sha=repo_head,
        metadata=metadata,
        project_slug=project_slug,
        policy=policy,
    )
    if stale:
        return SwiftScipProvenance(
            False,
            reason,
            repo_head,
            artifact_commit,
            None,
            metadata_path,
            metadata,
        )
    digest = swift_scip_file_digest(scip_path)
    if digest is None:
        return SwiftScipProvenance(
            False,
            "scip_artifact_unreadable",
            repo_head,
            artifact_commit,
            None,
            metadata_path,
            metadata,
        )
    return SwiftScipProvenance(
        True,
        reason,
        repo_head,
        artifact_commit,
        digest,
        metadata_path,
        metadata,
    )


async def inspect_swift_scip_index_state(
    driver: AsyncDriver,
    *,
    project_slug: str,
    project_id: str,
    repo_path: Path,
    scip_path: Path | None = None,
) -> SwiftScipIndexState:
    artifact_path = scip_path or repo_path / "scip" / "index.scip"
    provenance = inspect_swift_scip_provenance(
        repo_path=repo_path,
        project_slug=project_slug,
        scip_path=artifact_path,
        policy=SwiftScipProvenancePolicy.CONSUMPTION,
    )
    baseline = await load_extractor_baseline(
        driver,
        project_id=project_id,
        extractor=SWIFT_SYMBOL_EXTRACTOR,
        baseline_kind=SWIFT_SYMBOL_BASELINE_KIND,
    )
    if not provenance.current:
        stale = (
            True
            if provenance.reason in {"repo_head_sha_mismatch", "slug_mismatch"}
            else None
        )
        return SwiftScipIndexState(
            False, provenance.reason, stale, provenance, baseline
        )
    if baseline is None:
        return SwiftScipIndexState(
            False, "scip_baseline_missing", None, provenance, None
        )
    if (
        baseline.status != BASELINE_STATUS_VALID
        or baseline.state_version != SWIFT_SYMBOL_BASELINE_STATE_VERSION
    ):
        return SwiftScipIndexState(
            False, "scip_baseline_invalid", None, provenance, baseline
        )
    if baseline.commit_sha != provenance.repo_head_sha:
        return SwiftScipIndexState(
            False, "scip_baseline_commit_mismatch", True, provenance, baseline
        )
    if not baseline.scip_digest:
        return SwiftScipIndexState(
            False, "scip_baseline_digest_missing", None, provenance, baseline
        )
    if baseline.scip_digest != provenance.scip_digest:
        return SwiftScipIndexState(
            False, "scip_baseline_digest_mismatch", True, provenance, baseline
        )
    return SwiftScipIndexState(True, "current", False, provenance, baseline)
