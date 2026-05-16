"""Hardened subprocess wrapper for read-only git invocations.

Single fork point for every git call. Enforces Section 5 invariants
of the spec: whitelist, env sanitization, timeout, capped streaming,
stderr drain on kill.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_VERBS: frozenset[str] = frozenset(
    {"log", "show", "blame", "diff", "ls-tree", "cat-file"}
)

DEFAULT_TIMEOUT_S: float = 10.0

SAFE_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
}


@dataclass(frozen=True)
class GitResult:
    """Outcome of a single git subprocess run."""

    rc: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool


class ForbiddenGitCommand(ValueError):
    def __init__(self, verb: str) -> None:
        super().__init__(f"git verb not allowed: {verb!r}")
        self.verb = verb


class GitTimeout(RuntimeError):
    pass


class GitError(RuntimeError):
    def __init__(self, rc: int, stderr: str) -> None:
        super().__init__(f"git exit {rc}: {stderr[:200]}")
        self.rc = rc
        self.stderr = stderr


def run_git(
    args: list[str],
    *,
    repo_path: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_stdout_lines: int | None = None,
) -> GitResult:
    """Run `git <args>` under `repo_path` with hardened env.

    - args[0] must be in ALLOWED_VERBS.
    - Output capped at max_stdout_lines if provided; truncation at
      line boundary.
    """
    if not args:
        raise ForbiddenGitCommand("")
    verb = args[0]
    if verb not in ALLOWED_VERBS:
        raise ForbiddenGitCommand(verb)

    git_bin = shutil.which("git", path=SAFE_ENV["PATH"])
    if git_bin is None:
        raise GitError(
            rc=-1, stderr=f"git binary not found in PATH={SAFE_ENV['PATH']!r}"
        )
    full = [git_bin, "-C", str(repo_path), *args]

    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            full,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(SAFE_ENV),
            cwd=str(repo_path),
            bufsize=0,
        )
    except (FileNotFoundError, OSError) as exc:
        raise GitError(rc=-1, stderr=f"git: {exc}") from exc

    stdout_lines: list[str] = []
    truncated = False
    try:
        assert proc.stdout is not None
        raw = proc.stdout
        # Decode line-by-line with replacement.
        while True:
            line_bytes = raw.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            stdout_lines.append(line)
            if max_stdout_lines is not None and len(stdout_lines) >= max_stdout_lines:
                truncated = True
                break
            # Timeout check.
            if time.monotonic() - start > timeout_s:
                _drain_and_kill(proc)
                raise GitTimeout(f"git {verb} exceeded {timeout_s}s")
    except GitTimeout:
        raise
    except Exception as exc:
        _drain_and_kill(proc)
        raise GitError(rc=-1, stderr=str(exc)) from exc

    if truncated:
        stderr_tail = _drain_and_kill(proc)
        # Reaching the caller's output cap is an intentional success path.
        # Different platforms may report the killed producer as non-zero even
        # after we have already collected the requested output.
        rc = 0
    else:
        # Let it finish (bounded by timeout).
        try:
            _, stderr_bytes = proc.communicate(
                timeout=max(timeout_s - (time.monotonic() - start), 0.1)
            )
            stderr_tail = stderr_bytes.decode("utf-8", errors="replace")[:4096]
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            _drain_and_kill(proc)
            raise GitTimeout(f"git {verb} exceeded {timeout_s}s")

    duration_ms = int((time.monotonic() - start) * 1000)
    return GitResult(
        rc=rc,
        stdout="".join(stdout_lines),
        stderr=stderr_tail,
        duration_ms=duration_ms,
        truncated=truncated,
    )


def _drain_and_kill(proc: subprocess.Popen[bytes]) -> str:
    """Drain bounded stderr, kill, reap. See spec §5.7."""
    try:
        if proc.stdout is not None:
            proc.stdout.close()
        tail = b""
        if proc.stderr is not None:
            try:
                tail = proc.stderr.read(4096)
            except Exception:
                tail = b""
            proc.stderr.close()
        proc.kill()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning("git pid=%d did not exit after SIGKILL", proc.pid)
        return tail.decode("utf-8", errors="replace")
    except Exception:
        return ""
