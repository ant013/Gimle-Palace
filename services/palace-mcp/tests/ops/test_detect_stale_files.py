from __future__ import annotations

import hashlib
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path

import pytest

from palace_mcp.ops.detect_stale_files import _classify_file
from palace_mcp.ops.detect_stale_files import _repo_path_for_project
from palace_mcp.ops.detect_stale_files import _should_ignore
from palace_mcp.memory.schema import ProjectInfo


def _project_info() -> ProjectInfo:
    return ProjectInfo(
        slug="tron-kit",
        name="tron-kit",
        tags=[],
        relative_path="TronKit.Swift",
        language_profile="swift_kit",
    )


def test_repo_path_for_project_uses_workspace_root_when_parent_mount_missing(
    tmp_path: Path,
) -> None:
    repo_path = _repo_path_for_project(_project_info(), tmp_path)
    assert repo_path == tmp_path / "TronKit.Swift"


def test_should_ignore_matches_globs() -> None:
    assert _should_ignore("Sources/Foo.generated.swift", ["*.generated.swift"])
    assert not _should_ignore("Sources/Foo.swift", ["*.generated.swift"])


@pytest.mark.asyncio
async def test_classify_file_marks_null_finished_at_as_stale(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "Sources" / "Wallet.swift"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("struct Wallet {}\n", encoding="utf-8")

    decision = await _classify_file(
        repo_path=repo_path,
        relative_path="Sources/Wallet.swift",
        previous_body_hash="abc",
        finished_at=None,
        ignore_globs=[],
    )

    assert decision.bucket == "stale"
    assert decision.reason == "ingest_run_unfinished"


@pytest.mark.asyncio
async def test_classify_file_marks_metadata_only_change_without_reingest(
    tmp_path: Path,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "Sources" / "Wallet.swift"
    file_path.parent.mkdir(parents=True)
    body = "struct Wallet {}\n"
    file_path.write_text(body, encoding="utf-8")
    older = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    file_path.touch()

    previous_body_hash = hashlib.sha256(body.encode()).hexdigest()

    decision = await _classify_file(
        repo_path=repo_path,
        relative_path="Sources/Wallet.swift",
        previous_body_hash=previous_body_hash,
        finished_at=older,
        ignore_globs=[],
    )

    assert decision.mtime is not None
    assert decision.bucket == "metadata_only"
    assert decision.reason == "mtime_newer_but_body_hash_unchanged"


@pytest.mark.asyncio
async def test_classify_file_marks_content_change_as_stale(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "Sources" / "Wallet.swift"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("struct Wallet { let id: Int }\n", encoding="utf-8")
    older = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()

    decision = await _classify_file(
        repo_path=repo_path,
        relative_path="Sources/Wallet.swift",
        previous_body_hash="different",
        finished_at=older,
        ignore_globs=[],
    )

    assert decision.bucket == "stale"
    assert decision.reason == "mtime_newer_than_finished_at"
