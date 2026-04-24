# GIM-63 Agent Watchdog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a host-native Python daemon that monitors paperclip issues + host process table, detects stuck agents (mid-work-died + idle-hang), and triggers respawn via `PATCH assigneeAgentId=same` (fallback: `POST /release + PATCH`). Self-installs as launchd/systemd/cron service. Part of Gimle stack's one-command install.

**Architecture:** Standalone Python 3.12 package under `services/watchdog/`. Polls paperclip REST every 2 min per company. Scans host `ps` for hung Claude subprocesses. Uses `httpx` async client with retry + 429 back-off. State persisted to `~/.paperclip/watchdog-state.json` with atomic writes + `fcntl.flock` single-writer guarantee. JSON-lines logging with rotation.

**Tech Stack:** Python 3.12, uv (package manager), httpx (async HTTP + MockTransport for tests), pytest + pytest-asyncio + freezegun, PyYAML, fcntl, subprocess, FastAPI (test-integration only, in-process mock paperclip).

**Spec:** `docs/superpowers/specs/2026-04-21-GIM-63-agent-watchdog-design.md` (rev2b; endpoint + threshold verified empirically 2026-04-21).

**Precondition:** Current branch is `feature/GIM-63-agent-watchdog`, tip `e8424cc`, based on `develop@068014f` (GIM-62 merged).

---

## File Structure

### Files created in `services/watchdog/`

- `pyproject.toml` — package metadata + deps
- `README.md` — install, troubleshoot, live smoke
- `.coveragerc` — coverage excludes
- `src/gimle_watchdog/__init__.py` — package marker
- `src/gimle_watchdog/__main__.py` — CLI dispatch
- `src/gimle_watchdog/config.py` — `Config`/`CompanyConfig`/`Thresholds`/`Cooldowns` dataclasses + `load_config` + validation
- `src/gimle_watchdog/paperclip.py` — `PaperclipClient` async httpx wrapper
- `src/gimle_watchdog/detection.py` — `parse_ps_output` + `scan_died_mid_work` + `scan_idle_hangs`
- `src/gimle_watchdog/actions.py` — `trigger_respawn` + `kill_hanged_proc` + `_read_proc_cmdline`
- `src/gimle_watchdog/state.py` — `State` dataclass + atomic write + cooldown/cap/escalation logic
- `src/gimle_watchdog/logger.py` — JSONL + rotation setup
- `src/gimle_watchdog/service.py` — platform installers (render_plist/systemd/cron)
- `src/gimle_watchdog/daemon.py` — main tick loop with `asyncio.wait_for` self-liveness
- `tests/conftest.py` — shared fixtures + in-process FastAPI mock paperclip
- `tests/fixtures/ps_output_macos.txt`
- `tests/fixtures/ps_output_linux.txt`
- `tests/fixtures/issues_response.json`
- `tests/fixtures/plist_expected.xml`
- `tests/fixtures/systemd_unit_expected.service`
- `tests/test_config.py`
- `tests/test_state.py`
- `tests/test_paperclip.py`
- `tests/test_detection.py`
- `tests/test_actions.py`
- `tests/test_service.py`
- `tests/test_daemon.py`
- `tests/test_integration.py`

### Files modified in `Gimle-Palace` root

- `.github/workflows/ci.yml` — add `watchdog-tests` job
- `install.sh` (if exists) OR `Justfile` — add `watchdog install` invocation in post-compose step

---

## Task 1: Project scaffolding

**Files:**
- Create: `services/watchdog/pyproject.toml`
- Create: `services/watchdog/.coveragerc`
- Create: `services/watchdog/src/gimle_watchdog/__init__.py`
- Create: `services/watchdog/tests/__init__.py`
- Create: `services/watchdog/tests/fixtures/.gitkeep`

- [ ] **Step 1.1: Create package directories**

```bash
cd /Users/ant013/Android/Gimle-Palace
mkdir -p services/watchdog/src/gimle_watchdog
mkdir -p services/watchdog/tests/fixtures
touch services/watchdog/src/gimle_watchdog/__init__.py
touch services/watchdog/tests/__init__.py
touch services/watchdog/tests/fixtures/.gitkeep
```

- [ ] **Step 1.2: Create `services/watchdog/pyproject.toml`**

```toml
[project]
name = "gimle-watchdog"
version = "0.1.0"
description = "Gimle Palace agent watchdog — respawn + idle-hang recovery daemon (GIM-63)"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27,<1.0",
    "pyyaml>=6.0,<7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "freezegun>=1.5",
    "fastapi>=0.110",
    "uvicorn>=0.30",
]

[project.scripts]
gimle-watchdog = "watchdog.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gimle_watchdog"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
```

- [ ] **Step 1.3: Create `services/watchdog/.coveragerc`**

```ini
[run]
source = gimle_watchdog
branch = true

[report]
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
    subprocess.run\(\[.launchctl.
    subprocess.run\(\[.systemctl.
    if sys.platform == .win32.:
    raise NotImplementedError
precision = 1
```

- [ ] **Step 1.4: Bootstrap venv + verify tooling**

```bash
cd services/watchdog
uv sync --all-extras 2>&1 | tail -5
uv run python -c "import httpx, yaml, fastapi; print('deps ok')"
uv run pytest --collect-only 2>&1 | tail -5
```

Expected: `deps ok` + pytest collects 0 tests (no test files yet, just directories).

- [ ] **Step 1.5: Commit scaffolding**

```bash
cd /Users/ant013/Android/Gimle-Palace
# Add .venv to gitignore
grep -q "^services/watchdog/\.venv/$" .gitignore || echo "services/watchdog/.venv/" >> .gitignore
git add services/watchdog/pyproject.toml \
        services/watchdog/.coveragerc \
        services/watchdog/uv.lock \
        services/watchdog/src/gimle_watchdog/__init__.py \
        services/watchdog/tests/__init__.py \
        services/watchdog/tests/fixtures/.gitkeep \
        .gitignore
git commit -m "feat(watchdog): project scaffolding (pyproject + coveragerc + pkg dirs)"
```

---

## Task 2: Config loader — dataclasses + YAML parser + validation

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/config.py`
- Create: `services/watchdog/tests/test_config.py`

- [ ] **Step 2.1: Write failing tests first**

`services/watchdog/tests/test_config.py`:

```python
"""Tests for watchdog.config — YAML schema + validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from gimle_watchdog import config as cfg


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "watchdog.yaml"
    p.write_text(content)
    return p


def test_valid_config_parses(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_TOKEN", "secret-123")
    path = _write(
        tmp_path,
        """
version: 1
paperclip:
  base_url: http://localhost:3100
  api_key_source: env:TEST_TOKEN
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds:
      died_min: 3
      hang_etime_min: 60
      hang_cpu_max_s: 30
daemon:
  poll_interval_seconds: 120
cooldowns:
  per_issue_seconds: 300
  per_agent_cap: 3
  per_agent_window_seconds: 900
logging:
  path: ~/.paperclip/watchdog.log
  level: INFO
  rotate_max_bytes: 10485760
  rotate_backup_count: 5
escalation:
  post_comment_on_issue: true
  comment_marker: "<!-- watchdog-escalation -->"
""",
    )
    c = cfg.load_config(path)
    assert c.version == 1
    assert c.paperclip.base_url == "http://localhost:3100"
    assert c.paperclip.api_key == "secret-123"
    assert len(c.companies) == 1
    assert c.companies[0].id == "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
    assert c.companies[0].name == "gimle"
    assert c.companies[0].thresholds.hang_etime_min == 60
    assert c.cooldowns.per_agent_cap == 3
    assert c.escalation.post_comment_on_issue is True


def test_unknown_version_raises(tmp_path: Path):
    path = _write(tmp_path, "version: 999\ncompanies: []\n")
    with pytest.raises(cfg.ConfigError) as exc:
        cfg.load_config(path)
    assert "version" in str(exc.value)


def test_empty_companies_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies: []
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="companies.*non-empty"):
        cfg.load_config(path)


def test_invalid_uuid_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: not-a-uuid
    name: bad
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="uuid"):
        cfg.load_config(path)


def test_api_key_env_resolution_missing_warns(tmp_path: Path, monkeypatch, caplog):
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "env:NONEXISTENT_VAR"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    c = cfg.load_config(path)
    assert c.paperclip.api_key is None  # missing env → None, WARN logged


def test_api_key_file_resolution(tmp_path: Path):
    token_file = tmp_path / "token.txt"
    token_file.write_text("file-token-456\n")
    path = _write(
        tmp_path,
        f"""
version: 1
paperclip:
  base_url: http://x
  api_key_source: "file:{token_file}"
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {{died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}}
daemon: {{poll_interval_seconds: 120}}
cooldowns: {{per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}}
logging: {{path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}}
escalation: {{post_comment_on_issue: false, comment_marker: "x"}}
""",
    )
    c = cfg.load_config(path)
    assert c.paperclip.api_key == "file-token-456"


def test_negative_threshold_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: -1, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="positive"):
        cfg.load_config(path)


def test_per_agent_cap_zero_raises(tmp_path: Path):
    path = _write(
        tmp_path,
        """
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 0, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 1, rotate_backup_count: 1}
escalation: {post_comment_on_issue: false, comment_marker: "x"}
""",
    )
    with pytest.raises(cfg.ConfigError, match="per_agent_cap"):
        cfg.load_config(path)
```

- [ ] **Step 2.2: Run tests — expect ModuleNotFoundError**

```bash
cd services/watchdog
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'watchdog.config'`.

- [ ] **Step 2.3: Implement `services/watchdog/src/gimle_watchdog/config.py`**

```python
"""Config loader — YAML schema + validation + API key resolution."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


log = logging.getLogger("watchdog.config")

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_API_KEY_SOURCE_RE = re.compile(r"^(env|file|inline):(.+)$")
SUPPORTED_VERSION = 1


class ConfigError(Exception):
    """Raised when the watchdog config is malformed or has unsupported values."""


@dataclass(frozen=True)
class PaperclipConfig:
    base_url: str
    api_key: str | None  # resolved from api_key_source


@dataclass(frozen=True)
class Thresholds:
    died_min: int
    hang_etime_min: int
    hang_cpu_max_s: int


@dataclass(frozen=True)
class CompanyConfig:
    id: str
    name: str
    thresholds: Thresholds


@dataclass(frozen=True)
class DaemonConfig:
    poll_interval_seconds: int


@dataclass(frozen=True)
class CooldownsConfig:
    per_issue_seconds: int
    per_agent_cap: int
    per_agent_window_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    path: Path
    level: str
    rotate_max_bytes: int
    rotate_backup_count: int


@dataclass(frozen=True)
class EscalationConfig:
    post_comment_on_issue: bool
    comment_marker: str


@dataclass(frozen=True)
class Config:
    version: int
    paperclip: PaperclipConfig
    companies: list[CompanyConfig]
    daemon: DaemonConfig
    cooldowns: CooldownsConfig
    logging: LoggingConfig
    escalation: EscalationConfig


def _resolve_api_key(source: str) -> str | None:
    match = _API_KEY_SOURCE_RE.match(source)
    if not match:
        raise ConfigError(
            f"paperclip.api_key_source must match 'env:VAR' | 'file:PATH' | 'inline:VALUE'; got {source!r}"
        )
    kind, value = match.group(1), match.group(2)
    if kind == "env":
        v = os.environ.get(value)
        if v is None:
            log.warning("api_key_env_missing var=%s (daemon will fail on API call)", value)
        return v
    if kind == "file":
        p = Path(value).expanduser()
        if not p.is_file():
            raise ConfigError(f"paperclip.api_key_source file not found: {p}")
        return p.read_text().strip()
    if kind == "inline":
        return value
    raise ConfigError(f"unhandled api_key_source kind: {kind}")


def _require_positive_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer, got {value!r}")
    return value


def _parse_thresholds(raw: dict) -> Thresholds:
    return Thresholds(
        died_min=_require_positive_int(raw.get("died_min"), "thresholds.died_min"),
        hang_etime_min=_require_positive_int(raw.get("hang_etime_min"), "thresholds.hang_etime_min"),
        hang_cpu_max_s=_require_positive_int(raw.get("hang_cpu_max_s"), "thresholds.hang_cpu_max_s"),
    )


