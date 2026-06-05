"""Tests for prune_swift_symbols subprocess hardening."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from palace_mcp.extractors.prune_swift_symbols.subprocess_helpers import (
    get_git_head_sha,
)


def test_repo_path_outside_allowlist_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PALACE_ALLOWED_REPO_ROOTS", str(tmp_path / "allowed"))

    with pytest.raises(ValueError, match="not under allowed roots"):
        get_git_head_sha(tmp_path / "outside")


def test_subprocess_uses_shell_false_and_absolute_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    monkeypatch.setenv("PALACE_ALLOWED_REPO_ROOTS", str(tmp_path))

    completed = subprocess.CompletedProcess(
        args=["/usr/bin/git", "rev-parse", "HEAD"],
        returncode=0,
        stdout="abc123\n",
        stderr="",
    )

    with patch(
        "palace_mcp.extractors.prune_swift_symbols.subprocess_helpers.subprocess.run",
        return_value=completed,
    ) as run_mock:
        sha = get_git_head_sha(repo_path)

    assert sha == "abc123"
    run_mock.assert_called_once()
    _, kwargs = run_mock.call_args
    assert run_mock.call_args.args[0][0] == "/usr/bin/git"
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == str(repo_path.resolve())
