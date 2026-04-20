# GIM-62 — Async-signal integration design

**Date:** 2026-04-20
**Author:** Board (brainstorm with operator)
**Status:** DRAFT — pending operator review

**Predecessor SHAs this spec is grounded in:**
- `develop` tip: `7bdc302` (at brainstorm start; verify before implementation)
- `paperclips/fragments/shared` submodule tracked: `8bae8b7` (Gimle develop)
- `paperclips/fragments/shared` upstream main: `b40da10` (PR #5 landed, Gimle pointer not yet bumped — expected to be absorbed into this slice's final submodule bump)

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

  - trigger: pr.review
    target: issue_assignee

  - trigger: pr.review_comment
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
  - Valid `trigger` values: `ci.success`, `pr.review`, `pr.review_comment`, `qa.smoke_complete`. Unknown → config-error fail.
  - Valid `target` values: `issue_assignee` (implemented), `role(<Name>)` (stub — resolver raises NotImplementedError).
- `bot_authors`: list of strings. Checked against `github.event.sender.login` before any processing.

### 4.2 GitHub workflow — `.github/workflows/paperclip-signal.yml`

```yaml
name: paperclip-signal

on:
  workflow_run:
    workflows: ["ci"]
    types: [completed]
  pull_request_review:
    types: [submitted]
  pull_request_review_comment:
    types: [created]
  repository_dispatch:
    types: [qa-smoke-complete]

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

**Structure (~150 LOC, targeted < 200):**

```
# Module-level
CONFIG_PATH = ".github/paperclip-signals.yml"
TRIGGERS = {"ci.success", "pr.review", "pr.review_comment", "qa.smoke_complete"}
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
| `pull_request_review_comment` | `action=created` | `pr.review_comment` |
| `repository_dispatch` | `event_type=qa-smoke-complete` | `qa.smoke_complete` |

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

Valid events: `ci.success`, `pr.review`, `pr.review_comment`, `qa.smoke_complete`.

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
- Updates `templates/engineers/mcp-engineer.md`, `templates/engineers/python-engineer.md`, `templates/quality/code-reviewer.md` with `@include` of the new fragment
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
| Paperclip 409 (execution lock stale) | HTTP status | Retry 1x within main retry loop. |
| Branch name does not match `feature/GIM-N-...` | Regex miss | Log WARNING, Action exits 0. Not a failure — could be human PR. |
| `assigneeId` null on issue | API response field | WARNING + `⚠ Issue has no assignee` PR comment, exit 0. |
| Config parse error (bad YAML, unknown trigger, etc.) | PyYAML / validation exception | Action FAIL (exit 1). Repo-level bug, must block future PRs until fixed. |
| `role(<Name>)` target in config | NotImplementedError from resolver | Action FAIL with clear message. Explicitly tested. |
| Marker-comment already present for (trigger, sha) | Dedup check | Log INFO "already signaled", exit 0. |
| Bot-sender event | `sender.type==Bot` or `sender.login in bot_authors` | Workflow `if:` skips job entirely — no API calls, no marker writes. |

**Observability layers (no extra infra):**

1. **GitHub Actions run history** — every signal attempt = one job run, full log + event payload available at `https://github.com/ant013/Gimle-Palace/actions/workflows/paperclip-signal.yml`.
2. **PR marker-comments** — `<!-- paperclip-signal: ... -->` for success, `<!-- paperclip-signal-failed: ... -->` for failure. `grep` on any PR yields full signal history.
3. **Agent-side wait-marker** — `## Waiting for signal: ci.success on <sha>` on issue/PR. Combined with PR signal-comments, drift is immediately diagnosable: marker exists + no signal-comment = infra broken; signal-comment exists + agent still idle = paperclip wake failed.
4. **Paperclip `issue.history`** — reassign-refresh writes audit entry with `actorType=api`. Correlates "Action fired" with "agent reassigned".

## 7. Testing plan

### 7.1 Unit tests — `tests/github_scripts/test_paperclip_signal.py`

| Test | Verifies |
|---|---|
| `test_config_parse_valid` | Valid YAML → Config object with expected rules |
| `test_config_parse_unknown_trigger` | Unknown trigger → raises ConfigError |
| `test_config_parse_unknown_target` | `target: foo` (not `issue_assignee` or `role(X)`) → ConfigError |
| `test_config_parse_role_target_parses_but_not_callable` | `target: role(X)` parses ok, but resolver raises NotImplementedError |
| `test_parse_event_ci_success` | `workflow_run` + `conclusion=success` → trigger=ci.success |
| `test_parse_event_ci_failure_returns_none` | `workflow_run` + `conclusion=failure` → None (not in scope) |
| `test_parse_event_pr_review_approved` | `pull_request_review` submitted approved → trigger=pr.review |
| `test_parse_event_pr_review_comment` | `pull_request_review_comment` created → trigger=pr.review_comment |
| `test_parse_event_repository_dispatch_qa` | dispatch `qa-smoke-complete` → trigger=qa.smoke_complete |
| `test_branch_regex_feature_slash` | `feature/GIM-62-async-signal` → 62 |
| `test_branch_regex_no_match` | `fix/typo` → None |
| `test_bot_filter_github_actions` | sender=github-actions[bot] → early exit |
| `test_bot_filter_ant013_listed` | sender=ant013 → early exit |
| `test_dedup_marker_present` | comments contain matching marker → returns True (skip) |
| `test_dedup_marker_absent` | comments empty → returns False (proceed) |

### 7.2 Integration tests (httpx MockTransport)

| Test | Verifies |
|---|---|
| `test_reassign_refresh_success` | Full flow: GET issue → POST release → PATCH assignee → POST comment. All 4 HTTP calls made with correct payloads. |
| `test_reassign_refresh_5xx_retry` | 503, 503, 200 → succeeds. Confirms 3 attempts, delays honored (use freezegun). |
| `test_reassign_refresh_all_fail` | 503 forever → raises PaperclipError → `main()` posts signal-failed comment → exit 1. |
| `test_issue_not_found_404` | GET issue 404 → signal-failed comment, exit 1. |
| `test_409_execution_lock_retry` | POST release 409 → 1 retry → success. |

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
- CR's push-fix cycle is auto-woken via `pr.review` or `pr.review_comment`.
- A `signal-failed` comment appears on the PR when paperclip is unavailable, with enough info for operator to diagnose.
- Unit + integration tests pass in CI.
- Zero changes to `develop`/`main` branch-protection rules required (signal Action runs independently of required-checks).

## 10. Open questions / explicit trade-offs

- **`## CI pending` migration**: existing open PRs (if any) using the old marker will not be auto-migrated. They'll continue to require manual wake until the branch is rebased. Acceptable — old marker isn't broken, just deprecated.
- **Shared-token bot-filter list**: `ant013` is in `bot_authors` so that an agent's own commit/comment does not wake itself. Consequence: a human PR author (operator) who pushes as `ant013` also won't trigger a wake. Fine because operator PRs are usually not on feature branches (meta/ops work goes through separate workflow), and when they are, operator is actively monitoring.
- **No retry on CI failure**: intentional. Red CI is a signal the engineer-in-session will act on; if they're already idle, they can refresh manually or the next push will trigger the loop again on the following green.

---

**Predecessor context cited:** GIM-57 introduced the `## CI pending` marker pattern, GIM-61 introduced the test-design-discipline fragment structure that this slice's tests must conform to, stale-execution-lock reference memory documents the release+reassign workaround that this Action uses as its wake primitive.
