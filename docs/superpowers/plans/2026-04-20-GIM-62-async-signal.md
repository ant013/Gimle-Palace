# GIM-62 Async-Signal Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual "Board re-wakes agent after CI green" operator action with an automated GitHub → paperclip signal pipeline that wakes the current issue-assignee when external async events (CI success, PR review) fire.

**Architecture:** Config-driven GitHub Action dispatcher reads `.github/paperclip-signals.yml`, normalizes GitHub webhook events into internal trigger keys, resolves targets via paperclip REST API, and wakes agents via the proven release+reassign-refresh primitive. Includes dedup via PR marker comments, retry on transient failures, pre-check for active agent sessions (`executionRunId`), and two layers of bot-filter.

**Tech Stack:** Python 3.12, httpx (with MockTransport for tests), PyYAML, pytest + pytest-httpx + freezegun, GitHub Actions (`workflow_run`, `pull_request_review`, `pull_request_review_comment`, `repository_dispatch`), paperclip REST API (`/api/issues/*`).

**Spec:** `docs/superpowers/specs/2026-04-20-async-signal-integration-design.md` (rev2, SHA captured in Task 2).

**Precondition — before Task 1:** The spec file must exist at the path above. The current Gimle branch is `feature/GIM-62-async-signal` (already created off `develop`). A separate clone of `paperclip-shared-fragments` must exist on disk (default location: `/Users/ant013/Code/paperclip-shared-fragments` or wherever operator keeps it); Task 1 navigates there.

---

## File Structure

### Files created in `paperclip-shared-fragments` (upstream submodule)

- `fragments/async-signal-wait.md` — new shared fragment (~28 lines), project-agnostic async-signal-wait discipline.
- `templates/engineers/python-engineer.md` — add one `@include` line.
- `templates/quality/code-reviewer.md` — add one `@include` line.

> **NOTE:** No `templates/engineers/mcp-engineer.md` exists upstream. The Gimle-local `paperclips/roles/mcp-engineer.md` is updated in Task 18.

### Files created in Gimle-Palace

- `.github/paperclip-signals.yml` — dispatcher config (~30 lines).
- `.github/workflows/paperclip-signal.yml` — Action workflow (~45 lines).
- `.github/scripts/paperclip_signal.py` — dispatcher script (~300 LOC).
- `.github/scripts/requirements.txt` — pinned deps for local dev + CI.
- `.github/scripts/tests/__init__.py` — empty package marker.
- `.github/scripts/tests/conftest.py` — pytest fixtures + sys.path setup.
- `.github/scripts/tests/test_paperclip_signal.py` — unit + integration tests (~600 LOC).
- `.github/scripts/tests/fixtures/workflow_run_success.json` — synthetic; replaced with real capture post-merge.
- `.github/scripts/tests/fixtures/workflow_run_failure.json`
- `.github/scripts/tests/fixtures/pull_request_review_approved.json`
- `.github/scripts/tests/fixtures/pull_request_review_comment_created.json`
- `.github/scripts/tests/fixtures/repository_dispatch_qa_smoke.json`
- `.github/scripts/tests/fixtures/sender_is_bot.json`

### Files modified in Gimle-Palace

- `paperclips/fragments/shared` — submodule SHA bump to upstream merge commit.
- `paperclips/roles/mcp-engineer.md` — add `@include async-signal-wait.md`, remove `## Waiting for CI` section (lines 71-115, see Task 17 for exact block).
- `paperclips/roles/python-engineer.md` — add `@include async-signal-wait.md`.
- `paperclips/roles/code-reviewer.md` — add `@include async-signal-wait.md`.
- `paperclips/dist/*.md` — rebuilt via `./paperclips/build.sh` (3 role bundles change).
- `.github/workflows/ci.yml` — add a new `github-scripts-tests` job.

### Operator actions (not code)

- Add repo secret `PAPERCLIP_API_KEY` via `gh secret set` before merging.
- Post-merge iMac deploy: `ssh imac && cd /Users/Shared/Ios/Gimle-Palace && git pull && ./paperclips/deploy-agents.sh --local`.

---

## Task 1: Upstream — create fragment + update templates + merge PR

**Files (in `paperclip-shared-fragments` clone, NOT Gimle):**
- Create: `fragments/async-signal-wait.md`
- Modify: `templates/engineers/python-engineer.md`
- Modify: `templates/quality/code-reviewer.md`

**Why separate from Gimle:** Per memory Iron Rule #1, edits inside Gimle's `paperclips/fragments/shared/` checkout are transient — must be pushed upstream first, then pointer bumped. This task lives in the `paperclip-shared-fragments` repo, not Gimle.

- [ ] **Step 1.1: Navigate to paperclip-shared-fragments clone**

```bash
# Default location on operator machine; adjust if different
cd /Users/ant013/Code/paperclip-shared-fragments
# Verify: remote should match the submodule's origin
git remote -v
# Expected output includes: origin https://github.com/ant013/paperclip-shared-fragments.git
git fetch origin
git checkout main
git pull origin main
```

Expected: clean checkout, HEAD on `origin/main`.

- [ ] **Step 1.2: Create feature branch**

```bash
git checkout -b feat/async-signal-wait-fragment
```

- [ ] **Step 1.3: Create `fragments/async-signal-wait.md`**

```markdown
## Async signal waiting

When your phase requires waiting for an **external async event** (CI run,
peer review, post-deploy smoke), do NOT loop-poll. Exit cleanly with an
explicit wait-marker so the signal infrastructure can resume you.

**Wait-marker format** (last line of your exit comment, top-level on PR or issue):

    ## Waiting for signal: <event> on <sha>

Valid events: `ci.success`, `pr.review`, `qa.smoke_complete`.

**On resume** (you were reassigned without new instructions):

1. Check PR for `<!-- paperclip-signal: ... -->` marker — what woke you.
2. Re-read PR state:
   `gh pr view <N> --json statusCheckRollup,reviews,comments,body`.
3. Act on the signal (handoff / fix / merge / etc.) per your role's phase rules.
4. If you see `<!-- paperclip-signal-failed: ... -->` or
   `<!-- paperclip-signal-deferred: ... -->` — signal infra failed or
   deferred; escalate to operator, do NOT retry silently.

**Anti-pattern:** exiting with vague "waiting for CI" without the marker.
Signal infra cannot target you reliably, operator has no diagnostic.
```

- [ ] **Step 1.4: Add `@include` to `templates/engineers/python-engineer.md`**

Same pattern — append:

```markdown
<!-- @include ../../fragments/async-signal-wait.md -->
```

- [ ] **Step 1.5: Add `@include` to `templates/quality/code-reviewer.md`**

Same pattern — append:

```markdown
<!-- @include ../../fragments/async-signal-wait.md -->
```

- [ ] **Step 1.6: Commit + push**

```bash
git add fragments/async-signal-wait.md \
        templates/engineers/python-engineer.md \
        templates/quality/code-reviewer.md
git commit -m "feat(fragments): async-signal-wait discipline + 2 template includes

Adds the async-signal-wait fragment consumed by Gimle-Palace GIM-62 and
future paperclip projects. Disciplines agent exit behavior when waiting
for CI / PR review / post-deploy smoke signals so a dispatcher Action
can wake them without operator intervention.
"
git push -u origin feat/async-signal-wait-fragment
```

- [ ] **Step 1.8: Open PR in paperclip-shared-fragments**

