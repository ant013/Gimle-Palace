"""Unit tests for foundation/semgrep_runner.py (GIM-355)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_semgrep_result(path: str) -> dict[str, Any]:
    return {
        "path": path,
        "check_id": "test-rule",
        "start": {"line": 1},
        "end": {"line": 1},
        "extra": {"severity": "WARNING", "message": "test", "metadata": {}},
    }


class _FakeProc:
    def __init__(self, *, returncode: int = 0, stdout: str = '{"results": []}') -> None:
        self.returncode = returncode
        self._stdout = stdout.encode()

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, b""

    def kill(self) -> None:
        pass

    async def wait(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Stop-list: .build/ dirs excluded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_checkouts_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files under .build/ must not appear in semgrep target args."""
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    src = tmp_path / "Sources" / "App.swift"
    src.parent.mkdir(parents=True)
    src.write_text("let x = 1\n")

    dep = tmp_path / ".build" / "checkouts" / "Lib" / "Lib.swift"
    dep.parent.mkdir(parents=True)
    dep.write_text("let y = 2\n")

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    seen: list[str] = []

    async def fake_exec(*args: object, **_kw: object) -> object:
        seen.extend(str(a) for a in args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await run_semgrep(rules_dir=rules_dir, target=tmp_path)

    assert str(src) in seen
    assert str(dep) not in seen


@pytest.mark.asyncio
async def test_node_modules_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files under node_modules/ must not appear in semgrep target args."""
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    src = tmp_path / "src" / "App.swift"
    src.parent.mkdir(parents=True)
    src.write_text("let x = 1\n")

    vendor = tmp_path / "node_modules" / "lib" / "index.swift"
    vendor.parent.mkdir(parents=True)
    vendor.write_text("let z = 3\n")

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    seen: list[str] = []

    async def fake_exec(*args: object, **_kw: object) -> object:
        seen.extend(str(a) for a in args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await run_semgrep(rules_dir=rules_dir, target=tmp_path)

    assert str(src) in seen
    assert str(vendor) not in seen


# ---------------------------------------------------------------------------
# Empty target: no subprocess spawned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_target_returns_empty_no_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No eligible files → return [], semgrep never invoked."""
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    (tmp_path / "README.md").write_text("nothing\n")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    spawned: list[object] = []

    async def fake_exec(*args: object, **_kw: object) -> object:
        spawned.append(args)
        raise AssertionError("must not be called")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await run_semgrep(rules_dir=rules_dir, target=tmp_path)

    assert result == []
    assert spawned == []


# ---------------------------------------------------------------------------
# Batching: 3 files with batch_size=2 → 2 subprocess calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batching_splits_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    for i in range(3):
        f = tmp_path / f"File{i}.swift"
        f.write_text(f"let x{i} = {i}\n")

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    call_count = 0

    async def fake_exec(*args: object, **_kw: object) -> object:
        nonlocal call_count
        call_count += 1
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await run_semgrep(rules_dir=rules_dir, target=tmp_path, batch_size=2)

    assert call_count == 2  # ceil(3/2) = 2 batches


# ---------------------------------------------------------------------------
# skip_test_paths: Tests/ excluded when requested
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skip_test_paths_excludes_test_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    src = tmp_path / "Sources" / "App.swift"
    src.parent.mkdir(parents=True)
    src.write_text("let x = 1\n")

    test_file = tmp_path / "Tests" / "AppTests.swift"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("let t = 1\n")

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    seen: list[str] = []

    async def fake_exec(*args: object, **_kw: object) -> object:
        seen.extend(str(a) for a in args)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    await run_semgrep(rules_dir=rules_dir, target=tmp_path, skip_test_paths=True)

    assert str(src) in seen
    assert str(test_file) not in seen


# ---------------------------------------------------------------------------
# Timeout: SemgrepInternalError raised
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_raises_semgrep_internal_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from palace_mcp.extractors.foundation.semgrep_runner import (
        SemgrepInternalError,
        run_semgrep,
    )

    src = tmp_path / "App.swift"
    src.write_text("let x = 1\n")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    class _HangingProc:
        returncode = None

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(9999)
            return b"", b""

        def kill(self) -> None:
            pass

        async def wait(self) -> None:
            pass

    async def fake_exec(*args: object, **_kw: object) -> object:
        return _HangingProc()

    async def fake_wait_for(coro: object, timeout: float) -> object:  # type: ignore[override]
        raise TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(SemgrepInternalError, match="timed out"):
        await run_semgrep(rules_dir=rules_dir, target=tmp_path, timeout_s=1)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nonzero_exit_invalid_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from palace_mcp.extractors.foundation.semgrep_runner import (
        SemgrepConfigInvalidError,
        run_semgrep,
    )

    src = tmp_path / "App.swift"
    src.write_text("let x = 1\n")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    stderr_msg = "invalid rule: bad yaml"
    bad_proc = _FakeProc(returncode=2, stdout="{}")

    async def fake_exec(*args: object, **_kw: object) -> object:
        return bad_proc

    async def _patched_communicate(self: object) -> tuple[bytes, bytes]:
        return b"{}", stderr_msg.encode()

    bad_proc.communicate = lambda: _patched_communicate(bad_proc)  # type: ignore[method-assign]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(SemgrepConfigInvalidError):
        await run_semgrep(rules_dir=rules_dir, target=tmp_path, timeout_s=30)


# ---------------------------------------------------------------------------
# Single-file target: passed directly, no enumeration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_file_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from palace_mcp.extractors.foundation.semgrep_runner import run_semgrep

    src = tmp_path / "App.swift"
    src.write_text("let x = 1\n")
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()

    result_data = [_make_semgrep_result(str(src))]
    proc = _FakeProc(stdout=json.dumps({"results": result_data}))

    async def fake_exec(*args: object, **_kw: object) -> object:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    results = await run_semgrep(rules_dir=rules_dir, target=src)

    assert len(results) == 1
    assert results[0]["path"] == str(src)
