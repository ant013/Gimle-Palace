"""Unit tests for palace_mcp.memory.prime.roles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from palace_mcp.memory.prime.deps import PrimingDeps
from palace_mcp.memory.prime.roles import VALID_ROLES, render_role_extras


def _make_deps(role_prime_dir: Path) -> PrimingDeps:
    settings = MagicMock()
    settings.palace_git_workspace = "/repos/gimle"
    settings.paperclip_api_url = "http://localhost:3000"
    return PrimingDeps(
        graphiti=MagicMock(),
        driver=MagicMock(),
        settings=settings,
        default_group_id="project/gimle",
        role_prime_dir=role_prime_dir,
    )


# ── VALID_ROLES ────────────────────────────────────────────────────────────────


def test_valid_roles_contains_expected_roles() -> None:
    expected = {
        "operator",
        "cto",
        "codereviewer",
        "pythonengineer",
        "opusarchitectreviewer",
        "qaengineer",
    }
    assert VALID_ROLES == expected


# ── render_role_extras: unknown role ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_render_role_extras_raises_for_unknown_role(tmp_path: Path) -> None:
    deps = _make_deps(tmp_path)
    with pytest.raises(ValueError, match="Unknown role"):
        await render_role_extras("boardmember", deps)


# ── render_role_extras: missing file → stub ───────────────────────────────────


@pytest.mark.asyncio
async def test_render_role_extras_stub_when_file_missing(tmp_path: Path) -> None:
    deps = _make_deps(tmp_path)
    result = await render_role_extras("cto", deps)
    assert "GIM-95b" in result
    assert "cto" in result
    assert "palace.code.search_graph" in result


# ── render_role_extras: file present → substitution ──────────────────────────


@pytest.mark.asyncio
async def test_render_role_extras_operator_substitutes_recent_commits(
    tmp_path: Path,
) -> None:
    role_file = tmp_path / "operator.md"
    role_file.write_text(
        "Recent:\n{{ recent_develop_commits }}\n"
        "Slices: {{ in_progress_slices }}\n"
        "Backlog: {{ backlog_high_priority }}\n",
        encoding="utf-8",
    )
    deps = _make_deps(tmp_path)

    with patch(
        "palace_mcp.memory.prime.roles._fetch_recent_commits",
        new_callable=AsyncMock,
        return_value="abc1234 some commit",
    ):
        result = await render_role_extras("operator", deps)

    assert "abc1234 some commit" in result
    # Static placeholders replaced with instructions (not literal placeholder)
    assert "{{ in_progress_slices }}" not in result
    assert "{{ backlog_high_priority }}" not in result
    assert "palace.memory.lookup" in result


@pytest.mark.asyncio
async def test_render_role_extras_non_operator_no_git_call(tmp_path: Path) -> None:
    role_file = tmp_path / "pythonengineer.md"
    role_file.write_text("PythonEngineer context here.\n", encoding="utf-8")
    deps = _make_deps(tmp_path)

    with patch(
        "palace_mcp.memory.prime.roles._fetch_recent_commits",
        new_callable=AsyncMock,
    ) as mock_git:
        result = await render_role_extras("pythonengineer", deps)

    mock_git.assert_not_called()
    assert "PythonEngineer context here." in result


@pytest.mark.asyncio
async def test_render_role_extras_replaces_static_url_placeholder(
    tmp_path: Path,
) -> None:
    role_file = tmp_path / "cto.md"
    role_file.write_text("API: {{ paperclip_api_url }}", encoding="utf-8")
    deps = _make_deps(tmp_path)

    result = await render_role_extras("cto", deps)

    assert "{{ paperclip_api_url }}" not in result
    assert "http://localhost:3000" in result


@pytest.mark.asyncio
async def test_render_role_extras_replaces_git_workspace_placeholder(
    tmp_path: Path,
) -> None:
    role_file = tmp_path / "codereviewer.md"
    role_file.write_text("Workspace: {{ git_workspace }}", encoding="utf-8")
    deps = _make_deps(tmp_path)

    result = await render_role_extras("codereviewer", deps)

    assert "{{ git_workspace }}" not in result
    assert "/repos/gimle" in result