```bash
gh pr create \
  --repo ant013/paperclip-shared-fragments \
  --title "feat: async-signal-wait fragment + 3 template includes" \
  --body "$(cat <<'EOF'
## Summary
- New `fragments/async-signal-wait.md` — project-agnostic discipline for agents waiting on external async events.
- Templates updated (`mcp-engineer`, `python-engineer`, `code-reviewer`) so new paperclip projects inherit the discipline.

## Consumer
Gimle-Palace GIM-62 async-signal dispatcher Action consumes this fragment.

## Test plan
- N/A for shared-fragments repo — content-only change.
- Gimle-Palace rebuilds `dist/*.md` after submodule SHA bump; agents pick up on next deploy.
EOF
)"
```

Expected output: `https://github.com/ant013/paperclip-shared-fragments/pull/N`.

- [ ] **Step 1.9: Merge PR + capture new SHA**

```bash
gh pr merge <PR-number> --squash --delete-branch --repo ant013/paperclip-shared-fragments
git checkout main
git pull origin main
# Capture SHA for Task 2 — write it down:
git rev-parse HEAD
```

Record the output (e.g., `a1b2c3d...`) — this is the **UPSTREAM_SHA** used in Task 2.

---

## Task 2: Gimle — submodule SHA bump

**Files:**
- Modify: `paperclips/fragments/shared` (submodule pointer)

- [ ] **Step 2.1: Return to Gimle checkout on the feature branch**

```bash
cd /Users/ant013/Android/Gimle-Palace
git branch --show-current
# Expected: feature/GIM-62-async-signal
```

If not on that branch, `git checkout feature/GIM-62-async-signal`.

- [ ] **Step 2.2: Fetch + checkout new submodule SHA**

```bash
cd paperclips/fragments/shared
git fetch origin main
git checkout <UPSTREAM_SHA_FROM_TASK_1>
cd -
```

- [ ] **Step 2.3: Verify submodule pointer change is exactly what's expected**

```bash
git diff paperclips/fragments/shared
```

Expected output (one-line change):
```
-Subproject commit <OLD_SHA>
+Subproject commit <UPSTREAM_SHA_FROM_TASK_1>
```

If the diff shows additional unrelated change, STOP and investigate (Iron Rule #2 — never `git add` a surprise submodule change).

- [ ] **Step 2.4: Commit submodule bump**

```bash
git add paperclips/fragments/shared
git commit -m "chore(submodule): bump shared-fragments to include async-signal-wait

Absorbs upstream PRs #5 (GIM-61 templates, already landed upstream but
not yet bumped in Gimle) and async-signal-wait fragment + template
updates from GIM-62 upstream PR.

Upstream SHA: <UPSTREAM_SHA_FROM_TASK_1>
"
```

- [ ] **Step 2.5: Update spec with captured SHAs**

Edit `docs/superpowers/specs/2026-04-20-async-signal-integration-design.md`:

Find the "Predecessor SHAs" block near the top and update the submodule SHA line to reflect the actual upstream SHA captured in Task 1.9:

```markdown
- `paperclips/fragments/shared` submodule tracked post-bump: `<UPSTREAM_SHA_FROM_TASK_1>`
```

Commit:
```bash
git add docs/superpowers/specs/2026-04-20-async-signal-integration-design.md
git commit -m "docs(spec): pin GIM-62 submodule SHA post-upstream-merge"
```

---

## Task 3: Create dispatcher config file

**Files:**
- Create: `.github/paperclip-signals.yml`

- [ ] **Step 3.1: Create the config file**

```yaml
# Dispatcher config for paperclip-signal GitHub Action.
# Read by .github/scripts/paperclip_signal.py on every event.
# Schema validation in `load_config()`; unknown keys → config-error.

version: 1

# Paperclip company UUID. Fallback default — override via env PAPERCLIP_COMPANY_ID if needed.
company_id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64

# Rules: map normalized trigger keys to wake targets.
# Trigger normalization happens in parse_event (see paperclip_signal.py):
#   workflow_run[success]           → ci.success
#   pull_request_review             → pr.review
#   pull_request_review_comment     → pr.review    (folded — debounce)
#   repository_dispatch[qa-smoke]   → qa.smoke_complete
rules:
  - trigger: ci.success
    target: issue_assignee

  - trigger: pr.review
    target: issue_assignee

  # Extension point — wired to dispatcher but no iMac automation yet.
  # Followup slice will provision the iMac post-deploy smoke script
  # that calls `gh api repos/.../dispatches -f event_type=qa-smoke-complete`.
  - trigger: qa.smoke_complete
    target: issue_assignee
    note: "Awaiting iMac post-deploy smoke automation (followup)"

# Accounts whose events MUST NOT trigger wake. Prevents self-wake loops.
# github-actions[bot] is also filtered at workflow level via if:.
# ant013 is the shared human/agent token — filtered only at Python level
# because sender.type=User for this account, not Bot.
bot_authors:
  - github-actions[bot]
  - ant013
```

- [ ] **Step 3.2: Commit**

```bash
git add .github/paperclip-signals.yml
git commit -m "feat(signal): add paperclip-signals dispatcher config

Declarative rule-set for the GIM-62 async-signal Action. Config shape
is versioned (v1); schema changes require bump + migration. qa.smoke_complete
rule is wired but unused until iMac post-deploy smoke automation lands.
"
```

---

## Task 4: Python script test infrastructure

**Files:**
- Create: `.github/scripts/` directory
- Create: `.github/scripts/requirements.txt`
- Create: `.github/scripts/tests/__init__.py`
- Create: `.github/scripts/tests/conftest.py`
- Create: `.github/scripts/tests/fixtures/` directory + initial synthetic payloads

- [ ] **Step 4.1: Create directory structure**

```bash
mkdir -p .github/scripts/tests/fixtures
touch .github/scripts/tests/__init__.py
```

- [ ] **Step 4.2: Create `.github/scripts/requirements.txt`**

```
pyyaml==6.0.2
httpx==0.27.2
pytest==8.3.3
pytest-httpx==0.32.0
freezegun==1.5.1
```

- [ ] **Step 4.3: Create `.github/scripts/tests/conftest.py`**

```python
"""Pytest config for paperclip_signal tests.

Adds the parent directory (.github/scripts/) to sys.path so tests can
`import paperclip_signal` without the script being a real Python package.
This approach keeps the Action script distributable as a single file
without pyproject.toml overhead.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))


import pytest  # noqa: E402


@pytest.fixture
def fixtures_dir() -> Path:
    """Path to tests/fixtures/ for loading JSON webhook payloads."""
    return FIXTURES_DIR


@pytest.fixture
def load_fixture(fixtures_dir: Path):
    """Callable that loads a JSON fixture by filename stem."""

    def _load(name: str) -> dict:
        path = fixtures_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Fixture {path} missing. Create a synthetic payload or capture from a real Action run."
            )
        return json.loads(path.read_text())

    return _load
```

- [ ] **Step 4.4: Create synthetic fixture `workflow_run_success.json`**

Minimal synthetic payload — to be replaced with a real capture post-merge (see `@pytest.mark.fixture_pending` convention).

```json
{
  "action": "completed",
  "workflow_run": {
    "id": 12345678,
    "name": "CI",
    "head_branch": "feature/GIM-62-async-signal",
    "head_sha": "abc123def456",
    "conclusion": "success",
    "status": "completed",
    "pull_requests": [
      {"number": 77, "head": {"ref": "feature/GIM-62-async-signal", "sha": "abc123def456"}}
    ]
  },
  "sender": {
    "login": "ant013",
    "type": "User"
  },
  "repository": {
    "full_name": "ant013/Gimle-Palace"
  }
}
```

- [ ] **Step 4.5: Create synthetic fixture `workflow_run_failure.json`**

Same shape as success but `"conclusion": "failure"`:

```json
{
  "action": "completed",
  "workflow_run": {
    "id": 12345679,
    "name": "CI",
    "head_branch": "feature/GIM-62-async-signal",
    "head_sha": "abc123def456",
    "conclusion": "failure",
    "status": "completed",
    "pull_requests": [
      {"number": 77, "head": {"ref": "feature/GIM-62-async-signal", "sha": "abc123def456"}}
    ]
  },
  "sender": {
    "login": "ant013",
    "type": "User"
  },
  "repository": {
    "full_name": "ant013/Gimle-Palace"
  }
}
```

- [ ] **Step 4.6: Create synthetic fixture `pull_request_review_approved.json`**

```json
{
  "action": "submitted",
  "review": {
    "state": "approved",
    "commit_id": "abc123def456",
    "submitted_at": "2026-04-20T12:00:00Z"
  },
  "pull_request": {
    "number": 77,
    "head": {
      "ref": "feature/GIM-62-async-signal",
      "sha": "abc123def456"
    }
  },
  "sender": {
    "login": "operator",
    "type": "User"
  },
  "repository": {
    "full_name": "ant013/Gimle-Palace"
  }
}
```

- [ ] **Step 4.7: Create synthetic fixture `pull_request_review_comment_created.json`**

```json
{
  "action": "created",
  "comment": {
    "id": 999,
    "body": "nit: rename this variable",
    "commit_id": "abc123def456"
  },
  "pull_request": {
    "number": 77,
    "head": {
      "ref": "feature/GIM-62-async-signal",
      "sha": "abc123def456"
    }
  },
  "sender": {
    "login": "operator",
    "type": "User"
  },
  "repository": {
    "full_name": "ant013/Gimle-Palace"
  }
}
```

- [ ] **Step 4.8: Create synthetic fixture `repository_dispatch_qa_smoke.json`**

```json
{
  "action": "qa-smoke-complete",
  "client_payload": {
    "branch": "develop",
    "pr_number": 80,
    "sha": "xyz789",
    "smoke_status": "passed"
  },
  "sender": {
    "login": "operator",
    "type": "User"
  },
  "repository": {
    "full_name": "ant013/Gimle-Palace"
  }
}
```

- [ ] **Step 4.9: Create synthetic fixture `sender_is_bot.json`**

```json
{
  "action": "submitted",
  "review": {"state": "commented", "commit_id": "abc123def456"},
  "pull_request": {"number": 77, "head": {"ref": "feature/GIM-62-async-signal", "sha": "abc123def456"}},
  "sender": {"login": "github-actions[bot]", "type": "Bot"},
  "repository": {"full_name": "ant013/Gimle-Palace"}
}
```

- [ ] **Step 4.10: Create empty test file to validate infrastructure**

`.github/scripts/tests/test_paperclip_signal.py`:

```python
"""Tests for paperclip_signal.py — added incrementally per plan tasks."""

from __future__ import annotations


def test_infrastructure_loads(load_fixture):
    """Smoke-test: fixtures load via conftest helper."""
    payload = load_fixture("workflow_run_success")
    assert payload["workflow_run"]["conclusion"] == "success"
```

- [ ] **Step 4.11: Install deps + verify the smoke test passes**

```bash
cd .github/scripts
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```

Expected: `test_infrastructure_loads PASSED`.

- [ ] **Step 4.12: Add `.venv/` to `.gitignore` if not already ignored**

```bash
cd /Users/ant013/Android/Gimle-Palace
grep -q "^\.github/scripts/\.venv/$" .gitignore || echo ".github/scripts/.venv/" >> .gitignore
```

- [ ] **Step 4.13: Commit**

```bash
git add .github/scripts/ .gitignore
git commit -m "test(signal): pytest infra + synthetic webhook fixtures

Adds conftest.py with sys.path bridge so tests/ can import the
standalone Action script without packaging it. Six synthetic webhook
payloads cover workflow_run success/failure, PR review and
review_comment, repository_dispatch qa-smoke, and bot-sender.
Synthetic payloads are flagged for replacement with real captures
post-first-Action-run.
"
```

---

## Task 5: Config loader — TDD

**Files:**
- Create: `.github/scripts/paperclip_signal.py` (partial — only config types + load_config)
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 5.1: Write failing tests for config loader**

Append to `.github/scripts/tests/test_paperclip_signal.py`:

```python
from pathlib import Path

import pytest

import paperclip_signal as ps


def test_config_parse_valid(tmp_path: Path):
    """Valid config parses into Config with expected rules and bot_authors."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64
rules:
  - trigger: ci.success
    target: issue_assignee
  - trigger: pr.review
    target: issue_assignee
bot_authors:
  - github-actions[bot]
  - ant013
"""
    )
    config = ps.load_config(cfg)
    assert config.version == 1
    assert config.company_id == "9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64"
    assert len(config.rules) == 2
    assert config.rules[0].trigger == "ci.success"
    assert config.rules[0].target == "issue_assignee"
    assert config.bot_authors == ["github-actions[bot]", "ant013"]


def test_config_parse_unknown_trigger_raises(tmp_path: Path):
    """trigger not in {ci.success, pr.review, qa.smoke_complete} → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: not.a.real.trigger
    target: issue_assignee
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError) as excinfo:
        ps.load_config(cfg)
    assert "not.a.real.trigger" in str(excinfo.value)


def test_config_parse_pr_review_comment_rejected(tmp_path: Path):
    """pr.review_comment as a config trigger → ConfigError (must be folded to pr.review)."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: pr.review_comment
    target: issue_assignee
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError) as excinfo:
        ps.load_config(cfg)
    assert "pr.review_comment" in str(excinfo.value)
    assert "pr.review" in str(excinfo.value)  # hint at correct value


def test_config_parse_unknown_target_raises(tmp_path: Path):
    """target not in {issue_assignee, role(...)} → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: ci.success
    target: bogus_target
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError):
        ps.load_config(cfg)


def test_config_parse_role_target_parses(tmp_path: Path):
    """role(Name) target parses successfully; runtime raises NotImplementedError later."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: x
rules:
  - trigger: ci.success
    target: role(Translator)
bot_authors: []
"""
    )
    config = ps.load_config(cfg)
    assert config.rules[0].target == "role(Translator)"


def test_config_parse_unknown_version_raises(tmp_path: Path):
    """version != 1 → ConfigError."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 999
company_id: x
rules: []
bot_authors: []
"""
    )
    with pytest.raises(ps.ConfigError):
        ps.load_config(cfg)
```

- [ ] **Step 5.2: Run tests — expect import error**

```bash
cd .github/scripts
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: `ModuleNotFoundError: No module named 'paperclip_signal'` — confirms we need the script.

- [ ] **Step 5.3: Create minimal `paperclip_signal.py` with config types + loader**

`.github/scripts/paperclip_signal.py`:

```python
"""paperclip-signal dispatcher.

Reads a GitHub event + .github/paperclip-signals.yml config, resolves a
wake target (currently only `issue_assignee`), and triggers a paperclip
reassign-refresh to wake the current assignee of the linked paperclip
issue. Designed to run as a GitHub Action on workflow_run /
pull_request_review / pull_request_review_comment / repository_dispatch.

Spec: docs/superpowers/specs/2026-04-20-async-signal-integration-design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


ALLOWED_TRIGGERS = frozenset({"ci.success", "pr.review", "qa.smoke_complete"})
ROLE_TARGET_RE = re.compile(r"^role\(([A-Za-z][A-Za-z0-9_-]*)\)$")
SUPPORTED_VERSION = 1


class ConfigError(Exception):
    """Raised when the signals config is malformed or contains unsupported values."""


@dataclass(frozen=True)
class Rule:
    trigger: str
    target: str
    note: str = ""


@dataclass(frozen=True)
class Config:
    version: int
    company_id: str
    rules: list[Rule] = field(default_factory=list)
    bot_authors: list[str] = field(default_factory=list)


def _validate_target(target: str) -> None:
    if target == "issue_assignee":
        return
    if ROLE_TARGET_RE.match(target):
        return
    raise ConfigError(
        f"Unknown target {target!r}. Supported: 'issue_assignee' or 'role(<Name>)'."
    )


def _validate_trigger(trigger: str) -> None:
    if trigger == "pr.review_comment":
        raise ConfigError(
            "trigger 'pr.review_comment' is not a valid config key. "
            "The GitHub event pull_request_review_comment is normalized to "
            "'pr.review' in parse_event; use 'pr.review' instead."
        )
    if trigger not in ALLOWED_TRIGGERS:
        raise ConfigError(
            f"Unknown trigger {trigger!r}. Supported: {sorted(ALLOWED_TRIGGERS)}."
        )


def load_config(path: Path) -> Config:
    """Parse and validate the signals config from disk."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}.")

    version = raw.get("version")
    if version != SUPPORTED_VERSION:
        raise ConfigError(
            f"Unsupported config version {version!r}. Expected {SUPPORTED_VERSION}."
        )

    company_id = raw.get("company_id")
    if not isinstance(company_id, str) or not company_id:
        raise ConfigError("company_id must be a non-empty string.")

    rules_raw = raw.get("rules") or []
    if not isinstance(rules_raw, list):
        raise ConfigError("rules must be a list.")

    rules: list[Rule] = []
    for i, entry in enumerate(rules_raw):
        if not isinstance(entry, dict):
            raise ConfigError(f"rules[{i}] must be a mapping.")
        trigger = entry.get("trigger")
        target = entry.get("target")
        note = entry.get("note", "")
        if not isinstance(trigger, str):
            raise ConfigError(f"rules[{i}].trigger must be a string.")
        if not isinstance(target, str):
            raise ConfigError(f"rules[{i}].target must be a string.")
        _validate_trigger(trigger)
        _validate_target(target)
        rules.append(Rule(trigger=trigger, target=target, note=note))

    bot_authors = raw.get("bot_authors") or []
    if not isinstance(bot_authors, list) or not all(isinstance(x, str) for x in bot_authors):
        raise ConfigError("bot_authors must be a list of strings.")

    return Config(
        version=version,
        company_id=company_id,
        rules=rules,
        bot_authors=list(bot_authors),
    )
```

- [ ] **Step 5.4: Run tests — all 6 should pass**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k config
```

Expected: 6 passed.

- [ ] **Step 5.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): config loader + schema validation (TDD)

Dataclasses: Config, Rule. Validation rejects unknown trigger/target
keys; specifically rejects pr.review_comment with a hint to use
pr.review (the normalized form). role(<Name>) target parses (for
future Translator use-case) but resolver raises NotImplementedError.
"
```

---

## Task 6: Event parser — all 4 event types (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` (add Event dataclass + parse_event)
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 6.1: Write failing tests for parse_event**

Append to `test_paperclip_signal.py`:

```python
def test_parse_event_ci_success(load_fixture):
    """workflow_run with conclusion=success → Event(trigger=ci.success, ...)."""
    payload = load_fixture("workflow_run_success")
    event = ps.parse_event("workflow_run", payload)
    assert event is not None
    assert event.trigger == "ci.success"
    assert event.sha == "abc123def456"
    assert event.pr_number == 77
    assert event.branch == "feature/GIM-62-async-signal"
    assert event.author == "ant013"


def test_parse_event_ci_failure_returns_none(load_fixture):
    """workflow_run with conclusion=failure → None (red CI out of scope)."""
    payload = load_fixture("workflow_run_failure")
    event = ps.parse_event("workflow_run", payload)
    assert event is None


def test_parse_event_pr_review_approved(load_fixture):
    """pull_request_review submitted → trigger=pr.review."""
    payload = load_fixture("pull_request_review_approved")
    event = ps.parse_event("pull_request_review", payload)
    assert event is not None
    assert event.trigger == "pr.review"
    assert event.sha == "abc123def456"
    assert event.pr_number == 77
    assert event.branch == "feature/GIM-62-async-signal"
    assert event.author == "operator"


def test_parse_event_pr_review_comment_folds_to_pr_review(load_fixture):
    """pull_request_review_comment → trigger=pr.review (debounce fold)."""
    payload = load_fixture("pull_request_review_comment_created")
    event = ps.parse_event("pull_request_review_comment", payload)
    assert event is not None
    assert event.trigger == "pr.review"   # folded, NOT pr.review_comment
    assert event.sha == "abc123def456"
    assert event.pr_number == 77


def test_parse_event_repository_dispatch_qa_smoke(load_fixture):
    """repository_dispatch action=qa-smoke-complete → trigger=qa.smoke_complete."""
    payload = load_fixture("repository_dispatch_qa_smoke")
    event = ps.parse_event("repository_dispatch", payload)
    assert event is not None
    assert event.trigger == "qa.smoke_complete"
    assert event.sha == "xyz789"
    assert event.pr_number == 80
    assert event.branch == "develop"


def test_parse_event_repository_dispatch_missing_branch_raises():
    """repository_dispatch without client_payload.branch → ConfigError."""
    payload = {
        "action": "qa-smoke-complete",
        "client_payload": {"pr_number": 80, "sha": "abc"},
        "sender": {"login": "x", "type": "User"},
    }
    with pytest.raises(ps.ConfigError):
        ps.parse_event("repository_dispatch", payload)


def test_parse_event_unknown_event_name_returns_none():
    """Unknown event_name → None (graceful, not fail)."""
    event = ps.parse_event("push", {"ref": "refs/heads/main"})
    assert event is None
```

- [ ] **Step 6.2: Run tests — expect AttributeError on ps.parse_event**

```bash
cd .github/scripts
source .venv/bin/activate
python -m pytest tests/test_paperclip_signal.py::test_parse_event_ci_success -v
```

Expected: `AttributeError: module 'paperclip_signal' has no attribute 'parse_event'`.

- [ ] **Step 6.3: Add Event dataclass + parse_event to paperclip_signal.py**

Append to `paperclip_signal.py` (before `load_config`):

```python
@dataclass(frozen=True)
class Event:
    """Normalized GitHub webhook event."""

    trigger: str          # One of ALLOWED_TRIGGERS (after normalization).
    sha: str              # Head commit SHA the event relates to.
    pr_number: int        # PR number on the Gimle repo.
    branch: str           # Head ref / branch name for resolving the paperclip issue.
    author: str           # github sender.login, used for bot-filter.


def _parse_workflow_run(payload: dict) -> Event | None:
    run = payload.get("workflow_run") or {}
    conclusion = run.get("conclusion")
    if conclusion != "success":
        return None   # red/cancelled/neutral CI not in scope
    prs = run.get("pull_requests") or []
    if not prs:
        return None   # CI without associated PR (e.g. push to default branch)
    pr = prs[0]
    return Event(
        trigger="ci.success",
        sha=run.get("head_sha") or "",
        pr_number=pr.get("number") or 0,
        branch=run.get("head_branch") or pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_pull_request_review(payload: dict) -> Event | None:
    pr = payload.get("pull_request") or {}
    return Event(
        trigger="pr.review",
        sha=(payload.get("review") or {}).get("commit_id") or pr.get("head", {}).get("sha", ""),
        pr_number=pr.get("number") or 0,
        branch=pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_pull_request_review_comment(payload: dict) -> Event | None:
    pr = payload.get("pull_request") or {}
    return Event(
        trigger="pr.review",   # FOLDED — debounce review + review_comment into one trigger
        sha=(payload.get("comment") or {}).get("commit_id") or pr.get("head", {}).get("sha", ""),
        pr_number=pr.get("number") or 0,
        branch=pr.get("head", {}).get("ref") or "",
        author=(payload.get("sender") or {}).get("login") or "",
    )


def _parse_repository_dispatch(payload: dict) -> Event | None:
    action = payload.get("action") or ""
    if action != "qa-smoke-complete":
        return None
    cp = payload.get("client_payload") or {}
    branch = cp.get("branch")
    pr_number = cp.get("pr_number")
    sha = cp.get("sha")
    if not branch:
        raise ConfigError(
            "repository_dispatch qa-smoke-complete payload missing required "
            "field 'branch' in client_payload."
        )
    return Event(
        trigger="qa.smoke_complete",
        sha=sha or "",
        pr_number=pr_number or 0,
        branch=branch,
        author=(payload.get("sender") or {}).get("login") or "",
    )


_EVENT_PARSERS = {
    "workflow_run": _parse_workflow_run,
    "pull_request_review": _parse_pull_request_review,
    "pull_request_review_comment": _parse_pull_request_review_comment,
    "repository_dispatch": _parse_repository_dispatch,
}


def parse_event(event_name: str, payload: dict) -> Event | None:
    """Normalize a GitHub webhook into an internal Event, or None if non-actionable.

    Events outside the known set return None (graceful no-op). Partial payloads
    may raise ConfigError where required fields are absent from known events.
    """
    parser = _EVENT_PARSERS.get(event_name)
    if parser is None:
        return None
    return parser(payload)
```

- [ ] **Step 6.4: Run tests — all 7 event tests should pass**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k parse_event
```

Expected: 7 passed.

- [ ] **Step 6.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): parse_event for 4 GitHub event types (TDD)

workflow_run[success] → ci.success (red returns None, not in scope)
pull_request_review → pr.review
pull_request_review_comment → pr.review (folded — debounce)
repository_dispatch[qa-smoke-complete] → qa.smoke_complete (requires
  client_payload.branch, raises ConfigError if missing)

Unknown event names return None gracefully — the Action workflow
limits which events fire anyway.
"
```

---

## Task 7: Branch regex + issue-number extraction (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py`
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 7.1: Write failing tests**

Append:

```python
def test_extract_issue_number_valid_branch():
    """feature/GIM-62-async-signal → 62."""
    assert ps.extract_issue_number("feature/GIM-62-async-signal") == 62


def test_extract_issue_number_two_digit_number():
    """feature/GIM-123-big-slug → 123."""
    assert ps.extract_issue_number("feature/GIM-123-big-slug") == 123


def test_extract_issue_number_no_match():
    """Non-feature branches return None (log warning, skip)."""
    assert ps.extract_issue_number("fix/typo") is None
    assert ps.extract_issue_number("main") is None
    assert ps.extract_issue_number("feature/bootstrap-no-number") is None


def test_extract_issue_number_empty_branch():
    assert ps.extract_issue_number("") is None
```

- [ ] **Step 7.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k extract_issue
```

- [ ] **Step 7.3: Add extract_issue_number**

Append to `paperclip_signal.py`:

```python
BRANCH_RE = re.compile(r"^feature/GIM-(\d+)-")


def extract_issue_number(branch: str) -> int | None:
    """Parse the paperclip issueNumber from a feature-branch name.

    Convention: feature/GIM-<N>-<slug> (enforced by git-workflow.md fragment).
    Non-matching branches return None — Action logs WARNING and exits 0.
    """
    if not branch:
        return None
    match = BRANCH_RE.match(branch)
    return int(match.group(1)) if match else None
```

- [ ] **Step 7.4: Run tests — expect all pass**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k extract_issue
```

Expected: 4 passed.

- [ ] **Step 7.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): branch regex → paperclip issue number (TDD)

feature/GIM-<N>-<slug> → N. Non-matching branches return None so the
Action logs WARNING and no-ops without failing — human PRs with
arbitrary branch names are expected.
"
```

---

## Task 8: Bot filter — Python-level (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py`
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 8.1: Write failing tests**

```python
def test_is_bot_author_in_list():
    """author in bot_authors → True."""
    bot_authors = ["github-actions[bot]", "ant013"]
    assert ps.is_bot_author("ant013", bot_authors) is True
    assert ps.is_bot_author("github-actions[bot]", bot_authors) is True


def test_is_bot_author_not_in_list():
    bot_authors = ["github-actions[bot]", "ant013"]
    assert ps.is_bot_author("operator", bot_authors) is False
    assert ps.is_bot_author("", bot_authors) is False
```

- [ ] **Step 8.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k is_bot_author
```

- [ ] **Step 8.3: Add is_bot_author**

Append:

```python
def is_bot_author(author: str, bot_authors: list[str]) -> bool:
    """Return True if the sender login should be filtered out.

    Complements the workflow-level `if:` which filters Bot-type senders.
    This Python-level check covers shared-token accounts like `ant013`
    where sender.type is User.
    """
    return author in bot_authors
```

- [ ] **Step 8.4: Run tests — 2 passed**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k is_bot_author
```

- [ ] **Step 8.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): is_bot_author Python-level filter (TDD)

Complements workflow-level if: that filters Bot-type senders. Python
check covers shared-token User accounts like ant013 which bypass the
Bot-type filter.
"
```

---

## Task 9: Paperclip API client — httpx wrapper (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add PaperclipClient class
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

This task covers: GET issue (for assigneeId + executionRunId), POST release, PATCH assignee, POST comment. Retries done in Task 10; active-session pre-check in Task 11.

- [ ] **Step 9.1: Write failing test for GET issue**

```python
import httpx
from pytest_httpx import HTTPXMock


def test_paperclip_get_issue_success(httpx_mock: HTTPXMock):
    """GET /api/issues?issueNumber=62 returns single issue with assignee + executionRunId."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "issue-uuid-1",
            "issueNumber": 62,
            "assigneeId": "agent-uuid-1",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    client = ps.PaperclipClient(base_url="https://paperclip.example.com", api_key="k", company_id="C1")
    issue = client.get_issue_by_number(62)
    assert issue.id == "issue-uuid-1"
    assert issue.assignee_id == "agent-uuid-1"
    assert issue.assignee_name == "MCPEngineer"
    assert issue.execution_run_id is None


def test_paperclip_get_issue_not_found(httpx_mock: HTTPXMock):
    """Empty response list → raises PaperclipError."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=99&companyId=C1",
        json=[],
    )
    client = ps.PaperclipClient(base_url="https://paperclip.example.com", api_key="k", company_id="C1")
    with pytest.raises(ps.PaperclipError) as excinfo:
        client.get_issue_by_number(99)
    assert "99" in str(excinfo.value)


def test_paperclip_release_and_reassign(httpx_mock: HTTPXMock):
    """POST /release + PATCH assigneeId. Both calls made with correct payloads."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/issue-uuid-1/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/issue-uuid-1",
        match_json={"assigneeId": "agent-uuid-1"},
        json={"ok": True},
    )
    client = ps.PaperclipClient(base_url="https://paperclip.example.com", api_key="k", company_id="C1")
    client.release_and_reassign(issue_id="issue-uuid-1", assignee_id="agent-uuid-1")
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert requests[0].method == "POST" and requests[0].url.path.endswith("/release")
    assert requests[1].method == "PATCH"
```

- [ ] **Step 9.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k paperclip
```

- [ ] **Step 9.3: Add PaperclipClient + Issue dataclass**

Append to `paperclip_signal.py`:

```python
class PaperclipError(Exception):
    """Raised for paperclip API failures (network, 4xx, 5xx after retries)."""


@dataclass(frozen=True)
class Issue:
    """Subset of paperclip issue fields this script needs."""

    id: str
    issue_number: int
    assignee_id: str | None
    assignee_name: str | None
    execution_run_id: str | None


class PaperclipClient:
    """Thin httpx wrapper over paperclip REST API.

    Timeouts are conservative (10s connect, 30s read) because paperclip
    occasionally has slow GC-pause-style latency. Retries are applied in
    the higher-level release_and_reassign_with_retry wrapper (Task 10).
    """

    def __init__(self, base_url: str, api_key: str, company_id: str, timeout: float = 30.0):
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout),
        )
        self._company_id = company_id

    def get_issue_by_number(self, issue_number: int) -> Issue:
        resp = self._client.get(
            "/api/issues",
            params={"issueNumber": issue_number, "companyId": self._company_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise PaperclipError(
                f"Issue with issueNumber={issue_number} not found in company {self._company_id}."
            )
        entry = data[0]
        return Issue(
            id=entry["id"],
            issue_number=entry["issueNumber"],
            assignee_id=entry.get("assigneeId"),
            assignee_name=entry.get("assigneeName"),
            execution_run_id=entry.get("executionRunId"),
        )

    def release_and_reassign(self, issue_id: str, assignee_id: str) -> None:
        """Wake an assignee by releasing the current execution lock + re-patching the assignee.

        Proven workaround from GIM-52/53 stale-execution-lock incidents:
        paperclip treats PATCH assigneeId=same-id as a fresh assignment event.
        """
        release = self._client.post(f"/api/issues/{issue_id}/release")
        release.raise_for_status()
        patch = self._client.patch(f"/api/issues/{issue_id}", json={"assigneeId": assignee_id})
        patch.raise_for_status()

    def post_comment(self, issue_id: str, body: str) -> None:
        resp = self._client.post(f"/api/issues/{issue_id}/comments", json={"body": body})
        resp.raise_for_status()

    def close(self) -> None:
        self._client.close()
```

Add the httpx import at top of file if not present:

```python
import httpx
```

- [ ] **Step 9.4: Run paperclip tests — 3 passed**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k paperclip
```

- [ ] **Step 9.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): PaperclipClient — GET issue + release + reassign (TDD)

Thin httpx wrapper. Issue dataclass carries assignee_id and
execution_run_id (latter used by active-session pre-check in Task 11).
release_and_reassign encodes the proven GIM-52/53 workaround —
PATCH assigneeId=same-id triggers a fresh assignment event on paperclip.
"
```

---

## Task 10: Retry logic — 5xx + 409 with backoff (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add `release_and_reassign_with_retry`
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 10.1: Write failing tests**

```python
from unittest.mock import patch


def test_release_and_reassign_retry_5xx_then_success(httpx_mock: HTTPXMock):
    """503 on release → retry → success. Confirms retry loop wraps call."""
    # Two 503s then 200 on release
    for _ in range(2):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/uuid/release",
            status_code=503,
            json={"error": "temporarily unavailable"},
        )
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/uuid",
        json={"ok": True},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):  # skip real sleeps
        ps.release_and_reassign_with_retry(client, issue_id="uuid", assignee_id="agent-uuid")


def test_release_and_reassign_retry_all_fail(httpx_mock: HTTPXMock):
    """503 forever → PaperclipError after max attempts."""
    for _ in range(3):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/uuid/release",
            status_code=503,
            json={"error": "down"},
        )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        with pytest.raises(ps.PaperclipError):
            ps.release_and_reassign_with_retry(client, issue_id="uuid", assignee_id="agent-uuid")


def test_release_and_reassign_retry_409_transient_lock(httpx_mock: HTTPXMock):
    """409 on release → retry → success (stale-lock recovers)."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        status_code=409,
        json={"error": "execution lock"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/uuid",
        json={"ok": True},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        ps.release_and_reassign_with_retry(client, issue_id="uuid", assignee_id="agent-uuid")


def test_release_and_reassign_no_retry_on_4xx_not_409(httpx_mock: HTTPXMock):
    """403 on release → immediate PaperclipError (no retry)."""
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/uuid/release",
        status_code=403,
        json={"error": "forbidden"},
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        with pytest.raises(ps.PaperclipError):
            ps.release_and_reassign_with_retry(client, issue_id="uuid", assignee_id="agent-uuid")
    # Exactly one request (no retry on non-5xx non-409)
    assert len(httpx_mock.get_requests()) == 1
```

- [ ] **Step 10.2: Run tests — expect AttributeError on release_and_reassign_with_retry**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k retry
```

- [ ] **Step 10.3: Add retry wrapper**

Append to `paperclip_signal.py`:

```python
import time


RETRY_DELAYS_SECONDS = (10, 30)    # Attempts at t=0, t=10s, t=30s total 3 attempts.
RETRY_STATUS_CODES = {409, 500, 502, 503, 504}


def _sleep(seconds: float) -> None:
    """Indirection point for patching in tests."""
    time.sleep(seconds)


def release_and_reassign_with_retry(
    client: PaperclipClient,
    issue_id: str,
    assignee_id: str,
) -> None:
    """Call release + reassign with retry on transient failures.

    Retries on HTTP 409 (stale execution lock) and 5xx. Does NOT retry on
    other 4xx — those are deterministic errors (auth, malformed payload).
    After exhausting retries, raises PaperclipError with the last status.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0, *RETRY_DELAYS_SECONDS]):
        if delay:
            _sleep(delay)
        try:
            client.release_and_reassign(issue_id=issue_id, assignee_id=assignee_id)
            return
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status not in RETRY_STATUS_CODES:
                raise PaperclipError(
                    f"release_and_reassign failed with non-retryable status {status}: {exc.response.text}"
                ) from exc
            last_exc = exc
        except httpx.RequestError as exc:
            last_exc = exc   # connection / timeout — retry
    raise PaperclipError(
        f"release_and_reassign failed after {len(RETRY_DELAYS_SECONDS) + 1} attempts: {last_exc}"
    ) from last_exc
```

- [ ] **Step 10.4: Run retry tests — 4 passed**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k retry
```

- [ ] **Step 10.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): retry on 5xx + 409 with 10s/30s backoff (TDD)

3 attempts total (t=0, t=10s, t=30s). Retries 409 because GIM-52/53
stale-execution-lock sometimes clears on second attempt. Non-409 4xx
are deterministic (auth, bad payload) — fail fast. _sleep indirection
so tests patch it to zero.
"
```

---

## Task 11: Active-session pre-check + deferred path (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add `resolve_target` with pre-check
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

Addresses the "race with active agent session" concern (spec §6 row). If `executionRunId` is non-null, sleep 30s + recheck; still non-null → post deferred comment, exit 0.

- [ ] **Step 11.1: Write failing tests**

```python
def test_resolve_target_issue_assignee_active_run_null(httpx_mock: HTTPXMock):
    """executionRunId=null → ResolveResult.proceed with assignee."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "proceed"
    assert result.issue.id == "uuid"
    assert result.issue.assignee_id == "agent-uuid"


def test_resolve_target_issue_assignee_deferred_active_run_persists(httpx_mock: HTTPXMock):
    """executionRunId non-null on first AND recheck → status=deferred."""
    for _ in range(2):
        httpx_mock.add_response(
            method="GET",
            url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
            json=[{
                "id": "uuid",
                "issueNumber": 62,
                "assigneeId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": "run-active-1",
            }],
        )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "deferred"
    assert result.issue.execution_run_id == "run-active-1"


def test_resolve_target_issue_assignee_active_run_clears(httpx_mock: HTTPXMock):
    """executionRunId non-null then null → status=proceed."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": "run-active-1",
        }],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    with patch.object(ps, "_sleep", lambda s: None):
        result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "proceed"


def test_resolve_target_issue_assignee_null_assignee(httpx_mock: HTTPXMock):
    """Assignee is null on issue → status=no_assignee."""
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "uuid",
            "issueNumber": 62,
            "assigneeId": None,
            "assigneeName": None,
            "executionRunId": None,
        }],
    )
    client = ps.PaperclipClient("https://paperclip.example.com", "k", "C1")
    result = ps.resolve_target_issue_assignee(client, issue_number=62)
    assert result.status == "no_assignee"
```

- [ ] **Step 11.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k resolve_target
```

- [ ] **Step 11.3: Add resolve_target_issue_assignee + ResolveResult**

Append to `paperclip_signal.py`:

```python
ACTIVE_RUN_RECHECK_DELAY_SECONDS = 30


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of resolving a target for a given event.

    status ∈ {"proceed", "deferred", "no_assignee"}.
    proceed → main() calls release_and_reassign_with_retry + post success comment.
    deferred → main() posts deferred comment and exits 0 (agent is actively running).
    no_assignee → main() posts warning comment and exits 0.
    """

    status: str
    issue: Issue


def resolve_target_issue_assignee(
    client: PaperclipClient,
    issue_number: int,
) -> ResolveResult:
    """Resolve the target issue's assignee, with active-session pre-check.

    If executionRunId is non-null, sleep ACTIVE_RUN_RECHECK_DELAY_SECONDS and
    GET again. Still non-null → status=deferred (agent truly running; do not
    pound API with release attempts that will 409 against the live run).
    """
    issue = client.get_issue_by_number(issue_number)
    if issue.assignee_id is None:
        return ResolveResult(status="no_assignee", issue=issue)
    if issue.execution_run_id is not None:
        _sleep(ACTIVE_RUN_RECHECK_DELAY_SECONDS)
        issue = client.get_issue_by_number(issue_number)
        if issue.execution_run_id is not None:
            return ResolveResult(status="deferred", issue=issue)
    return ResolveResult(status="proceed", issue=issue)
```

- [ ] **Step 11.4: Run resolve_target tests — 4 passed**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k resolve_target
```

- [ ] **Step 11.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): active-session pre-check → deferred path (TDD)

Addresses spec §6 active-session race. If executionRunId is non-null,
sleep 30s and recheck; still non-null → status=deferred so main()
posts deferred comment and exits 0. Null assignee also handled as
status=no_assignee with a different warning comment path.
"
```

---

## Task 12: Dedup marker check via gh api (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add `pr_has_signal_marker`
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 12.1: Write failing tests**

```python
def test_pr_has_signal_marker_present():
    """Comment body with matching marker → True."""
    comments = [
        {"body": "Some random comment"},
        {"body": "<!-- paperclip-signal: ci.success abc123 assignee=MCPEngineer --> Woke MCPEngineer on ci.success at abc123."},
    ]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is True


def test_pr_has_signal_marker_absent():
    """Comments without matching marker → False."""
    comments = [
        {"body": "Unrelated"},
        {"body": "<!-- paperclip-signal: ci.success DIFFERENT_SHA -->"},
    ]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False


def test_pr_has_signal_marker_different_trigger():
    """Marker with same sha but different trigger → False."""
    comments = [{"body": "<!-- paperclip-signal: pr.review abc123 -->"}]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False


def test_pr_has_signal_marker_empty_comments():
    assert ps.pr_has_signal_marker([], trigger="ci.success", sha="abc123") is False


def test_pr_has_signal_marker_failed_marker_not_counted():
    """signal-failed markers do NOT deduplicate — a failed prior attempt should retry."""
    comments = [{"body": "<!-- paperclip-signal-failed: ci.success abc123 -->"}]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False


def test_pr_has_signal_marker_deferred_marker_not_counted():
    """signal-deferred markers do NOT deduplicate — a deferred signal should retry next event."""
    comments = [{"body": "<!-- paperclip-signal-deferred: ci.success abc123 -->"}]
    assert ps.pr_has_signal_marker(comments, trigger="ci.success", sha="abc123") is False
```

- [ ] **Step 12.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k signal_marker
```

- [ ] **Step 12.3: Add pr_has_signal_marker**

Append to `paperclip_signal.py`:

```python
def pr_has_signal_marker(comments: list[dict], trigger: str, sha: str) -> bool:
    """Check if a success marker for this (trigger, sha) already exists.

    Only success markers count — failed and deferred markers intentionally
    don't dedupe so a future retry can succeed.
    """
    success_pattern = f"<!-- paperclip-signal: {trigger} {sha}"
    for c in comments:
        body = c.get("body", "")
        if success_pattern in body:
            return True
    return False
```

- [ ] **Step 12.4: Run tests — 6 passed**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k signal_marker
```

- [ ] **Step 12.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): PR comment dedup via marker scan (TDD)

Only success markers dedupe. Failed/deferred markers do NOT count so
subsequent events can retry. String-matching rather than regex —
trigger and sha are both bounded alphanumerics.
"
```

---

## Task 13: Post signal comments — success / deferred / failed (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add comment-building functions + GitHub API helpers
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 13.1: Write failing tests**

```python
def test_build_success_comment_body():
    body = ps.build_success_comment(
        trigger="ci.success",
        sha="abc123",
        agent_name="MCPEngineer",
    )
    assert "<!-- paperclip-signal: ci.success abc123 assignee=MCPEngineer -->" in body
    assert "Woke MCPEngineer on ci.success at abc123" in body


def test_build_deferred_comment_body():
    body = ps.build_deferred_comment(
        trigger="ci.success",
        sha="abc123",
        execution_run_id="run-xyz",
    )
    assert "<!-- paperclip-signal-deferred: ci.success abc123 -->" in body
    assert "run-xyz" in body
    assert "deferred" in body.lower()


def test_build_failed_comment_body():
    body = ps.build_failed_comment(
        trigger="ci.success",
        sha="abc123",
        error_message="503 Service Unavailable",
    )
    assert "<!-- paperclip-signal-failed: ci.success abc123 -->" in body
    assert "503 Service Unavailable" in body
    assert "operator" in body.lower()


def test_build_no_assignee_comment_body():
    body = ps.build_no_assignee_comment(trigger="ci.success", sha="abc123")
    assert "no assignee" in body.lower()
    assert "ci.success" in body
```

Also test GitHub API wrappers with httpx_mock:

```python
def test_github_post_pr_comment(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        match_json={"body": "hello"},
        json={"id": 1234},
    )
    ps.github_post_pr_comment(
        repo="ant013/Gimle-Palace",
        pr_number=77,
        body="hello",
        github_token="gh_token",
    )


def test_github_get_pr_comments(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[{"body": "c1"}, {"body": "c2"}],
    )
    comments = ps.github_get_pr_comments(
        repo="ant013/Gimle-Palace",
        pr_number=77,
        github_token="gh_token",
    )
    assert len(comments) == 2
    assert comments[0]["body"] == "c1"
```

- [ ] **Step 13.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k "build_.*_comment or github_"
```

- [ ] **Step 13.3: Add comment builders + GitHub helpers**

Append to `paperclip_signal.py`:

```python
GITHUB_API_BASE = "https://api.github.com"


def build_success_comment(trigger: str, sha: str, agent_name: str) -> str:
    return (
        f"<!-- paperclip-signal: {trigger} {sha} assignee={agent_name} -->\n"
        f"Woke {agent_name} on {trigger} at {sha}."
    )


def build_deferred_comment(trigger: str, sha: str, execution_run_id: str) -> str:
    return (
        f"<!-- paperclip-signal-deferred: {trigger} {sha} -->\n"
        f"Signal {trigger} received at {sha}, but agent session is actively running "
        f"(executionRunId={execution_run_id}); deferred. Next matching event will retry."
    )


def build_failed_comment(trigger: str, sha: str, error_message: str) -> str:
    return (
        f"<!-- paperclip-signal-failed: {trigger} {sha} -->\n"
        f"⚠ Failed to wake agent on {trigger} at {sha}: {error_message}. "
        f"Operator intervention may be needed."
    )


def build_no_assignee_comment(trigger: str, sha: str) -> str:
    return (
        f"<!-- paperclip-signal-no-assignee: {trigger} {sha} -->\n"
        f"⚠ Signal {trigger} received at {sha} but the linked paperclip issue "
        f"has no assignee. Operator must assign someone manually."
    )


def github_post_pr_comment(repo: str, pr_number: int, body: str, github_token: str) -> None:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    resp = httpx.post(
        url,
        json={"body": body},
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()


def github_get_pr_comments(repo: str, pr_number: int, github_token: str) -> list[dict]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    resp = httpx.get(
        url,
        params={"per_page": 100},
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise PaperclipError(f"Unexpected GitHub API response shape: {type(data).__name__}")
    return data
```

- [ ] **Step 13.4: Run tests — all pass**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k "build_.*_comment or github_"
```

- [ ] **Step 13.5: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): comment builders + GitHub API helpers (TDD)

Four marker types: signal (success), signal-deferred, signal-failed,
signal-no-assignee. Only success dedupes (see Task 12). GitHub helpers
are bare httpx calls — no retry (GitHub API rarely flakes at this
volume and the workflow will rerun if it does).
"
```

---

## Task 14: main() orchestration (TDD)

**Files:**
- Modify: `.github/scripts/paperclip_signal.py` — add main()
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 14.1: Write failing integration-style tests**

```python
import os


def _env(**kwargs) -> dict:
    """Build env-dict shape main() reads from os.environ."""
    base = {
        "PAPERCLIP_API_KEY": "k",
        "PAPERCLIP_BASE_URL": "https://paperclip.example.com",
        "GITHUB_TOKEN": "ght",
        "REPO": "ant013/Gimle-Palace",
        "CONFIG_PATH": str(Path(__file__).resolve().parent / "fixtures" / "real_config_current.yml"),
    }
    base.update(kwargs)
    return base


@pytest.fixture
def minimal_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: C1
rules:
  - trigger: ci.success
    target: issue_assignee
bot_authors:
  - github-actions[bot]
  - ant013
"""
    )
    return cfg


def test_main_happy_path_ci_success(httpx_mock: HTTPXMock, load_fixture, minimal_config: Path, monkeypatch):
    """workflow_run success → GET issue → release+patch → success comment → exit 0."""
    payload = load_fixture("workflow_run_success")
    # Sender ant013 is in bot_authors; this test uses a different payload without that
    payload = dict(payload)
    payload["sender"] = {"login": "operator", "type": "User"}

    # paperclip GET
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "issue-uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    # GitHub dedup GET — empty comments
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[],
    )
    # paperclip release + patch
    httpx_mock.add_response(
        method="POST",
        url="https://paperclip.example.com/api/issues/issue-uuid/release",
        json={"ok": True},
    )
    httpx_mock.add_response(
        method="PATCH",
        url="https://paperclip.example.com/api/issues/issue-uuid",
        json={"ok": True},
    )
    # Success marker comment post to PR
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 1},
    )

    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 0


def test_main_bot_sender_exits_early(load_fixture, minimal_config, httpx_mock: HTTPXMock):
    """sender=ant013 → exit 0, no API calls."""
    payload = load_fixture("workflow_run_success")   # sender=ant013 by default
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0
    assert httpx_mock.get_requests() == []


def test_main_branch_mismatch_warn_exit_0(load_fixture, minimal_config):
    """Branch not feature/GIM-N → exit 0 with log WARNING, no API calls."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    payload["workflow_run"]["head_branch"] = "random-branch"
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0


def test_main_dedup_hit_exits_0(httpx_mock: HTTPXMock, load_fixture, minimal_config):
    """Existing success marker → skip reassign, exit 0, no paperclip calls."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    # First: paperclip GET succeeds
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "issue-uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    # GitHub dedup: marker present
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[{"body": "<!-- paperclip-signal: ci.success abc123def456 assignee=MCPEngineer --> Woke."}],
    )
    rc = ps.main(
        event_name="workflow_run",
        event_payload=payload,
        config_path=minimal_config,
        paperclip_base_url="https://paperclip.example.com",
        paperclip_api_key="k",
        github_token="ght",
        repo="ant013/Gimle-Palace",
    )
    assert rc == 0


def test_main_deferred_posts_deferred_comment_exits_0(httpx_mock: HTTPXMock, load_fixture, minimal_config):
    """executionRunId persists non-null → post deferred comment, exit 0."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    # Two GETs both showing active run
    for _ in range(2):
        httpx_mock.add_response(
            method="GET",
            url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
            json=[{
                "id": "issue-uuid",
                "issueNumber": 62,
                "assigneeId": "agent-uuid",
                "assigneeName": "MCPEngineer",
                "executionRunId": "run-active",
            }],
        )
    # Dedup GET — empty
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[],
    )
    # Deferred comment POST
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 42},
    )
    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 0


def test_main_role_target_raises(load_fixture, tmp_path):
    """role(<Name>) target triggers NotImplementedError → exit 1."""
    cfg = tmp_path / "signals.yml"
    cfg.write_text(
        """
version: 1
company_id: C1
rules:
  - trigger: ci.success
    target: role(Translator)
bot_authors: []
"""
    )
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    with pytest.raises(NotImplementedError):
        ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=cfg,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )


def test_main_paperclip_down_posts_failed_exits_1(httpx_mock: HTTPXMock, load_fixture, minimal_config):
    """Paperclip 503 forever → signal-failed comment + exit 1."""
    payload = load_fixture("workflow_run_success")
    payload["sender"] = {"login": "operator", "type": "User"}
    httpx_mock.add_response(
        method="GET",
        url="https://paperclip.example.com/api/issues?issueNumber=62&companyId=C1",
        json=[{
            "id": "issue-uuid",
            "issueNumber": 62,
            "assigneeId": "agent-uuid",
            "assigneeName": "MCPEngineer",
            "executionRunId": None,
        }],
    )
    httpx_mock.add_response(
        method="GET",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments?per_page=100",
        json=[],
    )
    # Release 503 × 3 attempts
    for _ in range(3):
        httpx_mock.add_response(
            method="POST",
            url="https://paperclip.example.com/api/issues/issue-uuid/release",
            status_code=503,
            json={"error": "down"},
        )
    # Failed marker comment POST
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/ant013/Gimle-Palace/issues/77/comments",
        json={"id": 99},
    )
    with patch.object(ps, "_sleep", lambda s: None):
        rc = ps.main(
            event_name="workflow_run",
            event_payload=payload,
            config_path=minimal_config,
            paperclip_base_url="https://paperclip.example.com",
            paperclip_api_key="k",
            github_token="ght",
            repo="ant013/Gimle-Palace",
        )
    assert rc == 1
```

- [ ] **Step 14.2: Run tests — expect AttributeError**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k test_main
```

- [ ] **Step 14.3: Add main()**

Append to `paperclip_signal.py`:

```python
import logging


log = logging.getLogger("paperclip-signal")


def _resolve_target(rule: Rule, client: PaperclipClient, issue_number: int) -> ResolveResult:
    """Dispatch target to the correct resolver. Currently only issue_assignee is implemented."""
    if rule.target == "issue_assignee":
        return resolve_target_issue_assignee(client, issue_number)
    if ROLE_TARGET_RE.match(rule.target):
        raise NotImplementedError(
            f"Target {rule.target!r} is an extension-point placeholder; "
            f"implementation is scheduled for a followup slice."
        )
    raise ConfigError(f"Unknown target {rule.target!r}.")


def main(
    *,
    event_name: str,
    event_payload: dict,
    config_path: Path,
    paperclip_base_url: str,
    paperclip_api_key: str,
    github_token: str,
    repo: str,
) -> int:
    """Entry point. Returns process exit code."""
    config = load_config(config_path)
    event = parse_event(event_name, event_payload)
    if event is None:
        log.info("Event %s non-actionable; exiting 0.", event_name)
        return 0

    if is_bot_author(event.author, config.bot_authors):
        log.info("Event author %s is in bot_authors; exiting 0.", event.author)
        return 0

    matching_rules = [r for r in config.rules if r.trigger == event.trigger]
    if not matching_rules:
        log.info("No config rule matches trigger %s; exiting 0.", event.trigger)
        return 0

    issue_number = extract_issue_number(event.branch)
    if issue_number is None:
        log.warning("Branch %s does not match feature/GIM-N pattern; exiting 0.", event.branch)
        return 0

    client = PaperclipClient(
        base_url=paperclip_base_url,
        api_key=paperclip_api_key,
        company_id=config.company_id,
    )
    try:
        for rule in matching_rules:
            result = _resolve_target(rule, client, issue_number)

            if result.status == "no_assignee":
                body = build_no_assignee_comment(trigger=event.trigger, sha=event.sha)
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.warning("Issue %s has no assignee; posted warning.", result.issue.id)
                continue

            if result.status == "deferred":
                body = build_deferred_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    execution_run_id=result.issue.execution_run_id or "",
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.info("Signal deferred for issue %s (executionRunId=%s).",
                         result.issue.id, result.issue.execution_run_id)
                continue

            # result.status == "proceed"
            existing = github_get_pr_comments(repo, event.pr_number, github_token)
            if pr_has_signal_marker(existing, event.trigger, event.sha):
                log.info("Signal %s at %s already posted; dedup skip.", event.trigger, event.sha)
                continue

            try:
                release_and_reassign_with_retry(
                    client=client,
                    issue_id=result.issue.id,
                    assignee_id=result.issue.assignee_id or "",
                )
                body = build_success_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    agent_name=result.issue.assignee_name or "unknown",
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.info("Woke %s on %s at %s.", result.issue.assignee_name, event.trigger, event.sha)
            except PaperclipError as exc:
                body = build_failed_comment(
                    trigger=event.trigger,
                    sha=event.sha,
                    error_message=str(exc),
                )
                github_post_pr_comment(repo, event.pr_number, body, github_token)
                log.error("Paperclip signal failed: %s", exc)
                return 1
    finally:
        client.close()

    return 0


def _cli() -> int:
    """CLI entry used by the GitHub Action step."""
    import json as _json
    import os as _os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    event_name = _os.environ["EVENT_NAME"]
    event_payload = _json.loads(_os.environ["EVENT_JSON"])
    config_path = Path(_os.environ.get("CONFIG_PATH", ".github/paperclip-signals.yml"))
    return main(
        event_name=event_name,
        event_payload=event_payload,
        config_path=config_path,
        paperclip_base_url=_os.environ["PAPERCLIP_BASE_URL"],
        paperclip_api_key=_os.environ["PAPERCLIP_API_KEY"],
        github_token=_os.environ["GITHUB_TOKEN"],
        repo=_os.environ["REPO"],
    )


if __name__ == "__main__":
    raise SystemExit(_cli())
```

- [ ] **Step 14.4: Run main tests — all pass**

```bash
python -m pytest tests/test_paperclip_signal.py -v -k test_main
```

- [ ] **Step 14.5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass. Count should be ~35+ tests.

- [ ] **Step 14.6: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/paperclip_signal.py .github/scripts/tests/test_paperclip_signal.py
git commit -m "feat(signal): main() orchestration + CLI entry (TDD)

Wires config → event parse → bot filter → branch regex → target
resolve (with active-session pre-check) → dedup → reassign + comment.
Four terminal states: proceed+wake, dedup-skip, deferred, no_assignee,
failed. role(<Name>) target raises NotImplementedError.
_cli() reads env vars and dispatches main() — mirrors the Action step.
"
```

---

## Task 15: Invariant tests — real config + CI workflow name

**Files:**
- Modify: `.github/scripts/tests/test_paperclip_signal.py`

- [ ] **Step 15.1: Write failing tests for repo-level invariants**

Append to `test_paperclip_signal.py`:

```python
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_real_config_parses():
    """.github/paperclip-signals.yml must parse without error on every PR."""
    config_path = REPO_ROOT / ".github" / "paperclip-signals.yml"
    assert config_path.exists(), f"Live config missing at {config_path}"
    config = ps.load_config(config_path)
    assert config.version == 1
    assert config.company_id   # non-empty
    assert len(config.rules) >= 1


def test_ci_workflow_name_pinned():
    """The workflow file referenced by paperclip-signal must have name: CI."""
    ci_yaml = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_yaml.exists(), f"Missing {ci_yaml}"
    raw = yaml.safe_load(ci_yaml.read_text())
    assert raw.get("name") == "CI", (
        f"Expected top-level `name: CI` in .github/workflows/ci.yml for "
        f"workflow_run trigger matching; found {raw.get('name')!r}. "
        f"Update .github/workflows/paperclip-signal.yml workflows: key "
        f"if this name is changed intentionally."
    )
```

- [ ] **Step 15.2: Run — expect them to pass if the config + ci.yml both exist**

```bash
cd .github/scripts
source .venv/bin/activate
python -m pytest tests/ -v -k "real_config_parses or ci_workflow_name_pinned"
```

Expected: 2 passed (the config was created in Task 3; ci.yml already exists on develop).

- [ ] **Step 15.3: Commit**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add .github/scripts/tests/test_paperclip_signal.py
git commit -m "test(signal): invariant tests — live config + CI workflow name

Both tests run on every CI execution. If someone renames .github/workflows/ci.yml's
top-level 'name: CI' without updating paperclip-signal.yml's workflows: list,
test_ci_workflow_name_pinned catches it. test_real_config_parses blocks
malformed config pushes from landing on develop.
"
```

---

## Task 16: GitHub Action workflow file

**Files:**
- Create: `.github/workflows/paperclip-signal.yml`

- [ ] **Step 16.1: Create workflow file**

`.github/workflows/paperclip-signal.yml`:

```yaml
name: paperclip-signal

on:
  workflow_run:
    workflows: ["CI"]                # matches .github/workflows/ci.yml top-level `name: CI`
    types: [completed]
  pull_request_review:
    types: [submitted]
  pull_request_review_comment:
    types: [created]
  repository_dispatch:
    types: [qa-smoke-complete]

permissions:
  pull-requests: write     # dedup GET + POST marker/failed/deferred comments
  contents: read           # checkout only

concurrency:
  group: paperclip-signal-${{ github.event.pull_request.number || github.event.workflow_run.pull_requests[0].number || github.event.client_payload.pr_number || github.run_id }}
  cancel-in-progress: false

jobs:
  signal:
    runs-on: ubuntu-latest
    if: |
      github.event.sender.login != 'github-actions[bot]'
      && github.event.sender.type != 'Bot'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        working-directory: .github/scripts
        run: pip install -r requirements.txt
      - name: Dispatch signal
        working-directory: .github/scripts
        env:
          PAPERCLIP_API_KEY: ${{ secrets.PAPERCLIP_API_KEY }}
          PAPERCLIP_BASE_URL: https://paperclip.ant013.work
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          EVENT_NAME: ${{ github.event_name }}
          EVENT_JSON: ${{ toJSON(github.event) }}
          REPO: ${{ github.repository }}
          CONFIG_PATH: ${{ github.workspace }}/.github/paperclip-signals.yml
        run: python paperclip_signal.py
```

- [ ] **Step 16.2: Commit**

```bash
git add .github/workflows/paperclip-signal.yml
git commit -m "feat(signal): GitHub Action workflow for paperclip-signal dispatcher

Triggers: workflow_run (CI success), pull_request_review, 
pull_request_review_comment, repository_dispatch (qa-smoke-complete).
Explicit permissions (pull-requests:write); concurrency group per PR
to prevent TOCTOU on dedup; job-level if: filters Bot senders
pre-runner.
"
```

---

## Task 17: Add github_scripts tests to CI

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 17.1: Inspect current CI structure**

```bash
cat .github/workflows/ci.yml
```

Identify the existing jobs (`lint`, `typecheck`, `test`, `docker-build`) and the structure used for pipeline ordering / cache.

- [ ] **Step 17.2: Add new job `github-scripts-tests`**

Edit `.github/workflows/ci.yml`. Add a new job under `jobs:` (alphabetically, or at end — follow existing convention). Add:

```yaml
  github-scripts-tests:
    name: github-scripts-tests
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        working-directory: .github/scripts
        run: pip install -r requirements.txt
      - name: Run tests
        working-directory: .github/scripts
        run: python -m pytest tests/ -v
```

- [ ] **Step 17.3: Verify YAML still parses**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

Expected: no output (parses successfully).

- [ ] **Step 17.4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run github-scripts tests on every PR

Covers paperclip_signal.py unit + integration tests. New required
status check: github-scripts-tests. Branch protection update
(operator side) follows the merge of this PR.
"
```

Note: after merge, operator will need to add `github-scripts-tests` to the develop branch-protection required contexts. This is documented in Task 18 operator checklist.

---

## Task 18: Role files — add @include + remove `## CI pending` + rebuild dist

**Files:**
- Modify: `paperclips/roles/mcp-engineer.md`
- Modify: `paperclips/roles/python-engineer.md`
- Modify: `paperclips/roles/code-reviewer.md`
- Modify: `paperclips/dist/*.md` (rebuilt — 3+ files change)

- [ ] **Step 18.1: Remove `## Waiting for CI` section from mcp-engineer.md**

Open `paperclips/roles/mcp-engineer.md`. Find and delete lines 71-115 — the entire section starting with `## Waiting for CI — do not active-poll` through (but not including) the next `<!-- @include` line. The exact block to remove:

```markdown
## Waiting for CI — do not active-poll

After `git push origin feature/...` at Phase 2→3.1, Phase 3.1 re-push (after CR findings), or Phase 4.2 PR-merge attempt, CI triggers automatically. Choose one of two patterns:

### Pattern 1 (default, zero token cost during wait)

Post a CI-pending marker on the paperclip issue and end your run:

\`\`\`
## CI pending — awaiting Board re-wake

PR: <link>
Commit: <sha>
Expected green: lint, typecheck, test, docker-build, qa-evidence-present (5 checks).
Re-wake me (@MCPEngineer) when all checks green to continue Phase 4.2 merge.
\`\`\`

Board re-wakes via `release + reassign` when CI reports green. You resume from the merge step in a fresh run.

### Pattern 2 (bounded active poll — only if urgency justifies token burn)

For hotfixes or when Board is unavailable:

\`\`\`bash
gh pr checks <PR#> --watch      # blocks up to ~3 min on this repo
\`\`\`

If not complete within 3 min, fall back to poll:

\`\`\`bash
for i in $(seq 1 10); do
  sleep 60
  status=$(gh pr checks <PR#> --required | awk '{print $2}' | sort -u)
  if ! echo "$status" | grep -q pending; then break; fi
done
gh pr checks <PR#>
\`\`\`

Total budget 10 min. Beyond that, fall back to Pattern 1 with a pending marker.

### DO NOT

Post `Phase 4.2 in progress — waiting for CI` and terminate silently **without** a re-wake marker. That produces ghost runs — MCPEngineer's state machine pending forever, Board left guessing if you're working or stuck.

A full async-signal integration (paperclip CI webhook → automatic agent wake on green) is a followup slice.

```

Note: the above block includes 4 triple-backtick fenced blocks — in the real file, the backticks are literal; the above uses backslash-escapes to show them inside this plan. When editing, remove from `## Waiting for CI — do not active-poll` down to and including the line `A full async-signal integration (paperclip CI webhook → automatic agent wake on green) is a followup slice.` plus the blank line after.

- [ ] **Step 18.2: Add `@include` lines to mcp-engineer.md**

Still in `paperclips/roles/mcp-engineer.md`, find the existing block of `<!-- @include ... -->` lines (typically near the bottom of the file before the role-specific body ends). Add this line at the end of that block:

```markdown
<!-- @include fragments/shared/fragments/async-signal-wait.md -->
```

- [ ] **Step 18.3: Add `@include` to python-engineer.md**

Open `paperclips/roles/python-engineer.md`. Append at the end of the existing `@include` block:

```markdown
<!-- @include fragments/shared/fragments/async-signal-wait.md -->
```

- [ ] **Step 18.4: Add `@include` to code-reviewer.md**

Open `paperclips/roles/code-reviewer.md`. Append at the end of the existing `@include` block:

```markdown
<!-- @include fragments/shared/fragments/async-signal-wait.md -->
```

- [ ] **Step 18.5: Rebuild `paperclips/dist/*.md`**

```bash
cd /Users/ant013/Android/Gimle-Palace
./paperclips/build.sh
```

Expected: `paperclips/dist/mcp-engineer.md`, `paperclips/dist/python-engineer.md`, `paperclips/dist/code-reviewer.md` all updated.

- [ ] **Step 18.6: Verify async-signal-wait content is present in dist bundles**

```bash
grep -l "Waiting for signal" paperclips/dist/*.md
```

Expected output: the three bundle paths listed.

- [ ] **Step 18.7: Verify `## CI pending` is GONE from mcp-engineer dist bundle**

```bash
grep -c "CI pending" paperclips/dist/mcp-engineer.md
```

Expected: `0`.

- [ ] **Step 18.8: Commit**

```bash
git add paperclips/roles/mcp-engineer.md \
        paperclips/roles/python-engineer.md \
        paperclips/roles/code-reviewer.md \
        paperclips/dist/
git commit -m "feat(roles): wire async-signal-wait + retire '## CI pending' (MCPE)

MCPEngineer, PythonEngineer, CodeReviewer get the new shared fragment.
MCPEngineer's '## Waiting for CI' block (Pattern 1 marker + Pattern 2
active poll) is retired — the dispatcher Action replaces operator
re-wakes, and the unified '## Waiting for signal:' marker format works
across CI / PR review / future qa-smoke triggers. dist/*.md rebuilt.
"
```

---

## Task 19: Self-review + operator pre-merge checklist + open PR

- [ ] **Step 19.1: Run final full test suite**

```bash
cd .github/scripts
source .venv/bin/activate
python -m pytest tests/ -v
```

Expected: all tests pass. Approximate count:
- Config tests: 6
- Event parser tests: 7
- Branch regex tests: 4
- Bot filter tests: 2
- PaperclipClient tests: 3
- Retry tests: 4
- resolve_target tests: 4
- Dedup marker tests: 6
- Comment builder + GitHub helper tests: 6
- main() tests: 7
- Invariant tests: 2
- **Total: ~51 tests**

- [ ] **Step 19.2: Verify the whole slice on git log**

```bash
cd /Users/ant013/Android/Gimle-Palace
git log --oneline develop..HEAD
```

Expected: sequential commits from Task 2 (submodule bump) through Task 18 (role files + dist rebuild). Count should be ~17-18 commits.

- [ ] **Step 19.3: Operator pre-merge checklist**

Before opening the PR, operator (or engineer running through this plan) must ensure:

1. **`PAPERCLIP_API_KEY` secret is set** on the Gimle-Palace repo:
   ```bash
   gh secret set PAPERCLIP_API_KEY --repo ant013/Gimle-Palace
   # paste the paperclip token when prompted (same one used in curl experiments)
   ```
   Verify:
   ```bash
   gh secret list --repo ant013/Gimle-Palace | grep PAPERCLIP_API_KEY
   ```

2. **Branch protection requires `github-scripts-tests`** as a required status check on `develop`:
   ```bash
   # View current protection
   gh api repos/ant013/Gimle-Palace/branches/develop/protection --jq '.required_status_checks.contexts'
   # Operator adds 'github-scripts-tests' — update the JSON via existing
   # .github/branch-protection/develop.json and re-apply with the usual tooling.
   ```

3. **Submodule pointer matches the merged upstream SHA** (from Task 1.9):
   ```bash
   git diff develop..HEAD -- paperclips/fragments/shared
   ```
   Expected: pointer advances to UPSTREAM_SHA_FROM_TASK_1.

- [ ] **Step 19.4: Push the branch**

```bash
git push -u origin feature/GIM-62-async-signal
```

- [ ] **Step 19.5: Open the PR**

```bash
gh pr create \
  --title "feat: GIM-62 async-signal dispatcher (GitHub → paperclip wake)" \
  --body "$(cat <<'EOF'
## Summary
- New GitHub Action dispatcher that wakes paperclip issue-assignees on CI success + PR review events.
- Replaces manual "Board re-wakes agent after CI green" operator action.
- Declarative config at `.github/paperclip-signals.yml`; extensible to `role(<Name>)` target and `repository_dispatch qa-smoke-complete` without code change.
- Three agent roles (MCPE, PE, CR) get a new shared fragment `async-signal-wait.md`; MCPE's legacy `## CI pending` block retired.
- Spec: `docs/superpowers/specs/2026-04-20-async-signal-integration-design.md` (rev2).
- Plan: `docs/superpowers/plans/2026-04-20-GIM-62-async-signal.md`.

## Dependencies
- Upstream paperclip-shared-fragments PR (SHA in submodule bump commit): adds `fragments/async-signal-wait.md` + 3 template updates. Merged before this PR.
- Repo secret `PAPERCLIP_API_KEY` must be set before merge (operator action).
- Branch protection on `develop` must add `github-scripts-tests` as a required status check (operator action post-merge).

## QA Evidence
Will be added by QAEngineer in Phase 4.1 per CLAUDE.md workflow. Will include:
- SHA of the latest commit
- Self-test PR run showing Action triggered, reassign + marker comment visible
- Verification `## CI pending` block absent from MCPE bundle

## Test plan
- [x] `pytest .github/scripts/tests/` — ~51 tests, all pass locally
- [ ] CI `github-scripts-tests` job passes on this PR
- [ ] QA live-smoke on iMac post-deploy

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Output: PR URL. Report to user.

- [ ] **Step 19.6: Wait for CI + exit with `## Waiting for signal:` marker**

```bash
# On the issue, post the wait-marker (agent-side convention from the new fragment):
#
# ## Waiting for signal: ci.success on <head-sha>
#
# Then exit the session. The Action (once PAPERCLIP_API_KEY secret is set and the
# PR has been pushed) will wake the agent on CI green — live validating the feature
# on its own rollout PR.
```

---

## Self-Review

**Spec coverage** — walking through the rev2 spec sections:

| Spec section | Task |
|---|---|
| §4.1 Config file | Task 3 |
| §4.2 Workflow YAML (permissions + concurrency + triggers + bot-filter if) | Task 16 |
| §4.3 Python script — config parse | Task 5 |
| §4.3 parse_event (4 event types, fold pr.review_comment) | Task 6 |
| §4.3 Branch extraction + PR extraction | Tasks 6, 7 |
| §4.3 Active-session pre-check (executionRunId) | Task 11 |
| §4.3 Retry on 5xx + 409 | Task 10 |
| §4.3 Dedup marker via gh api | Task 12 |
| §4.3 main() control flow + two bot-filter layers | Tasks 8, 14 |
| §4.4 Fragment changes (new + 3 templates + 3 Gimle roles) | Tasks 1, 18 |
| §4.4 Retire `## CI pending` block | Task 18 |
| §4.5 Secrets (PAPERCLIP_API_KEY) | Task 19.3 |
| §6.1 Security model | Documented in spec; no code action required |
| §6.1 Signal-failed / signal-deferred / signal-no-assignee | Task 13 |
| §7.1 Unit tests incl. config, event, branch, bot filter, dedup | Tasks 5-12 |
| §7.1 Fixtures convention | Task 4 |
| §7.1 `test_real_config_parses` | Task 15 |
| §7.1 `test_ci_workflow_name_pinned` | Task 15 |
| §7.2 Integration tests (MockTransport, 5xx retry, 409 lock, 404, deferred, transient) | Tasks 10, 11, 14 |
| §8 Rollout order: upstream PR → submodule bump → config → script → workflow → role files → rebuild → operator checklist → merge | Tasks 1 → 2 → 3 → 4-15 → 16-17 → 18 → 19 |
| §9 Success criteria | Validated by Task 19.6 live PR |

**Placeholder scan:** no TODO/TBD/FIXME in plan. Each step has exact commands or exact code.

**Type consistency:**
- `Config.rules: list[Rule]` consistent across all uses.
- `PaperclipClient.get_issue_by_number` → `Issue` with `assignee_id`, `execution_run_id`, `assignee_name` — all used consistently in `resolve_target_issue_assignee`, `main`, and `build_success_comment`.
- `Event.trigger`, `.sha`, `.pr_number`, `.branch`, `.author` — consistent across parse_event subfunctions and main.
- `ResolveResult.status` ∈ {"proceed", "deferred", "no_assignee"} — consistent across tests, resolver, and main.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-GIM-62-async-signal.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

For this slice the expected engineer is MCPEngineer (implementer), then CodeReviewer (mechanical review Phase 3.1), then OpusArchitectReviewer (adversarial Phase 3.2), then QAEngineer (Phase 4.1). Running under paperclip phase workflow is the intended path — not subagent-driven implementation in this session.
