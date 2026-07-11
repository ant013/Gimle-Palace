"""Cap-plumbing + truncation-metadata tests for resolve_snippet (whole-file support)."""

from __future__ import annotations

from pathlib import Path

from palace_mcp.code.snippet_provider import resolve_snippet


def _write(repo: Path, name: str, n_lines: int) -> None:
    (repo / name).write_text(
        "\n".join(f"line {i}" for i in range(1, n_lines + 1)) + "\n"
    )


def test_default_caps_at_200_and_reports_counts(tmp_path: Path) -> None:
    _write(tmp_path, "big.swift", 300)
    result, code, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="big.swift",
        line_start=1,
        line_end=None,
    )
    assert code is None and result is not None
    assert result.truncated is True
    assert result.line_count == 200
    assert result.total_lines == 300
    assert result.truncated_lines == 100
    assert result.truncated_reason == "lines"


def test_max_lines_override_reads_whole_file(tmp_path: Path) -> None:
    _write(tmp_path, "big.swift", 300)
    result, code, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="big.swift",
        line_start=1,
        line_end=None,
        max_lines=1200,
    )
    assert code is None and result is not None
    assert result.truncated is False
    assert result.line_count == 300
    assert result.total_lines == 300
    assert result.truncated_lines == 0
    assert result.truncated_reason is None


def test_byte_cap_sets_reason_bytes(tmp_path: Path) -> None:
    _write(tmp_path, "big.swift", 50)  # ~ small
    result, code, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="big.swift",
        line_start=1,
        line_end=None,
        max_lines=1200,
        max_bytes=40,
    )
    assert code is None and result is not None
    assert result.truncated is True
    assert result.truncated_reason == "bytes"


def test_line_cap_boundary_exact(tmp_path: Path) -> None:
    _write(tmp_path, "b.swift", 1200)
    result, _, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="b.swift",
        line_start=1,
        line_end=None,
        max_lines=1200,
    )
    assert result is not None
    assert result.truncated is False
    assert result.line_count == 1200
    _write(tmp_path, "c.swift", 1201)
    result2, _, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="c.swift",
        line_start=1,
        line_end=None,
        max_lines=1200,
    )
    assert result2 is not None
    assert result2.truncated is True
    assert result2.line_count == 1200
    assert result2.total_lines == 1201
    assert result2.truncated_lines == 1


def test_empty_file_no_inverted_range(tmp_path: Path) -> None:
    (tmp_path / "empty.swift").write_text("")
    result, code, _ = resolve_snippet(
        project="p",
        repo_path=tmp_path,
        file_path="empty.swift",
        line_start=1,
        line_end=None,
        max_lines=1200,
    )
    assert code is None and result is not None
    assert result.total_lines == 0
    assert result.line_count == 0
    assert result.end_line >= 0
    assert result.truncated is False
