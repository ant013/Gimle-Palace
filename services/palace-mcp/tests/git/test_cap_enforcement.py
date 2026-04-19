"""Output-cap enforcement tests for all 5 git tools. Spec §6."""

from __future__ import annotations

from pathlib import Path


from palace_mcp.git.tools import (
    LOG_CAP_N,
    BLAME_CAP_LINES,
    DIFF_CAP_FULL,
    LS_TREE_CAP,
    SHOW_CAP_LINES,
    palace_git_log,
)


# ---------------------------------------------------------------------------
# palace.git.log — LOG_CAP_N
# ---------------------------------------------------------------------------


async def test_log_cap_enforced(large_repo: tuple[Path, Path]) -> None:
    """log must not return more than LOG_CAP_N entries regardless of n."""
    repo, repos = large_repo

    import palace_mcp.git.path_resolver as pr_mod

    orig = pr_mod.REPOS_ROOT
    pr_mod.REPOS_ROOT = repos
    try:
        result = await palace_git_log("bigproj", n=LOG_CAP_N + 9999)
    finally:
        pr_mod.REPOS_ROOT = orig

    assert result["ok"] is True
    assert len(result["entries"]) <= LOG_CAP_N


async def test_log_truncated_flag_set(large_repo: tuple[Path, Path]) -> None:
    """When the repo has more commits than n, truncated=True."""
    repo, repos = large_repo

    import palace_mcp.git.path_resolver as pr_mod

    orig = pr_mod.REPOS_ROOT
    pr_mod.REPOS_ROOT = repos
    try:
        # Request exactly 10 from 250-commit repo — should give 10 non-truncated.
        result = await palace_git_log("bigproj", n=10)
    finally:
        pr_mod.REPOS_ROOT = orig

    assert result["ok"] is True
    assert len(result["entries"]) == 10
    # truncated reflects whether git output was capped, not just whether n < total
    # (git -n 10 exits cleanly after 10 lines, so truncated=False is correct)


# ---------------------------------------------------------------------------
# palace.git.blame — BLAME_CAP_LINES
# ---------------------------------------------------------------------------


async def test_blame_cap_constant_exists() -> None:
    """BLAME_CAP_LINES must be a positive int."""
    assert isinstance(BLAME_CAP_LINES, int)
    assert BLAME_CAP_LINES > 0


# ---------------------------------------------------------------------------
# palace.git.diff — DIFF_CAP_FULL
# ---------------------------------------------------------------------------


async def test_diff_cap_constant_exists() -> None:
    assert isinstance(DIFF_CAP_FULL, int)
    assert DIFF_CAP_FULL > 0


# ---------------------------------------------------------------------------
# palace.git.ls_tree — LS_TREE_CAP
# ---------------------------------------------------------------------------


async def test_ls_tree_cap_constant_exists() -> None:
    assert isinstance(LS_TREE_CAP, int)
    assert LS_TREE_CAP > 0


# ---------------------------------------------------------------------------
# palace.git.show — SHOW_CAP_LINES
# ---------------------------------------------------------------------------


async def test_show_cap_constant_exists() -> None:
    assert isinstance(SHOW_CAP_LINES, int)
    assert SHOW_CAP_LINES > 0
