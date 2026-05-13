# Watchdog operational coverage + recovery re-enable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-05-13-watchdog-operational-coverage-reenable.md` (base: `origin/develop@69ce650`).

**Owner team:** CX / Codex.

**Goal:** Make `gimle-watchdog` safe to move out of read-only mode for mechanical recovery by adding (a) a typed `EffectiveMode` classifier with a total-function truth table, (b) a `gimle-watchdog status` extension that reconciles configured-vs-live companies, (c) two structured log events (`watchdog_starting` pre-load, `watchdog_posture` per-tick), (d) a Paperclip-write-callsite registry, and (e) a CI cohort isolation harness backed by a committed fixture.

**Architecture:** Pure helpers (`describe_effective_mode`, registry constants) land in `config.py` so CLI and daemon can both import them with no circular deps. The new `PaperclipClient.list_companies()` is a read-only HTTP method; status reconciles its result against `Config.companies`. Two log events are emitted at distinct lifecycle points: `watchdog_starting` is the first log line of `_cmd_run`/`main` before any config load, and `watchdog_posture` fires at the top of `_tick`. The cohort harness is an e2e test under `tests/e2e/` that loads `tests/fixtures/gim255_cohort.json` into an in-memory Paperclip fake with a write-sink that fails the test on any `post_issue_comment` call against a cohort issue.

**Tech Stack:** Python 3.11, `dataclass(frozen=True)`, `argparse`, `httpx` (existing `PaperclipClient`), `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `uv`.

**Workflow gates (paperclip phases):**
- 1.1 Formalize (CX/CTO) — issue number is `GIM-282`; reassign to CR
  after the gate passes. **Cohort literal gate (spec §9):** before
  reassigning to CR, CTO must confirm the operator has committed real
  incident literals into `services/watchdog/tests/fixtures/gim255_cohort.json`
  (the committed PR #160 fixture has 52 Paperclip issue UUIDs, matching
  GIM-N numbers, 379 spam comment UUIDs, posted-at time window, and Board
  author user UUID; older 32/258 prose is historical incident shorthand).
  Task 11 preserves the real fixture and adds schema/coverage validation;
  **CI cohort harness in Task 12 is only meaningful against those committed
  real literals**. If the operator has not provided literals, CTO halts here
  — do not proceed to Phase 1.2.
- 1.2 Plan-first review (CX/CR) — every task below has concrete test + impl + commit. CR APPROVE before Phase 2.
- 2 Implement (CX/PE) — TDD through tasks below on `feature/GIM-<N>-watchdog-operational-coverage-reenable`.
- 3.1 Mechanical review (CX/CR) — paste `uv run ruff check services/watchdog/`, `uv run mypy services/watchdog/src/`, `uv run pytest services/watchdog/ -v`, AND `gh pr checks <num>` output verbatim. No "LGTM" approve without all four.
- 3.2 Adversarial review (CX/Opus or Architect) — partition the mode classifier, poke at API-failure paths.
- 4.1 Live smoke (CX/QA) — iMac: real `gimle-watchdog status` against production Paperclip; one observe-only tick; verify zero outbound writes.
- 4.2 Merge — squash to develop.

**Out of scope for this plan** (deferred to followup specs): `maintenance_read_only_until` field; promoting `recovery_pass_disabled` to Board alert; splitting visibility from recovery re-enable; PBUG-5 / PBUG-6 / PBUG-8 fixes.

---

## File Structure

**Create:**
- `services/watchdog/tests/_factories.py` — shared `_make_config` helper for mode/posture/cohort tests.
- `services/watchdog/tests/test_modes.py` — `EffectiveMode` + `describe_effective_mode` unit and partition tests.
- `services/watchdog/tests/test_posture_log.py` — `watchdog_starting` + `watchdog_posture` event emission tests.
- `services/watchdog/tests/test_comment_registry.py` — `POST_COMMENT_PATHS` enforcement test.
- `services/watchdog/tests/test_list_companies.py` — `PaperclipClient.list_companies()` unit tests (mocked httpx).
- `services/watchdog/tests/test_cohort_fixture_schema.py` — schema/coverage guard for the committed real incident fixture.
- `services/watchdog/tests/e2e/test_gim255_cohort_isolation.py` — per-detector cohort harness.
- `services/watchdog/tests/e2e/test_observe_only_smoke.py` — daemon-level mode-contract behavioral test.
- `docs/runbooks/watchdog-operational-reenable.md` — staged re-enable runbook (mirrors spec §5.4).

**Modify:**
- `services/watchdog/src/gimle_watchdog/config.py` — add `EffectiveMode` enum, `ALERT_FLAG_NAMES`, `AUTO_REPAIR_FLAG_NAME`, `POST_COMMENT_PATHS`, `describe_effective_mode`.
- `services/watchdog/src/gimle_watchdog/paperclip.py` — add `list_companies()` method.
- `services/watchdog/src/gimle_watchdog/daemon.py` — emit `watchdog_posture` at top of `_tick`; keep existing `tick_start` line for backward compat.
- `services/watchdog/src/gimle_watchdog/__main__.py` — emit `watchdog_starting` as first line of `main`; extend `_cmd_status` with mode/reconciliation/warnings/`--allow-degraded`.
- `services/watchdog/tests/test_cli.py` — extend existing `test_cmd_status` assertions for new lines; backward-compat assertions stay.
- `services/watchdog/tests/test_daemon.py` — add shared-budget identity regression test.

**Touch (verify, do not modify):**
- `services/watchdog/tests/fixtures/gim255_cohort.json` — real incident evidence fixture committed by PR #160; do not overwrite with placeholders.
- `services/watchdog/src/gimle_watchdog/detection.py` — recovery age gate stays as-is (`updated_at + recover_max_age_min`).
- `services/watchdog/src/gimle_watchdog/detection_semantic.py` — `_issue_is_eligible` stays as-is (`origin_kind in SKIP_ORIGINS`).

---

## Task 1: `EffectiveMode` enum + flag-name constants

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/config.py` (add after `_HANDOFF_KNOWN_KEYS` block, ~line 103).
- Test: `services/watchdog/tests/test_modes.py` (new).

- [ ] **Step 1: Write the failing test**

Create `services/watchdog/tests/test_modes.py`:

```python
"""Tests for EffectiveMode enum + describe_effective_mode classifier."""
from __future__ import annotations

import pytest

from gimle_watchdog.config import (
    ALERT_FLAG_NAMES,
    AUTO_REPAIR_FLAG_NAME,
    EffectiveMode,
)


def test_effective_mode_enum_has_five_members():
    assert {m.value for m in EffectiveMode} == {
        "observe-only",
        "alert-only",
        "recovery-only",
        "full-watchdog",
        "unsafe-auto-repair",
    }


def test_alert_flag_names_is_frozenset_of_strs():
    assert isinstance(ALERT_FLAG_NAMES, frozenset)
    assert ALERT_FLAG_NAMES == frozenset({
        "handoff_alert_enabled",
        "handoff_cross_team_enabled",
        "handoff_ownerless_enabled",
        "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled",
    })


def test_auto_repair_flag_name_constant():
    assert AUTO_REPAIR_FLAG_NAME == "handoff_auto_repair_enabled"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest services/watchdog/tests/test_modes.py -v
```

Expected: `ImportError: cannot import name 'EffectiveMode' from 'gimle_watchdog.config'`.

- [ ] **Step 3: Add enum + constants to `config.py`**

After the `_HANDOFF_KNOWN_KEYS` frozenset (around line 103), insert:

```python
from enum import Enum


class EffectiveMode(str, Enum):
    """Operational mode summarising recovery + alert + auto-repair posture.

    See spec §5.1 for the truth-table definition.
    """
    OBSERVE_ONLY = "observe-only"
    ALERT_ONLY = "alert-only"
    RECOVERY_ONLY = "recovery-only"
    FULL_WATCHDOG = "full-watchdog"
    UNSAFE_AUTO_REPAIR = "unsafe-auto-repair"


ALERT_FLAG_NAMES: frozenset[str] = frozenset({
    "handoff_alert_enabled",
    "handoff_cross_team_enabled",
    "handoff_ownerless_enabled",
    "handoff_infra_block_enabled",
    "handoff_stale_bundle_enabled",
})

AUTO_REPAIR_FLAG_NAME: str = "handoff_auto_repair_enabled"
```

Make sure `from enum import Enum` lands once at the top of the file with the other imports — do NOT duplicate.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest services/watchdog/tests/test_modes.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/config.py services/watchdog/tests/test_modes.py
git commit -m "feat(watchdog): add EffectiveMode enum + alert flag-name constants"
```

---

## Task 2: `describe_effective_mode` classifier + partition test

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/config.py` (add after Task 1 additions).
- Create: `services/watchdog/tests/_factories.py` (shared config factory).
- Test: `services/watchdog/tests/test_modes.py` (extend).

- [ ] **Step 1a: Create the shared config factory**

Create `services/watchdog/tests/_factories.py` so later suites do not import
helpers from another test module:

