"""F1: tri-state freshness — no path reports fresh without positive evidence.

Sprint-1 reliability response (GIM-SEMANTIC-ROW-FRESHNESS): previously every
non-positive branch of inspect_freshness returned stale=False, presenting
"no data" as assurance.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from palace_mcp.code.snippet_provider import (
    FRESHNESS_BEHIND,
    FRESHNESS_CURRENT,
    FRESHNESS_UNKNOWN,
    inspect_freshness,
)


def _git_repo(tmp_path: Path, commits: int = 1) -> tuple[Path, list[str]]:
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t")
    g("config", "user.name", "T")
    shas: list[str] = []
    for i in range(commits):
        (repo / "a.txt").write_text(f"v{i}\n")
        g("add", ".")
        g("commit", "-m", f"c{i}", "-q")
        shas.append(
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    return repo, shas


def test_no_commit_sha_is_unknown_not_fresh(tmp_path: Path) -> None:
    result = inspect_freshness(tmp_path, None)
    assert result.stale is None
    assert result.freshness_state == FRESHNESS_UNKNOWN
    assert result.freshness_reason == "no_indexed_commit"


def test_unresolved_repo_is_unknown_not_fresh() -> None:
    result = inspect_freshness(None, "abc123")
    assert result.stale is None
    assert result.freshness_state == FRESHNESS_UNKNOWN
    assert result.freshness_reason == "repo_unresolved"


def test_non_git_dir_is_unknown_not_fresh(tmp_path: Path) -> None:
    result = inspect_freshness(tmp_path, "abc123")  # no .git here
    assert result.stale is None
    assert result.freshness_state == FRESHNESS_UNKNOWN
    assert result.freshness_reason == "git_error"


def test_commit_not_in_tree_is_unknown_with_identity_signature(
    tmp_path: Path,
) -> None:
    repo, _ = _git_repo(tmp_path)
    foreign_sha = "0123456789abcdef0123456789abcdef01234567"
    result = inspect_freshness(repo, foreign_sha)
    assert result.stale is None
    assert result.freshness_state == FRESHNESS_UNKNOWN
    assert result.freshness_reason == "indexed_commit_not_in_tree"


def test_head_match_is_positively_current(tmp_path: Path) -> None:
    repo, shas = _git_repo(tmp_path)
    result = inspect_freshness(repo, shas[-1])
    assert result.stale is False
    assert result.freshness_state == FRESHNESS_CURRENT
    assert result.freshness_reason is None
    assert result.commits_behind_head == 0


def test_behind_is_positively_stale(tmp_path: Path) -> None:
    repo, shas = _git_repo(tmp_path, commits=3)
    result = inspect_freshness(repo, shas[0])
    assert result.stale is True
    assert result.freshness_state == FRESHNESS_BEHIND
    assert result.commits_behind_head == 2
