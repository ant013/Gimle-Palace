from __future__ import annotations

import json
import subprocess
from pathlib import Path

from palace_mcp.ops.sync_status import RepositorySpec
from palace_mcp.ops.sync_status import render_markdown
from palace_mcp.ops.sync_status import reports_payload
from palace_mcp.ops.sync_status import sync_repository


def _run(argv: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit(repo: Path, filename: str, body: str, message: str) -> str:
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _run(["git", "add", filename], cwd=repo)
    _run(["git", "commit", "-m", message, "-q"], cwd=repo)
    return _run(["git", "rev-parse", "HEAD"], cwd=repo)


def _init_origin_with_clone(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    remote_work = tmp_path / "remote-work"
    local = tmp_path / "local"

    _run(["git", "init", "--bare", "-q", str(origin)], cwd=tmp_path)
    _run(["git", "clone", "-q", str(origin), str(remote_work)], cwd=tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=remote_work)
    _run(["git", "config", "user.name", "Test"], cwd=remote_work)
    _run(["git", "switch", "-c", "main"], cwd=remote_work)
    _commit(remote_work, "README.md", "base\n", "base")
    _run(["git", "push", "-q", "-u", "origin", "main"], cwd=remote_work)

    _run(["git", "clone", "-q", str(origin), str(local)], cwd=tmp_path)
    _run(["git", "switch", "main"], cwd=local)
    _run(["git", "config", "user.email", "test@example.com"], cwd=local)
    _run(["git", "config", "user.name", "Test"], cwd=local)
    return remote_work, local


def test_sync_repository_fast_forwards_clean_repo(tmp_path: Path) -> None:
    remote_work, local = _init_origin_with_clone(tmp_path)
    remote_head = _commit(remote_work, "README.md", "base\nnext\n", "next")
    _run(["git", "push", "-q"], cwd=remote_work)

    report = sync_repository(RepositorySpec(slug="kit", repo_path=local))

    assert report.status == "fast_forwarded"
    assert report.updated is True
    assert report.head_after == remote_head
    assert report.ahead == 0
    assert report.behind == 1


def test_sync_repository_blocks_dirty_worktree_before_fast_forward(
    tmp_path: Path,
) -> None:
    remote_work, local = _init_origin_with_clone(tmp_path)
    local_head = _run(["git", "rev-parse", "HEAD"], cwd=local)
    _commit(remote_work, "README.md", "base\nremote\n", "remote")
    _run(["git", "push", "-q"], cwd=remote_work)
    (local / "local.txt").write_text("dirty\n", encoding="utf-8")

    report = sync_repository(RepositorySpec(slug="kit", repo_path=local))

    assert report.status == "blocked"
    assert report.skipped_reason == "dirty_worktree"
    assert report.dirty is True
    assert report.untracked_count == 1
    assert report.head_after == local_head


def test_sync_repository_uses_explicit_ref_when_upstream_is_missing(
    tmp_path: Path,
) -> None:
    remote_work, local = _init_origin_with_clone(tmp_path)
    _commit(remote_work, "README.md", "base\nremote\n", "remote")
    _run(["git", "push", "-q"], cwd=remote_work)
    _run(["git", "branch", "--unset-upstream"], cwd=local)

    report = sync_repository(
        RepositorySpec(
            slug="kit",
            repo_path=local,
            explicit_ref="origin/main",
        )
    )

    assert report.status == "fast_forwarded"
    assert report.compare_ref == "origin/main"
    assert report.upstream is None
    assert report.skipped_reason is None


def test_sync_report_renders_json_and_markdown(tmp_path: Path) -> None:
    _, local = _init_origin_with_clone(tmp_path)

    report = sync_repository(
        RepositorySpec(slug="kit", repo_path=local),
        fetch=False,
        dry_run=True,
    )
    payload = reports_payload([report])
    markdown = render_markdown([report])

    assert json.loads(json.dumps(payload))["repositories"][0]["slug"] == "kit"
    assert "| kit | up_to_date | main | origin/main | 0 | 0 | no | no |  |" in markdown