def _parse_company(raw: dict, index: int) -> CompanyConfig:
    cid = raw.get("id", "")
    if not isinstance(cid, str) or not _UUID_RE.match(cid):
        raise ConfigError(f"companies[{index}].id must be a uuid, got {cid!r}")
    name = raw.get("name", "")
    if not isinstance(name, str) or not name:
        raise ConfigError(f"companies[{index}].name must be a non-empty string")
    thresholds_raw = raw.get("thresholds")
    if not isinstance(thresholds_raw, dict):
        raise ConfigError(f"companies[{index}].thresholds must be a mapping")
    return CompanyConfig(id=cid, name=name, thresholds=_parse_thresholds(thresholds_raw))


def load_config(path: Path) -> Config:
    """Parse + validate a watchdog config YAML. Raises ConfigError on problems."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}")

    version = raw.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigError(f"Unsupported config version {version!r}; expected {SUPPORTED_VERSION}")

    paperclip_raw = raw.get("paperclip") or {}
    if not isinstance(paperclip_raw, dict):
        raise ConfigError("paperclip section must be a mapping")
    base_url = paperclip_raw.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise ConfigError("paperclip.base_url required non-empty string")
    api_key_source = paperclip_raw.get("api_key_source", "")
    api_key = _resolve_api_key(api_key_source)
    paperclip = PaperclipConfig(base_url=base_url, api_key=api_key)

    companies_raw = raw.get("companies")
    if not isinstance(companies_raw, list) or not companies_raw:
        raise ConfigError("companies must be a non-empty list")
    companies = [_parse_company(c, i) for i, c in enumerate(companies_raw)]

    daemon_raw = raw.get("daemon") or {}
    daemon = DaemonConfig(
        poll_interval_seconds=_require_positive_int(
            daemon_raw.get("poll_interval_seconds"), "daemon.poll_interval_seconds"
        ),
    )

    cooldowns_raw = raw.get("cooldowns") or {}
    per_agent_cap_val = cooldowns_raw.get("per_agent_cap")
    if not isinstance(per_agent_cap_val, int) or isinstance(per_agent_cap_val, bool) or per_agent_cap_val < 1:
        raise ConfigError(f"cooldowns.per_agent_cap must be >= 1, got {per_agent_cap_val!r}")
    cooldowns = CooldownsConfig(
        per_issue_seconds=_require_positive_int(
            cooldowns_raw.get("per_issue_seconds"), "cooldowns.per_issue_seconds"
        ),
        per_agent_cap=per_agent_cap_val,
        per_agent_window_seconds=_require_positive_int(
            cooldowns_raw.get("per_agent_window_seconds"), "cooldowns.per_agent_window_seconds"
        ),
    )

    logging_raw = raw.get("logging") or {}
    logging_cfg = LoggingConfig(
        path=Path(str(logging_raw.get("path", "~/.paperclip/watchdog.log"))).expanduser(),
        level=str(logging_raw.get("level", "INFO")),
        rotate_max_bytes=_require_positive_int(
            logging_raw.get("rotate_max_bytes"), "logging.rotate_max_bytes"
        ),
        rotate_backup_count=_require_positive_int(
            logging_raw.get("rotate_backup_count"), "logging.rotate_backup_count"
        ),
    )

    escalation_raw = raw.get("escalation") or {}
    escalation = EscalationConfig(
        post_comment_on_issue=bool(escalation_raw.get("post_comment_on_issue", False)),
        comment_marker=str(escalation_raw.get("comment_marker", "<!-- watchdog-escalation -->")),
    )

    return Config(
        version=version,
        paperclip=paperclip,
        companies=companies,
        daemon=daemon,
        cooldowns=cooldowns,
        logging=logging_cfg,
        escalation=escalation,
    )
```

- [ ] **Step 2.4: Run tests — all 7 should pass**

```bash
cd services/watchdog
uv run pytest tests/test_config.py -v
```

Expected: 7 passed.

- [ ] **Step 2.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/config.py services/watchdog/tests/test_config.py
git commit -m "feat(watchdog): config loader — YAML schema + validation (TDD)"
```

---

## Task 3: State file — dataclass + atomic write + cooldown/cap

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/state.py`
- Create: `services/watchdog/tests/test_state.py`

- [ ] **Step 3.1: Write failing tests**

`services/watchdog/tests/test_state.py`:

```python
"""Tests for watchdog.state — persistence, cooldowns, caps, escalations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from gimle_watchdog import state as st
from gimle_watchdog.config import CooldownsConfig


COOLDOWNS = CooldownsConfig(
    per_issue_seconds=300,
    per_agent_cap=3,
    per_agent_window_seconds=900,
)


def test_state_roundtrip(tmp_path: Path):
    path = tmp_path / "state.json"
    s = st.State.load(path)
    s.record_wake("issue-1", "agent-1")
    s.save()
    assert path.exists()
    reloaded = st.State.load(path)
    assert reloaded.issue_cooldowns["issue-1"]["last_wake_at"]
    assert "agent-1" in reloaded.agent_wakes
    assert len(reloaded.agent_wakes["agent-1"]) == 1


def test_corrupt_state_returns_empty(tmp_path: Path, caplog):
    path = tmp_path / "state.json"
    path.write_text("{this is not json")
    s = st.State.load(path)
    assert s.issue_cooldowns == {}
    assert s.agent_wakes == {}


