from datetime import datetime, timezone
from pathlib import Path
import pytest
import pygit2

from palace_mcp.extractors.git_history.pygit2_walker import (
    Pygit2Walker,
    CommitNotFoundError,
)


def _build_synthetic_repo(tmp: Path, n_commits: int = 5) -> str:
    """Create a real git repo with n linear commits. Returns path."""
    repo_path = tmp / "synth-repo"
    repo = pygit2.init_repository(str(repo_path), bare=False)
    sig = pygit2.Signature(
        "Foo", "foo@example.com", int(datetime.now(timezone.utc).timestamp()), 0
    )
    parent: list[pygit2.Oid] = []
    for i in range(n_commits):
        blob_id = repo.create_blob(f"content-{i}".encode())
        tb = repo.TreeBuilder()
        tb.insert(f"file-{i}.txt", blob_id, pygit2.GIT_FILEMODE_BLOB)
        tree_id = tb.write()
        commit_id = repo.create_commit(
            "HEAD", sig, sig, f"commit {i}\n\nbody", tree_id, parent
        )
        parent = [commit_id]
    return str(repo_path)


def test_walker_full_walk_yields_all_commits(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    assert len(commits) == 5


def test_walker_incremental_yields_only_new_since(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    all_commits = list(walker.walk_since(None))
    # Use third commit's sha as checkpoint
    checkpoint_sha = all_commits[2]["sha"]
    incremental = list(walker.walk_since(checkpoint_sha))
    # Walk should yield commits NEWER than checkpoint, exclusive (top 2)
    assert len(incremental) == 2


def test_walker_checkpoint_not_found_raises(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=5)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    with pytest.raises(CommitNotFoundError):
        list(walker.walk_since("0" * 40))


def test_walker_head_sha_returns_latest(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=3)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    head = walker.head_sha()
    all_commits = list(walker.walk_since(None))
    assert head == all_commits[0]["sha"]  # most recent first


def test_walker_extracts_author_committer_email(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=1)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    assert commits[0]["author_email"] == "foo@example.com"
    assert commits[0]["committer_email"] == "foo@example.com"


def test_walker_yields_touched_files(tmp_path: Path):
    repo_path = _build_synthetic_repo(tmp_path, n_commits=3)
    walker = Pygit2Walker(repo_path=Path(repo_path))
    commits = list(walker.walk_since(None))
    for c in commits:
        assert "touched_files" in c
        assert len(c["touched_files"]) >= 1
