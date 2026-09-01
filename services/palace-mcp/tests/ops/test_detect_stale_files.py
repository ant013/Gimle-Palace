from __future__ import annotations

import hashlib
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.ops.detect_stale_files import _classify_file
from palace_mcp.ops.detect_stale_files import detect_project_stale_files
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


@pytest.mark.parametrize(
    "reason",
    ["repo_head_sha_mismatch", "scip_baseline_digest_mismatch"],
)
@pytest.mark.asyncio
async def test_detector_requires_reingest_for_noncurrent_swift_scip_state(
    tmp_path: Path,
    reason: str,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    source_path = repo_path / "Sources" / "Wallet.swift"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("struct Wallet {}\n", encoding="utf-8")
    body_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

    class _Result:
        def __init__(
            self,
            *,
            single_row: dict[str, Any] | None = None,
            rows: list[dict[str, Any]] | None = None,
        ) -> None:
            self.single_row = single_row
            self.rows = rows or []

        async def single(self) -> dict[str, Any] | None:
            return self.single_row

        async def data(self) -> list[dict[str, Any]]:
            return self.rows

    async def _run(query: str, **_params: Any) -> _Result:
        if "IngestRun" in query:
            return _Result(
                single_row={
                    "run_id": "run-1",
                    "finished_at": "2099-01-01T00:00:00+00:00",
                }
            )
        return _Result(rows=[{"path": "Sources/Wallet.swift", "body_hash": body_hash}])

    session = MagicMock()
    session.run = _run
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    driver = MagicMock()
    driver.session.return_value = session
    project = ProjectInfo(
        slug="swift-kit",
        name="Swift Kit",
        tags=[],
        repo_path=str(repo_path),
        language_profile="swift_kit",
    )

    with patch(
        "palace_mcp.ops.detect_stale_files.inspect_swift_scip_index_state",
        new=AsyncMock(
            return_value=SimpleNamespace(current=False, stale=True, reason=reason)
        ),
    ) as inspect_mock:
        report = await detect_project_stale_files(
            driver,
            project=project,
            workspace_root=tmp_path,
            ignore_globs=[],
        )

    assert report.stale_files == []
    assert report.requires_reingest is True
    assert report.project_reason == reason
    inspect_mock.assert_awaited_once_with(
        driver,
        project_slug="swift-kit",
        project_id="project/swift-kit",
        repo_path=repo_path,
    )