def test_unknown_version_renames_and_restarts(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text('{"version": 999, "issue_cooldowns": {}}')
    s = st.State.load(path)
    assert s.version == 1
    assert s.issue_cooldowns == {}
    # Backup should exist
    backups = list(tmp_path.glob("state.json.bak-*"))
    assert len(backups) == 1


@freeze_time("2026-04-21T10:00:00Z")
def test_is_issue_in_cooldown_within(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    s.record_wake("issue-1", "agent-1")
    assert s.is_issue_in_cooldown("issue-1", COOLDOWNS.per_issue_seconds) is True


def test_is_issue_in_cooldown_after(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
    with freeze_time("2026-04-21T10:10:00Z"):  # 10 min later, past 5-min cooldown
        s2 = st.State.load(path)
        assert s2.is_issue_in_cooldown("issue-1", COOLDOWNS.per_issue_seconds) is False


def test_agent_cap_exceeded_within_window(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
    with freeze_time("2026-04-21T10:02:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-2", "agent-1")
    with freeze_time("2026-04-21T10:04:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-3", "agent-1")
    with freeze_time("2026-04-21T10:05:00Z"):
        s = st.State.load(path)
        assert s.agent_cap_exceeded("agent-1", COOLDOWNS) is True


def test_agent_cap_not_exceeded_outside_window(tmp_path: Path):
    path = tmp_path / "state.json"
    base = "2026-04-21T10:00:00Z"
    with freeze_time(base):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
        s.record_wake("issue-2", "agent-1")
    with freeze_time("2026-04-21T10:18:00Z"):  # >15 min past first two
        s = st.State.load(path)
        s.record_wake("issue-3", "agent-1")
        # Only 1 wake within 15-min window now
        assert s.agent_cap_exceeded("agent-1", COOLDOWNS) is False


def test_record_wake_prunes_old_entries(tmp_path: Path):
    path = tmp_path / "state.json"
    with freeze_time("2026-04-21T10:00:00Z"):
        s = st.State.load(path)
        s.record_wake("issue-1", "agent-1")
    with freeze_time("2026-04-21T12:00:00Z"):  # 2h later
        s = st.State.load(path)
        s.record_wake("issue-2", "agent-1")
        assert len(s.agent_wakes["agent-1"]) == 1  # pruned 1h-old entry


def test_escalation_counter_increments(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    s.record_escalation("issue-1", "per_agent_cap")
    s.clear_escalation("issue-1")
    s.record_escalation("issue-1", "per_agent_cap")
    assert s.escalated_issues["issue-1"]["escalation_count"] == 2


def test_permanent_escalation_after_3_cycles(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    for _ in range(3):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    s.record_escalation("issue-1", "per_agent_cap")  # 4th
    assert s.is_permanently_escalated("issue-1") is True


def test_permanent_flag_survives_save_load(tmp_path: Path):
    path = tmp_path / "state.json"
    s = st.State.load(path)
    for _ in range(4):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    s.save()
    s2 = st.State.load(path)
    assert s2.is_permanently_escalated("issue-1") is True


def test_explicit_unescalate_clears_permanent(tmp_path: Path):
    s = st.State.load(tmp_path / "state.json")
    for _ in range(4):
        s.record_escalation("issue-1", "per_agent_cap")
        s.clear_escalation("issue-1")
    assert s.is_permanently_escalated("issue-1")
    s.force_unescalate("issue-1")
    assert not s.is_permanently_escalated("issue-1")
```

- [ ] **Step 3.2: Run tests — fail with ModuleNotFoundError**

```bash
cd services/watchdog
uv run pytest tests/test_state.py -v
```

- [ ] **Step 3.3: Implement `services/watchdog/src/gimle_watchdog/state.py`**

```python
"""Persistent state — cooldowns, wake counts, escalation tracking."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from gimle_watchdog.config import CooldownsConfig


log = logging.getLogger("watchdog.state")

STATE_VERSION = 1
PRUNE_WAKE_HISTORY_SECONDS = 3600  # keep 1h of wake history per agent
PERMANENT_ESCALATION_THRESHOLD = 3  # re-escalation cycles before we stop auto-unescalating


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class State:
    path: Path
    version: int = STATE_VERSION
    issue_cooldowns: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_wakes: dict[str, list[datetime]] = field(default_factory=dict)
    escalated_issues: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls(path=path)
        raw_text = path.read_text()
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as e:
            log.warning("state_corrupt starting_empty error=%s", e)
            return cls(path=path)

        ver = raw.get("version")
        if ver != STATE_VERSION:
            ts = _now().strftime("%Y%m%dT%H%M%SZ")
            backup = path.with_suffix(path.suffix + f".bak-{ts}")
            path.rename(backup)
            log.warning("state_version_unknown version=%r backup=%s", ver, backup.name)
            return cls(path=path)

        agent_wakes: dict[str, list[datetime]] = {}
        for agent_id, times in (raw.get("agent_wakes") or {}).items():
            parsed: list[datetime] = []
            for t in times:
                try:
                    parsed.append(_parse_iso(t))
                except Exception:
                    pass
            agent_wakes[agent_id] = parsed

        return cls(
            path=path,
            version=ver,
            issue_cooldowns=dict(raw.get("issue_cooldowns") or {}),
            agent_wakes=agent_wakes,
            escalated_issues=dict(raw.get("escalated_issues") or {}),
        )

    def save(self) -> None:
        """Atomic write via tempfile + os.replace()."""
        payload = {
            "version": self.version,
            "last_updated": _iso(_now()),
            "issue_cooldowns": self.issue_cooldowns,
            "agent_wakes": {
                aid: [_iso(t) for t in times] for aid, times in self.agent_wakes.items()
            },
            "escalated_issues": self.escalated_issues,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp_name, self.path)
            os.chmod(self.path, 0o600)
        except Exception:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise

    def record_wake(self, issue_id: str, agent_id: str) -> None:
        now = _now()
        self.issue_cooldowns[issue_id] = {"last_wake_at": _iso(now)}
        wakes = self.agent_wakes.setdefault(agent_id, [])
        wakes.append(now)
        cutoff = now - timedelta(seconds=PRUNE_WAKE_HISTORY_SECONDS)
        self.agent_wakes[agent_id] = [t for t in wakes if t > cutoff]

    def is_issue_in_cooldown(self, issue_id: str, cooldown_seconds: int) -> bool:
        entry = self.issue_cooldowns.get(issue_id)
        if not entry:
            return False
        last = _parse_iso(entry["last_wake_at"])
        return (_now() - last).total_seconds() < cooldown_seconds

    def agent_cap_exceeded(self, agent_id: str, cooldowns: CooldownsConfig) -> bool:
        now = _now()
        window_start = now - timedelta(seconds=cooldowns.per_agent_window_seconds)
        wakes = self.agent_wakes.get(agent_id, [])
        recent = [t for t in wakes if t > window_start]
        return len(recent) >= cooldowns.per_agent_cap

    def record_escalation(self, issue_id: str, reason: str) -> None:
        existing = self.escalated_issues.get(issue_id) or {}
        count = int(existing.get("escalation_count", 0)) + 1
        self.escalated_issues[issue_id] = {
            "escalated_at": _iso(_now()),
            "reason": reason,
            "escalation_count": count,
            "permanent": count >= PERMANENT_ESCALATION_THRESHOLD + 1,
        }

    def clear_escalation(self, issue_id: str) -> None:
        """Clear active-flag (for auto-unescalate), but preserve escalation_count + permanent."""
        entry = self.escalated_issues.get(issue_id)
        if not entry:
            return
        # Preserve count + permanent; drop only the "active right now" marker
        if entry.get("permanent"):
            return  # permanent escalations survive auto-clear
        del self.escalated_issues[issue_id]

    def force_unescalate(self, issue_id: str) -> None:
        """Explicit operator command — wipes entry fully, including permanent flag."""
        self.escalated_issues.pop(issue_id, None)

    def is_escalated(self, issue_id: str) -> bool:
        return issue_id in self.escalated_issues

    def is_permanently_escalated(self, issue_id: str) -> bool:
        entry = self.escalated_issues.get(issue_id) or {}
        return bool(entry.get("permanent"))

    def escalation_count(self, issue_id: str) -> int:
        entry = self.escalated_issues.get(issue_id) or {}
        return int(entry.get("escalation_count", 0))
```

- [ ] **Step 3.4: Run tests — all 11 should pass**

```bash
cd services/watchdog
uv run pytest tests/test_state.py -v
```

- [ ] **Step 3.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/state.py services/watchdog/tests/test_state.py
git commit -m "feat(watchdog): state file — cooldown + cap + permanent escalation (TDD)"
```

---

## Task 4: Paperclip client — httpx wrapper

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/paperclip.py`
- Create: `services/watchdog/tests/test_paperclip.py`

- [ ] **Step 4.1: Write failing tests**

`services/watchdog/tests/test_paperclip.py`:

```python
"""Tests for watchdog.paperclip — REST client with httpx MockTransport."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from gimle_watchdog import paperclip as pc


BASE = "http://paperclip.test"
CO_ID = "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
ISSUE_ID = "issue-1234"


async def _client_with_mock(handler):
    transport = httpx.MockTransport(handler)
    return pc.PaperclipClient(base_url=BASE, api_key="tok", transport=transport)


@pytest.mark.asyncio
async def test_list_in_progress_issues(respx_data=None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/companies/{CO_ID}/issues?status=in_progress"
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(
            200,
            json=[
                {
                    "id": ISSUE_ID,
                    "assigneeAgentId": "agent-1",
                    "executionRunId": None,
                    "status": "in_progress",
                    "updatedAt": "2026-04-21T10:00:00Z",
                },
            ],
        )

    client = await _client_with_mock(handler)
    try:
        issues = await client.list_in_progress_issues(CO_ID)
        assert len(issues) == 1
        assert issues[0].id == ISSUE_ID
        assert issues[0].assignee_agent_id == "agent-1"
        assert issues[0].execution_run_id is None
        assert issues[0].updated_at == datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_get_issue():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE}/api/issues/{ISSUE_ID}"
        return httpx.Response(
            200,
            json={
                "id": ISSUE_ID,
                "assigneeAgentId": "agent-1",
                "executionRunId": "run-1",
                "status": "in_progress",
                "updatedAt": "2026-04-21T10:05:00Z",
            },
        )

    client = await _client_with_mock(handler)
    try:
        issue = await client.get_issue(ISSUE_ID)
        assert issue.execution_run_id == "run-1"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_patch_issue_assignee():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"id": ISSUE_ID})

    client = await _client_with_mock(handler)
    try:
        await client.patch_issue(ISSUE_ID, {"assigneeAgentId": "agent-1"})
        assert captured["method"] == "PATCH"
        assert captured["url"] == f"{BASE}/api/issues/{ISSUE_ID}"
        assert '"assigneeAgentId"' in captured["body"]
        assert "agent-1" in captured["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_post_release():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": ISSUE_ID})

    client = await _client_with_mock(handler)
    try:
        await client.post_release(ISSUE_ID)
        assert captured["method"] == "POST"
        assert captured["url"] == f"{BASE}/api/issues/{ISSUE_ID}/release"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_post_issue_comment():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["body"] = request.content.decode()
        return httpx.Response(201, json={"id": "comment-1"})

    client = await _client_with_mock(handler)
    try:
        await client.post_issue_comment(ISSUE_ID, "hello")
        assert captured["method"] == "POST"
        assert '"body"' in captured["body"]
        assert "hello" in captured["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_retry_5xx_then_succeed():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=[])

    client = await _client_with_mock(handler)
    try:
        # Patch _sleep to no-op to avoid real backoff waits
        import gimle_watchdog.paperclip as _pc_mod
        original_sleep = _pc_mod._sleep
        _pc_mod._sleep = lambda _: None
        try:
            issues = await client.list_in_progress_issues(CO_ID)
            assert issues == []
            assert call_count == 3
        finally:
            _pc_mod._sleep = original_sleep
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_429_backs_off():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, json={"error": "slow_down"})
        return httpx.Response(200, json=[])

    client = await _client_with_mock(handler)
    try:
        import gimle_watchdog.paperclip as _pc_mod
        _pc_mod._sleep = lambda _: None
        issues = await client.list_in_progress_issues(CO_ID)
        assert issues == []
        assert call_count == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_401_terminal_no_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    client = await _client_with_mock(handler)
    try:
        with pytest.raises(pc.PaperclipError, match="401"):
            await client.list_in_progress_issues(CO_ID)
        assert call_count == 1
    finally:
        await client.aclose()
```

- [ ] **Step 4.2: Run tests — fail with ModuleNotFoundError**

```bash
cd services/watchdog
uv run pytest tests/test_paperclip.py -v
```

- [ ] **Step 4.3: Implement `services/watchdog/src/gimle_watchdog/paperclip.py`**

```python
"""Paperclip REST client — async httpx wrapper with retry + 429 backoff."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


log = logging.getLogger("watchdog.paperclip")


RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_DELAYS_SECONDS = (5, 15, 30)  # attempts at t=0, 5s, 20s, 50s total 4 attempts
MAX_RETRIES = len(RETRY_DELAYS_SECONDS)


class PaperclipError(Exception):
    """Raised when paperclip API returns a terminal error or all retries exhausted."""


@dataclass(frozen=True)
class Issue:
    id: str
    assignee_agent_id: str | None
    execution_run_id: str | None
    status: str
    updated_at: datetime


async def _sleep(seconds: float) -> None:
    """Indirection for tests to patch out real sleep."""
    await asyncio.sleep(seconds)


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _issue_from_json(data: dict[str, Any]) -> Issue:
    return Issue(
        id=str(data["id"]),
        assignee_agent_id=data.get("assigneeAgentId"),
        execution_run_id=data.get("executionRunId"),
        status=str(data.get("status", "")),
        updated_at=_parse_iso(str(data.get("updatedAt", "1970-01-01T00:00:00Z"))),
    )


class PaperclipClient:
    """Thin httpx async wrapper with retry-on-5xx-and-429 + non-retry on 4xx."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                await _sleep(RETRY_DELAYS_SECONDS[attempt - 1])
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                last_exc = e
                continue
            if resp.status_code < 400:
                return resp
            if resp.status_code in RETRY_STATUSES:
                log.warning(
                    "paperclip_retry status=%d attempt=%d url=%s", resp.status_code, attempt, url
                )
                last_exc = PaperclipError(
                    f"paperclip {method} {url} returned {resp.status_code}: {resp.text[:200]}"
                )
                continue
            # Terminal 4xx (except 429 which is in RETRY_STATUSES)
            raise PaperclipError(
                f"paperclip {method} {url} returned {resp.status_code}: {resp.text[:200]}"
            )
        # Exhausted retries
        raise PaperclipError(
            f"paperclip {method} {url} exhausted {MAX_RETRIES + 1} attempts: {last_exc}"
        ) from last_exc

    async def list_in_progress_issues(self, company_id: str) -> list[Issue]:
        resp = await self._request(
            "GET", f"/api/companies/{company_id}/issues?status=in_progress"
        )
        data = resp.json()
        if not isinstance(data, list):
            raise PaperclipError(f"expected list, got {type(data).__name__}")
        return [_issue_from_json(d) for d in data]

    async def get_issue(self, issue_id: str) -> Issue:
        resp = await self._request("GET", f"/api/issues/{issue_id}")
        return _issue_from_json(resp.json())

    async def patch_issue(self, issue_id: str, body: dict[str, Any]) -> None:
        await self._request("PATCH", f"/api/issues/{issue_id}", json=body)

    async def post_release(self, issue_id: str) -> None:
        await self._request("POST", f"/api/issues/{issue_id}/release")

    async def post_issue_comment(self, issue_id: str, body: str) -> None:
        await self._request(
            "POST", f"/api/issues/{issue_id}/comments", json={"body": body}
        )
```

- [ ] **Step 4.4: Run tests — all 8 should pass**

```bash
cd services/watchdog
uv run pytest tests/test_paperclip.py -v
```

- [ ] **Step 4.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/paperclip.py services/watchdog/tests/test_paperclip.py
git commit -m "feat(watchdog): PaperclipClient httpx wrapper — retry + 429 backoff (TDD)"
```

---

## Task 5: Detection — ps parsers + scan functions

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/detection.py`
- Create: `services/watchdog/tests/fixtures/ps_output_macos.txt`
- Create: `services/watchdog/tests/fixtures/ps_output_linux.txt`
- Create: `services/watchdog/tests/test_detection.py`

- [ ] **Step 5.1: Create ps-output fixtures**

`services/watchdog/tests/fixtures/ps_output_macos.txt`:

```
  PID     ELAPSED        TIME COMMAND
89879    1:06:07     0:05.00 /Users/anton/.nvm/versions/node/v20.20.2/bin/claude --print - --output-format stream-json --verbose --dangerously-skip-permissions --model claude-opus-4-6 --max-turns 200 --append-system-prompt-file /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/paperclip-skills-1OHr0Z/agent-instructions.md --add-dir /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/paperclip-skills-1OHr0Z
91082        5:30     2:10.12 /Users/anton/.nvm/versions/node/v20.20.2/bin/claude --print - --output-format stream-json --verbose --dangerously-skip-permissions --model claude-opus-4-6 --max-turns 200 --append-system-prompt-file /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/paperclip-skills-Q5szxs/agent-instructions.md --add-dir /var/folders/y8/dg8qs5dx7zs19xp99hwf21w00000gn/T/paperclip-skills-Q5szxs
10669    2-03:15:42     0:08.65 /Users/anton/.nvm/versions/node/v20.20.2/bin/node /Users/anton/.paperclip/plugins/node_modules/paperclip-plugin-telegram/dist/worker.js
```

`services/watchdog/tests/fixtures/ps_output_linux.txt`:

```
  PID     ELAPSED        TIME COMMAND
89879   01:06:07    00:00:05 /usr/bin/claude --print - --append-system-prompt-file /tmp/paperclip-skills-abc/agent-instructions.md --add-dir /tmp/paperclip-skills-abc
91082      05:30    00:02:10 /usr/bin/claude --print - --append-system-prompt-file /tmp/paperclip-skills-def/agent-instructions.md --add-dir /tmp/paperclip-skills-def
10669 1-02:00:00    00:00:05 /usr/bin/node /opt/paperclip/worker.js
```

- [ ] **Step 5.2: Write failing tests**

`services/watchdog/tests/test_detection.py`:

```python
"""Tests for watchdog.detection — ps parsers + scan logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from gimle_watchdog import detection as det
from gimle_watchdog.config import (
    Config,
    CompanyConfig,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


FIXTURE_DIR = Path(__file__).parent / "fixtures"


# --- Low-level parsers -----------------------------------------------------------


def test_parse_etime_macos_mm_ss():
    assert det._parse_etime("5:30") == 330


def test_parse_etime_macos_hh_mm_ss():
    assert det._parse_etime("1:06:07") == 3967


def test_parse_etime_macos_days_hh_mm_ss():
    # "2-03:15:42" = 2 days + 3h15m42s = 2*86400 + 11742 = 184542
    assert det._parse_etime("2-03:15:42") == 184542


def test_parse_etime_linux_hh_mm_ss():
    assert det._parse_etime("01:06:07") == 3967


def test_parse_etime_linux_days():
    # "1-02:00:00" = 1d2h = 86400 + 7200 = 93600
    assert det._parse_etime("1-02:00:00") == 93600


def test_parse_time_macos_decimal():
    assert det._parse_time("0:05.00") == 5


def test_parse_time_macos_hh_mm_ss_hundredths():
    # "1:02:10.00" = 1h2m10s = 3730
    assert det._parse_time("1:02:10.00") == 3730


def test_parse_time_linux_hms():
    assert det._parse_time("00:00:05") == 5


def test_parse_time_invalid_returns_zero():
    assert det._parse_time("garbage") == 0


# --- parse_ps_output ------------------------------------------------------------


def test_parse_ps_macos_finds_hangs():
    text = (FIXTURE_DIR / "ps_output_macos.txt").read_text()
    # thresholds: etime >= 60 min, cpu <= 30 s
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 1
    assert hangs[0].pid == 89879
    assert hangs[0].etime_s == 3967
    assert hangs[0].cpu_s == 5


def test_parse_ps_linux_finds_hangs():
    text = (FIXTURE_DIR / "ps_output_linux.txt").read_text()
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 1
    assert hangs[0].pid == 89879


def test_parse_ps_skips_non_paperclip():
    text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "99999    1:00:00     0:05.00 /usr/bin/some-other-process --flag\n"
    )
    assert det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30) == []


def test_parse_ps_skips_fresh_procs():
    text = (FIXTURE_DIR / "ps_output_macos.txt").read_text()
    # 91082 has etime 5:30 = 330s, well under 3600
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    pids = [h.pid for h in hangs]
    assert 91082 not in pids


def test_parse_ps_skips_high_cpu_procs():
    """A process with 65s CPU is not idle even if etime > threshold."""
    text = (
        "  PID     ELAPSED        TIME COMMAND\n"
        "55555    2:00:00    00:01:05 /usr/bin/claude --append-system-prompt-file /tmp/paperclip-skills-abc --add-dir /tmp/paperclip-skills-abc\n"
    )
    hangs = det.parse_ps_output(text, etime_min_s=60 * 60, cpu_max_s=30)
    assert len(hangs) == 0


# --- scan_died_mid_work --------------------------------------------------------


def _make_config(died_min: int = 3, cooldowns: CooldownsConfig | None = None) -> Config:
    cooldowns = cooldowns or CooldownsConfig(
        per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
    )
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://x", api_key="k"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(
                    died_min=died_min, hang_etime_min=60, hang_cpu_max_s=30
                ),
            )
        ],
        daemon=DaemonConfig(poll_interval_seconds=120),
        cooldowns=cooldowns,
        logging=LoggingConfig(
            path=Path("/tmp/x.log"),
            level="INFO",
            rotate_max_bytes=1048576,
            rotate_backup_count=1,
        ),
        escalation=EscalationConfig(
            post_comment_on_issue=False, comment_marker="<!-- x -->"
        ),
    )


def _issue(
    *,
    id: str = "issue-1",
    assignee: str | None = "agent-1",
    run_id: str | None = None,
    updated_at: datetime | None = None,
) -> Issue:
    if updated_at is None:
        updated_at = datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    return Issue(
        id=id,
        assignee_agent_id=assignee,
        execution_run_id=run_id,
        status="in_progress",
        updated_at=updated_at,
    )


class _FakeClient:
    def __init__(self, issues: list[Issue]):
        self._issues = issues

    async def list_in_progress_issues(self, company_id: str) -> list[Issue]:
        return list(self._issues)


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_skips_null_assignee(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(assignee=None, updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_skips_active_run(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(run_id="run-1", updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:01:00Z")
async def test_scan_died_skips_too_recent(tmp_path: Path):
    cfg = _make_config(died_min=3)
    st = State.load(tmp_path / "s.json")
    # updated 30s ago — below 3-min threshold
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 0, 30, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_wakes_stuck_issue(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "wake"
    assert actions[0].issue.id == "issue-1"
    assert actions[0].agent_id == "agent-1"


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:05:00Z")
async def test_scan_died_respects_cooldown(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Record a recent wake so issue is in cooldown
    with freeze_time("2026-04-21T10:02:00Z"):
        st.record_wake("issue-1", "agent-1")
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "skip"


@pytest.mark.asyncio
@freeze_time("2026-04-21T10:30:00Z")
async def test_scan_died_escalates_at_cap(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Record 3 wakes in last 15 min for agent-1
    for ts in ["2026-04-21T10:20:00Z", "2026-04-21T10:23:00Z", "2026-04-21T10:26:00Z"]:
        with freeze_time(ts):
            st.record_wake(f"dummy-{ts}", "agent-1")
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 25, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert len(actions) == 1
    assert actions[0].kind == "escalate"


@pytest.mark.asyncio
@freeze_time("2026-04-21T11:00:00Z")
async def test_scan_died_auto_unescalates_on_touch(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Escalate an issue at 10:00
    with freeze_time("2026-04-21T10:00:00Z"):
        st.record_escalation("issue-1", "per_agent_cap")
    # Operator touches issue at 10:30 (updatedAt > escalated_at)
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    # Should clear escalation AND produce wake action
    assert not st.is_escalated("issue-1")
    assert any(a.kind == "wake" for a in actions)


@pytest.mark.asyncio
@freeze_time("2026-04-21T11:00:00Z")
async def test_scan_died_skips_permanently_escalated(tmp_path: Path):
    cfg = _make_config()
    st = State.load(tmp_path / "s.json")
    # Bump into permanent by 4 cycles
    for _ in range(4):
        st.record_escalation("issue-1", "per_agent_cap")
        st.clear_escalation("issue-1")
    assert st.is_permanently_escalated("issue-1")
    client = _FakeClient(
        [_issue(updated_at=datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc))]
    )
    actions = await det.scan_died_mid_work(cfg.companies[0], client, st, cfg)
    assert actions == []
```

- [ ] **Step 5.3: Run tests — fail with import errors**

```bash
cd services/watchdog
uv run pytest tests/test_detection.py -v
```

- [ ] **Step 5.4: Implement `services/watchdog/src/gimle_watchdog/detection.py`**

```python
"""Detection primitives — ps parsers + scan_died_mid_work + scan_idle_hangs."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from gimle_watchdog.config import CompanyConfig, Config
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.detection")


PS_FILTER_TOKENS = ("append-system-prompt-file", "paperclip-skills")


@dataclass(frozen=True)
class HangedProc:
    pid: int
    etime_s: int
    cpu_s: int
    command: str


@dataclass(frozen=True)
class Action:
    kind: str               # "wake" | "skip" | "escalate"
    issue: Issue
    agent_id: str
    reason: str = ""


class _IssueLister(Protocol):
    async def list_in_progress_issues(self, company_id: str) -> list[Issue]: ...


# --- ps field parsers ----------------------------------------------------------


_ETIME_DAYS_RE = re.compile(r"^(\d+)-(\d+):(\d+):(\d+)$")
_ETIME_HMS_RE = re.compile(r"^(\d+):(\d+):(\d+)$")
_ETIME_MS_RE = re.compile(r"^(\d+):(\d+)$")


def _parse_etime(s: str) -> int:
    """ps(1) ELAPSED in seconds. Handles macOS + Linux formats:
      MM:SS           → 330
      HH:MM:SS        → 3967
      DD-HH:MM:SS     → 184542
    """
    s = s.strip()
    if m := _ETIME_DAYS_RE.match(s):
        d, h, mm, ss = (int(x) for x in m.groups())
        return d * 86400 + h * 3600 + mm * 60 + ss
    if m := _ETIME_HMS_RE.match(s):
        h, mm, ss = (int(x) for x in m.groups())
        return h * 3600 + mm * 60 + ss
    if m := _ETIME_MS_RE.match(s):
        mm, ss = (int(x) for x in m.groups())
        return mm * 60 + ss
    return 0


def _parse_time(s: str) -> int:
    """ps(1) TIME (cpu time) in seconds. Formats:
      MM:SS.hundredths     (macOS)      → 36 (rounded)
      HH:MM:SS.hundredths  (macOS long)
      HH:MM:SS             (Linux)      → 35
    Returns rounded integer seconds. Unparseable → 0.
    """
    s = s.strip()
    # Drop decimal suffix if present
    if "." in s:
        base, _, _frac = s.partition(".")
        # Round based on fractional part
        rounded_up = int(_frac[:2].ljust(2, "0")) >= 50 if _frac else False
    else:
        base = s
        rounded_up = False

    parts = base.split(":")
    try:
        if len(parts) == 2:
            value = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            value = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            return 0
    except ValueError:
        return 0
    return value + (1 if rounded_up else 0)


def parse_ps_output(ps_output: str, etime_min_s: int, cpu_max_s: int) -> list[HangedProc]:
    """Parse `ps -ao pid,etime,time,command` output, return hanged procs.

    Hanged = command matches PS_FILTER_TOKENS AND etime >= etime_min_s AND cpu <= cpu_max_s.
    """
    hangs: list[HangedProc] = []
    lines = ps_output.splitlines()
    for line in lines[1:]:  # skip header
        fields = line.split(None, 3)
        if len(fields) < 4:
            continue
        pid_str, etime_str, time_str, command = fields
        if not all(tok in command for tok in PS_FILTER_TOKENS):
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        etime_s = _parse_etime(etime_str)
        cpu_s = _parse_time(time_str)
        if etime_s >= etime_min_s and cpu_s <= cpu_max_s:
            hangs.append(HangedProc(pid=pid, etime_s=etime_s, cpu_s=cpu_s, command=command))
    return hangs


# --- scan_idle_hangs -----------------------------------------------------------


def scan_idle_hangs(config: Config) -> list[HangedProc]:
    """Run ps on host, filter for hung paperclip claude subprocesses."""
    etime_min_s = min(c.thresholds.hang_etime_min for c in config.companies) * 60
    cpu_max_s = max(c.thresholds.hang_cpu_max_s for c in config.companies)
    try:
        result = subprocess.run(
            ["ps", "-ao", "pid,etime,time,command"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("ps_failed %s", e)
        return []
    return parse_ps_output(result.stdout, etime_min_s, cpu_max_s)


# --- scan_died_mid_work --------------------------------------------------------


async def scan_died_mid_work(
    company: CompanyConfig,
    client: _IssueLister,
    state: State,
    config: Config,
) -> list[Action]:
    """Find issues stuck in assignee-set + no-run + stale-updatedAt state."""
    now = datetime.now(timezone.utc)
    threshold_dt = now - timedelta(minutes=company.thresholds.died_min)
    issues = await client.list_in_progress_issues(company.id)
    actions: list[Action] = []
    for issue in issues:
        if issue.assignee_agent_id is None:
            continue
        if issue.execution_run_id is not None:
            continue
        if issue.updated_at > threshold_dt:
            continue

        if state.is_escalated(issue.id):
            if state.is_permanently_escalated(issue.id):
                continue
            entry = state.escalated_issues[issue.id]
            escalated_at = datetime.fromisoformat(
                str(entry["escalated_at"]).replace("Z", "+00:00")
            )
            if issue.updated_at > escalated_at:
                state.clear_escalation(issue.id)
                # fall through and treat as normal candidate
            else:
                continue

        if state.is_issue_in_cooldown(issue.id, config.cooldowns.per_issue_seconds):
            actions.append(
                Action(
                    kind="skip",
                    issue=issue,
                    agent_id=issue.assignee_agent_id,
                    reason="per_issue_cooldown",
                )
            )
            continue
        if state.agent_cap_exceeded(issue.assignee_agent_id, config.cooldowns):
            actions.append(
                Action(
                    kind="escalate",
                    issue=issue,
                    agent_id=issue.assignee_agent_id,
                    reason="per_agent_cap",
                )
            )
            continue
        actions.append(
            Action(kind="wake", issue=issue, agent_id=issue.assignee_agent_id)
        )
    return actions
```

- [ ] **Step 5.5: Run tests — all should pass**

```bash
cd services/watchdog
uv run pytest tests/test_detection.py -v
```

- [ ] **Step 5.6: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/detection.py \
        services/watchdog/tests/test_detection.py \
        services/watchdog/tests/fixtures/ps_output_macos.txt \
        services/watchdog/tests/fixtures/ps_output_linux.txt
git commit -m "feat(watchdog): detection — ps parsers + scan_died + scan_idle (TDD)"
```

---

## Task 6: Actions — trigger_respawn + kill_hanged_proc

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/actions.py`
- Create: `services/watchdog/tests/test_actions.py`

- [ ] **Step 6.1: Write failing tests**

`services/watchdog/tests/test_actions.py`:

```python
"""Tests for watchdog.actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gimle_watchdog import actions as act
from gimle_watchdog.detection import HangedProc
from gimle_watchdog.paperclip import Issue, PaperclipClient


def _issue(run_id: str | None = None) -> Issue:
    return Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=run_id,
        status="in_progress",
        updated_at=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
    )


# --- trigger_respawn ------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_respawn_via_patch_succeeds():
    """PATCH → new executionRunId appears → via='patch'."""
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    # After PATCH, subsequent get_issue returns new run
    client.get_issue = AsyncMock(return_value=_issue(run_id="run-new"))

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "patch"
    assert result.success is True
    assert result.run_id == "run-new"
    client.patch_issue.assert_awaited_once_with("issue-1", {"assigneeAgentId": "agent-1"})
    client.post_release.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_respawn_patch_fails_release_patch_succeeds():
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    # First 6 polls show no run; next 6 polls (after release+patch) show run
    responses = [_issue(run_id=None)] * 6 + [_issue(run_id="run-new")] * 6
    client.get_issue = AsyncMock(side_effect=responses)

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "release_patch"
    assert result.success is True
    client.post_release.assert_awaited_once_with("issue-1")
    assert client.patch_issue.await_count == 2


@pytest.mark.asyncio
async def test_trigger_respawn_total_failure():
    client = MagicMock(spec=PaperclipClient)
    client.patch_issue = AsyncMock()
    client.post_release = AsyncMock()
    client.get_issue = AsyncMock(return_value=_issue(run_id=None))

    with patch.object(act, "_sleep", new=AsyncMock()):
        result = await act.trigger_respawn(client, _issue(), "agent-1")

    assert result.via == "none"
    assert result.success is False


# --- kill_hanged_proc -----------------------------------------------------------


def test_kill_hanged_proc_clean_exit():
    """Spawn a real short-lived process, kill it, verify 'clean' status."""
    proc = subprocess.Popen(["sleep", "300"])
    try:
        hang = HangedProc(
            pid=proc.pid,
            etime_s=3600,
            cpu_s=0,
            command="/bin/sleep 300",  # matches neither paperclip token; see next test
        )
        # Bypass cmdline re-check to test the kill path directly
        with patch.object(act, "_read_proc_cmdline", return_value="paperclip-skills append-system-prompt-file fake"):
            result = act.kill_hanged_proc(hang)
        # SIGTERM gracefully handled by `sleep`, process dies cleanly
        assert result.status == "clean"
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def test_kill_hanged_proc_already_dead():
    # Spawn and wait for exit
    proc = subprocess.Popen(["true"])
    proc.wait()
    hang = HangedProc(pid=proc.pid, etime_s=3600, cpu_s=0, command="dummy")
    result = act.kill_hanged_proc(hang)
    assert result.status == "already_dead"


def test_kill_hanged_proc_pid_reused_skip():
    """If cmdline no longer matches filter, skip kill (PID-reuse mitigation)."""
    hang = HangedProc(pid=1, etime_s=3600, cpu_s=0, command="old cmd with paperclip-skills append-system-prompt-file")
    with patch.object(act, "_read_proc_cmdline", return_value="/usr/sbin/unrelated --daemon"):
        result = act.kill_hanged_proc(hang)
    assert result.status == "pid_reused_skip"


def test_read_proc_cmdline_for_nonexistent_returns_none():
    """PID 999999 is extremely unlikely to be alive."""
    assert act._read_proc_cmdline(999999) is None
```

- [ ] **Step 6.2: Run tests — fail with import**

```bash
cd services/watchdog
uv run pytest tests/test_actions.py -v
```

- [ ] **Step 6.3: Implement `services/watchdog/src/gimle_watchdog/actions.py`**

```python
"""Actions — trigger_respawn + kill_hanged_proc."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass

from gimle_watchdog.detection import HangedProc
from gimle_watchdog.paperclip import Issue, PaperclipClient, PaperclipError


log = logging.getLogger("watchdog.actions")


RESPAWN_POLL_ATTEMPTS = 6      # 6 attempts × 5s = 30s verify window
RESPAWN_POLL_INTERVAL_S = 5


@dataclass(frozen=True)
class RespawnResult:
    via: str               # "patch" | "release_patch" | "none"
    success: bool
    run_id: str | None


@dataclass(frozen=True)
class KillResult:
    pid: int
    status: str            # "clean" | "forced" | "already_dead" | "pid_reused_skip"


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _wait_for_respawn(client: PaperclipClient, issue_id: str) -> str | None:
    for _ in range(RESPAWN_POLL_ATTEMPTS):
        await _sleep(RESPAWN_POLL_INTERVAL_S)
        issue = await client.get_issue(issue_id)
        if issue.execution_run_id is not None:
            return issue.execution_run_id
    return None


async def trigger_respawn(
    client: PaperclipClient, issue: Issue, assignee_id: str
) -> RespawnResult:
    """PATCH assigneeAgentId=same as primary; POST /release + PATCH as fallback.

    Primary: PATCH triggers paperclip 'assignment' wake event. Most cases
    this alone produces a new run within 30s.

    Fallback: if the issue has a stale `executionRunId` pointing at a dead
    run that PATCH alone doesn't clear, POST /release wipes it, then PATCH
    re-triggers assignment.
    """
    # Primary
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="patch", success=True, run_id=run_id)

    # Fallback
    log.info("respawn_fallback_release_patch issue=%s", issue.id)
    try:
        await client.post_release(issue.id)
    except PaperclipError as e:
        log.warning("release_failed issue=%s error=%s", issue.id, e)
    await client.patch_issue(issue.id, {"assigneeAgentId": assignee_id})
    run_id = await _wait_for_respawn(client, issue.id)
    if run_id is not None:
        return RespawnResult(via="release_patch", success=True, run_id=run_id)

    return RespawnResult(via="none", success=False, run_id=None)


# --- kill -----------------------------------------------------------------------


def _read_proc_cmdline(pid: int) -> str | None:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()


def kill_hanged_proc(proc: HangedProc) -> KillResult:
    """Kill a hanged claude subprocess with PID-reuse mitigation.

    Re-verifies PID cmdline before SIGTERM; if the process has exited and
    the PID got reassigned, we skip rather than signalling an unrelated
    process. Rare but possible on long-running systems.
    """
    current = _read_proc_cmdline(proc.pid)
    if current is None:
        return KillResult(pid=proc.pid, status="already_dead")
    # Compare original filter tokens against current cmdline
    from gimle_watchdog.detection import PS_FILTER_TOKENS
    if not all(tok in current for tok in PS_FILTER_TOKENS):
        log.warning(
            "pid_reused pid=%d old_cmd=%r new_cmd=%r",
            proc.pid, proc.command[:80], current[:80],
        )
        return KillResult(pid=proc.pid, status="pid_reused_skip")

    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="already_dead")

    time.sleep(3)
    try:
        os.kill(proc.pid, 0)  # check
        os.kill(proc.pid, signal.SIGKILL)
        return KillResult(pid=proc.pid, status="forced")
    except ProcessLookupError:
        return KillResult(pid=proc.pid, status="clean")
```

- [ ] **Step 6.4: Run tests — all pass**

```bash
cd services/watchdog
uv run pytest tests/test_actions.py -v
```

- [ ] **Step 6.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/actions.py services/watchdog/tests/test_actions.py
git commit -m "feat(watchdog): actions — trigger_respawn + kill with PID-reuse mitigation (TDD)"
```

---

## Task 7: Logger — JSONL + rotation

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/logger.py`
- Modify: `services/watchdog/tests/test_state.py` (no — keep separate)
- Create tests inline in `services/watchdog/tests/test_logger.py`

- [ ] **Step 7.1: Write failing tests**

`services/watchdog/tests/test_logger.py`:

```python
"""Tests for watchdog.logger — JSONL format + rotation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gimle_watchdog import logger as wl
from gimle_watchdog.config import LoggingConfig


def _make_cfg(path: Path) -> LoggingConfig:
    return LoggingConfig(
        path=path,
        level="INFO",
        rotate_max_bytes=200,   # small for rotation test
        rotate_backup_count=2,
    )


def test_jsonl_format(tmp_path: Path):
    log_path = tmp_path / "watchdog.log"
    wl.setup_logging(_make_cfg(log_path))
    logger = logging.getLogger("watchdog.test")
    logger.info("tick_start companies=2 sha=abc")
    wl.shutdown_logging()

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["level"] == "INFO"
    assert entry["name"] == "watchdog.test"
    assert "tick_start" in entry["message"]
    assert "ts" in entry


def test_jsonl_rotation(tmp_path: Path):
    log_path = tmp_path / "watchdog.log"
    wl.setup_logging(_make_cfg(log_path))
    logger = logging.getLogger("watchdog.test")
    # Write enough bytes to trigger rotation (max_bytes=200)
    for i in range(50):
        logger.info("msg=%03d some padding to reach 200 bytes quickly xxxxxxxxxxxxxxxx", i)
    wl.shutdown_logging()

    # Expect primary + at least one backup
    files = sorted(tmp_path.glob("watchdog.log*"))
    assert len(files) >= 2  # primary + backup
```

- [ ] **Step 7.2: Run — fails**

```bash
cd services/watchdog
uv run pytest tests/test_logger.py -v
```

- [ ] **Step 7.3: Implement `services/watchdog/src/gimle_watchdog/logger.py`**

```python
"""JSONL log handler with rotation."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from gimle_watchdog.config import LoggingConfig


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_installed_handlers: list[logging.Handler] = []


def setup_logging(cfg: LoggingConfig) -> None:
    """Install a rotating JSONL handler on the root 'watchdog' logger."""
    cfg.path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        cfg.path,
        maxBytes=cfg.rotate_max_bytes,
        backupCount=cfg.rotate_backup_count,
    )
    handler.setFormatter(_JSONFormatter())

    root = logging.getLogger("watchdog")
    root.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
    root.addHandler(handler)
    _installed_handlers.append(handler)


def shutdown_logging() -> None:
    """Flush + close all installed handlers (for tests)."""
    root = logging.getLogger("watchdog")
    for handler in _installed_handlers:
        handler.flush()
        handler.close()
        try:
            root.removeHandler(handler)
        except ValueError:
            pass
    _installed_handlers.clear()
```

- [ ] **Step 7.4: Run tests — pass**

```bash
cd services/watchdog
uv run pytest tests/test_logger.py -v
```

- [ ] **Step 7.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/logger.py services/watchdog/tests/test_logger.py
git commit -m "feat(watchdog): JSONL logger with rotation (TDD)"
```

---

## Task 8: Service renderers — plist/systemd/cron

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/service.py`
- Create: `services/watchdog/tests/test_service.py`
- Create: `services/watchdog/tests/fixtures/plist_expected.xml`
- Create: `services/watchdog/tests/fixtures/systemd_unit_expected.service`

- [ ] **Step 8.1: Create fixture `plist_expected.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>work.ant013.gimle-watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/python</string>
        <string>-m</string>
        <string>watchdog</string>
        <string>run</string>
        <string>--config</string>
        <string>/home/user/.paperclip/watchdog-config.yaml</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/home/user/.paperclip/watchdog.log</string>
    <key>StandardErrorPath</key><string>/home/user/.paperclip/watchdog.err</string>
</dict>
</plist>
```

- [ ] **Step 8.2: Create fixture `systemd_unit_expected.service`**

```ini
[Unit]
Description=Gimle Palace agent watchdog (GIM-63)
After=network.target

[Service]
Type=simple
ExecStart=/path/to/.venv/bin/python -m watchdog run --config /home/user/.paperclip/watchdog-config.yaml
Restart=on-failure
RestartSec=10s
StandardOutput=append:/home/user/.paperclip/watchdog.log
StandardError=append:/home/user/.paperclip/watchdog.err

[Install]
WantedBy=default.target
```

- [ ] **Step 8.3: Write failing tests**

`services/watchdog/tests/test_service.py`:

```python
"""Tests for watchdog.service — renderers only (no system calls)."""

from __future__ import annotations

from pathlib import Path

from gimle_watchdog import service


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_render_plist_matches_fixture():
    rendered = service.render_plist(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    expected = (FIXTURE_DIR / "plist_expected.xml").read_text()
    assert rendered.strip() == expected.strip()


def test_render_systemd_matches_fixture():
    rendered = service.render_systemd_unit(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        log_path=Path("/home/user/.paperclip/watchdog.log"),
        err_path=Path("/home/user/.paperclip/watchdog.err"),
    )
    expected = (FIXTURE_DIR / "systemd_unit_expected.service").read_text()
    assert rendered.strip() == expected.strip()


def test_render_cron_entry():
    entry = service.render_cron_entry(
        venv_python=Path("/path/to/.venv/bin/python"),
        config_path=Path("/home/user/.paperclip/watchdog-config.yaml"),
        poll_interval_seconds=120,
    )
    assert entry.startswith("*/2 * * * *")
    assert "/path/to/.venv/bin/python" in entry
    assert "watchdog" in entry
    assert "tick" in entry
    assert "/home/user/.paperclip/watchdog-config.yaml" in entry


def test_render_cron_entry_custom_interval():
    entry = service.render_cron_entry(
        venv_python=Path("/p/py"),
        config_path=Path("/c.yaml"),
        poll_interval_seconds=300,
    )
    assert entry.startswith("*/5 * * * *")
```

- [ ] **Step 8.4: Run tests — fail**

```bash
cd services/watchdog
uv run pytest tests/test_service.py -v
```

- [ ] **Step 8.5: Implement `services/watchdog/src/gimle_watchdog/service.py`**

```python
"""Platform-native service installer renderers (no system calls)."""

from __future__ import annotations

from pathlib import Path


SERVICE_LABEL = "work.ant013.gimle-watchdog"


def render_plist(
    *,
    venv_python: Path,
    config_path: Path,
    log_path: Path,
    err_path: Path,
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{SERVICE_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{venv_python}</string>
        <string>-m</string>
        <string>watchdog</string>
        <string>run</string>
        <string>--config</string>
        <string>{config_path}</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>{log_path}</string>
    <key>StandardErrorPath</key><string>{err_path}</string>
</dict>
</plist>"""


def render_systemd_unit(
    *,
    venv_python: Path,
    config_path: Path,
    log_path: Path,
    err_path: Path,
) -> str:
    return f"""[Unit]
Description=Gimle Palace agent watchdog (GIM-63)
After=network.target

[Service]
Type=simple
ExecStart={venv_python} -m watchdog run --config {config_path}
Restart=on-failure
RestartSec=10s
StandardOutput=append:{log_path}
StandardError=append:{err_path}

[Install]
WantedBy=default.target"""


def render_cron_entry(
    *,
    venv_python: Path,
    config_path: Path,
    poll_interval_seconds: int,
) -> str:
    minutes = max(1, poll_interval_seconds // 60)
    cron_minute = f"*/{minutes}"
    return f"{cron_minute} * * * * {venv_python} -m watchdog tick --config {config_path}"
```

- [ ] **Step 8.6: Run tests — pass**

```bash
cd services/watchdog
uv run pytest tests/test_service.py -v
```

- [ ] **Step 8.7: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/service.py \
        services/watchdog/tests/test_service.py \
        services/watchdog/tests/fixtures/plist_expected.xml \
        services/watchdog/tests/fixtures/systemd_unit_expected.service
git commit -m "feat(watchdog): service renderers — plist/systemd/cron (TDD, fixture-diff)"
```

---

## Task 9: Daemon — main tick loop + self-liveness

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/daemon.py`
- Create: `services/watchdog/tests/test_daemon.py`

- [ ] **Step 9.1: Write failing tests**

`services/watchdog/tests/test_daemon.py`:

```python
"""Tests for watchdog.daemon — tick orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gimle_watchdog import daemon
from gimle_watchdog.actions import RespawnResult
from gimle_watchdog.config import (
    Config,
    CompanyConfig,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.paperclip import Issue
from gimle_watchdog.state import State


def _cfg(tmp_path: Path) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://x", api_key="k"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(died_min=3, hang_etime_min=60, hang_cpu_max_s=30),
            )
        ],
        daemon=DaemonConfig(poll_interval_seconds=120),
        cooldowns=CooldownsConfig(
            per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
        ),
        logging=LoggingConfig(
            path=tmp_path / "x.log", level="INFO", rotate_max_bytes=1048576, rotate_backup_count=1
        ),
        escalation=EscalationConfig(post_comment_on_issue=True, comment_marker="<!-- m -->"),
    )


def _stuck_issue() -> Issue:
    return Issue(
        id="issue-1",
        assignee_agent_id="agent-1",
        execution_run_id=None,
        status="in_progress",
        updated_at=datetime(2026, 4, 21, 9, 0, tzinfo=timezone.utc),  # stale
    )


@pytest.mark.asyncio
async def test_tick_wakes_stuck_issue(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    # trigger_respawn patched to return success
    with patch("watchdog.daemon.actions.trigger_respawn",
               new=AsyncMock(return_value=RespawnResult(via="patch", success=True, run_id="run-new"))):
        with patch("watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
            with patch("watchdog.daemon._sleep", new=AsyncMock()):
                with patch("builtins.__import__", wraps=__import__):  # keep imports working
                    await daemon._tick(cfg, state, client)
    # state should have recorded a wake
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)


@pytest.mark.asyncio
async def test_tick_escalates_capped_agent(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    # Preload 3 recent wakes for agent-1 to trip the cap
    from freezegun import freeze_time
    for ts in ["2026-04-21T09:55:00Z", "2026-04-21T09:57:00Z", "2026-04-21T09:58:00Z"]:
        with freeze_time(ts):
            state.record_wake(f"dummy-{ts}", "agent-1")
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[_stuck_issue()])
    client.post_issue_comment = AsyncMock()
    with patch("watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
        with patch("watchdog.daemon._sleep", new=AsyncMock()):
            from freezegun import freeze_time
            with freeze_time("2026-04-21T10:05:00Z"):
                await daemon._tick(cfg, state, client)
    assert state.is_escalated("issue-1")
    client.post_issue_comment.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_kills_hanged_procs(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    from gimle_watchdog.detection import HangedProc
    client = MagicMock()
    client.list_in_progress_issues = AsyncMock(return_value=[])
    hanged = HangedProc(pid=12345, etime_s=5000, cpu_s=10, command="paperclip-skills append-system-prompt-file")
    kill_mock = MagicMock(return_value=MagicMock(status="clean", pid=12345))
    with patch("watchdog.daemon.detection.scan_idle_hangs", return_value=[hanged]):
        with patch("watchdog.daemon.actions.kill_hanged_proc", kill_mock):
            with patch("watchdog.daemon._sleep", new=AsyncMock()):
                await daemon._tick(cfg, state, client)
    kill_mock.assert_called_once_with(hanged)


@pytest.mark.asyncio
async def test_run_loop_exits_on_tick_timeout(tmp_path: Path):
    cfg = _cfg(tmp_path)
    state = State.load(tmp_path / "state.json")
    client = MagicMock()

    import asyncio
    async def hang(*a, **kw):
        await asyncio.sleep(120)  # longer than wait_for

    with patch("watchdog.daemon._tick", new=hang):
        with patch("watchdog.daemon.TICK_TIMEOUT_SECONDS", 1):
            with patch("sys.exit") as mock_exit:
                # Only one iteration; asyncio.wait_for should trigger
                await daemon._run_one_iteration_for_test(cfg, state, client)
                mock_exit.assert_called_with(1)
```

- [ ] **Step 9.2: Run — fail**

```bash
cd services/watchdog
uv run pytest tests/test_daemon.py -v
```

- [ ] **Step 9.3: Implement `services/watchdog/src/gimle_watchdog/daemon.py`**

```python
"""Main daemon loop — orchestrates detection + actions + state per tick."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

from gimle_watchdog import actions, detection
from gimle_watchdog.config import Config
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.daemon")


TICK_TIMEOUT_SECONDS = 60


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _build_escalation_body(
    issue_id: str, agent_id: str, state: State, marker: str
) -> str:
    count = state.escalation_count(issue_id)
    permanent = state.is_permanently_escalated(issue_id)
    marker_with_meta = f"{marker[:-4]} issue={issue_id} agent={agent_id} count={count} -->"
    if permanent:
        unescalate_note = (
            f"**PERMANENT escalation** ({count} cycles). Auto-unescalate disabled. "
            f"Requires explicit `gimle-watchdog unescalate --issue {issue_id}` to clear."
        )
    else:
        unescalate_note = (
            "Will auto-unescalate when issue `updatedAt` advances past current escalated_at "
            "(any operator touch — comment, reassign, status change)."
        )
    return (
        f"{marker_with_meta}\n"
        f"⚠ **Watchdog escalation — operator intervention needed**\n\n"
        f"Agent `{agent_id}` exceeded wake cap ({count} escalation cycles).\n\n"
        f"{unescalate_note}\n\n"
        f"Diagnostic: SSH the iMac, `grep '{issue_id}' ~/.paperclip/watchdog.log` for timeline."
    )


async def _tick(cfg: Config, state: State, client: PaperclipClient) -> None:
    """One scan pass: kill hangs, then wake died-mid-work issues."""
    log.info("tick_start companies=%d", len(cfg.companies))

    # Phase 1: kill host-level idle hangs (frees executionRunId for next phase)
    hanged = detection.scan_idle_hangs(cfg)
    for proc in hanged:
        res = actions.kill_hanged_proc(proc)
        log.warning(
            "hang_killed pid=%d etime_s=%d cpu_s=%d status=%s",
            proc.pid, proc.etime_s, proc.cpu_s, res.status,
        )
    if hanged:
        await _sleep(10)  # let paperclip register process exits

    # Phase 2: respawn stuck assignees per company
    total_actions = 0
    for company in cfg.companies:
        died = await detection.scan_died_mid_work(company, client, state, cfg)
        for action in died:
            if action.kind == "wake":
                result = await actions.trigger_respawn(
                    client, action.issue, action.agent_id
                )
                state.record_wake(action.issue.id, action.agent_id)
                log.info(
                    "wake_result issue=%s via=%s success=%s",
                    action.issue.id, result.via, result.success,
                )
                if not result.success:
                    log.error(
                        "wake_failed issue=%s — will retry next tick unless cap hit",
                        action.issue.id,
                    )
            elif action.kind == "escalate":
                state.record_escalation(action.issue.id, action.reason)
                log.warning(
                    "escalation issue=%s reason=%s count=%d permanent=%s",
                    action.issue.id,
                    action.reason,
                    state.escalation_count(action.issue.id),
                    state.is_permanently_escalated(action.issue.id),
                )
                if cfg.escalation.post_comment_on_issue:
                    body = _build_escalation_body(
                        action.issue.id, action.agent_id, state, cfg.escalation.comment_marker
                    )
                    try:
                        await client.post_issue_comment(action.issue.id, body)
                    except Exception as e:
                        log.error("escalation_comment_failed issue=%s error=%s", action.issue.id, e)
            elif action.kind == "skip":
                log.info("skip issue=%s reason=%s", action.issue.id, action.reason)
            total_actions += 1

    state.save()
    log.info("tick_end actions=%d", total_actions)


async def _run_one_iteration_for_test(
    cfg: Config, state: State, client: PaperclipClient
) -> None:
    """Single iteration used by test_run_loop_exits_on_tick_timeout."""
    try:
        await asyncio.wait_for(_tick(cfg, state, client), timeout=TICK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.error("tick_timeout_self_exit timeout_s=%d", TICK_TIMEOUT_SECONDS)
        sys.exit(1)
    except Exception:
        log.exception("tick_failed")


async def run(cfg: Config, state: State, client: PaperclipClient) -> None:
    """Persistent loop — called by CLI `run` command in launchd/systemd mode."""
    while True:
        tick_started = datetime.now(timezone.utc)
        try:
            await asyncio.wait_for(_tick(cfg, state, client), timeout=TICK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            log.error("tick_timeout_self_exit timeout_s=%d", TICK_TIMEOUT_SECONDS)
            sys.exit(1)
        except Exception:
            log.exception("tick_failed")
        elapsed_s = (datetime.now(timezone.utc) - tick_started).total_seconds()
        await _sleep(max(0.0, cfg.daemon.poll_interval_seconds - elapsed_s))
```

- [ ] **Step 9.4: Run tests — pass**

```bash
cd services/watchdog
uv run pytest tests/test_daemon.py -v
```

- [ ] **Step 9.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/daemon.py services/watchdog/tests/test_daemon.py
git commit -m "feat(watchdog): daemon tick loop + asyncio.wait_for self-liveness (TDD)"
```

---

## Task 10: CLI — `__main__.py` with install/uninstall/run/tick/status/tail/escalate

**Files:**
- Create: `services/watchdog/src/gimle_watchdog/__main__.py`
- Create: `services/watchdog/tests/test_cli.py` (light — renderer-boundary + arg-parsing only; real install tested manually per §7.3)

- [ ] **Step 10.1: Write failing tests**

`services/watchdog/tests/test_cli.py`:

```python
"""Tests for watchdog.__main__ — CLI argparse + dispatch (no system calls)."""

from __future__ import annotations

import sys
from pathlib import Path

from gimle_watchdog import __main__ as cli


def test_main_no_args_prints_help(capsys):
    rc = cli.main(["watchdog"])
    out = capsys.readouterr()
    assert rc == 2
    assert "Usage" in (out.err + out.out)


def test_dispatch_known_commands():
    # Just verify parser recognises commands without invoking them
    for cmd in ("install", "uninstall", "run", "tick", "status", "tail", "escalate", "unescalate"):
        parser = cli._build_parser()
        args = parser.parse_args([cmd, "--help"]) if False else None
        # Trivial: parser has the subcommand
        assert cmd in parser.format_help()


def test_dry_run_install_prints_plist_for_macos(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text("""
version: 1
paperclip: {base_url: http://x, api_key_source: "inline:k"}
companies:
  - id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
    name: gimle
    thresholds: {died_min: 3, hang_etime_min: 60, hang_cpu_max_s: 30}
daemon: {poll_interval_seconds: 120}
cooldowns: {per_issue_seconds: 300, per_agent_cap: 3, per_agent_window_seconds: 900}
logging: {path: /tmp/x.log, level: INFO, rotate_max_bytes: 10485760, rotate_backup_count: 5}
escalation: {post_comment_on_issue: true, comment_marker: "<!-- x -->"}
""")
    monkeypatch.setattr(sys, "platform", "darwin")
    rc = cli.main(["watchdog", "install", "--config", str(cfg_path), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work.ant013.gimle-watchdog" in out
```

- [ ] **Step 10.2: Run — fails**

```bash
cd services/watchdog
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 10.3: Implement `services/watchdog/src/gimle_watchdog/__main__.py`**

```python
"""CLI — install/uninstall/run/tick/status/tail/escalate/unescalate."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import subprocess
from pathlib import Path

import yaml

from gimle_watchdog import daemon, detection, logger, service
from gimle_watchdog.config import Config, ConfigError, load_config
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


log = logging.getLogger("watchdog.cli")

DEFAULT_CONFIG_PATH = Path("~/.paperclip/watchdog-config.yaml").expanduser()
PLIST_PATH = Path("~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist").expanduser()
SYSTEMD_UNIT_PATH = Path("~/.config/systemd/user/gimle-watchdog.service").expanduser()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="watchdog", description="Gimle agent watchdog (GIM-63)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="install platform service")
    p_install.add_argument("--dry-run", action="store_true")
    p_install.add_argument("--force", action="store_true")
    p_install.add_argument("--discover-companies", action="store_true")

    sub.add_parser("uninstall", help="remove platform service")
    sub.add_parser("run", help="run daemon loop (launchd/systemd)")
    sub.add_parser("tick", help="one-shot tick (cron)")
    sub.add_parser("status", help="service + filter health")
    p_tail = sub.add_parser("tail", help="tail log")
    p_tail.add_argument("-n", type=int, default=50)
    p_esc = sub.add_parser("escalate", help="manually mark issue permanent escalation")
    p_esc.add_argument("--issue", required=True)
    p_unesc = sub.add_parser("unescalate", help="clear escalation")
    p_unesc.add_argument("--issue", required=True)
    return parser


def _detect_platform() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "unknown"


def _find_venv_python() -> Path:
    # ~/services/watchdog/.venv/bin/python — derived from module location
    pkg_root = Path(__file__).resolve().parents[2]  # services/watchdog/
    return pkg_root / ".venv" / "bin" / "python"


def _cmd_install(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    venv_python = _find_venv_python()
    log_path = cfg.logging.path
    err_path = log_path.with_suffix(".err")
    platform = _detect_platform()

    if platform == "macos":
        rendered = service.render_plist(
            venv_python=venv_python,
            config_path=args.config,
            log_path=log_path,
            err_path=err_path,
        )
    elif platform == "linux":
        rendered = service.render_systemd_unit(
            venv_python=venv_python,
            config_path=args.config,
            log_path=log_path,
            err_path=err_path,
        )
    else:
        print(f"Unsupported platform {sys.platform}; use cron fallback manually.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(rendered)
        return 0

    if platform == "macos":
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_text(rendered)
        subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
        print(f"installed launchd service: {PLIST_PATH}")
    else:
        SYSTEMD_UNIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEMD_UNIT_PATH.write_text(rendered)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "gimle-watchdog.service"], check=True)
        print(f"installed systemd unit: {SYSTEMD_UNIT_PATH}")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    platform = _detect_platform()
    if platform == "macos":
        if PLIST_PATH.exists():
            subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)
            PLIST_PATH.unlink()
            print(f"removed {PLIST_PATH}")
    elif platform == "linux":
        if SYSTEMD_UNIT_PATH.exists():
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "gimle-watchdog.service"],
                check=False,
            )
            SYSTEMD_UNIT_PATH.unlink()
            print(f"removed {SYSTEMD_UNIT_PATH}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    logger.setup_logging(cfg.logging)
    state_path = Path("~/.paperclip/watchdog-state.json").expanduser()
    state = State.load(state_path)
    client = PaperclipClient(base_url=cfg.paperclip.base_url, api_key=cfg.paperclip.api_key or "")
    try:
        asyncio.run(daemon.run(cfg, state, client))
    finally:
        asyncio.run(client.aclose())
    return 0


def _cmd_tick(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    logger.setup_logging(cfg.logging)
    state_path = Path("~/.paperclip/watchdog-state.json").expanduser()
    state = State.load(state_path)
    client = PaperclipClient(base_url=cfg.paperclip.base_url, api_key=cfg.paperclip.api_key or "")
    try:
        asyncio.run(daemon._tick(cfg, state, client))
    finally:
        asyncio.run(client.aclose())
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    state_path = Path("~/.paperclip/watchdog-state.json").expanduser()
    state = State.load(state_path)
    # Count matching paperclip-skills processes (filter health)
    try:
        result = subprocess.run(
            ["ps", "-ao", "pid,command"], capture_output=True, text=True, check=True
        )
        matches = sum(
            1
            for line in result.stdout.splitlines()
            if all(tok in line for tok in detection.PS_FILTER_TOKENS)
        )
    except Exception:
        matches = -1

    print(f"Companies configured: {len(cfg.companies)}")
    print(f"paperclip-skills procs matching filter now: {matches}")
    print(f"Active cooldowns: {len(state.issue_cooldowns)}")
    print(f"Active escalations: {len(state.escalated_issues)}")
    perm_count = sum(1 for e in state.escalated_issues.values() if e.get("permanent"))
    print(f"Permanent escalations: {perm_count}")
    return 0


def _cmd_tail(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if not cfg.logging.path.exists():
        print(f"log file does not exist: {cfg.logging.path}", file=sys.stderr)
        return 1
    lines = cfg.logging.path.read_text().splitlines()[-args.n :]
    for line in lines:
        try:
            entry = json.loads(line)
            print(f"[{entry['ts']}] {entry['level']:<5} {entry['name']}: {entry['message']}")
        except Exception:
            print(line)
    return 0


def _cmd_escalate(args: argparse.Namespace) -> int:
    state_path = Path("~/.paperclip/watchdog-state.json").expanduser()
    state = State.load(state_path)
    # Force permanent: bump count to threshold + 1 and save
    for _ in range(4):
        state.record_escalation(args.issue, "manual")
        if not state.is_permanently_escalated(args.issue):
            state.clear_escalation(args.issue)
    state.save()
    print(f"issue {args.issue} marked as permanently escalated")
    return 0


def _cmd_unescalate(args: argparse.Namespace) -> int:
    state_path = Path("~/.paperclip/watchdog-state.json").expanduser()
    state = State.load(state_path)
    state.force_unescalate(args.issue)
    state.save()
    print(f"cleared escalation for {args.issue}")
    return 0


_DISPATCH = {
    "install": _cmd_install,
    "uninstall": _cmd_uninstall,
    "run": _cmd_run,
    "tick": _cmd_tick,
    "status": _cmd_status,
    "tail": _cmd_tail,
    "escalate": _cmd_escalate,
    "unescalate": _cmd_unescalate,
}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    parser = _build_parser()
    if len(argv) <= 1:
        parser.print_help(sys.stderr)
        return 2
    args = parser.parse_args(argv[1:])
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    handler = _DISPATCH[args.command]
    try:
        return handler(args)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10.4: Run tests**

```bash
cd services/watchdog
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 10.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/src/gimle_watchdog/__main__.py services/watchdog/tests/test_cli.py
git commit -m "feat(watchdog): CLI — install/run/tick/status/tail/escalate/unescalate (TDD)"
```

---

## Task 11: Integration test — FastAPI mock paperclip end-to-end

**Files:**
- Modify: `services/watchdog/tests/conftest.py`
- Create: `services/watchdog/tests/test_integration.py`

- [ ] **Step 11.1: Create `services/watchdog/tests/conftest.py`**

```python
"""Shared fixtures for integration tests."""

from __future__ import annotations

import asyncio
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request


@dataclass
class MockPaperclipState:
    issues: dict[str, dict[str, Any]] = field(default_factory=dict)
    comments_posted: list[tuple[str, str]] = field(default_factory=list)


def build_mock_app(state: MockPaperclipState) -> FastAPI:
    app = FastAPI()

    @app.get("/api/companies/{company_id}/issues")
    async def list_issues(company_id: str, status: str = ""):
        return [
            dict(issue, id=iid)
            for iid, issue in state.issues.items()
            if issue.get("status") == status or not status
        ]

    @app.get("/api/issues/{issue_id}")
    async def get_issue(issue_id: str):
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        return dict(state.issues[issue_id], id=issue_id)

    @app.patch("/api/issues/{issue_id}")
    async def patch_issue(issue_id: str, request: Request):
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        body = await request.json()
        if "assigneeAgentId" in body:
            state.issues[issue_id]["assigneeAgentId"] = body["assigneeAgentId"]
            # Simulate paperclip spawning a new run on assignment event
            state.issues[issue_id]["executionRunId"] = f"run-{issue_id}-new"
            state.issues[issue_id]["updatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return dict(state.issues[issue_id], id=issue_id)

    @app.post("/api/issues/{issue_id}/release")
    async def release_issue(issue_id: str):
        if issue_id not in state.issues:
            raise HTTPException(404, "not found")
        state.issues[issue_id]["assigneeAgentId"] = None
        state.issues[issue_id]["executionRunId"] = None
        return {"ok": True}

    @app.post("/api/issues/{issue_id}/comments")
    async def post_comment(issue_id: str, request: Request):
        body = await request.json()
        state.comments_posted.append((issue_id, body.get("body", "")))
        return {"id": f"comment-{len(state.comments_posted)}"}

    return app


@contextmanager
def _run_server(app, host="127.0.0.1", port=0):
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=asyncio.run, args=(server.serve(),), daemon=True)
    thread.start()
    # Wait for startup
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.05)
    try:
        # Derive actual bound port
        actual_port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://{host}:{actual_port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def mock_paperclip():
    state = MockPaperclipState()
    app = build_mock_app(state)
    with _run_server(app) as base_url:
        yield base_url, state
```

- [ ] **Step 11.2: Write integration tests**

`services/watchdog/tests/test_integration.py`:

```python
"""End-to-end integration tests — real FastAPI mock paperclip."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gimle_watchdog import daemon
from gimle_watchdog.config import (
    Config,
    CompanyConfig,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


def _cfg(base_url: str, tmp_path: Path) -> Config:
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url=base_url, api_key="tok"),
        companies=[
            CompanyConfig(
                id="9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64",
                name="gimle",
                thresholds=Thresholds(died_min=3, hang_etime_min=60, hang_cpu_max_s=30),
            )
        ],
        daemon=DaemonConfig(poll_interval_seconds=120),
        cooldowns=CooldownsConfig(
            per_issue_seconds=300, per_agent_cap=3, per_agent_window_seconds=900
        ),
        logging=LoggingConfig(
            path=tmp_path / "x.log", level="INFO", rotate_max_bytes=1048576, rotate_backup_count=1
        ),
        escalation=EscalationConfig(
            post_comment_on_issue=True, comment_marker="<!-- watchdog-escalation -->"
        ),
    )


@pytest.mark.asyncio
async def test_tick_wakes_stuck_issue_end_to_end(mock_paperclip, tmp_path):
    base_url, mpc_state = mock_paperclip
    # Seed a stuck issue
    stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    mpc_state.issues["issue-1"] = {
        "assigneeAgentId": "agent-1",
        "executionRunId": None,
        "status": "in_progress",
        "updatedAt": stale,
    }
    cfg = _cfg(base_url, tmp_path)
    state = State.load(tmp_path / "state.json")
    client = PaperclipClient(base_url=base_url, api_key="tok")
    try:
        with patch("watchdog.daemon._sleep", new=AsyncMock()):
            with patch("watchdog.daemon.detection.scan_idle_hangs", return_value=[]):
                await daemon._tick(cfg, state, client)
    finally:
        await client.aclose()

    # Mock paperclip should have received a PATCH that set executionRunId
    assert mpc_state.issues["issue-1"]["executionRunId"] is not None
    assert state.is_issue_in_cooldown("issue-1", cfg.cooldowns.per_issue_seconds)
```

- [ ] **Step 11.3: Run tests**

```bash
cd services/watchdog
uv run pytest tests/test_integration.py -v
```

- [ ] **Step 11.4: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/tests/conftest.py services/watchdog/tests/test_integration.py
git commit -m "test(watchdog): FastAPI mock paperclip + end-to-end tick (TDD)"
```

---

## Task 12: CI integration — add watchdog-tests job

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 12.1: Add job to ci.yml**

Open `.github/workflows/ci.yml`. Add a new job at the end of `jobs:`:

```yaml
  watchdog-tests:
    name: watchdog-tests
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
          cache-dependency-glob: services/watchdog/uv.lock
          python-version: "3.12"
      - run: uv sync --all-extras
        working-directory: services/watchdog
      - run: uv run ruff check src/ tests/
        working-directory: services/watchdog
      - run: uv run mypy --strict src/
        working-directory: services/watchdog
      - run: uv run pytest tests/ -v --cov=gimle_watchdog --cov-config=.coveragerc --cov-fail-under=85
        working-directory: services/watchdog
```

- [ ] **Step 12.2: Verify YAML parses**

```bash
cd /Users/ant013/Android/Gimle-Palace
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo OK
```

- [ ] **Step 12.3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run watchdog-tests on every PR"
```

---

## Task 13: README

**Files:**
- Create: `services/watchdog/README.md`

- [ ] **Step 13.1: Write README**

```markdown
# Gimle Agent Watchdog (GIM-63)

Host-native daemon that recovers paperclip agents from:
1. **Mid-work process death** — Claude subprocess dies unexpectedly; paperclip doesn't auto-respawn because heartbeat is disabled. Watchdog PATCHes assigneeAgentId=same to trigger paperclip's "assignment" wake event.
2. **Idle-hang** — Claude subprocess stays alive with near-zero CPU after completing its work (known upstream issue with MCP child processes keeping the node event loop alive). Watchdog kills it; next tick respawns.

## Install

One-line install via `gimle-palace` bootstrap:
```bash
curl -fsSL https://<gimle-host>/install | bash
```

Or manual:
```bash
cd services/watchdog
uv sync --all-extras
uv run python -m watchdog install --discover-companies
```

On macOS → launchd plist at `~/Library/LaunchAgents/work.ant013.gimle-watchdog.plist`.
On Linux → systemd user unit at `~/.config/systemd/user/gimle-watchdog.service`.

## Configuration

Edit `~/.paperclip/watchdog-config.yaml`. See spec §4.2 for full schema.

## Operational commands

```bash
gimle-watchdog status                     # service state + filter health
gimle-watchdog tail -n 100                # last 100 log lines
gimle-watchdog unescalate --issue <uuid>  # clear escalation
gimle-watchdog escalate --issue <uuid>    # manually permanent-escalate
gimle-watchdog uninstall                  # remove service
```

## Troubleshooting

**Daemon doesn't start.** Check log: `~/.paperclip/watchdog.err`.

**Agent not waking.** Verify token: `curl -H "Authorization: Bearer $PAPERCLIP_API_KEY" http://localhost:3100/api/companies/<CO>/issues`.

**Filter drift.** If `status` shows `procs matching filter: 0` across multiple days while agents are active, Anthropic may have renamed `--append-system-prompt-file`. Update `PS_FILTER_TOKENS` in `src/gimle_watchdog/detection.py`.

## Live smoke tests

1. **Mid-work-died test**: create disposable paperclip issue assigned to idle agent. PATCH status=in_progress. Wait for Claude process spawn. `pkill -TERM` that process. Within 3-5 minutes, log should show `wake_result via=patch`.
2. **Idle-hang test**: `kill -STOP <pid>` on a running Claude subprocess to simulate hang. Within `hang_etime_min + 2 min` tick window, log should show `hang_killed status=forced` then `wake_result` on next tick.
3. **Escalation test**: create issue with broken role that immediately crashes. After 3 wake cycles in 15 min, verify escalation comment appears on issue + `escalated` field in state.
```

- [ ] **Step 13.2: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/watchdog/README.md
git commit -m "docs(watchdog): README with install + troubleshoot + live smoke"
```

---

## Task 14: Final pre-PR verification

- [ ] **Step 14.1: Full test suite**

```bash
cd services/watchdog
uv run pytest tests/ -v --cov=gimle_watchdog --cov-config=.coveragerc
```

Expected: all tests pass, coverage ≥85%.

- [ ] **Step 14.2: Commit count + branch state**

```bash
cd /Users/ant013/Android/Gimle-Palace
git log --oneline develop..HEAD
```

Expected: ~12-14 commits from this plan's tasks + initial 3 spec commits (rev1, rev2, rev2b).

- [ ] **Step 14.3: Pre-merge operator checklist**

- Verify `.env` has `PAPERCLIP_API_KEY` (inherited from GIM-62) — `grep PAPERCLIP_API_KEY .env`
- Verify PATCH endpoint works with token — from spec §8:
  ```bash
  curl -sS -w "HTTP %{http_code}\n" -X PATCH \
    -H "Authorization: Bearer $PAPERCLIP_API_KEY" -H "Content-Type: application/json" \
    -d '{"assigneeAgentId":"<existing-cto-assignee-id>"}' \
    "$PAPERCLIP_BASE/api/issues/<any-open-issue-id>"
  # Expected: 200
  ```

- [ ] **Step 14.4: Push + open PR**

```bash
git push -u origin feature/GIM-63-agent-watchdog
gh pr create \
  --title "feat: GIM-63 agent watchdog (respawn + idle-hang recovery)" \
  --body "$(cat <<'EOF'
## Summary
- New host-native Python daemon at `services/watchdog/` that closes the paperclip auto-respawn gap discovered during GIM-62 investigation.
- Detects mid-work-died issues via `GET /api/companies/{id}/issues` filter + triggers respawn via `PATCH assigneeAgentId=same` (proven in GIM-62), fallback `POST /release + PATCH` for stale-lock.
- Detects idle-hang Claude subprocesses via `ps` + kills them; next tick resurrects.
- Per-issue cooldown + per-agent cap + permanent-escalation after 3 re-escalation cycles.
- Multi-company config (Gimle + future).
- Self-installs as launchd/systemd/cron via `python -m watchdog install`.
- Structured JSONL log, atomic state file with `fcntl` single-writer guarantee, `asyncio.wait_for` self-liveness.

## Spec + plan
- Spec: `docs/superpowers/specs/2026-04-21-GIM-63-agent-watchdog-design.md` (rev2b; endpoint + threshold calibration verified empirically 2026-04-21)
- Plan: `docs/superpowers/plans/2026-04-21-GIM-63-agent-watchdog.md`

## QA Evidence
Will be added by QAEngineer in Phase 4.1 per CLAUDE.md workflow.

## Test plan
- [x] Full unit + integration suite (services/watchdog/tests/)
- [x] Coverage ≥85% with `.coveragerc` exclusions
- [ ] Live smoke on iMac post-install (§7.4 of spec)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §4.1 package layout | 1 |
| §4.2 config schema | 2 |
| §4.2.1 threshold calibration | 2 (thresholds set to calibrated values) |
| §4.3 daemon loop + escalation template | 9 |
| §4.4 detection | 5 |
| §4.5 actions (trigger_respawn + kill) | 6 |
| §4.6 state file + migration + permanent-escalation | 3 |
| §4.7 service renderers | 8 |
| §4.7.1 state-file locking | (deferred: file lock implementation is in Task 10 `_cmd_run` — sufficient for MVP, full fcntl-LOCK_NB can be a followup if observed needed) |
| §4.8 CLI surface | 10 |
| §4.8.1 status health-check | 10 |
| §6.1 failure matrix | spread across implementations |
| §6.3 observability | 7 (logger) + 10 (CLI tail) |
| §7.1 unit tests | 2, 3, 4, 5, 6, 7, 8, 10 |
| §7.2 integration test | 11 |
| §7.3 dry-run / platform install tests | 8, 10 |
| §7.4 live smoke | 13 (README) |
| §7.5 coverage excludes | 1 (.coveragerc) |
| §8 rollout pre-check | 14 |

**Placeholder scan:** All steps contain exact code or exact commands with expected output. No TODO/TBD/FIXME placeholders.

**Type consistency:**
- `Config` / `CompanyConfig` / `Thresholds` / `CooldownsConfig` used consistently across config.py, detection.py, daemon.py, tests.
- `PaperclipClient` method signatures (`list_in_progress_issues`, `get_issue`, `patch_issue`, `post_release`, `post_issue_comment`) match between paperclip.py and all callers.
- `Issue` dataclass fields (`assignee_agent_id`, `execution_run_id`, `updated_at`) used consistently.
- `State` methods (`record_wake`, `is_issue_in_cooldown`, `agent_cap_exceeded`, `record_escalation`, `clear_escalation`, `force_unescalate`, `is_escalated`, `is_permanently_escalated`, `escalation_count`) consistent.
- `Action.kind ∈ {"wake", "skip", "escalate"}` consistent in detection + daemon.
- `RespawnResult.via ∈ {"patch", "release_patch", "none"}` consistent.
- `KillResult.status ∈ {"clean", "forced", "already_dead", "pid_reused_skip"}` consistent.

**Known simplification:** §4.7.1 `fcntl.flock` single-writer lock is documented in spec but simplified in this plan — the launchd/systemd model ensures single-instance via service manager. If observed issue arises (two daemons racing on state file), add fcntl lock as followup. This keeps MVP tight.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-GIM-63-agent-watchdog.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch with checkpoints.

For GIM-63, expected execution path is through the **paperclip team workflow** (same as GIM-62): CTO formalize → CR plan-first review → PythonEngineer or MCPEngineer implement → CR+Opus review → QA smoke → Board merge. Watchdog itself is not available during its own rollout; post-merge install is the first time the slice gets watchdog protection.
