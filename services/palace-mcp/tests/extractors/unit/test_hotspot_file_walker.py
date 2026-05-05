from __future__ import annotations

from pathlib import Path

from palace_mcp.extractors.hotspot.file_walker import _has_subseq, _walk


def test_has_subseq_basic():
    assert _has_subseq(("a", "b", "c", "d"), ("b", "c")) is True
    assert _has_subseq(("a", "b", "c", "d"), ("c", "b")) is False
    assert _has_subseq(("tests", "extractors", "fixtures", "x.py"), ("tests", "extractors", "fixtures")) is True
    assert _has_subseq(("docs", "tests", "extractors", "fixtures-policy.md"), ("tests", "extractors", "fixtures")) is False


def test_walk_picks_only_known_extensions(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def x(): pass\n")
    (tmp_path / "src" / "a.kt").write_text("fun x() {}\n")
    (tmp_path / "src" / "ignore.txt").write_text("not source\n")
    (tmp_path / "README.md").write_text("# r\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["src/a.kt", "src/a.py"]


def test_walk_skips_stop_dirs(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "head.py").write_text("x\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("x\n")
    (tmp_path / "build" / "out").mkdir(parents=True)
    (tmp_path / "build" / "out" / "compiled.kt").write_text("x\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "ok.py").write_text("def x(): pass\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["src/ok.py"]


def test_walk_skips_fixture_dirs_subseq_only(tmp_path: Path):
    fixture_dir = tmp_path / "tests" / "extractors" / "fixtures"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "skip_me.py").write_text("x\n")

    not_fixture = tmp_path / "docs" / "tests-fixtures-policy.py"
    not_fixture.parent.mkdir(parents=True)
    not_fixture.write_text("x\n")

    out = sorted(p.relative_to(tmp_path).as_posix() for p in _walk(tmp_path))
    assert out == ["docs/tests-fixtures-policy.py"]
