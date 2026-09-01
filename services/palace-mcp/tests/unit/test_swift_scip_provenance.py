from __future__ import annotations

import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from palace_mcp.extractors.foundation.baseline import (
    BASELINE_STATUS_VALID,
    ExtractorBaseline,
)
from palace_mcp.swift_scip_provenance import (
    SWIFT_SCIP_EMITTER_NAME,
    SWIFT_SCIP_EMITTER_VERSION,
    SwiftScipProvenancePolicy,
    git_head_sha,
    inspect_swift_scip_index_state,
    inspect_swift_scip_provenance,
    swift_scip_file_digest,
    swift_scip_metadata_path,
)


def _run(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_repo(path: Path) -> str:
    path.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], path)
    _run(["git", "config", "user.email", "t@t"], path)
    _run(["git", "config", "user.name", "T"], path)
    (path / "Package.swift").write_text("// swift-tools-version: 6.0\n")
    _run(["git", "add", "."], path)
    _run(["git", "commit", "-q", "-m", "initial"], path)
    return _run(["git", "rev-parse", "HEAD"], path)


def _write_artifact(
    *,
    repo: Path,
    slug: str,
    head: str,
    destination_repo_path: str | None = None,
) -> Path:
    scip_path = repo / "scip" / "index.scip"
    scip_path.parent.mkdir(parents=True, exist_ok=True)
    scip_path.write_bytes(b"current-scip")
    metadata = {
        "slug": slug,
        "repo_head_sha": head,
        "emitter_name": SWIFT_SCIP_EMITTER_NAME,
        "emitter_version": SWIFT_SCIP_EMITTER_VERSION,
        "artifact_origin": "local",
        "package_path": "Package.swift",
        "generator_host": socket.gethostname(),
        "source_repo_path": str(repo.resolve()),
        "destination_repo_path": destination_repo_path or str(repo.resolve()),
    }
    swift_scip_metadata_path(scip_path).write_text(json.dumps(metadata))
    return scip_path


def _baseline(*, head: str, scip_digest: str | None) -> ExtractorBaseline:
    return ExtractorBaseline(
        project_id="project/tron-kit",
        project_slug="tron-kit",
        extractor="symbol_index_swift",
        baseline_kind="swift_symbol_scope",
        state_version=1,
        commit_sha=head,
        indexed_commit=head,
        scip_digest=scip_digest,
        scip_path="scip/index.scip",
        scip_document_count=1,
        scip_occurrence_count=1,
        body_hash_manifest_digest="sha256:body",
        file_count=1,
        successful_run_id="run-1",
        status=BASELINE_STATUS_VALID,
        invalid_reason=None,
        updated_at=datetime.now(tz=timezone.utc),
    )


def test_consumption_accepts_configured_mount_translation(tmp_path: Path) -> None:
    repo = tmp_path / "mounted" / "TronKit.Swift"
    head = _make_repo(repo)
    scip_path = _write_artifact(
        repo=repo,
        slug="tron-kit",
        head=head,
        destination_repo_path="/Users/host/TronKit.Swift",
    )

    consumed = inspect_swift_scip_provenance(
        repo_path=repo,
        project_slug="tron-kit",
        scip_path=scip_path,
        policy=SwiftScipProvenancePolicy.CONSUMPTION,
    )
    prepared = inspect_swift_scip_provenance(
        repo_path=repo,
        project_slug="tron-kit",
        scip_path=scip_path,
        policy=SwiftScipProvenancePolicy.PREPARATION,
    )

    assert consumed.current is True
    assert prepared.current is False
    assert prepared.reason == "destination_repo_path_mismatch"


def test_provenance_rejects_stale_commit_and_wrong_slug(tmp_path: Path) -> None:
    repo = tmp_path / "TronKit.Swift"
    head = _make_repo(repo)
    scip_path = _write_artifact(repo=repo, slug="wrong-kit", head="old-head")

    stale = inspect_swift_scip_provenance(
        repo_path=repo,
        project_slug="tron-kit",
        scip_path=scip_path,
        policy=SwiftScipProvenancePolicy.CONSUMPTION,
    )
    assert stale.current is False
    assert stale.repo_head_sha == head
    assert stale.reason == "repo_head_sha_mismatch"

    metadata = json.loads(swift_scip_metadata_path(scip_path).read_text())
    metadata["repo_head_sha"] = head
    swift_scip_metadata_path(scip_path).write_text(json.dumps(metadata))
    wrong_slug = inspect_swift_scip_provenance(
        repo_path=repo,
        project_slug="tron-kit",
        scip_path=scip_path,
        policy=SwiftScipProvenancePolicy.CONSUMPTION,
    )
    assert wrong_slug.current is False
    assert wrong_slug.reason == "slug_mismatch"


def test_git_head_sha_supports_linked_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _make_repo(repo)
    worktree = tmp_path / "linked"
    _run(["git", "worktree", "add", "-q", "-b", "topic", str(worktree)], repo)

    assert (worktree / ".git").is_file()
    assert git_head_sha(worktree) == _run(["git", "rev-parse", "HEAD"], worktree)


@pytest.mark.asyncio
async def test_index_state_requires_current_artifact_digest_in_baseline(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "TronKit.Swift"
    head = _make_repo(repo)
    scip_path = _write_artifact(repo=repo, slug="tron-kit", head=head)
    actual_digest = swift_scip_file_digest(scip_path)

    with patch(
        "palace_mcp.swift_scip_provenance.load_extractor_baseline",
        new=AsyncMock(return_value=_baseline(head=head, scip_digest="sha256:old")),
    ):
        stale = await inspect_swift_scip_index_state(
            AsyncMock(),
            project_slug="tron-kit",
            project_id="project/tron-kit",
            repo_path=repo,
        )

    assert stale.current is False
    assert stale.stale is True
    assert stale.reason == "scip_baseline_digest_mismatch"

    with patch(
        "palace_mcp.swift_scip_provenance.load_extractor_baseline",
        new=AsyncMock(return_value=_baseline(head=head, scip_digest=actual_digest)),
    ):
        current = await inspect_swift_scip_index_state(
            AsyncMock(),
            project_slug="tron-kit",
            project_id="project/tron-kit",
            repo_path=repo,
        )

    assert current.current is True
    assert current.reason == "current"
