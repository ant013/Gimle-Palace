# GIM-62 — Async-signal integration design

**Date:** 2026-04-20
**Author:** Board (brainstorm with operator)
**Status:** REV2 — adversarial review incorporated (permissions/concurrency/debounce/security/race; LOC estimate + fixtures + validation tests).

**Rev2 change log:**
- §4.1 — removed `pr.review_comment` as separate rule (unified into `pr.review`).
- §4.2 — added explicit `permissions:` block and `concurrency:` block.
- §4.3 — added branch-extraction table per event type; revised LOC estimate (250–350 prod, 400–600 test); explicit 409 pre-check on active `executionRunId`.
- §6 — added §6.1 Security model and §6.2 Active-session race row.
- §7.1 — added webhook-fixtures convention and `test_real_config_parses` + `test_ci_workflow_name_pinned`.
- §10 — expanded migration note for `## CI pending` deprecation; bot-PAT followup clearly labeled.

**Predecessor SHAs this spec is grounded in:**
- `develop` tip: `7bdc302` (at brainstorm start; verify before implementation)
- `paperclips/fragments/shared` submodule tracked post-bump: `63744230bf986bd87c509564b969178d0472d4d7`
- `paperclips/fragments/shared` upstream main pre-bump: `b40da10` (PR #5 landed); post-bump: `6374423` (PR #6 async-signal-wait merged)

---

## 1. Goal

Replace manual "Board re-wakes agent after CI green" workflow with an
automated GitHub → paperclip signal pipeline. Agents exit their phase
with an explicit **wait-marker** and get auto-woken when the external
event they are waiting for fires.

Scope covers two agents (MCPEngineer, CodeReviewer) and three event
triggers (CI success, PR review submitted, PR review-comment created).
Architecture is designed to extend — a future Translator or post-deploy
QA-smoke flow plugs in via config, not code duplication.

## 2. Motivation

**Current manual flow (pain we're removing):**

1. MCPE finishes implementation, posts commit + PR URL, exits with `## CI pending` marker.
2. GitHub Actions run CI (~5-10 min). Agent is idle (paperclip `status=todo`).
3. Operator/Board *manually* sees green check on GitHub → *manually* reassigns MCPE in paperclip.
4. MCPE wakes, reads CI result, hands off to CR.

**Problems:**
- Human-in-the-loop on every slice — kills the autonomy premise.
- If operator is AFK for hours, slice stalls with zero diagnostic signal.
- CR-cycle has the same pattern (CR waits for engineer to push fix → re-review), doubling manual wake count per slice.
- No audit trail: what woke whom, when, for which SHA — all lives in operator's head.

**Non-goals:**
- Paperclip-native webhook subscriptions (upstream change, out of scope).
- Post-deploy iMac smoke automation (prerequisite doesn't exist; separate slice).
- Slack/email alerting for failures (over-engineering for first version).

## 3. High-level architecture

```
┌──────────────────────┐       ┌──────────────────────────────┐
│  GitHub PR / CI      │       │  .github/paperclip-signals   │
│  event               │       │  .yml (config)               │
│  (workflow_run,      │       │                              │
│   pr_review,         │       │  rules: trigger → target     │
│   pr_review_comment, │       │  bot_authors: [...]          │
│   repository_dispatch│       └──────────────┬───────────────┘
│   )                  │                      │
└──────────┬───────────┘                      │
           │                                  ▼
           │          ┌──────────────────────────────────────┐
           └─────────▶│  .github/workflows/paperclip-signal  │
                      │  .yml + paperclip_signal.py (~150LOC)│
                      │                                      │
                      │  1. parse_event → trigger            │
                      │  2. bot filter                       │
                      │  3. resolve target (issue_assignee   │
                      │     via branch-regex + paperclip GET)│
                      │  4. dedup check (PR markers scan)    │
                      │  5. reassign-refresh + retry         │
                      │  6. post success/failed marker       │
                      └──────────────┬───────────────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────────────┐
                      │  paperclip.ant013.work API           │
                      │  POST /api/issues/{id}/release       │
                      │  PATCH /api/issues/{id} assigneeId   │
                      │  POST /api/issues/{id}/comments      │
                      └──────────────┬───────────────────────┘
                                     │
                                     ▼
                      ┌──────────────────────────────────────┐
                      │  Agent wakes, reads fresh context    │
                      │  (fragment: async-signal-wait.md     │
                      │   drives discipline on resume)       │
                      └──────────────────────────────────────┘
```

### Data flow — typical MCPE cycle

```
MCPE push → exit comment ending with:
    ## Waiting for signal: ci.success on <sha>

CI runs → completes with success
  → GitHub `workflow_run` event (type=completed, conclusion=success)
  → paperclip-signal workflow triggered
  → paperclip_signal.py:
      parse_event       → trigger=ci.success, sha=<sha>, pr_number=N
      bot filter        → sender is not bot, continue
      branch regex      → feature/GIM-62-async-signal → issue_number=62
      paperclip GET     → assigneeId=<MCPE uuid>
      dedup check       → no <!-- paperclip-signal: ci.success <sha> --> in PR comments
      paperclip POST release + PATCH assigneeId → MCPE wakes
      paperclip POST comment "<!-- paperclip-signal: ci.success <sha> assignee=MCPEngineer --> Woke MCPEngineer on ci.success at <sha>."
  → MCPE (per async-signal-wait fragment):
      reads signal marker
      runs `gh pr view N --json statusCheckRollup,reviews,comments`
      executes phase handoff to CodeReviewer
```

## 4. Components

### 4.1 Config file — `.github/paperclip-signals.yml`

```yaml
version: 1

# Paperclip company UUID. Fallback default; override via repo secret PAPERCLIP_COMPANY_ID if needed.
company_id: 9d8f432c-ff7d-4e3a-bbe3-3cd355f73b64

rules:
  - trigger: ci.success
    target: issue_assignee

  # Unified trigger: fires on pull_request_review.submitted AND
  # pull_request_review_comment.created (both normalize to pr.review in parse_event).
  # Debouncing benefit: CR-cycle with 3 inline comments + final APPROVE → 1 wake
  # per sha, not 4. Split into distinct triggers in followup if divergent targets needed.
  - trigger: pr.review
    target: issue_assignee

  # Extension point — not wired to any iMac automation yet.
  - trigger: qa.smoke_complete
    target: issue_assignee
    note: "Waiting for iMac post-deploy smoke automation (followup slice)"

# Accounts whose events MUST NOT trigger wake (prevents self-wake loops).
bot_authors:
  - github-actions[bot]
  - ant013            # shared human/agent token
```

**Schema contract:**
- `version`: integer. Dispatcher rejects unknown versions with config-error fail.
- `company_id`: UUID string. Used in all paperclip API calls.
- `rules`: list of `{trigger, target, note?}`.
  - Valid `trigger` values: `ci.success`, `pr.review`, `qa.smoke_complete`. Unknown → config-error fail. Note: `pr.review_comment` is NOT a valid config trigger — the GitHub event `pull_request_review_comment` is normalized to `pr.review` in `parse_event` (debounce).
  - Valid `target` values: `issue_assignee` (implemented), `role(<Name>)` (stub — resolver raises NotImplementedError).
- `bot_authors`: list of strings. Checked against `github.event.sender.login` before any processing.

### 4.2 GitHub workflow — `.github/workflows/paperclip-signal.yml`

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

# Minimum scopes needed: PR comment read/write for dedup + marker posting.
# Explicit grant required because repo "Default workflow permissions" may be
# set to restricted (read-only), in which case POST comments silently 403.
permissions:
  pull-requests: write     # dedup GET + POST marker/failed/deferred comments
  contents: read           # checkout only

# Serialize runs per PR to avoid TOCTOU on dedup marker check.
# Without this: 3 near-simultaneous pr.review_comment events → 3 parallel
# workflow runs → all 3 see "no marker" → all 3 reassign → triple-wake.
# `cancel-in-progress: false` because each run is short (~10-20s) and must
# complete its marker POST; cancelling mid-flight would leave dedup state inconsistent.
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
      - run: pip install pyyaml httpx
      - name: Dispatch signal
        env:
          PAPERCLIP_API_KEY: ${{ secrets.PAPERCLIP_API_KEY }}
          PAPERCLIP_BASE_URL: https://paperclip.ant013.work
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          EVENT_NAME: ${{ github.event_name }}
          EVENT_JSON: ${{ toJSON(github.event) }}
          REPO: ${{ github.repository }}
        run: python .github/scripts/paperclip_signal.py
```

**Design notes:**
- Single workflow handles all trigger types — simpler than multiple workflows, shares retry/dedup logic.
- `workflows: ["ci"]` points at the CI job that already enforces `lint/typecheck/test/docker-build/check` contexts for branch protection.
- Bot filter at job level `if:` so bot events don't even spawn a runner (saves minutes, rules out self-wake at the earliest point).

### 4.3 Python script — `.github/scripts/paperclip_signal.py`

**Structure (~250–350 prod LOC + ~400–600 test LOC):**

Revised estimate after adversarial review. Honest breakdown:
- config parse + schema validation: ~40 LOC
- 4 event shapes × parse_event branches: ~60 LOC
- httpx client + retry + 409 pre-check handling: ~70 LOC
- dedup via `gh api repos/.../issues/{n}/comments`: ~40 LOC
- branch-regex + paperclip issue resolve: ~30 LOC
- two bot-filter layers, error taxonomy, logging: ~40 LOC
- `main()` control flow + exit codes: ~20 LOC


```
# Module-level
CONFIG_PATH = ".github/paperclip-signals.yml"
TRIGGERS = {"ci.success", "pr.review", "qa.smoke_complete"}  # pr.review_comment folded → pr.review in parse_event
BRANCH_RE = re.compile(r"^feature/GIM-(\d+)-")

# Functions
load_config(path)                      -> Config
parse_event(event_name, event_json)    -> Event | None   # None if non-actionable (e.g. CI=failure)
resolve_target(rule, event, config)    -> Target | None  # None if branch doesn't match etc.
pr_has_signal_marker(pr_n, trigger, sha, event_payload) -> bool
paperclip_release_and_reassign(target, api_key, base_url) -> None   # retries internally
post_signal_comment(pr_n, trigger, sha, agent_name)       -> None
post_failed_comment(pr_n, trigger, sha, error_message)    -> None
main()                                 -> int (exit code)
```

**`main()` control flow:**

```
config = load_config(CONFIG_PATH)
event  = parse_event(EVENT_NAME, EVENT_JSON)
if event is None:
    return 0                           # non-actionable (CI failure, etc.)
if event.author in config.bot_authors:
    return 0                           # Python-level bot filter (covers 'ant013')
matching_rules = [r for r in config.rules if r.trigger == event.trigger]
for rule in matching_rules:
    target = resolve_target(rule, event, config)
    if target is None:
        continue                       # branch mismatch, null assignee, etc.
    if pr_has_signal_marker(event.pr_number, event.trigger, event.sha):
        continue                       # dedup
    try:
        paperclip_release_and_reassign(target, ...)
        post_signal_comment(event.pr_number, event.trigger, event.sha, target.agent_name)
    except PaperclipError as e:
        post_failed_comment(event.pr_number, event.trigger, event.sha, str(e))
        return 1
return 0
```

**Two layers of bot filter — deliberate:**
- Workflow-level `if:` (Section 4.2): blocks GitHub platform bots (`github-actions[bot]`) before any runner spin-up. Cheap.
- Python-level check against `config.bot_authors`: blocks shared-token authors like `ant013` where `sender.type` is `User`, not `Bot`. Covers self-wake loops via agents committing under the shared account.

**Event normalization (`parse_event`):**

| GitHub event | Condition | Normalized trigger |
|---|---|---|
| `workflow_run` | `conclusion=success` | `ci.success` |
| `workflow_run` | `conclusion=failure` / other | `None` (skip — red CI not in scope) |
| `pull_request_review` | `action=submitted`, `state=approved/commented/changes_requested` | `pr.review` |
| `pull_request_review_comment` | `action=created` | `pr.review` (folded — debounce) |
| `repository_dispatch` | `event_type=qa-smoke-complete` | `qa.smoke_complete` |

**Branch extraction per event type (used by `resolve_target` for `issue_assignee`):**

| Event | Branch field path |
|---|---|
| `workflow_run` | `event.workflow_run.head_branch` |
| `pull_request_review` | `event.pull_request.head.ref` |
| `pull_request_review_comment` | `event.pull_request.head.ref` |
| `repository_dispatch` | `event.client_payload.branch` (required field; dispatcher fails with config-error if missing in payload) |

**PR number extraction (used for dedup GET + marker posting):**

| Event | PR number field path |
|---|---|
| `workflow_run` | `event.workflow_run.pull_requests[0].number` (if PR-triggered CI) |
| `pull_request_review` | `event.pull_request.number` |
| `pull_request_review_comment` | `event.pull_request.number` |
| `repository_dispatch` | `event.client_payload.pr_number` (required) |

**409 / active-session pre-check (addresses GIM-52/53 stale-lock race):**

Before `POST /release + PATCH assigneeId`, the script fetches the target issue and inspects `executionRunId`:

- If `executionRunId` is `null` → proceed normally (reassign + comment).
- If `executionRunId` is `non-null` → agent session is actively running OR has a stale lock. We do NOT retry-spam here. Instead:
  1. Sleep 30s, re-check `executionRunId`.
  2. If still non-null → post `<!-- paperclip-signal-deferred: {trigger} {sha} --> Signal received while agent session active (executionRunId=<id>); deferred. Next matching event will retry.` Exit 0 (not a failure).
  3. Operator sees the deferred comment; can intervene or simply wait for next CI rerun / review comment.

This is simpler than "detect stale vs. live lock" heuristics and avoids pounding the paperclip API. Documented trade-off: an isolated CI-green signal during a long-running agent session may be silently dropped if no follow-up event fires. Acceptable because:
- Agent sessions rarely outlast CI (push takes seconds; session exits; CI finishes minutes later).
- The `## Waiting for signal:` marker on the agent side is the secondary observability channel — operator sees marker + no `signal:` PR comment → knows infra didn't fire, manually wakes.

**Retry logic (inside `paperclip_release_and_reassign`):**
- Attempts at `t=0`, `t=10s`, `t=30s`.
- Retry on: HTTP 5xx, connection timeout, HTTP 409 (execution_lock_stale).
- Do NOT retry on: HTTP 4xx (except 409), parse errors.
- After 3 failed attempts → raise `PaperclipError` — caught by `main()`, which posts `signal-failed` comment and `sys.exit(1)`.

**Dedup marker check (`pr_has_signal_marker`):**
- GET PR comments via `gh api repos/{REPO}/issues/{pr_n}/comments` (authenticated with `GITHUB_TOKEN`).
- Regex: `<!-- paperclip-signal: {re.escape(trigger)} {re.escape(sha)} `
- If match found → return True (skip wake).

### 4.4 Fragment changes

#### 4.4.1 New shared fragment — `paperclip-shared-fragments/fragments/async-signal-wait.md`

Target size: ~25-30 lines. Project-agnostic discipline usable by any paperclip project.

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
4. If you see `<!-- paperclip-signal-failed: ... -->` — signal infra failed;
   escalate to operator, do NOT retry silently.

**Anti-pattern:** exiting with vague "waiting for CI" without the marker.
Signal infra cannot target you reliably, operator has no diagnostic.
```

**Upstream PR in paperclip-shared-fragments repo**:
- Adds `fragments/async-signal-wait.md`
- Updates `templates/engineers/python-engineer.md`, `templates/quality/code-reviewer.md` with `@include` of the new fragment (NOTE: no `templates/engineers/mcp-engineer.md` exists upstream — the Gimle-local `paperclips/roles/mcp-engineer.md` is handled in §4.4.2)
- **Does NOT** update templates/qa-engineer.md — explicitly excluded (see Section 5.2).
- **Does NOT** update templates/infra-engineer.md — no async-wait case identified.

#### 4.4.2 Gimle role-file changes

Submodule bump lands after upstream PR merges. Then:

- `paperclips/roles/MCPEngineer.md`:
  - ADD `@include paperclips/fragments/shared/fragments/async-signal-wait.md`
  - REMOVE existing `## CI pending` block (superseded by the universal marker). Semantic migration: the old `## CI pending` comment pattern (introduced in GIM-57) is replaced by `## Waiting for signal: ci.success on <sha>`.
- `paperclips/roles/CodeReviewer.md`:
  - ADD `@include ...async-signal-wait.md`.
  - NEW use-case documented: "when waiting for engineer push-fix after review-change-request, exit with `## Waiting for signal: pr.review` — you will be woken via signal."
- `paperclips/roles/PythonEngineer.md`:
  - ADD `@include ...async-signal-wait.md`. (Rare use-case but possible: PE may push a fix and wait for CI before handoff.)

#### 4.4.3 Gimle-local supplement — NONE required in GIM-62

No Gimle-specific discipline identified. Shared fragment is fully generic.

### 4.5 Secrets + auth

**New GitHub repo secret (operator action):**
- `PAPERCLIP_API_KEY` — paperclip bearer token, same one currently used in local CLI/curl experiments. Scope: `write:issues, write:comments`.

**Existing secrets used:**
- `GITHUB_TOKEN` (auto-provided to Actions) — for reading PR comments (dedup check) and posting marker comments.

No new secrets for GitHub App or webhook — we stay inside Actions permissions model.

## 5. Scope boundaries

### 5.1 In scope

- Config file `.github/paperclip-signals.yml` with 4 rules (3 active, 1 stub).
- Workflow file `.github/workflows/paperclip-signal.yml`.
- Python script `.github/scripts/paperclip_signal.py` + unit/integration tests under `tests/github_scripts/`.
- New shared fragment `async-signal-wait.md` (upstream PR in paperclip-shared-fragments).
- Template updates in shared submodule (mcp-engineer, python-engineer, code-reviewer).
- Gimle role-file updates (`paperclips/roles/{MCPEngineer,PythonEngineer,CodeReviewer}.md`) and submodule SHA bump.
- Repo secret `PAPERCLIP_API_KEY` — operator setup, documented in PR body.
- `repository_dispatch:qa-smoke-complete` trigger declared in workflow + config rule (stub, no iMac script yet).

### 5.2 Out of scope (deferred to followups)

- **QA-engineer fragment inclusion** — no iMac automation to signal from, fragment would be dead code.
- **iMac post-deploy smoke script** — separate slice. When it lands, it `curl`s `POST /repos/.../dispatches` with `event_type=qa-smoke-complete`; dispatcher is already wired.
- **`role(<Name>)` target implementation** — Translator use-case. Config syntax documented, resolver stub raises `NotImplementedError`.
- **Paperclip-native webhook subscriptions** — upstream feature.
- **Metrics dashboard** — Action run history + PR comment markers are sufficient audit trail for first weeks.
- **Slack/email alerting on signal-failed** — the `signal-failed` PR comment is visible enough for operator mono-watching PRs.
- **CI-red triggering wake** — intentionally excluded per brainstorm; engineer is typically still active when they just pushed, red-CI noise outweighs value. Revisit if operator observes stalls after N incidents.

### 5.3 Non-goals

- Replacing paperclip's own assignee mechanism. Signal is a *wake* trigger, not a *reassign* trigger. Phase transitions still happen via explicit `gh` commands by agents.
- Making the Action the sole source of truth. `## Waiting for signal:` marker on the agent side is a redundant, human-readable signal; operator can diagnose signal-infra failure by comparing agent marker vs PR signal-marker.

## 6. Failure modes + observability

| Situation | Detection | Response |
|---|---|---|
| Paperclip API 5xx | httpx exception | Retry 2x (10s, 30s). Final fail → `signal-failed` comment, Action exits 1. |
| Paperclip 409 on release/patch | HTTP status | Retry 1x within main retry loop. If still 409 after retry, treat as active-session race (see row below). |
| **Active agent session on target issue** | GET issue returns `executionRunId != null` | Sleep 30s, recheck. If still non-null → post `signal-deferred` comment, exit 0. Do NOT retry-spam. Next event retries. |
| Branch name does not match `feature/GIM-N-...` | Regex miss | Log WARNING, Action exits 0. Not a failure — could be human PR. |
| `assigneeId` null on issue | API response field | WARNING + `⚠ Issue has no assignee` PR comment, exit 0. |
| Config parse error (bad YAML, unknown trigger, etc.) | PyYAML / validation exception | Action FAIL (exit 1). Repo-level bug, must block future PRs until fixed. |
| `role(<Name>)` target in config | NotImplementedError from resolver | Action FAIL with clear message. Explicitly tested. |
| Marker-comment already present for (trigger, sha) | Dedup check | Log INFO "already signaled", exit 0. |
| Concurrent workflow runs for same PR | GitHub `concurrency:` group | Second run queues behind first; no parallel execution. |
| Bot-sender event | `sender.type==Bot` or `sender.login in bot_authors` | Workflow `if:` (for platform bots) OR Python filter (for `ant013`) skips — no paperclip API calls, no marker writes. |

### 6.1 Security model — PAPERCLIP_API_KEY exposure surface

**Threat:** a contributor modifies `.github/workflows/paperclip-signal.yml` or `.github/scripts/paperclip_signal.py` in a PR to exfiltrate `secrets.PAPERCLIP_API_KEY`.

**GitHub event semantics (verify during implementation):**
- `workflow_run` — triggered by the `ci` workflow completing. The **workflow file that runs** is the one from the **default branch** (not the PR head). Safe against PR modifications.
- `pull_request_review`, `pull_request_review_comment` — for **same-repo PRs** (our case: all Gimle agents commit to the same repo), the workflow file is read from the **PR head branch**. An attacker with push access could modify the Action in their PR and exfiltrate the secret on the next review comment.
- `repository_dispatch` — triggered by API call; workflow from default branch.

**Ground reality for Gimle-Palace:**
- Private repo, 2 trusted committers (operator + agents under shared token).
- All agents run with the operator's trust level (no isolation between agent accounts).
- The `PAPERCLIP_API_KEY` is the same token agents already possess (identical blast radius to current state).

**Mitigations in scope:**
1. **Documented trust boundary** — this spec is the explicit record that the security model assumes trusted committer set.
2. **Bot-filter at workflow level** — `github.event.sender.type != 'Bot'` at job `if:` prevents any Bot-authored event from triggering the Action (pre-runner).

**Followup mitigations (out of scope, documented in §10):**
- Separate `PAPERCLIP_BOT_PAT` (limited scope: only `POST /release`, `PATCH assignee` on specific agents) rather than reusing operator's full-scope token.
- Move the script to `.github/actions/paperclip-signal/` as a composite action pinned to a SHA; consuming workflows reference `uses: ./.github/actions/paperclip-signal@{sha}` so modification requires a merged commit to default branch.

**Not suitable for:** public repos, repos with untrusted contributors, repos where review events can be fired by external contributors against forks.

**Observability layers (no extra infra):**

1. **GitHub Actions run history** — every signal attempt = one job run, full log + event payload available at `https://github.com/ant013/Gimle-Palace/actions/workflows/paperclip-signal.yml`.
2. **PR marker-comments** — `<!-- paperclip-signal: ... -->` for success, `<!-- paperclip-signal-failed: ... -->` for failure. `grep` on any PR yields full signal history.
3. **Agent-side wait-marker** — `## Waiting for signal: ci.success on <sha>` on issue/PR. Combined with PR signal-comments, drift is immediately diagnosable: marker exists + no signal-comment = infra broken; signal-comment exists + agent still idle = paperclip wake failed.
4. **Paperclip `issue.history`** — reassign-refresh writes audit entry with `actorType=api`. Correlates "Action fired" with "agent reassigned".

## 7. Testing plan

### 7.1 Unit tests — `tests/github_scripts/test_paperclip_signal.py`

**Fixtures convention (required by test-design-discipline):**

All `parse_event` tests MUST load real GitHub webhook payloads saved to `tests/github_scripts/fixtures/`. These are captured from actual Action runs, not hand-written mental models.

```
tests/github_scripts/fixtures/
  workflow_run_success.json      # from a real green-CI run (sanitized)
  workflow_run_failure.json      # red-CI for negative test
  pull_request_review_approved.json
  pull_request_review_comment_created.json
  repository_dispatch_qa_smoke.json
  sender_is_bot_github_actions.json
  sender_is_human_ant013.json
  real_config_current.yml        # snapshot of .github/paperclip-signals.yml at time of test
```

Operator captures initial fixtures during first post-merge smoke run and commits them in a followup PR if missing. Tests written against synthetic JSON until then, flagged with `pytest.mark.fixture_pending` — these must be replaced with real captures before the slice is considered closed.

| Test | Verifies |
|---|---|
| `test_config_parse_valid` | Valid YAML → Config object with expected rules |
| `test_config_parse_unknown_trigger` | Unknown trigger → raises ConfigError |
| `test_config_parse_unknown_target` | `target: foo` (not `issue_assignee` or `role(X)`) → ConfigError |
| `test_config_parse_role_target_parses_but_not_callable` | `target: role(X)` parses ok, but resolver raises NotImplementedError |
| `test_config_parse_pr_review_comment_rejected` | `trigger: pr.review_comment` in config → ConfigError (only normalized-side key allowed) |
| `test_real_config_parses` | Loads the live `.github/paperclip-signals.yml` from repo root, must parse without error. Runs on every PR; breaks if someone introduces an invalid rule. |
| `test_parse_event_ci_success` | `workflow_run` fixture + `conclusion=success` → trigger=ci.success |
| `test_parse_event_ci_failure_returns_none` | `workflow_run` fixture + `conclusion=failure` → None |
| `test_parse_event_pr_review_approved` | `pull_request_review` fixture submitted approved → trigger=pr.review |
| `test_parse_event_pr_review_comment_normalizes_to_pr_review` | `pull_request_review_comment` fixture → trigger=pr.review (folded, not separate) |
| `test_parse_event_repository_dispatch_qa` | dispatch fixture `qa-smoke-complete` → trigger=qa.smoke_complete |
| `test_parse_event_repository_dispatch_missing_branch` | dispatch missing `client_payload.branch` → ConfigError with clear message |
| `test_branch_extraction_per_event_type` | Each event fixture yields correct branch via `extract_branch()` table |
| `test_branch_regex_feature_slash` | `feature/GIM-62-async-signal` → 62 |
| `test_branch_regex_no_match` | `fix/typo` → None (log WARNING, no raise) |
| `test_bot_filter_github_actions` | sender fixture=`github-actions[bot]` → early exit |
| `test_bot_filter_ant013_listed` | sender fixture=`ant013` → early exit |
| `test_dedup_marker_present` | mock comments contain matching marker → returns True (skip) |
| `test_dedup_marker_absent` | mock comments empty → returns False (proceed) |
| `test_ci_workflow_name_pinned` | Reads `.github/workflows/ci.yml` on disk, asserts top-level `name: CI`. Breaks loudly if someone renames the CI workflow. |

### 7.2 Integration tests (httpx MockTransport)

| Test | Verifies |
|---|---|
| `test_reassign_refresh_success_null_execution_run` | GET issue returns `executionRunId=null` → POST release → PATCH assignee → POST signal marker comment. All 4 HTTP calls asserted with correct payloads. |
| `test_reassign_refresh_5xx_retry` | 503, 503, 200 on release → succeeds. Confirms 3 attempts, delays 10s/30s honored (use freezegun for time). |
| `test_reassign_refresh_all_5xx_fail` | 503 forever on release → raises PaperclipError → `main()` posts signal-failed comment → exit 1. |
| `test_issue_not_found_404` | GET issue 404 → signal-failed comment, exit 1. |
| `test_409_active_execution_run_deferred` | GET issue returns `executionRunId="run-abc"` → after 30s recheck still non-null → posts `signal-deferred` comment, exits 0. No release/patch calls made. |
| `test_409_transient_execution_run_clears` | First GET shows `executionRunId="run-abc"`, post-sleep GET shows `null` → proceeds with normal release+patch+marker. |
| `test_409_on_release_after_null_precheck` | GET `executionRunId=null` → POST release returns 409 → 1 retry → success. (Covers true "stale lock" case distinct from active run.) |
| `test_concurrency_group_serializes` | Documented expectation only — concurrency is workflow-level, cannot unit-test. Live-validation plan exercises it. |

**Test-design-discipline compliance (GIM-61 fragment):**
- We use `httpx.MockTransport` (fake network, real httpx) — aligns with the rule. No whole-client `MagicMock`.
- No paperclip-live calls in CI tests; live validation happens on the first PR after merge.

### 7.3 Live validation smoke plan

Executed by operator/Board after merge:

1. **Self-test PR**: open throwaway PR off develop, push a trivial commit, wait CI green → observe Action run → verify paperclip issue reassigned, PR marker comment present.
2. **First real slice**: next engineer slice (GIM-63+) runs end-to-end through the new flow — document result in the slice's QA comment.
3. **Rollback trigger**: if Action misbehaves (spam reassigns, fails silently), disable via `gh workflow disable paperclip-signal.yml`. No code revert needed — config is declarative.

## 8. Rollout order

1. **Upstream PR in paperclip-shared-fragments** — add `fragments/async-signal-wait.md` + update 3 templates. Merge → note new SHA.
2. **Gimle branch `feature/GIM-62-async-signal`** — this branch:
   - Adds `.github/paperclip-signals.yml`
   - Adds `.github/workflows/paperclip-signal.yml`
   - Adds `.github/scripts/paperclip_signal.py` + tests
   - Bumps `paperclips/fragments/shared` submodule SHA (absorbs PR #5 + new fragment commit)
   - Updates `paperclips/roles/{MCPEngineer,PythonEngineer,CodeReviewer}.md` (@include + remove old CI-pending)
   - Rebuilds `paperclips/dist/*.md` via `./paperclips/build.sh`
3. **Operator secret setup** — add `PAPERCLIP_API_KEY` repo secret *before* merging.
4. **Merge to develop** — standard CI + QA + merge gate per CLAUDE.md workflow.
5. **Post-merge iMac deploy** — `./paperclips/deploy-agents.sh --local` on iMac to propagate updated role bundles to 11 agents.
6. **First-slice observation** — next engineer slice validates the flow in production.

## 9. Success criteria

This slice is successful when:
- A new engineer PR that exits with `## Waiting for signal: ci.success on <sha>` is auto-woken on CI green without manual operator action.
- CR's push-fix cycle is auto-woken via `pr.review` (both formal review submissions and inline review comments fold into this single trigger).
- A `signal-failed` comment appears on the PR when paperclip is unavailable, with enough info for operator to diagnose.
- Unit + integration tests pass in CI.
- Zero changes to `develop`/`main` branch-protection rules required (signal Action runs independently of required-checks).

## 10. Open questions / explicit trade-offs

- **`## CI pending` migration** — two-phase deprecation:
  - **Phase A (this slice, GIM-62):** ship new `async-signal-wait.md` fragment + infra + remove old `## CI pending` block from MCPEngineer role. Agents invoked after `deploy-agents.sh --local` use the new marker immediately.
  - **Phase B (first week after deploy):** any in-flight agent suspended with old `## CI pending` marker before deploy won't be auto-woken. Operator manually reassigns if they're still idle after the slice they belonged to merges. Bounded pain: at most N agents × M active slices at moment of deploy (observed max: 3 agents at any time).
  - **Not chosen: long backwards-compatible overlap.** Keeping both markers in dist/*.md during transition confuses agents (which one do I write?) and creates silent-bug surface (Action might regex-match old format and reassign to wrong target). A clean cut is safer given small fleet.
- **Shared-token bot-filter (`ant013` in `bot_authors`)** — operator pushing as `ant013` won't wake themselves. Acceptable because:
  - Operator PRs (meta/infra) are generally not on `feature/GIM-N-` branches → branch regex fails first anyway.
  - When operator does act on a GIM-N branch, they're actively monitoring.
  - **Followup slice (GIM-6X):** provision a separate `PAPERCLIP_BOT_PAT` for the Action, remove `ant013` from `bot_authors`. Gives agent-events proper wake while keeping operator visible. Blocked on paperclip side — operator needs to generate a scoped bot token.
- **No retry on CI failure** — intentional. Red CI is a signal the engineer-in-session will act on; if they're already idle, they can refresh manually or the next push will trigger the loop again on the following green.
- **Deferred signals may be silently dropped** — if CI goes green while agent is actively running (executionRunId non-null), Action posts `signal-deferred` and exits. If no subsequent CI rerun or review comment happens, the signal is lost. Operator observes via `## Waiting for signal:` marker on issue + absence of `<!-- paperclip-signal: -->` PR comment. Acceptable because: (a) agent session outlasting CI is rare, (b) agent can check CI status on their own when session ends, (c) manual operator wake is always available as fallback.
- **Webhook fixtures captured post-first-event** — unit tests flagged `@pytest.mark.fixture_pending` until first Action run produces real payloads. Followup PR replaces synthetic JSON with captured real-world payloads.
- **No threat isolation between agents** — all agents share `ant013` token; signal Action uses the same token for paperclip calls. Same blast radius as current state. Token-per-agent is a platform-level change (paperclip + deploy scripts), out of scope.

---

**Predecessor context cited:** GIM-57 introduced the `## CI pending` marker pattern, GIM-61 introduced the test-design-discipline fragment structure that this slice's tests must conform to, stale-execution-lock reference memory documents the release+reassign workaround that this Action uses as its wake primitive.
