from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pygit2
import pytest

from palace_mcp.extractors.code_ownership.blame_walker import walk_blame
from palace_mcp.extractors.code_ownership.mailmap import MailmapResolver
from palace_mcp.extractors.foundation.walk import should_skip_path


@pytest.fixture
def mini_repo(tmp_path) -> pygit2.Repository:
    """3 commits, 2 authors, 2 files (one text, one binary).

    File 1: 'a.py' — author1 writes 4 lines, author2 modifies 2 of them.
    File 2: 'b.bin' — binary, contains \\x00 bytes; blame must skip.
    """
    repo_path = tmp_path / "mini"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig1 = pygit2.Signature("Author One", "a1@example.com", 1_700_000_000, 0)
    sig2 = pygit2.Signature("Author Two", "a2@example.com", 1_700_001_000, 0)

    def commit(
        msg: str, files: dict[str, bytes], parents: list, sig: pygit2.Signature
    ) -> str:
        for name, data in files.items():
            (repo_path / name).write_bytes(data)
            repo.index.add(name)
        repo.index.write()
        tree = repo.index.write_tree()
        oid = repo.create_commit("HEAD", sig, sig, msg, tree, parents)
        return str(oid)

    sha1 = commit(
        "init",
        {"a.py": b"line1\nline2\nline3\nline4\n", "b.bin": b"\x00\x01\x02"},
        [],
        sig1,
    )
    head_oid = pygit2.Oid(hex=sha1)
    commit(
        "modify a.py",
        {"a.py": b"line1\nLINE2_modified\nLINE3_modified\nline4\n"},
        [head_oid],
        sig2,
    )
    return repo


def test_walk_blame_attributes_lines_to_two_authors(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys=set(),
    )
    assert "a.py" in blame_dict
    by_author = {b.canonical_id: b.lines for b in blame_dict["a.py"].values()}
    # Author One wrote lines 1+4 (2 lines), Author Two rewrote 2+3 (2 lines)
    assert by_author["a1@example.com"] == 2
    assert by_author["a2@example.com"] == 2
    assert "a.py" not in binary_paths


def test_walk_blame_skips_binary(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"b.bin"},
        mailmap=resolver,
        bot_keys=set(),
    )
    # Binary path reported in binary_paths, not in blame_dict
    assert "b.bin" in binary_paths
    assert "b.bin" not in blame_dict


def test_walk_blame_excludes_bots(mini_repo):
    resolver = MailmapResolver.from_repo(mini_repo, max_bytes=1_048_576)
    blame_dict, binary_paths = walk_blame(
        mini_repo,
        paths={"a.py"},
        mailmap=resolver,
        bot_keys={"a2@example.com"},  # treat Author Two as bot
    )
    by_author = {b.canonical_id: b.lines for b in blame_dict["a.py"].values()}
    assert "a2@example.com" not in by_author
    assert by_author["a1@example.com"] == 2  # only the lines author1 still owns


@pytest.fixture
def vendor_repo(tmp_path) -> pygit2.Repository:
    """Repo with a vendor path (.build/checkouts/dep.swift) and a first-party path (Sources/main.swift).

    Used to verify that should_skip_path filters out the vendor file before blame.
    """
    repo_path = tmp_path / "vendor"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig = pygit2.Signature("Dev", "dev@example.com", 1_700_000_000, 0)

    (repo_path / ".build").mkdir()
    (repo_path / ".build" / "checkouts").mkdir()
    (repo_path / ".build" / "checkouts" / "dep.swift").write_bytes(b"let x = 1\n")
    (repo_path / "Sources").mkdir()
    (repo_path / "Sources" / "main.swift").write_bytes(b'print("hello")\n')

    repo.index.add(".build/checkouts/dep.swift")
    repo.index.add("Sources/main.swift")
    repo.index.write()
    tree = repo.index.write_tree()
    repo.create_commit("HEAD", sig, sig, "init", tree, [])
    return repo


def test_vendor_paths_filtered_before_blame(vendor_repo):
    """should_skip_path removes .build/checkouts/dep.swift; only Sources/main.swift reaches walk_blame."""
    resolver = MailmapResolver.from_repo(vendor_repo, max_bytes=1_048_576)
    all_paths = {".build/checkouts/dep.swift", "Sources/main.swift"}

    # Reproduce the filter applied in extractor._run before walk_blame
    filtered = {p for p in all_paths if not should_skip_path(p.split("/"))}

    assert filtered == {"Sources/main.swift"}, (
        "vendor path must be excluded by should_skip_path"
    )

    blame_dict, binary_paths = walk_blame(
        vendor_repo,
        paths=filtered,
        mailmap=resolver,
        bot_keys=set(),
    )
    assert "Sources/main.swift" in blame_dict
    assert ".build/checkouts/dep.swift" not in blame_dict
    assert ".build/checkouts/dep.swift" not in binary_paths


def test_all_files_in_head_excludes_vendor(vendor_repo):
    """_all_files_in_head must exclude .build/checkouts/ paths via its internal should_skip_path guard.

    This exercises the production code path: if the should_skip_path check inside
    CodeOwnershipExtractor._all_files_in_head were removed, this test fails.
    """
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

    files = CodeOwnershipExtractor._all_files_in_head(vendor_repo)
    assert ".build/checkouts/dep.swift" not in files
    assert "Sources/main.swift" in files


