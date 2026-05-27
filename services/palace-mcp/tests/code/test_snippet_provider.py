"""Tests for palace_mcp.code.snippet_provider.

Covers: valid read, missing file, line bounds, byte bounds,
        absolute-path rejection, .. escape rejection, symlink escape rejection,
        staleness detection, language detection.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from palace_mcp.code.snippet_provider import (
    _MAX_SNIPPET_BYTES,
    _MAX_SNIPPET_LINES,
    resolve_snippet,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


def _run_text(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Real git repo with a Swift source file."""
    repos = tmp_path / "repos"
    r = repos / "myproject"
    r.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=r)
    _run(["git", "config", "user.email", "t@t"], cwd=r)
    _run(["git", "config", "user.name", "T"], cwd=r)
    (r / "Sources").mkdir()
    (r / "Sources" / "Wallet.swift").write_text(
        "\n".join(f"line{i}" for i in range(1, 21)) + "\n"
    )
    _run(["git", "add", "."], cwd=r)
    _run(["git", "commit", "-m", "initial", "-q"], cwd=r)
    return r


@pytest.fixture
def repos_root(repo: Path) -> Path:
    return repo.parent


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_snippet_returns_content(repo: Path, repos_root: Path) -> None:
    result, code, msg = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=2,
        line_end=5,
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    assert result.source == "line2\nline3\nline4\nline5"
    assert result.start_line == 2
    assert result.line_count == 4
    assert result.language == "swift"
    assert result.truncated is False
    assert result.stale is False


def test_no_line_range_returns_full_file(repo: Path, repos_root: Path) -> None:
    result, code, _ = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    assert result.line_count == 20


def test_fixture_semantic_result_with_context(repo: Path, repos_root: Path) -> None:
    """Integration fixture: snippet hydration matches the semantic search contract."""
    result, code, _ = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=1,
        line_end=3,
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    snippet_dict = {
        "language": result.language,
        "start_line": result.start_line,
        "end_line": result.end_line,
        "source": result.source,
    }
    assert snippet_dict["language"] == "swift"
    assert snippet_dict["start_line"] == 1
    assert snippet_dict["source"].startswith("line1")


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


def test_missing_file_returns_warning(repo: Path, repos_root: Path) -> None:
    result, code, msg = resolve_snippet(
        project="myproject",
        file_path="Sources/Nonexistent.swift",
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert result is None
    assert code == "missing_source_file"
    assert msg is not None


# ---------------------------------------------------------------------------
# Security: path traversal
# ---------------------------------------------------------------------------


def test_absolute_path_rejected(repo: Path, repos_root: Path) -> None:
    result, code, msg = resolve_snippet(
        project="myproject",
        file_path="/etc/passwd",
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert result is None
    assert code == "path_traversal_rejected"


def test_dotdot_escape_rejected(repo: Path, repos_root: Path) -> None:
    # Create a file just outside the repo root to be targeted.
    secret = repos_root / "secret.txt"
    secret.write_text("top_secret")

    result, code, msg = resolve_snippet(
        project="myproject",
        file_path="../secret.txt",
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert result is None
    assert code == "path_traversal_rejected"


def test_symlink_escape_rejected(repo: Path, repos_root: Path) -> None:
    outside = repos_root / "sibling_secret.key"
    outside.write_text("key_material")
    evil_link = repo / "evil"
    evil_link.symlink_to(outside)

    result, code, msg = resolve_snippet(
        project="myproject",
        file_path="evil",
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert result is None
    assert code == "path_traversal_rejected"


def test_none_file_path_returns_warning(repo: Path, repos_root: Path) -> None:
    result, code, msg = resolve_snippet(
        project="myproject",
        file_path=None,
        line_start=None,
        line_end=None,
        repos_root=repos_root,
    )
    assert result is None
    assert code == "missing_file_path"


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def test_line_count_capped(tmp_path: Path) -> None:
    repos = tmp_path / "repos"
    r = repos / "bigproject"
    r.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=r)
    _run(["git", "config", "user.email", "t@t"], cwd=r)
    _run(["git", "config", "user.name", "T"], cwd=r)
    total_lines = _MAX_SNIPPET_LINES + 50
    (r / "big.py").write_text("\n".join(f"x{i}" for i in range(total_lines)) + "\n")
    _run(["git", "add", "."], cwd=r)
    _run(["git", "commit", "-m", "init", "-q"], cwd=r)

    result, code, _ = resolve_snippet(
        project="bigproject",
        file_path="big.py",
        line_start=1,
        line_end=total_lines,
        repos_root=repos,
    )
    assert code is None
    assert result is not None
    assert result.line_count <= _MAX_SNIPPET_LINES
    assert result.truncated is True


def test_byte_count_capped(tmp_path: Path) -> None:
    repos = tmp_path / "repos"
    r = repos / "wideproject"
    r.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=r)
    _run(["git", "config", "user.email", "t@t"], cwd=r)
    _run(["git", "config", "user.name", "T"], cwd=r)
    # Each line ~100 bytes; 200 lines = 20 000 bytes > 16 384.
    (r / "wide.py").write_text("\n".join("a" * 99 for _ in range(200)) + "\n")
    _run(["git", "add", "."], cwd=r)
    _run(["git", "commit", "-m", "init", "-q"], cwd=r)

    result, code, _ = resolve_snippet(
        project="wideproject",
        file_path="wide.py",
        line_start=1,
        line_end=200,
        repos_root=repos,
    )
    assert code is None
    assert result is not None
    assert result.byte_count <= _MAX_SNIPPET_BYTES
    assert result.truncated is True


# ---------------------------------------------------------------------------
# Staleness
# ---------------------------------------------------------------------------


def test_stale_source_when_commit_sha_differs(repo: Path, repos_root: Path) -> None:
    result, code, _ = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=1,
        line_end=3,
        commit_sha="0000000000000000000000000000000000000000",
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    assert result.stale is True


def test_not_stale_when_commit_sha_matches_head(repo: Path, repos_root: Path) -> None:
    head = _run_text(["git", "rev-parse", "HEAD"], cwd=repo)
    result, code, _ = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=1,
        line_end=3,
        commit_sha=head,
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    assert result.stale is False


def test_not_stale_when_no_commit_sha(repo: Path, repos_root: Path) -> None:
    result, code, _ = resolve_snippet(
        project="myproject",
        file_path="Sources/Wallet.swift",
        line_start=1,
        line_end=3,
        commit_sha=None,
        repos_root=repos_root,
    )
    assert code is None
    assert result is not None
    assert result.stale is False
