from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.code.native_detect_changes import _valid_since, native_detect_changes


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _project_driver(project_node: dict[str, object]) -> object:
    result = MagicMock()
    result.single = AsyncMock(return_value={"p": project_node})
    session = MagicMock()
    session.run = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    driver = MagicMock()
    driver.session = MagicMock(return_value=session)
    return driver


@pytest.fixture
def dirty_repo(tmp_path: Path) -> tuple[Path, Path]:
    repos_root = tmp_path / "repos"
    repo = repos_root / "testproj"
    repo.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)
    (repo / "a.py").write_text("line1\n")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2\n")
    return repo, repos_root


@pytest.mark.asyncio
async def test_native_detect_changes_lists_worktree_files(
    dirty_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, repos_root = dirty_repo
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)

    result = await native_detect_changes(project="testproj")

    assert result["ok"] is True
    assert result["files"] == ["a.py"]


def test_valid_since_accepts_iso_and_approxidate() -> None:
    assert _valid_since("2026-06-07")
    assert _valid_since("2026-06-07T12:34:56Z")
    assert _valid_since("2 weeks ago")


@pytest.mark.asyncio
async def test_native_detect_changes_rejects_invalid_since(
    dirty_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo, repos_root = dirty_repo
    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)

    result = await native_detect_changes(project="testproj", since="HEAD~1")

    assert result["ok"] is False
    assert result["error_code"] == "invalid_since"


@pytest.mark.asyncio
async def test_native_detect_changes_uses_registered_parent_mount_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repos_root = tmp_path / "repos"
    repos_root.mkdir()
    repo = tmp_path / "repos-hs" / "EvmKit.Swift"
    repo.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=repo)
    _run(["git", "config", "user.email", "t@t"], cwd=repo)
    _run(["git", "config", "user.name", "T"], cwd=repo)
    (repo / "a.py").write_text("line1\n")
    _run(["git", "add", "."], cwd=repo)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=repo)
    (repo / "a.py").write_text("line1\nline2\n")

    monkeypatch.setattr("palace_mcp.git.path_resolver.REPOS_ROOT", repos_root)
    monkeypatch.setattr(
        "palace_mcp.mcp_server.get_driver",
        lambda: _project_driver(
            {"parent_mount": "hs", "relative_path": "EvmKit.Swift"}
        ),
    )

    result = await native_detect_changes(project="evm-kit")

    assert result["ok"] is True
    assert result["files"] == ["a.py"]