def test_filter_dirty_excludes_vendor_incremental():
    """_filter_dirty is the production helper called in _run for the incremental dirty-set.

    This test fails if _filter_dirty is removed or made a no-op, protecting the line
    ``dirty = CodeOwnershipExtractor._filter_dirty(dirty)`` in the _run incremental path.
    Deleted paths (passed as separate set) are intentionally NOT filtered — only dirty is.
    """
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor

    raw_dirty = {".build/checkouts/dep.swift", "Sources/main.swift", "Pods/Lib/foo.m"}
    filtered = CodeOwnershipExtractor._filter_dirty(raw_dirty)

    assert "Sources/main.swift" in filtered
    assert ".build/checkouts/dep.swift" not in filtered
    assert "Pods/Lib/foo.m" not in filtered


@pytest.fixture
def incremental_vendor_repo(tmp_path: Path):
    """Two-commit repo: commit-1 adds Sources/main.swift; commit-2 also adds .build/checkouts/dep.swift.

    Returns (repo, sha1_string, repo_path) so the test can supply sha1 as the
    checkpoint prev_head_sha, triggering the incremental diff path in _run.
    """
    repo_path = tmp_path / "incremental"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig = pygit2.Signature("Dev", "dev@example.com", 1_700_000_000, 0)

    (repo_path / "Sources").mkdir()
    (repo_path / "Sources" / "main.swift").write_bytes(b'print("v1")\n')
    repo.index.add("Sources/main.swift")
    repo.index.write()
    tree1 = repo.index.write_tree()
    sha1_oid = repo.create_commit("HEAD", sig, sig, "init", tree1, [])
    sha1 = str(sha1_oid)

    (repo_path / ".build").mkdir()
    (repo_path / ".build" / "checkouts").mkdir()
    (repo_path / ".build" / "checkouts" / "dep.swift").write_bytes(b"let dep = 1\n")
    (repo_path / "Sources" / "main.swift").write_bytes(b'print("v2")\n')
    repo.index.add(".build/checkouts/dep.swift")
    repo.index.add("Sources/main.swift")
    repo.index.write()
    tree2 = repo.index.write_tree()
    repo.create_commit("HEAD", sig, sig, "add vendor", tree2, [sha1_oid])

    return repo, sha1, repo_path


async def test_run_incremental_filters_vendor_before_walk_blame(
    incremental_vendor_repo: tuple,
) -> None:
    """_run incremental path must drop .build/checkouts/dep.swift before calling walk_blame.

    Deleting line 213 of extractor.py (_filter_dirty call) would cause dep.swift
    to appear in captured_paths — this test detects that regression.
    The deleted-paths set is left unfiltered (it goes to write_batch, not blame).
    """
    from palace_mcp.extractors.code_ownership.extractor import CodeOwnershipExtractor
    from palace_mcp.extractors.code_ownership.models import OwnershipCheckpoint

    repo, sha1, repo_path = incremental_vendor_repo

    checkpoint = OwnershipCheckpoint(
        project_id="proj",
        last_head_sha=sha1,
        last_completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        run_id="run-prev",
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    fake_settings = MagicMock()
    fake_settings.ownership_blame_weight = 0.7
    fake_settings.mailmap_max_bytes = 1_048_576
    fake_settings.ownership_max_files_per_run = 10_000
    fake_settings.ownership_write_batch_size = 500
    fake_settings.palace_recency_decay_days = 90

    captured_paths: set[str] = set()

    def _fake_walk_blame(repo_arg: object, *, paths: set[str], **_kw: object) -> tuple:
        captured_paths.update(paths)
        return {}, set()

    _MODULE = "palace_mcp.extractors.code_ownership.extractor"

    with (
        patch(f"{_MODULE}.ensure_ownership_schema", new=AsyncMock()),
        patch(f"{_MODULE}.load_checkpoint", new=AsyncMock(return_value=checkpoint)),
        patch(f"{_MODULE}.update_checkpoint", new=AsyncMock()),
        patch(f"{_MODULE}.aggregate_churn", new=AsyncMock(return_value={})),
        patch(f"{_MODULE}.write_batch", new=AsyncMock()),
        patch.object(
            CodeOwnershipExtractor,
            "_fetch_bot_identity_keys",
            new=AsyncMock(return_value=set()),
        ),
        patch.object(
            CodeOwnershipExtractor,
            "_fetch_known_author_ids",
            new=AsyncMock(return_value=set()),
        ),
        patch.object(
            CodeOwnershipExtractor,
            "_has_any_commits",
            new=AsyncMock(return_value=True),
        ),
        patch(f"{_MODULE}.walk_blame", side_effect=_fake_walk_blame),
    ):
        await CodeOwnershipExtractor()._run(
            driver=MagicMock(),
            project_id="proj",
            repo_path=repo_path,
            run_id="run-new",
            settings=fake_settings,
        )

    assert "Sources/main.swift" in captured_paths, (
        "first-party file must reach walk_blame"
    )
    assert ".build/checkouts/dep.swift" not in captured_paths, (
        "vendor path must be filtered by _filter_dirty before walk_blame"
    )