```python
"""Shared watchdog test factories."""
from __future__ import annotations

from pathlib import Path

from gimle_watchdog.config import (
    CompanyConfig,
    Config,
    CooldownsConfig,
    DaemonConfig,
    EscalationConfig,
    HandoffConfig,
    LoggingConfig,
    PaperclipConfig,
    Thresholds,
)


def _make_config(
    *,
    recovery_enabled: bool = False,
    any_alert: bool = False,
    auto_repair: bool = False,
    companies: list[CompanyConfig] | None = None,
) -> Config:
    """Build a minimal Config with the requested posture bits.

    None of `Config`'s sub-configs except `handoff` has a `default_factory`;
    they must be constructed explicitly. We pass realistic-but-minimal
    values — the classifier under test only reads `daemon.recovery_enabled`
    and `handoff.handoff_*_enabled`, so the other sub-configs are inert
    fillers.
    The default includes one company so daemon/e2e tests have a company id to
    iterate. Classifier-only tests may pass `companies=[]` explicitly.
    """
    handoff_kwargs: dict[str, bool] = {flag: False for flag in (
        "handoff_alert_enabled",
        "handoff_cross_team_enabled",
        "handoff_ownerless_enabled",
        "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled",
        "handoff_auto_repair_enabled",
    )}
    if any_alert:
        handoff_kwargs["handoff_alert_enabled"] = True
    if auto_repair:
        handoff_kwargs["handoff_auto_repair_enabled"] = True
    return Config(
        version=1,
        paperclip=PaperclipConfig(base_url="http://test", api_key="test"),
        daemon=DaemonConfig(poll_interval_seconds=60, recovery_enabled=recovery_enabled),
        companies=companies if companies is not None else [
            CompanyConfig(
                id="9d8f432c-test",
                name="Test",
                thresholds=Thresholds(
                    died_min=30,
                    hang_etime_min=45,
                    hang_cpu_max_s=None,
                    idle_cpu_ratio_max=0.01,
                    hang_stream_idle_max_s=300,
                ),
            )
        ],
        cooldowns=CooldownsConfig(
            per_issue_seconds=60, per_agent_cap=10, per_agent_window_seconds=3600
        ),
        logging=LoggingConfig(
            path=Path("/tmp/test.log"),
            level="INFO",
            rotate_max_bytes=1_000_000,
            rotate_backup_count=3,
        ),
        escalation=EscalationConfig(post_comment_on_issue=False, comment_marker="[test]"),
        handoff=HandoffConfig(**handoff_kwargs),
    )
```

- [ ] **Step 1b: Add failing test cases**

Append to `services/watchdog/tests/test_modes.py`:

```python
import itertools
from dataclasses import replace

from gimle_watchdog.config import (
    ConfigError,
    EffectiveMode,
    describe_effective_mode,
)

from tests._factories import _make_config


@pytest.mark.parametrize(
    "recovery,any_alert,auto_repair,expected",
    [
        (False, False, False, EffectiveMode.OBSERVE_ONLY),
        (False, True, False, EffectiveMode.ALERT_ONLY),
        (True, False, False, EffectiveMode.RECOVERY_ONLY),
        (True, True, False, EffectiveMode.FULL_WATCHDOG),
        (False, False, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (False, True, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (True, False, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
        (True, True, True, EffectiveMode.UNSAFE_AUTO_REPAIR),
    ],
)
def test_describe_effective_mode_partition(recovery, any_alert, auto_repair, expected):
    cfg = _make_config(
        recovery_enabled=recovery, any_alert=any_alert, auto_repair=auto_repair
    )
    assert describe_effective_mode(cfg) == expected


def test_partition_is_complete():
    """Every (recovery, any_alert, auto_repair) triple maps to exactly one mode."""
    seen: list[EffectiveMode] = []
    for recovery, any_alert, auto_repair in itertools.product([False, True], repeat=3):
        cfg = _make_config(
            recovery_enabled=recovery, any_alert=any_alert, auto_repair=auto_repair
        )
        seen.append(describe_effective_mode(cfg))
    assert len(seen) == 8
    assert all(isinstance(m, EffectiveMode) for m in seen)


def test_describe_rejects_unknown_handoff_flag():
    """Unknown handoff_*_enabled field on HandoffConfig must raise ConfigError."""
    cfg = _make_config()
    # Simulate a future flag added to HandoffConfig but not registered.
    bogus_handoff = replace(cfg.handoff)
    object.__setattr__(bogus_handoff, "handoff_experimental_enabled", True)
    bogus_cfg = replace(cfg, handoff=bogus_handoff)
    with pytest.raises(ConfigError, match="handoff_experimental_enabled"):
        describe_effective_mode(bogus_cfg)
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest services/watchdog/tests/test_modes.py -v
```

Expected: 3 new tests fail with `ImportError: cannot import name 'describe_effective_mode'`.

- [ ] **Step 3: Implement `describe_effective_mode`**

Append to `config.py` (after the `EffectiveMode` enum and constants):

```python
def describe_effective_mode(cfg: Config) -> EffectiveMode:
    """Classify the watchdog operational posture.

    See spec §5.1. Total function over the
    (recovery_enabled, any_alert_path_on, handoff_auto_repair_enabled) triplet.
    Raises ConfigError on unknown handoff_*_enabled fields so typo'd YAML or
    drifted code is caught at load time.
    """
    handoff = cfg.handoff
    known_flags = ALERT_FLAG_NAMES | {AUTO_REPAIR_FLAG_NAME}
    for attr in vars(handoff):
        if attr.startswith("handoff_") and attr.endswith("_enabled"):
            if attr not in known_flags:
                raise ConfigError(
                    f"unknown handoff_*_enabled flag {attr!r}; add to "
                    f"ALERT_FLAG_NAMES or AUTO_REPAIR_FLAG_NAME"
                )

    auto_repair = getattr(handoff, AUTO_REPAIR_FLAG_NAME)
    if auto_repair:
        return EffectiveMode.UNSAFE_AUTO_REPAIR

    any_alert_path_on = any(getattr(handoff, flag) for flag in ALERT_FLAG_NAMES)
    recovery_on = cfg.daemon.recovery_enabled

    if not recovery_on and not any_alert_path_on:
        return EffectiveMode.OBSERVE_ONLY
    if not recovery_on and any_alert_path_on:
        return EffectiveMode.ALERT_ONLY
    if recovery_on and not any_alert_path_on:
        return EffectiveMode.RECOVERY_ONLY
    return EffectiveMode.FULL_WATCHDOG
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_modes.py -v
```

