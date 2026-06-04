from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent / "scripts" / "palace-periodic-reingest.sh"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_wrapper_runs_detector_when_project_env_is_unset(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "detector-ran"

    _write_executable(
        fake_bin / "uv",
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"palace_mcp.ops.detect_stale_files"* ]]; then
    printf '%s\\n' "$*" > "{marker}"
    printf '%s\\n' '{{"projects":[]}}'
    exit 0
fi
printf 'unexpected uv invocation: %s\\n' "$*" >&2
exit 64
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.pop("PALACE_PERIODIC_REINGEST_PROJECTS", None)

    result = subprocess.run(
        ["bash", str(_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert (
        marker.read_text(encoding="utf-8")
        .strip()
        .endswith("python -m palace_mcp.ops.detect_stale_files")
    )


def test_wrapper_preserves_flock_lock_busy_exit_code(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    lock_dir = tmp_path / "locks"
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    _write_executable(
        fake_bin / "uv",
        f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"palace_mcp.ops.detect_stale_files"* ]]; then
    printf '%s\\n' '{{"projects":[{{"project":"tron-kit","repo_path":"{repo_path}","language_profile":"swift_kit","requires_reingest":true,"errors":[]}}]}}'
    exit 0
fi
printf 'unexpected uv invocation: %s\\n' "$*" >&2
exit 64
""",
    )
    _write_executable(
        fake_bin / "flock",
        """#!/usr/bin/env bash
exit 75
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["PALACE_PERIODIC_REINGEST_LOCK_DIR"] = str(lock_dir)
    env["PALACE_PERIODIC_REINGEST_PROJECTS"] = "tron-kit"

    result = subprocess.run(
        ["bash", str(_SCRIPT_PATH)],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 75
    assert "[periodic-reingest] skip lock busy for tron-kit" in result.stderr
    assert "rc=0" not in result.stderr
