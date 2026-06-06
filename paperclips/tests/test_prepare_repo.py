"""Executable behavior tests for prepare_repo.sh."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "paperclips" / "scripts" / "prepare_repo.sh"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_origin(tmp_path: Path, repo_name: str) -> Path:
    origin = tmp_path / "origin" / repo_name
    origin.mkdir(parents=True)
    _git("init", cwd=origin)
    _git("config", "user.name", "Test User", cwd=origin)
    _git("config", "user.email", "test@example.com", cwd=origin)
    (origin / "README.md").write_text("# fixture\n")
    _git("add", "README.md", cwd=origin)
    _git("commit", "-m", "init", cwd=origin)
    return origin


def test_script_exists_executable() -> None:
    assert SCRIPT.is_file()
    assert (SCRIPT.stat().st_mode & 0o111) != 0


def test_help_works() -> None:
    out = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True)
    assert out.returncode == 0
    assert "slug symlink" in out.stdout.lower()


def test_github_mode_clones_repo_and_creates_symlink(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path, "MarketKit.Swift")
    base_dir = tmp_path / "HorizontalSystems"

    out = subprocess.run(
        ["bash", str(SCRIPT), "--github", str(origin), "--base", str(base_dir)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    repo_path = base_dir / "MarketKit.Swift"
    symlink_path = base_dir / "market-kit"

    assert payload["slug"] == "market-kit"
    assert payload["repo_name"] == "MarketKit.Swift"
    assert payload["repo_path"] == str(repo_path)
    assert payload["symlink_path"] == str(symlink_path)
    assert payload["cloned"] is True
    assert payload["symlinked"] is True
    assert (repo_path / ".git").is_dir()
    assert symlink_path.is_symlink()
    assert os.readlink(symlink_path) == "MarketKit.Swift"

    rerun = subprocess.run(
        ["bash", str(SCRIPT), "--github", str(origin), "--base", str(base_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rerun.returncode == 0, rerun.stderr
    rerun_payload = json.loads(rerun.stdout)
    assert rerun_payload["cloned"] is False
    assert rerun_payload["symlinked"] is False


def test_slug_mode_uses_manifest_relative_path(tmp_path: Path) -> None:
    repo_name = "MarketKit.Swift"
    origin = _init_origin(tmp_path, repo_name)
    org_dir = tmp_path / "org"
    bare_repo = org_dir / f"{repo_name}.git"
    org_dir.mkdir()
    subprocess.run(
        ["git", "clone", "--bare", str(origin), str(bare_repo)],
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "members": [
                    {
                        "slug": "market-kit",
                        "relative_path": repo_name,
                    }
                ]
            }
        )
    )

    base_dir = tmp_path / "HorizontalSystems"
    env = {
        **os.environ,
        "PALACE_SWIFT_KIT_GITHUB_ORG": str(org_dir),
    }
    out = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--slug",
            "market-kit",
            "--manifest",
            str(manifest),
            "--base",
            str(base_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["repo_name"] == repo_name
    assert payload["slug"] == "market-kit"
    assert (base_dir / repo_name / ".git").is_dir()
    assert (base_dir / "market-kit").is_symlink()


def test_slug_mode_falls_back_to_conventional_repo_name_when_manifest_is_alias(
    tmp_path: Path,
) -> None:
    repo_name = "HsExtensions.Swift"
    origin = _init_origin(tmp_path, repo_name)
    org_dir = tmp_path / "org"
    bare_repo = org_dir / f"{repo_name}.git"
    org_dir.mkdir()
    subprocess.run(
        ["git", "clone", "--bare", str(origin), str(bare_repo)],
        check=True,
        capture_output=True,
        text=True,
    )

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "members": [
                    {
                        "slug": "hs-extensions",
                        "relative_path": "HsExtensions",
                    }
                ]
            }
        )
    )

    base_dir = tmp_path / "HorizontalSystems"
    env = {
        **os.environ,
        "PALACE_SWIFT_KIT_GITHUB_ORG": str(org_dir),
    }
    out = subprocess.run(
        [
            "bash",
            str(SCRIPT),
            "--slug",
            "hs-extensions",
            "--manifest",
            str(manifest),
            "--base",
            str(base_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["repo_name"] == repo_name
    assert payload["clone_url"] == f"{org_dir}/{repo_name}.git"
    assert (base_dir / repo_name / ".git").is_dir()
    assert (base_dir / "hs-extensions").is_symlink()
    assert os.readlink(base_dir / "hs-extensions") == repo_name