Expected: 6 passed (3 from Task 1 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/config.py services/watchdog/tests/_factories.py services/watchdog/tests/test_modes.py
git commit -m "feat(watchdog): describe_effective_mode classifier with partition test"
```

---

## Task 3: `POST_COMMENT_PATHS` registry + enforcement test

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/config.py`.
- Test: `services/watchdog/tests/test_comment_registry.py` (new).

Background: spec §7 requires every `paperclip.PaperclipClient.post_issue_comment` callsite to be registered, so a new caller cannot ship without explicit acknowledgement.

- [ ] **Step 1: Write the failing test**

Create `services/watchdog/tests/test_comment_registry.py`:

```python
"""Enforce POST_COMMENT_PATHS registry against actual callsites."""
from __future__ import annotations

import ast
from pathlib import Path

from gimle_watchdog.config import POST_COMMENT_PATHS

_SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "gimle_watchdog"


def _find_callsites() -> set[str]:
    """Return set of '<module>:<function>' for every post_issue_comment call."""
    found: set[str] = set()
    for py_file in _SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        module = py_file.stem
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                func_name = node.name
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "post_issue_comment"
                    ):
                        found.add(f"{module}:{func_name}")
    return found


def test_post_comment_callsites_match_registry():
    actual = _find_callsites()
    extra_in_code = actual - POST_COMMENT_PATHS
    extra_in_registry = POST_COMMENT_PATHS - actual
    assert not extra_in_code, (
        f"new post_issue_comment callsites not in POST_COMMENT_PATHS: "
        f"{sorted(extra_in_code)}. Update config.POST_COMMENT_PATHS."
    )
    assert not extra_in_registry, (
        f"POST_COMMENT_PATHS lists callsites no longer present in code: "
        f"{sorted(extra_in_registry)}. Remove them."
    )


def test_post_comment_paths_is_frozenset():
    assert isinstance(POST_COMMENT_PATHS, frozenset)
```

- [ ] **Step 2: Discover current callsites**

```bash
uv run pytest services/watchdog/tests/test_comment_registry.py::test_post_comment_paths_is_frozenset -v
```

Expected: `ImportError: cannot import name 'POST_COMMENT_PATHS'`.

Then manually enumerate via grep to seed the registry:

```bash
grep -rn 'post_issue_comment' services/watchdog/src/gimle_watchdog/ | grep -v 'def post_issue_comment'
```

- [ ] **Step 3: Add registry to `config.py`**

Append to `config.py`:

```python
# Every code path that calls PaperclipClient.post_issue_comment MUST be
# enumerated here as "<module_stem>:<enclosing_function>". A test in
# tests/test_comment_registry.py compares this set to the AST callsite
# scan; adding a new caller requires updating this constant AND the test.
# A full spec amendment is only required when introducing a new CLASS of
# side-effect channel (non-issue Paperclip endpoint or external service).
POST_COMMENT_PATHS: frozenset[str] = frozenset({
    # Populate from `grep -rn post_issue_comment services/watchdog/src/`
    # — implementer fills with the actual <module>:<func> pairs observed.
})
```

The implementer replaces the empty set with the actual callsite tuples found in Step 2. Run the test against discovered callsites to seed.

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_comment_registry.py -v
```

Expected: 2 passed. If the AST scan disagrees with the registry, fix the registry until the test passes — do NOT relax the test.

- [ ] **Step 5: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/config.py services/watchdog/tests/test_comment_registry.py
git commit -m "feat(watchdog): POST_COMMENT_PATHS registry enforced by AST scan"
```

---

## Task 4: `PaperclipClient.list_companies()` method

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/paperclip.py`.
- Test: `services/watchdog/tests/test_list_companies.py` (new).

Background: spec §5.2 requires a new read-only client method that filters to non-archived companies.

- [ ] **Step 1: Inspect the Paperclip companies endpoint**

Confirm the endpoint shape and archived discriminator. Run on iMac (or against staging):

```bash
curl -s -H "Authorization: Bearer $PALACE_PAPERCLIP_TOKEN" \
  https://paperclip.../api/companies | jq '.[0] | keys'
```

Record the active/archived field name in a code comment (likely `archived: bool` or `status: "active" | "archived"`).

- [ ] **Step 2: Write the failing test using existing `mock_paperclip` fixture**

The project already ships a full FastAPI Paperclip mock at `services/watchdog/tests/conftest.py` (`mock_paperclip` fixture, `build_mock_app`, `MockPaperclipState`). Use it — do NOT roll a bespoke `MagicMock` for `httpx`. First extend `build_mock_app` with a `/api/companies` route. Add to `conftest.py` immediately after `list_agents` (line ~95):

```python
@app.get("/api/companies")
async def list_companies() -> list[dict[str, Any]]:
    return list(state.companies)
```

and add the corresponding field to `MockPaperclipState`:

```python
companies: list[dict[str, Any]] = field(default_factory=list)
```

Then create `services/watchdog/tests/test_list_companies.py`:

```python
"""Tests for PaperclipClient.list_companies()."""
from __future__ import annotations

import pytest

from gimle_watchdog.paperclip import PaperclipClient


@pytest.mark.asyncio
async def test_list_companies_returns_active_only(mock_paperclip):
    """Archived companies are filtered out client-side."""
    base_url, state = mock_paperclip
    state.companies = [
        {"id": "uuid-1", "name": "Gimle", "archived": False},
        {"id": "uuid-2", "name": "OldCo", "archived": True},
        {"id": "uuid-3", "name": "Trading", "archived": False},
    ]
    client = PaperclipClient(base_url=base_url, api_key="test")
    try:
        companies = await client.list_companies()
    finally:
        await client.aclose()
    assert {c["id"] for c in companies} == {"uuid-1", "uuid-3"}


@pytest.mark.asyncio
async def test_list_companies_raises_on_502(mock_paperclip):
    """Non-2xx propagates as PaperclipError (after retries) — never silent []."""
    from gimle_watchdog.paperclip import PaperclipError
    base_url, state = mock_paperclip
    # Use a route that doesn't exist — server will 404; PaperclipClient
    # treats 4xx as terminal. Alternative: monkeypatch _request to raise.
    client = PaperclipClient(base_url=base_url + "-bogus", api_key="test")
    try:
        with pytest.raises(Exception):  # httpx.ConnectError or PaperclipError
            await client.list_companies()
    finally:
        await client.aclose()
```

- [ ] **Step 3: Run to verify failure**

```bash
uv run pytest services/watchdog/tests/test_list_companies.py -v
```

Expected: `AttributeError: 'PaperclipClient' object has no attribute 'list_companies'`.

- [ ] **Step 4: Implement `list_companies()` using the real client primitives**

In `services/watchdog/src/gimle_watchdog/paperclip.py`, add a method on `PaperclipClient` (place it adjacent to `list_company_agents` around line 228). The real client uses `await self._request(method, url)` which already handles 429/5xx retry, `Date` header capture, and raises `PaperclipError` on terminal failures — re-use it.

```python
async def list_companies(self) -> list[dict[str, Any]]:
    """Read-only GET of /api/companies, filtered to non-archived entries.

    Source of truth for spec §5.2 reconciliation. The 'archived' field
    discriminator was verified against the Paperclip schema on
    <YYYY-MM-DD by implementer>; if the schema evolves (e.g. moves to
    status: 'active'|'archived'), update this filter.
    """
    resp = await self._request("GET", "/api/companies")
    payload = resp.json()
    return [c for c in payload if not c.get("archived", False)]
```

If the schema uses `status: "active" | "archived"` instead of `archived: bool`, adjust the filter accordingly — and update both the test fixture in Step 2 and the docstring date.

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_list_companies.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/paperclip.py services/watchdog/tests/test_list_companies.py
git commit -m "feat(watchdog): PaperclipClient.list_companies (active-only)"
```

---

## Task 5: `watchdog_starting` event (pre-load)

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/__main__.py` (`main()` function, line 275).
- Test: `services/watchdog/tests/test_posture_log.py` (new).

Background: spec §5.3 requires `watchdog_starting` to be the FIRST log line, before any config load, so a config-load crash still leaves it in the log.

- [ ] **Step 1: Write the failing test**

Create `services/watchdog/tests/test_posture_log.py`:

```python
"""Tests for watchdog_starting + watchdog_posture structured log events."""
from __future__ import annotations

import json
import logging
import os

import pytest

from gimle_watchdog import __main__ as main_mod


def test_watchdog_starting_emitted_before_config_load(caplog, capfd, tmp_path):
    """watchdog_starting fires BEFORE config load.

    Two delivery channels (spec §5.3 reality): stderr-direct print (always)
    and logging.getLogger("watchdog.cli").info (lands on root logger when
    pre-load, file logger post-load). The test checks both.

    main() returns int 2 on bad args / ConfigError — it does NOT raise
    SystemExit when called directly from a test.
    """
    bogus_config = tmp_path / "does-not-exist.yaml"

    with caplog.at_level(logging.INFO, logger="watchdog"):
        rc = main_mod.main(["watchdog", "status", "--config", str(bogus_config)])

    assert rc == 2  # ConfigError → return 2 per __main__.py:288-290

    # Channel 1: stderr JSON print is guaranteed even with no logger setup.
    err = capfd.readouterr().err
    assert '"event": "watchdog_starting"' in err
    payload = json.loads(_extract_first_json_line(err))
    assert payload["pid"] == os.getpid()
    assert "version" in payload
    assert payload["config_path"] == str(bogus_config)
    assert "argv" in payload

    # Channel 2: logging record (root or watchdog.cli — both are captured
    # by caplog when at_level scopes the parent logger).
    starting_records = [
        r for r in caplog.records if getattr(r, "event", None) == "watchdog_starting"
    ]
    assert starting_records, "watchdog_starting log record was not emitted"
    assert caplog.records[0] is starting_records[0], (
        "watchdog_starting must be the first log record"
    )


def _extract_first_json_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return line
    raise AssertionError(f"no JSON line found in: {text!r}")
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest services/watchdog/tests/test_posture_log.py::test_watchdog_starting_emitted_before_config_load -v
```

Expected: `AssertionError: no JSON line found` or `AssertionError: watchdog_starting log record was not emitted`.

- [ ] **Step 3: Emit `watchdog_starting` in `main()` via BOTH channels**

Reality check (verified at `services/watchdog/src/gimle_watchdog/__main__.py:168,187`): `logger.setup_logging(cfg.logging)` runs AFTER `load_config(...)`. So a `log.info(...)` call before `load_config` does NOT land in the configured log file — it goes to root logger only (stderr `lastResort` handler at WARNING). Spec §5.3 therefore requires two delivery channels:

1. Direct `print(json.dumps(...), file=sys.stderr, flush=True)` — guaranteed durable via launchd/systemd stderr capture, regardless of logging state.
2. `log.info(...)` through `watchdog.cli` so post-setup ticks share the namespace.

Modify `services/watchdog/src/gimle_watchdog/__main__.py`. The module already has `log = logging.getLogger("watchdog.cli")` at line 19 — REUSE that, do NOT add `logging.getLogger(__name__)` (the package name resolves to `gimle_watchdog.__main__`, which is the wrong namespace).

Replace the body of `main()` (line 275) with:

```python
def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv

    # Spec §5.3 — emit watchdog_starting via TWO channels BEFORE config load.
    # Channel 1: stderr JSON — durable through launchd/systemd before
    # logger.setup_logging configures file handlers in _cmd_run/_cmd_tick.
    # Channel 2: logging — namespace-consistent with later watchdog_posture
    # events; reaches the configured log file once setup_logging runs (no-op
    # for pre-config short-lived commands like `status`).
    starting_payload = {
        "event": "watchdog_starting",
        "pid": os.getpid(),
        "version": _watchdog_version(),
        "config_path": _extract_config_path(argv),
        "argv": _sanitize_argv(argv),
    }
    print(json.dumps(starting_payload), file=sys.stderr, flush=True)
    log.info("watchdog_starting", extra=starting_payload)

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
```

Add the helpers near the top of the file (after the existing imports, before `_build_parser`):

```python
import os


def _watchdog_version() -> str:
    """Best-effort package version; falls back to 'unknown' until packaging
    exposes __version__ on gimle_watchdog."""
    try:
        from importlib.metadata import version
        return version("gimle-watchdog")
    except Exception:
        return "unknown"


def _extract_config_path(argv: list[str]) -> str | None:
    """Best-effort scan of argv for --config <path>. Does not parse argparse."""
    for i, tok in enumerate(argv):
        if tok == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--config="):
            return tok.split("=", 1)[1]
    return None


def _sanitize_argv(argv: list[str]) -> list[str]:
    """Token list copy. Today watchdog accepts no secret-bearing flags;
    future-proofs the surface in one place if any are added."""
    return list(argv)
```

`os` is already implicitly available through `from pathlib import Path` chain, but add it explicitly — do not rely on transitive imports.

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_posture_log.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/__main__.py services/watchdog/tests/test_posture_log.py
git commit -m "feat(watchdog): emit watchdog_starting before config load"
```

---

## Task 6: `watchdog_posture` event (per tick)

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/daemon.py` (`_tick()`, line 634).
- Test: `services/watchdog/tests/test_posture_log.py` (extend).

- [ ] **Step 1: Write the failing test**

Append to `services/watchdog/tests/test_posture_log.py`:

```python
import logging

import pytest

from gimle_watchdog.config import Config, EffectiveMode
from gimle_watchdog.daemon import _tick
from gimle_watchdog.state import State


@pytest.mark.asyncio
async def test_watchdog_posture_emitted_at_tick_start(
    caplog, observe_only_config: Config, mock_paperclip, tmp_path
):
    """spec §5.3 — watchdog_posture event at every tick start, full field set.

    The watchdog code uses `logging.getLogger("watchdog.daemon")` — capture
    against the `watchdog` parent namespace, NOT `gimle_watchdog`.
    """
    from gimle_watchdog.paperclip import PaperclipClient

    base_url, _state = mock_paperclip
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")

    try:
        with caplog.at_level(logging.INFO, logger="watchdog"):
            await _tick(observe_only_config, state, client)
    finally:
        await client.aclose()

    posture_records = [
        r for r in caplog.records if getattr(r, "event", None) == "watchdog_posture"
    ]
    assert len(posture_records) == 1
    r = posture_records[0]

    # Required fields per spec §5.3.
    for field_name in (
        "mode", "company_count", "company_names", "company_ids",
        "configured_but_missing", "live_but_unconfigured",
        "recovery_enabled", "recovery_baseline_completed",
        "max_actions_per_tick",
        "handoff_recent_window_min", "recover_max_age_min_per_company",
        "handoff_alert_enabled", "handoff_cross_team_enabled",
        "handoff_ownerless_enabled", "handoff_infra_block_enabled",
        "handoff_stale_bundle_enabled", "handoff_auto_repair_enabled",
        "alert_budget_soft", "alert_budget_hard",
    ):
        assert hasattr(r, field_name), f"watchdog_posture missing field {field_name!r}"

    assert r.mode == EffectiveMode.OBSERVE_ONLY.value
    assert isinstance(r.recover_max_age_min_per_company, dict)
```

The test depends on `observe_only_config` (add to `conftest.py`) and reuses the existing `mock_paperclip` fixture for the Paperclip client. `observe_only_config` is built by calling the shared `_make_config` helper from `tests/_factories.py` created in Task 2. Add this to `conftest.py`:

```python
@pytest.fixture
def observe_only_config():
    from tests._factories import _make_config
    return _make_config()  # all flags False = observe-only
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest services/watchdog/tests/test_posture_log.py::test_watchdog_posture_emitted_at_tick_start -v
```

Expected: AssertionError on missing `watchdog_posture` records.

- [ ] **Step 3: Emit `watchdog_posture` at top of `_tick`**

Modify `services/watchdog/src/gimle_watchdog/daemon.py` `_tick` (line 634), insert immediately after the `log.info("tick_start ...")` line:

```python
async def _tick(cfg: Config, state: State, client: PaperclipClient) -> None:
    """One scan pass: kill hangs, then wake died-mid-work issues."""
    log.info("tick_start companies=%d", len(cfg.companies))

    # spec §5.3 — structured posture event for ops visibility (PBUG-9 catch).
    posture_extra = _build_posture_extra(cfg, state, await _reconcile_companies(cfg, client))
    log.info("watchdog_posture", extra=posture_extra)

    # ... rest of existing _tick body unchanged ...
```

Add the helper near the top of `daemon.py`:

```python
async def _reconcile_companies(
    cfg: Config, client: PaperclipClient
) -> tuple[list[str], list[str]]:
    """Return (configured_but_missing, live_but_unconfigured) company IDs.

    Returns ([], []) on API failure — _tick MUST NOT crash on missing inventory;
    status command handles the visibility for the operator.
    """
    try:
        live = await client.list_companies()
    except Exception as exc:
        log.warning("list_companies_failed reason=%r", exc)
        return [], []
    live_ids = {c["id"] for c in live}
    configured_ids = {c.id for c in cfg.companies}
    return (
        sorted(configured_ids - live_ids),
        sorted(live_ids - configured_ids),
    )


def _build_posture_extra(
    cfg: Config,
    state: State,
    reconciliation: tuple[list[str], list[str]],
) -> dict[str, Any]:
    from gimle_watchdog.config import describe_effective_mode
    configured_but_missing, live_but_unconfigured = reconciliation
    return {
        "event": "watchdog_posture",
        "mode": describe_effective_mode(cfg).value,
        "company_count": len(cfg.companies),
        "company_names": [c.name for c in cfg.companies],
        "company_ids": [c.id for c in cfg.companies],
        "configured_but_missing": configured_but_missing,
        "live_but_unconfigured": live_but_unconfigured,
        "recovery_enabled": cfg.daemon.recovery_enabled,
        "recovery_baseline_completed": getattr(state, "recovery_baseline_completed", False),
        "max_actions_per_tick": cfg.daemon.max_actions_per_tick,
        "handoff_recent_window_min": cfg.handoff.handoff_recent_window_min,
        "recover_max_age_min_per_company": {
            c.id: c.thresholds.recover_max_age_min for c in cfg.companies
        },
        "handoff_alert_enabled": cfg.handoff.handoff_alert_enabled,
        "handoff_cross_team_enabled": cfg.handoff.handoff_cross_team_enabled,
        "handoff_ownerless_enabled": cfg.handoff.handoff_ownerless_enabled,
        "handoff_infra_block_enabled": cfg.handoff.handoff_infra_block_enabled,
        "handoff_stale_bundle_enabled": cfg.handoff.handoff_stale_bundle_enabled,
        "handoff_auto_repair_enabled": cfg.handoff.handoff_auto_repair_enabled,
        "alert_budget_soft": cfg.handoff.handoff_alert_soft_budget_per_tick,
        "alert_budget_hard": cfg.handoff.handoff_alert_hard_budget_per_tick,
    }
```

If `State` does not yet have `recovery_baseline_completed`, use `getattr` with default `False` as shown. If the field name in state.py differs (e.g. `recovery_first_baseline_done`), correct it here and document in commit message.

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_posture_log.py -v
```

Expected: 2 passed (Task 5 + Task 6 tests).

- [ ] **Step 5: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/daemon.py services/watchdog/tests/test_posture_log.py services/watchdog/tests/conftest.py
git commit -m "feat(watchdog): emit watchdog_posture event at every tick"
```

---

## Task 7: Shared `AlertPostBudget` identity regression test

**Files:**
- Test: `services/watchdog/tests/test_daemon.py` (extend).

Background: §3 / §7 — `_run_handoff_pass` and `_run_tier_pass` each default-construct their own budget when `budget=None`. The "one shared budget per tick" invariant currently holds because `_tick` passes the same instance. This test pins that invariant so a future refactor that drops the explicit pass-through fails CI.

- [ ] **Step 1: Write the test**

Append to `services/watchdog/tests/test_daemon.py`:

```python
@pytest.mark.asyncio
async def test_tick_passes_same_budget_to_handoff_and_tier(
    full_alert_config, fake_paperclip_client, tmp_path, monkeypatch
):
    """spec §3 / §7 — _tick MUST pass the same AlertPostBudget instance
    to _run_handoff_pass and _run_tier_pass. Refactor that drops the
    explicit pass-through (letting each pass default-construct) fails here.
    """
    from gimle_watchdog import daemon as daemon_mod

    captured: dict[str, object] = {}

    async def fake_handoff(cfg, state, client, now, *, budget=None):
        captured["handoff"] = budget

    async def fake_tier(cfg, state, client, now, repo_root, *, budget=None):
        captured["tier"] = budget

    monkeypatch.setattr(daemon_mod, "_run_handoff_pass", fake_handoff)
    monkeypatch.setattr(daemon_mod, "_run_tier_pass", fake_tier)

    state = State.load(tmp_path / "state.json")
    await daemon_mod._tick(full_alert_config, state, fake_paperclip_client)

    assert captured["handoff"] is captured["tier"], (
        "handoff and tier passes received different AlertPostBudget instances"
    )
    assert captured["handoff"] is not None
```

Add `full_alert_config` to `conftest.py` (similar to `observe_only_config` but with `handoff_alert_enabled=True`).

- [ ] **Step 2: Run to verify it passes**

```bash
uv run pytest services/watchdog/tests/test_daemon.py::test_tick_passes_same_budget_to_handoff_and_tier -v
```

Expected: PASS (the invariant holds today; this is a regression pin).

- [ ] **Step 3: Sanity-check the test catches regressions**

Temporarily edit `_tick` to remove `budget=budget` from one of the two pass calls (let it default-construct). Re-run the test — it MUST fail. Revert immediately.

- [ ] **Step 4: Commit**

```bash
git add services/watchdog/tests/test_daemon.py services/watchdog/tests/conftest.py
git commit -m "test(watchdog): regression for shared AlertPostBudget identity"
```

---

## Task 8: Extend `_cmd_status` — mode + reconciliation + `--allow-degraded`

**Files:**
- Modify: `services/watchdog/src/gimle_watchdog/__main__.py` (`_cmd_status` line 202, parser line 27).
- Test: `services/watchdog/tests/test_cli.py` (extend).

- [ ] **Step 1: Write the failing test cases**

Append to `services/watchdog/tests/test_cli.py`:

```python
def test_cmd_status_prints_mode_and_reconciliation(
    capsys, tmp_path, monkeypatch, observe_only_config_file
):
    """spec §5.2 — status prints mode, per-company recover_max_age_min,
    and configured_but_missing / live_but_unconfigured reconciliation.
    """
    from gimle_watchdog import __main__ as main_mod
    # mock list_companies to return same set as config — no reconciliation diff
    monkeypatch.setattr(
        "gimle_watchdog.paperclip.PaperclipClient.list_companies",
        AsyncMock(return_value=[{"id": "uuid-1", "name": "Gimle", "archived": False}]),
    )

    rc = main_mod.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Effective mode: observe-only" in out
    assert "Recovery enabled: false" in out.lower()
    assert "Handoff recent window min: 180" in out
    assert "recover_max_age_min=180" in out
    # Reconciliation warnings absent when sets match.
    assert "configured_but_missing" not in out
    assert "live_but_unconfigured" not in out
    # Backward-compat: existing lines still present.
    assert "Companies configured: 1" in out
    assert "Active cooldowns:" in out


def test_cmd_status_warns_on_live_but_unconfigured(
    capsys, tmp_path, monkeypatch, observe_only_config_file
):
    """spec §5.2 — PBUG-9 structural catch."""
    from gimle_watchdog import __main__ as main_mod
    monkeypatch.setattr(
        "gimle_watchdog.paperclip.PaperclipClient.list_companies",
        AsyncMock(return_value=[
            {"id": "uuid-1", "name": "Gimle", "archived": False},
            {"id": "uuid-7", "name": "Trading", "archived": False},
        ]),
    )

    rc = main_mod.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "live_but_unconfigured=uuid-7" in out
    assert "name=Trading" in out


def test_cmd_status_exits_2_on_api_failure(
    capsys, tmp_path, monkeypatch, observe_only_config_file
):
    """spec §5.2 — non-zero exit on API failure; never silently downgrade."""
    from gimle_watchdog import __main__ as main_mod
    monkeypatch.setattr(
        "gimle_watchdog.paperclip.PaperclipClient.list_companies",
        AsyncMock(side_effect=httpx.ConnectError("dns")),
    )

    rc = main_mod.main(["watchdog", "status", "--config", str(observe_only_config_file)])
    out = capsys.readouterr().out

    assert rc == 2
    assert "company_inventory=unreachable" in out
    assert "reason=" in out


def test_cmd_status_allow_degraded_returns_0_on_api_failure(
    capsys, tmp_path, monkeypatch, observe_only_config_file
):
    """spec §5.2 — --allow-degraded suppresses non-zero exit but still prints
    the unreachable line.
    """
    from gimle_watchdog import __main__ as main_mod
    monkeypatch.setattr(
        "gimle_watchdog.paperclip.PaperclipClient.list_companies",
        AsyncMock(side_effect=httpx.ConnectError("dns")),
    )

    rc = main_mod.main([
        "watchdog", "status", "--allow-degraded",
        "--config", str(observe_only_config_file),
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "company_inventory=unreachable" in out
```

Add `observe_only_config_file` fixture to `conftest.py` — writes a minimal YAML to `tmp_path` and returns the path.

- [ ] **Step 2: Run to verify failures**

```bash
uv run pytest services/watchdog/tests/test_cli.py -v -k status
```

Expected: 4 new tests fail.

- [ ] **Step 3: Extend `_cmd_status` and parser**

In `services/watchdog/src/gimle_watchdog/__main__.py`:

1. In `_build_parser()` (line 27), the existing subparsers variable is
named `sub` (not `subparsers`). Add `--allow-degraded` to the status
subparser using the existing pattern:

```python
status_parser = sub.add_parser(
    "status", parents=[config_parent], help="Print operational posture"
)
status_parser.add_argument(
    "--allow-degraded",
    action="store_true",
    help="Exit 0 even if Paperclip API is unreachable (still prints unreachable line)",
)
```

If a `status` subparser is already declared elsewhere via `sub.add_parser("status", ...)`,
locate that line and add the `--allow-degraded` argument to it rather
than declaring twice.

2. Replace `_cmd_status` (line 202) with:

```python
def _cmd_status(args: argparse.Namespace) -> int:
    from gimle_watchdog.config import (
        AUTO_REPAIR_FLAG_NAME,
        EffectiveMode,
        describe_effective_mode,
    )

    cfg = load_config(args.config)
    state_path = Path(_DEFAULT_STATE_PATH)
    state = State.load(state_path)

    mode = describe_effective_mode(cfg)
    if mode == EffectiveMode.UNSAFE_AUTO_REPAIR:
        print("!!! UNSAFE AUTO-REPAIR ENABLED — Board has not approved !!!")
    print(f"Effective mode: {mode.value}")
    print(f"Recovery enabled: {str(cfg.daemon.recovery_enabled).lower()}")
    print(f"Max actions per tick: {cfg.daemon.max_actions_per_tick}")
    print(f"Handoff recent window min: {cfg.handoff.handoff_recent_window_min}")

    print(f"Companies configured: {len(cfg.companies)}")
    for c in cfg.companies:
        print(f"  - {c.name} ({c.id}) recover_max_age_min={c.thresholds.recover_max_age_min}")

    # Reconcile against live Paperclip inventory.
    api_reachable, reconciliation_msg = _reconcile_for_status(cfg)
    if reconciliation_msg:
        print(reconciliation_msg)
    if not api_reachable and not args.allow_degraded:
        return 2

    try:
        ps_result = subprocess.run(
            ["ps", "-ao", "pid,command"], capture_output=True, text=True, check=True
        )
        matches = sum(
            1
            for line in ps_result.stdout.splitlines()
            if all(tok in line for tok in detection.PS_FILTER_TOKENS)
        )
    except Exception:
        matches = -1

    print(f"paperclip-skills procs matching filter now: {matches}")
    print(f"Active cooldowns: {len(state.issue_cooldowns)}")
    print(f"Active escalations: {len(state.escalated_issues)}")
    perm_count = sum(1 for e in state.escalated_issues.values() if e.get("permanent"))
    print(f"Permanent escalations: {perm_count}")
    return 0


def _reconcile_for_status(cfg) -> tuple[bool, str]:
    """Returns (api_reachable, formatted_warning_lines).

    Uses the same PaperclipClient construction pattern as _cmd_run and
    _cmd_tick (__main__.py:171,190): PaperclipClient(base_url=..., api_key=...).
    No `from_config` constructor exists today.
    """
    async def _run() -> list[dict[str, object]]:
        client = PaperclipClient(
            base_url=cfg.paperclip.base_url,
            api_key=cfg.paperclip.api_key or "",
        )
        try:
            return await client.list_companies()
        finally:
            await client.aclose()

    try:
        live = asyncio.run(_run())
    except Exception as exc:
        return False, f"company_inventory=unreachable reason={exc!r}"

    live_ids = {c["id"]: c for c in live}
    configured_ids = {c.id for c in cfg.companies}
    missing = sorted(configured_ids - set(live_ids))
    extra = sorted(set(live_ids) - configured_ids)
    lines: list[str] = []
    for company_id in missing:
        lines.append(f"configured_but_missing={company_id}")
    for company_id in extra:
        name = live_ids[company_id].get("name", "?")
        lines.append(f"live_but_unconfigured={company_id} name={name}")
    return True, "\n".join(lines)
```

`asyncio` is already imported at `__main__.py:6`. The existing
`PaperclipClient(base_url=..., api_key=...)` construction works
synchronously inside `asyncio.run(...)`.

- [ ] **Step 4: Update pre-existing `test_cmd_status` for new reconciliation behavior**

The pre-existing test at `services/watchdog/tests/test_cli.py:65-74` calls
`cli.main(["watchdog", "status", ...])` without any Paperclip server, so
after this task `_reconcile_for_status` will try to GET `http://<base_url>/api/companies`
and fail — the test will return 2 instead of 0. Update it to either:

(a) use `mock_paperclip` and assert `rc == 0`, OR
(b) pass `--allow-degraded` and assert `rc == 0` with the unreachable
    line visible.

Recommended (a) — it tests the happy path. Replace the existing test body:

```python
def test_cmd_status(tmp_path: Path, capsys, monkeypatch, mock_paperclip):
    base_url, state_mock = mock_paperclip
    state_mock.companies = [
        {"id": "9d8f432c-test", "name": "Test", "archived": False}
    ]
    cfg_path = _minimal_cfg(tmp_path, paperclip_base_url=base_url)
    state_file = tmp_path / "watchdog-state.json"
    monkeypatch.setattr(cli, "_DEFAULT_STATE_PATH", str(state_file))
    rc = cli.main(["watchdog", "status", "--config", str(cfg_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Companies configured: 1" in out
    assert "Active cooldowns: 0" in out
    # New: backward-compat lines coexist with new posture lines.
    assert "Effective mode:" in out
```

`_minimal_cfg` may need a new `paperclip_base_url` kwarg so the test
overrides the dummy URL to the mock server.

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest services/watchdog/tests/test_cli.py -v
```

Expected: all status tests pass, including updated `test_cmd_status`.

- [ ] **Step 6: Commit**

```bash
git add services/watchdog/src/gimle_watchdog/__main__.py services/watchdog/tests/test_cli.py services/watchdog/tests/conftest.py
git commit -m "feat(watchdog): extend status with mode, reconciliation, --allow-degraded"
```

---

## Task 9: Observe-only mode behavioral test (5-mode side-effect coverage)

**Files:**
- Test: `services/watchdog/tests/e2e/test_observe_only_smoke.py` (new).

Background: spec §7 — for EACH mode, daemon-level test asserts BOTH the mode string AND the side-effect counters on a synthetic tick. Task 9 implements observe-only; Task 10 covers the other four modes via parameterization.

- [ ] **Step 1: Write the test**

Create `services/watchdog/tests/e2e/test_observe_only_smoke.py`. Use the
existing `mock_paperclip` FastAPI fixture from `conftest.py` (it covers
EVERY route detectors hit — `list_active_issues`, `list_done_issues`,
`list_recent_comments`, `list_company_agents`, `post_issue_comment`,
`patch_issue`, `post_release`). A custom `_RecordingPaperclipClient` would
miss methods and produce false passes by swallowing `AttributeError` inside
the daemon — do NOT roll your own fake.

```python
"""Daemon-level mode-contract tests (spec §7 'Mode classifier coverage')."""
from __future__ import annotations

import logging

import pytest

from gimle_watchdog.config import EffectiveMode, describe_effective_mode
from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


@pytest.mark.asyncio
async def test_observe_only_tick_emits_zero_side_effects(
    observe_only_config, mock_paperclip, tmp_path, caplog
):
    """spec §7: observe-only ⇒ 0 outbound Paperclip writes across one tick.

    Uses the real PaperclipClient against the in-process FastAPI mock so
    every code path is exercised — no AttributeError swallowing. We also
    assert no ERROR/EXCEPTION log records to catch silent-failure regressions.
    """
    assert describe_effective_mode(observe_only_config) == EffectiveMode.OBSERVE_ONLY

    base_url, state_mock = mock_paperclip
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")

    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(observe_only_config, state, client)
    finally:
        await client.aclose()

    # No outbound writes recorded by the mock.
    assert state_mock.comments_posted == []
    # No issues were assigned (PATCH /api/issues/{id}) — `_run_recovery_pass`
    # returns early in observe-only because `recovery_enabled=False`.
    assert all(
        i.get("assigneeAgentId") is None or "test" in (i.get("assigneeAgentId") or "")
        for i in state_mock.issues.values()
    )
    # No unexpected ERROR-level log records (catches AttributeError swallow).
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, f"unexpected errors during observe-only tick: {errors}"
```

- [ ] **Step 2: Run**

```bash
uv run pytest services/watchdog/tests/e2e/test_observe_only_smoke.py -v
```

Expected: PASS (the invariant holds today since recovery + all alerts are off).

- [ ] **Step 3: Commit**

```bash
git add services/watchdog/tests/e2e/test_observe_only_smoke.py
git commit -m "test(watchdog): observe-only mode behavioral contract"
```

---

## Task 10: Recovery-only / alert-only / full-watchdog / unsafe behavioral tests

**Files:**
- Test: `services/watchdog/tests/e2e/test_observe_only_smoke.py` (extend; rename later if scope grows).

- [ ] **Step 1: Add the four remaining behavioral cases**

Spec §7 explicitly says "for EACH of the five modes" — full-watchdog gets
its own test, not implicit coverage. Seed a stuck issue via the
`mock_paperclip` state (not via `monkeypatch` on `scan_died_mid_work` —
detectors must run against real data so silent regressions surface).

Append to `services/watchdog/tests/e2e/test_observe_only_smoke.py`:

```python
import datetime as _dt
from gimle_watchdog.config import EffectiveMode, describe_effective_mode


def _seed_stuck_issue(state_mock, *, issue_id="issue-stuck-1",
                     company_id="9d8f432c-test"):
    """Insert a recovery-eligible issue: assignee set, executionRunId NULL,
    updatedAt 1h old (past died_min threshold but within recover_max_age_min).

    Critical: `executionRunId=None`. Recovery skips issues with a live run
    BEFORE the age gate (detection.py:236), so a non-null run id would make
    the test a false-positive — recovery would skip on the no-run gate, not
    on the age gate the test claims to exercise.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    state_mock.issues[issue_id] = {
        "id": issue_id,
        "title": "Stuck",
        "status": "in_progress",
        "assigneeAgentId": "agent-stuck",
        "executionRunId": None,
        "originKind": "agent",
        "updatedAt": (now - _dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "issueNumber": 999,
    }


@pytest.mark.asyncio
async def test_recovery_only_emits_no_alerts(
    recovery_only_config, mock_paperclip, tmp_path
):
    """recovery-only ⇒ may PATCH but 0 alert comments."""
    assert describe_effective_mode(recovery_only_config) == EffectiveMode.RECOVERY_ONLY
    base_url, state_mock = mock_paperclip
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(recovery_only_config, state, client)
    finally:
        await client.aclose()

    assert state_mock.comments_posted == []


@pytest.mark.asyncio
async def test_alert_only_emits_no_recovery(
    alert_only_config, mock_paperclip, tmp_path
):
    """alert-only ⇒ may post comments but 0 PATCH for recovery."""
    assert describe_effective_mode(alert_only_config) == EffectiveMode.ALERT_ONLY
    base_url, state_mock = mock_paperclip
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(alert_only_config, state, client)
    finally:
        await client.aclose()

    # alert-only MUST NOT change assignee — recovery is off.
    assert state_mock.issues["issue-stuck-1"]["assigneeAgentId"] == "agent-stuck"


@pytest.mark.asyncio
async def test_full_watchdog_can_both_alert_and_recover(
    full_watchdog_config, mock_paperclip, tmp_path
):
    """full-watchdog ⇒ recovery and alerts may both fire. The behavioral
    contract is: no exceptions, mode classifier returns full-watchdog,
    and per-tick AlertPostBudget is respected (not exceeded).
    """
    assert describe_effective_mode(full_watchdog_config) == EffectiveMode.FULL_WATCHDOG
    base_url, state_mock = mock_paperclip
    _seed_stuck_issue(state_mock)
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(full_watchdog_config, state, client)
    finally:
        await client.aclose()

    # Both side-effects ALLOWED; the contract is just "within budget".
    hard_budget = full_watchdog_config.handoff.handoff_alert_hard_budget_per_tick
    assert len(state_mock.comments_posted) <= hard_budget


@pytest.mark.asyncio
async def test_unsafe_auto_repair_banner_in_posture_log(
    unsafe_auto_repair_config, mock_paperclip, tmp_path, caplog
):
    """unsafe-auto-repair mode value reaches the watchdog_posture log."""
    base_url, _state = mock_paperclip
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        with caplog.at_level(logging.INFO, logger="watchdog"):
            await _tick(unsafe_auto_repair_config, state, client)
    finally:
        await client.aclose()

    posture = [r for r in caplog.records if getattr(r, "event", None) == "watchdog_posture"]
    assert posture
    assert posture[0].mode == "unsafe-auto-repair"
```

Add fixtures `recovery_only_config`, `alert_only_config`,
`full_watchdog_config`, `unsafe_auto_repair_config` to `conftest.py`,
derived from the shared `_make_config` factory (Task 2):

```python
@pytest.fixture
def recovery_only_config():
    from tests._factories import _make_config
    return _make_config(recovery_enabled=True)

@pytest.fixture
def alert_only_config():
    from tests._factories import _make_config
    return _make_config(any_alert=True)

@pytest.fixture
def full_watchdog_config():
    from tests._factories import _make_config
    return _make_config(recovery_enabled=True, any_alert=True)

@pytest.fixture
def unsafe_auto_repair_config():
    from tests._factories import _make_config
    return _make_config(auto_repair=True)
```

- [ ] **Step 2: Run**

```bash
uv run pytest services/watchdog/tests/e2e/test_observe_only_smoke.py -v
```

Expected: 5 passed (observe + recovery + alert + full + unsafe).

- [ ] **Step 3: Commit**

```bash
git add services/watchdog/tests/e2e/test_observe_only_smoke.py services/watchdog/tests/conftest.py
git commit -m "test(watchdog): per-mode behavioral side-effect contracts"
```

---

## Task 11: Validate committed cohort fixture (real incident data)

**Files:**
- Touch / verify only: `services/watchdog/tests/fixtures/gim255_cohort.json`.
- Create: `services/watchdog/tests/test_cohort_fixture_schema.py`.

Background: spec §4 / §9 — fixture exists as test evidence. PR #160 has
already committed the real GIM-244/GIM-255 incident literals to
`services/watchdog/tests/fixtures/gim255_cohort.json`. Do **not** create,
overwrite, regenerate, or replace this fixture with placeholders. The fixture is
test evidence only; production code must never load it as a runtime skip list.

- [ ] **Step 1: Verify the real fixture is present and has expected coverage**

Run:

```bash
test -f services/watchdog/tests/fixtures/gim255_cohort.json
jq '{issue_count:(.paperclip_issue_ids|length), issue_number_count:(.issue_numbers|length), comment_count:(.comment_ids|length), author_agent_count:(.author_agent_ids|length), author_user_count:(.author_user_ids|length), posted_at_window}' services/watchdog/tests/fixtures/gim255_cohort.json
```

Expected: `issue_count=52`, `issue_number_count=52`, `comment_count=379`,
`author_agent_count=0`, `author_user_count=1`, and posted-at window
`2026-05-08T17:12:07.843000Z..2026-05-08T17:29:04.951000Z`.
If these counts drift, stop and ask Board; do not "fix" the fixture locally.

- [ ] **Step 2: Add a schema-validation test**

Create `services/watchdog/tests/test_cohort_fixture_schema.py`:

```python
"""Validate the structure of gim255_cohort.json. Real data is operator-supplied."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

_FIXTURE = (
    Path(__file__).parent / "fixtures" / "gim255_cohort.json"
)


def test_fixture_has_required_schema():
    data = json.loads(_FIXTURE.read_text())
    assert isinstance(data["paperclip_issue_ids"], list)
    assert len(data["paperclip_issue_ids"]) == 52
    assert all(_is_uuid(s) for s in data["paperclip_issue_ids"])
    assert isinstance(data["issue_numbers"], list)
    assert len(data["issue_numbers"]) == len(data["paperclip_issue_ids"])
    assert all(isinstance(n, int) for n in data["issue_numbers"])
    assert isinstance(data["comment_ids"], list)
    assert len(data["comment_ids"]) == 379
    assert all(_is_uuid(s) for s in data["comment_ids"])
    assert data["posted_at_window"]["from"].endswith("Z")
    assert data["posted_at_window"]["to"].endswith("Z")
    assert isinstance(data["comment_markers"], list)
    # Real incident comments were posted via the Board user's API key, not
    # an agent identity; author_agent_ids may legitimately be empty.
    assert all(_is_uuid(s) for s in data["author_agent_ids"])
    assert all(_is_uuid(s) for s in data["author_user_ids"])
    assert data["author_agent_ids"] or data["author_user_ids"]


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 3: Run**

```bash
uv run pytest services/watchdog/tests/test_cohort_fixture_schema.py -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add services/watchdog/tests/test_cohort_fixture_schema.py
git commit -m "test(watchdog): validate committed GIM-255 cohort fixture"
```

---

## Task 12: CI cohort isolation harness

**Files:**
- Create: `services/watchdog/tests/e2e/test_gim255_cohort_isolation.py`.

Background: spec §7 — per-detector cohort harness. For each detector flag in `ALERT_FLAG_NAMES` plus the recovery code path plus `stale_bundle` (global), enable the flag, run one tick against the cohort fixture loaded into a Paperclip fake, assert zero writes against cohort IDs.

- [ ] **Step 1: Write the harness against the real `mock_paperclip` server**

This harness MUST exercise actual `PaperclipClient` HTTP calls against the
FastAPI mock from `conftest.py` — not a custom in-memory fake. Rationale:
detectors call `list_active_issues`, `list_done_issues`,
`list_recent_comments`, `list_company_agents`, `post_issue_comment`,
`patch_issue`, `post_release`. A partial fake that misses any of those will
raise `AttributeError` inside the daemon, which `_run_handoff_pass` /
`_run_tier_pass` may catch and convert to zero observed writes — that
becomes a false-positive cohort isolation pass. The FastAPI mock covers
every route the detectors hit and surfaces real exceptions.

Create `services/watchdog/tests/e2e/test_gim255_cohort_isolation.py`:

```python
"""GIM-255 cohort isolation — proves general GIM-255 hardening covers the
real Board-provided 379-comment / 52-issue cohort. Spec §7.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from gimle_watchdog.config import ALERT_FLAG_NAMES
from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "gim255_cohort.json"
)
_TEST_ASSIGNEE_AGENT_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(scope="module")
def cohort():
    return json.loads(_FIXTURE.read_text())


def _seed_cohort_into_mock(state_mock, cohort: dict, company_id: str) -> None:
    """Insert cohort issues as recovery-ELIGIBLE candidates.

    Critical: `executionRunId=None`. The recovery code path skips issues
    with a live run BEFORE the age gate (detection.py:236). If we seed
    `executionRunId="run-old"` the cohort issues fail recovery's no-run
    check and the age gate is never exercised — that would make this
    harness a false-positive. With `executionRunId=None`, the cohort
    issues reach the age gate, which then SKIPS them because
    `updated_at` is 48h old (older than recover_max_age_min=180min).
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    old = (now - _dt.timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    for issue_uuid, gim_n in zip(
        cohort["paperclip_issue_ids"], cohort["issue_numbers"]
    ):
        state_mock.issues[issue_uuid] = {
            "id": issue_uuid,
            "title": f"GIM-{gim_n}",
            "status": "in_progress",
            # Do not derive test assignment from incident authorship. The real
            # fixture has author_agent_ids=[] because comments were posted via
            # the Board user's API key; the harness only needs a stable agent id
            # so detector code can evaluate the cohort issue.
            "assigneeAgentId": _TEST_ASSIGNEE_AGENT_ID,
            "assigneeUserId": (cohort.get("author_user_ids") or [None])[0],
            "executionRunId": None,
            "originKind": "agent",
            "updatedAt": old,
            "issueNumber": gim_n,
        }


@pytest.mark.parametrize("flag_name", sorted(ALERT_FLAG_NAMES))
@pytest.mark.asyncio
async def test_cohort_isolation_per_detector_flag(
    flag_name, cohort, observe_only_config, mock_paperclip, tmp_path, caplog
):
    """With exactly one detector flag ON, cohort issues yield zero writes
    and no ERROR-level log records (which would indicate AttributeError
    swallowing — i.e. false pass).
    """
    base_url, state_mock = mock_paperclip
    company_id = observe_only_config.companies[0].id if observe_only_config.companies else "9d8f432c-test"
    _seed_cohort_into_mock(state_mock, cohort, company_id)

    cfg = replace(
        observe_only_config,
        handoff=replace(observe_only_config.handoff, **{flag_name: True}),
    )
    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(cfg, state, client)
    finally:
        await client.aclose()

    cohort_ids = set(cohort["paperclip_issue_ids"])
    posted_against_cohort = [
        (iid, body) for iid, body in state_mock.comments_posted if iid in cohort_ids
    ]
    # If recovery (or any path) woke a cohort issue, MockPaperclipState's
    # patch_issue handler would set executionRunId to "run-<id>-new"; the
    # original seed had None. Any non-None value means a wake happened.
    patched_against_cohort = [
        iid for iid, issue in state_mock.issues.items()
        if iid in cohort_ids and issue.get("executionRunId") is not None
    ]
    assert not posted_against_cohort, (
        f"{flag_name} posted on cohort: {posted_against_cohort}"
    )
    assert not patched_against_cohort, (
        f"{flag_name} patched (woke) cohort issues: {patched_against_cohort}"
    )
    # False-pass detector: any ERROR in the log means a code path crashed
    # silently and the assertions above are vacuous.
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, f"{flag_name} produced unexpected errors: {errors}"


@pytest.mark.asyncio
async def test_cohort_isolation_recovery_path(
    cohort, recovery_only_config, mock_paperclip, tmp_path, caplog
):
    """Recovery enabled ⇒ cohort issues (>24h old) MUST NOT be woken."""
    base_url, state_mock = mock_paperclip
    company_id = (
        recovery_only_config.companies[0].id
        if recovery_only_config.companies else "9d8f432c-test"
    )
    _seed_cohort_into_mock(state_mock, cohort, company_id)

    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        with caplog.at_level(logging.WARNING, logger="watchdog"):
            await _tick(recovery_only_config, state, client)
    finally:
        await client.aclose()

    cohort_ids = set(cohort["paperclip_issue_ids"])
    woken = [
        iid for iid, issue in state_mock.issues.items()
        if iid in cohort_ids and issue.get("executionRunId") is not None
    ]
    assert not woken, f"recovery woke cohort issues: {woken}"
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, f"recovery produced unexpected errors: {errors}"
```

The `observe_only_config` and `recovery_only_config` fixtures must include
at least one `CompanyConfig` so detectors have a company id to iterate. Keep
the Task 2 `_make_config` default company, and use its `companies` kwarg only
when a test needs to override the company list explicitly.

- [ ] **Step 2: Run**

```bash
uv run pytest services/watchdog/tests/e2e/test_gim255_cohort_isolation.py -v
```

Expected: 6 passed (5 ALERT_FLAG_NAMES parametrizations + 1 recovery
path). All should pass because:
- Cohort issues are seeded with `executionRunId=None` and `updatedAt`
  48h old → recovery reaches the age gate, which skips them because
  48h > 180min `recover_max_age_min`.
- Alert detectors iterate over active issues regardless of run id and
  skip on `handoff_recent_window_min=180min` for the same reason.

If any test fails, that's a real bug — the GIM-255 hardening does NOT cover the cohort for that detector. Do NOT relax the test; investigate the detector.

- [ ] **Step 3: Commit**

```bash
git add services/watchdog/tests/e2e/test_gim255_cohort_isolation.py
git commit -m "test(watchdog): GIM-255 cohort isolation harness"
```

---

## Task 13: Stale-issue age-gate coverage audit

**Files:**
- Verify existing: `services/watchdog/tests/e2e/test_no_spam_on_stale_issues.py` and others.
- Possibly extend: `services/watchdog/tests/e2e/test_stale_recovery_skip.py` (new, if existing coverage is incomplete).

Background: spec §7 requires explicit age-gate tests for (a) mechanical recovery via `recover_max_age_min`, (b) legacy handoff detectors via `handoff_recent_window_min`, (c) tier issue-bound detectors via `handoff_recent_window_min`. Verify existing tests cover (a)/(b)/(c) or add the missing ones.

- [ ] **Step 1: Audit existing coverage**

```bash
grep -rn "recover_max_age_min\|handoff_recent_window_min" services/watchdog/tests/
```

Map each spec requirement to an existing test name. Record the mapping in a comment block in `tests/e2e/__init__.py` or a `tests/COVERAGE.md`. If any of (a)/(b)/(c) lacks a dedicated test, add one using the same `mock_paperclip` + real `PaperclipClient` pattern as Task 12 (do NOT roll a bespoke fake — false-pass risk). Scaffold:

```python
import datetime as _dt
import pytest

from gimle_watchdog.daemon import _tick
from gimle_watchdog.paperclip import PaperclipClient
from gimle_watchdog.state import State


@pytest.mark.asyncio
async def test_recovery_skips_issue_older_than_recover_max_age_min(
    recovery_only_config, mock_paperclip, tmp_path
):
    """spec §7 — mechanical recovery MUST NOT wake an issue with
    updated_at < now - recover_max_age_min.
    """
    base_url, state_mock = mock_paperclip
    old = (
        _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=4)
    ).isoformat().replace("+00:00", "Z")
    # executionRunId=None is REQUIRED for the issue to be a recovery
    # candidate; otherwise the no-run gate (detection.py:236) skips it
    # before the age gate fires, making this test vacuous.
    state_mock.issues["stale-uuid"] = {
        "id": "stale-uuid",
        "status": "in_progress",
        "assigneeAgentId": "agent-x",
        "executionRunId": None,
        "originKind": "agent",
        "updatedAt": old,
        "issueNumber": 0,
    }

    client = PaperclipClient(base_url=base_url, api_key="test")
    state = State.load(tmp_path / "state.json")
    try:
        await _tick(recovery_only_config, state, client)
    finally:
        await client.aclose()

    # The age gate (4h > 3h recover_max_age_min) must skip the issue.
    # If recovery had woken it, MockPaperclipState would have stamped a new
    # executionRunId on the assignee PATCH (conftest.py:62).
    assert state_mock.issues["stale-uuid"]["executionRunId"] is None
```

- [ ] **Step 2: Run full watchdog suite**

```bash
uv run pytest services/watchdog/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit (only if new tests added)**

```bash
git add services/watchdog/tests/
git commit -m "test(watchdog): explicit age-gate coverage per spec §7"
```

Otherwise skip the commit and proceed to Task 14.

---

## Task 14: Runbook file

**Files:**
- Create: `docs/runbooks/watchdog-operational-reenable.md`.

Background: spec §5.4 is the canonical step ordering. The runbook is derivative documentation. Spec wins on conflict.

- [ ] **Step 1: Write the runbook**

Create `docs/runbooks/watchdog-operational-reenable.md`:

```markdown
# Watchdog operational re-enable

**Canonical source:** `docs/superpowers/specs/2026-05-13-watchdog-operational-coverage-reenable.md` (§5.4). On any conflict, the spec wins; this runbook is derivative.

**When to use:** taking `gimle-watchdog` from observe-only back into mechanical recovery (and later bounded alerting). One-way ratchet — do not skip phases or scale beyond evidence.

**Audit-trail context:** the committed PR #160 fixture records 379 spam comments across 52 affected issues for the GIM-244/GIM-255 incident. Watchdog ignores them via the general GIM-255 hardening (per-issue age gates, `origin_kind` eligibility, `AlertPostBudget`, cooldown bookkeeping) — there is no runtime cohort-skip list.

## Phase 1 — Observe-only precheck (recovery OFF)

- `recovery_enabled: false`;
- all `handoff_*_enabled` flags false;
- run `gimle-watchdog status`:
  - `Effective mode: observe-only`;
  - every expected company is listed;
  - `configured_but_missing` and `live_but_unconfigured` are absent;
  - `Handoff recent window min: 180`;
  - every `recover_max_age_min=180`.
- **observe-only side-effect smoke:** start the daemon for one full tick on iMac and confirm zero outbound Paperclip writes (no `wake_result`, no `*_alert_posted`, no `auto_repair_*`). This proves the mode contract end-to-end.

Gate to Phase 2: status output is clean and the one-tick smoke is silent.

## Phase 2 — Baseline tick (recovery ON, no wake)

- `recovery_enabled: true`;
- `recovery_first_run_baseline_only: true`;
- `max_actions_per_tick: 1`.

Run one tick and verify:
- `recovery_baseline_seeded` log line appears;
- zero wake actions taken;
- no issue older than 3 hours triggered a recovery action.

## Phase 3 — Controlled recovery (one wake per tick)

- `recovery_first_run_baseline_only: false`.

Run one tick and verify:
- at most one `wake_result`;
- the touched issue is recent legitimate work (operator manually cross-checks against the GIM-255 cohort fixture if uncertain — the fixture is for human inspection, not a runtime gate).

## Phase 4 — Scale mechanical recovery

**PBUG-5 gate:** do NOT raise `max_actions_per_tick` above 1 while PBUG-5 (stale execution lock → 403 on legitimate later comments/PATCHes) is unfixed. Mechanical recovery's release+PATCH path is exactly the surface PBUG-5 breaks. Under load every locked issue becomes a recurring failed-action loop that burns the tick budget on cohort-adjacent victims.

After PBUG-5 ships: raise `max_actions_per_tick` by one step per clean evidence cycle.

## Phase 5 — Bounded alert re-enable

- Enable one detector flag at a time (`handoff_alert_enabled`, then one tier flag, etc.).
- Before flipping a flag in production, confirm the CI cohort harness for that specific detector is green (`pytest services/watchdog/tests/e2e/test_gim255_cohort_isolation.py -k <flag>`).
- After flipping, observe one tick and verify `handoff_alert_posted` / `tier_alert_posted` volume against the `AlertPostBudget`.

## Phase 6 — Auto-repair stays off

`handoff_auto_repair_enabled: false` unless a separate Board-approved spec enables it. Until then `status` will print `!!! UNSAFE AUTO-REPAIR ENABLED !!!` for any config that turns this on.

## Rollback

At any phase: set `recovery_enabled: false`, restart the daemon, and confirm `status` shows `Effective mode: observe-only`. The runbook makes the daemon's posture trivially revertable via config alone.
```

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/watchdog-operational-reenable.md
git commit -m "docs: runbook for staged watchdog re-enable"
```

---

## Phase 3 / 4 paperclip gates (no implementation code — CR/QA responsibilities)

### CR Phase 3.1 — Mechanical review

Paperclip CR posts a comment with ALL of the following pasted verbatim. No "LGTM" approvals.

```bash
uv run ruff check services/watchdog/
uv run mypy services/watchdog/src/
uv run pytest services/watchdog/ -v
gh pr checks <PR-number>
```

CR Phase 3.1 also pastes `git diff --name-only origin/develop...HEAD` and confirms it matches the "File Structure" section of this plan. If the diff is narrower than this plan, that is a silent scope reduction — block the PR.

### CR Phase 3.2 — Adversarial review (Opus/Architect)

Walk the mode partition: pick three configurations not in the test parameterization and predict the classifier output. If any prediction disagrees with the implementation, file a finding. Audit the cohort fixture for plausibility (UUIDs match Paperclip schema, time window is the incident's actual 4-hour band).

### QA Phase 4.1 — Live smoke (iMac)

QA runs on iMac (not dev Mac, not fixture-only):

```bash
ssh imac-ssh.ant013.work
cd /Users/Shared/Ios/Gimle-Palace
git fetch origin
git checkout feature/GIM-<N>-watchdog-operational-coverage-reenable
# Real palace-mcp env, real /api/companies live GET
uv run gimle-watchdog status --config ~/.paperclip/watchdog-config.yaml
```

Evidence comment posts the literal stdout, the SHA the smoke ran on, and the iMac hostname. Per memory feedback `pe_qa_evidence_fabrication`: numbers must come from real iMac smoke, not from dev-Mac fixtures. If fixture output is the only thing available, QA labels it as fixture evidence and the PR does NOT proceed to merge.

### Phase 4.2 — Merge

Once CI green + CR Phase 3.1 APPROVE + Opus Phase 3.2 APPROVE + QA Phase 4.1 evidence comment with iMac stdout → squash-merge to `develop`. No admin override; if branch protection blocks, fix the underlying check, do not bypass.

---

## Followups — not in this slice

Operator-flagged design questions that do not block this plan but should
be considered for the next slice or a dedicated cleanup:

- **`watchdog_starting` event on every CLI invocation.** Current spec
  emits it for `status`, `tail`, `escalate`, etc. — not only the
  long-running `run`/`tick` daemon paths. Pros: complete operator audit
  trail of who invoked the CLI when. Cons: stderr noise on every
  short-lived command, and the "PBUG-9 catch on company-loading crash"
  motivation only applies to `run`/`tick`. If the noise becomes a
  problem, scope the event to `args.command in {"run", "tick"}` in a
  followup spec. For this slice, the full-CLI scope is acceptable.
- **`POST_COMMENT_PATHS` location.** Lives in `config.py` per Task 3.
  Functionally correct (any imported module can read it), but
  conceptually the registry is a *safety control*, not configuration.
  Followup: move to `services/watchdog/src/gimle_watchdog/safety.py`
  (or `side_effects.py`) so the `config.py` surface stays focused on
  parsed configuration values. Not blocking.
- **`list_companies()` return type.** Returns `list[dict[str, Any]]`.
  Sufficient for the CLI consumer in this slice. If a future caller
  needs typed access, introduce a `CompanySummary` dataclass and route
  through it. Not blocking.
- **Pre-load logging fallback as default behavior.** The stderr-JSON
  print in Task 5 is the durable channel today. A follow-up could move
  this into a shared `_emit_event(event_name, **fields)` helper used by
  both pre-load and post-load events, with a single source of truth for
  field formatting. Not blocking — Task 5 keeps the two channels
  explicit.

---

## Self-review checklist

Spec coverage map:

- §3 existing implementation preservation → Tasks 1, 7 (regression test), 13 (age gates).
- §4 In bullets → Tasks 8 (status warnings), 11 (cohort fixture), 14 (runbook), 9/10 (mode tests), 13 (age gates), 3 (registry).
- §4 stale_bundle clarification → Task 12 (cohort harness covers `stale_bundle` via flag iteration).
- §5.1 mode taxonomy → Tasks 1, 2.
- §5.2 status extension + reconciliation + `--allow-degraded` → Tasks 4, 8.
- §5.3 `watchdog_starting` + `watchdog_posture` → Tasks 5, 6.
- §5.4 runbook → Task 14.
- §6 affected files → all tasks (file-by-file mapping above).
- §7 acceptance criteria → Tasks 2 (partition), 9/10 (mode behaviorals), 7 (shared budget), 11/12 (cohort), 3 (registry), 13 (age gates), 14 (runbook).
- §9 open question Q1 — answered in spec §5.2; implementation discovers schema discriminator in Task 4 Step 1.

Placeholder scan: no TBD / TODO / "add error handling" / "similar to Task N" without code.

Type consistency: `EffectiveMode` enum values match spec strings exactly; `ALERT_FLAG_NAMES` matches `HandoffConfig` field names verified at config.py:108-123 on the spec branch; `POST_COMMENT_PATHS` callsite tuples populated from actual AST scan in Task 3.
