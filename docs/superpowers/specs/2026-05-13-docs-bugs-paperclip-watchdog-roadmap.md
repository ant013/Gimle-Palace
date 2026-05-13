---
slug: docs-bugs-paperclip-watchdog-roadmap
status: implemented
branch: docs/bugs-watchdog-roadmap-spec
base: origin/develop@69ce650
date: 2026-05-13
owner: CX/Codex
---

# Paperclip bug register from server logs and watchdog roadmap

## Goal

Bring `docs/BUGS.md` to a useful operational state by analyzing Paperclip
`server.logs`, grouping every observed failure case, checking which watchdog
roadmap changes already address them, and proposing the smallest prevention
improvements so the same failures stop recurring.

Success means `docs/BUGS.md` becomes an evidence-backed bug register, not a
loose notes file: each row must have a concrete symptom, log evidence, root
cause or best current hypothesis, current watchdog coverage, remaining gap,
and a recommended prevention action.

## Discovery so far

- Repository context loaded through `codebase-memory` and `serena`.
- The project is indexed in `codebase-memory` as
  `Users-ant013-Android-Gimle-Palace-cx`.
- Clean spec worktree was created from `origin/develop@69ce650`.
- Local `develop` is not current with `origin/develop`; it is `ahead 1,
  behind 9` in another worktree. To avoid rewriting unrelated work, this spec
  branch is based on current `origin/develop`.
- `docs/superpowers/specs/` is the established spec location.
- Operator clarified that `docs/BUGS.md` was added by PR #154 on `main`
  (`origin/main@568888a`) and also exists locally at
  `/Users/ant013/Android/Gimle-Palace-claude/docs/BUGS.md`.
- The clean `origin/develop@69ce650` ref in this worktree still does not
  contain `docs/BUGS.md`; implementation therefore restored the file from
  `origin/main:docs/BUGS.md` before extending it.
- `server.logs` is not a repository file. The authoritative Paperclip server
  log is on iMac production at
  `/Users/anton/.paperclip/instances/default/logs/server.log`.
- Relevant watchdog context already exists:
  - `docs/superpowers/specs/2026-05-03-GIM-181-watchdog-handoff-detector.md`
    defines alert-only semantic handoff detection.
  - `docs/superpowers/plans/2026-05-08-GIM-244-handoff-unification-p2p3.md`
    adds tier detectors and auto-repair/escalation design.
  - `docs/superpowers/plans/2026-05-09-GIM-255-watchdog-handoff-detector-hardening.md`
    records the spam regression: 258 alert comments across 32 issues in 4
    hours, then scopes age/status/origin gates and shared alert budgets.
  - `docs/superpowers/specs/2026-05-06-GIM-NN-watchdog-in-review-recovery.md`
    covers lost wakeups for `in_review` handoffs.
  - `docs/runbooks/watchdog-handoff-alerts.md` now documents safe re-enable,
    alert success logs, budget checks, and rollback.
  - `services/watchdog/src/gimle_watchdog/daemon.py` currently runs kill hangs,
    respawn recovery, legacy handoff alert pass, and tier pass with shared
    `AlertPostBudget`.

## Assumptions

- The intended `server.logs` are Paperclip server logs, not watchdog JSONL logs.
- Implementation will sample iMac logs over SSH and record aggregate evidence
  instead of copying log files into the repository.
- If `docs/BUGS.md` is absent on the implementation base, the implementation
  may restore it from `origin/main` / the local Claude checkout and then
  extend it.
- This task is documentation and planning first. Code changes to watchdog or
  Paperclip server require a follow-up implementation spec or explicit approval
  after this analysis lands.
- Existing dirty changes in `/Users/ant013/Android/Gimle-Palace-cx` are
  unrelated and must not be mixed into this work.

## Scope

### In

- Locate the authoritative Paperclip `server.logs` source or document that it
  is missing.
- Create or update `docs/BUGS.md` with a structured bug register.
- Analyze every distinct failure case found in the logs.
- Deduplicate repeated log lines into incidents and incident classes.
- Map each incident class to existing watchdog coverage:
  - mechanical idle/dead-work recovery;
  - semantic handoff alert-only detectors;
  - tier detectors;
  - GIM-255 gates and alert budget;
  - in-review recovery.
- Compare the findings against `docs/roadmap.md` and relevant watchdog
  plans/specs.
- Recommend prevention improvements, prioritizing:
  - lower alert volume;
  - earlier detection;
  - less agent wake churn;
  - clearer owner/action routing;
  - fewer false positives from stale, done, or recovery-origin issues.
- Mark each recommendation as documentation-only, config/runbook, watchdog code
  follow-up, Paperclip server follow-up, or roadmap follow-up.

### Out

- Deleting or rewriting existing server logs.
- Removing existing watchdog alert comments from Paperclip issues.
- Enabling `handoff_auto_repair_enabled` in production.
- Changing watchdog code in the same commit as the bug-register update.
- Changing roadmap priorities without explicit owner decision.

## Affected files and areas

Expected documentation targets:

- `docs/BUGS.md` - create/update main bug register.
- `docs/roadmap.md` - only if the analysis exposes a current roadmap mismatch.
- `docs/runbooks/watchdog-handoff-alerts.md` - only if new operator checks are
  needed.
- `docs/superpowers/plans/` or `docs/superpowers/specs/` - only for follow-up
  specs/plans produced from the analysis.

Reference-only implementation areas:

- `services/watchdog/src/gimle_watchdog/daemon.py`
- `services/watchdog/src/gimle_watchdog/detection.py`
- `services/watchdog/src/gimle_watchdog/detection_semantic.py`
- `services/watchdog/src/gimle_watchdog/actions.py`
- `services/watchdog/src/gimle_watchdog/state.py`
- `services/watchdog/src/gimle_watchdog/config.py`
- `services/watchdog/tests/`
- Paperclip server API/comment/issue lifecycle code, if log evidence points to
  server-side root causes.

## Proposed `docs/BUGS.md` structure

1. Header with date, log source path, analyzed time range, and base commit.
2. Executive summary:
   - total incidents;
   - total incident classes;
   - already-covered by watchdog;
   - uncovered or weakly covered;
   - recommended next actions.
3. Incident class table:
   - ID;
   - title;
   - first/last seen;
   - count;
   - severity;
   - affected issue IDs or endpoints;
   - symptom;
   - root cause / hypothesis;
   - current coverage;
   - prevention recommendation;
   - owner area.
4. Detailed case notes with short log excerpts or paraphrased evidence.
5. Watchdog roadmap cross-check.
6. Prevention backlog, grouped by:
   - config/runbook;
   - watchdog detector;
   - watchdog action/state;
   - Paperclip server;
   - agent instruction/process.
7. Open questions and missing evidence.

## Acceptance criteria

- `docs/BUGS.md` exists on the implementation branch.
- The document states the exact log source path and time range analyzed.
- Every distinct failure class from the provided logs has an entry.
- Repeated occurrences are grouped with counts rather than pasted verbatim.
- Each entry has evidence, impact, likely cause, current mitigation, and
  prevention recommendation.
- Watchdog-covered cases explicitly name the covering detector or recovery
  path.
- Gaps are translated into follow-up candidates with owner area and priority.
- If no `server.logs` can be found, `docs/BUGS.md` must state that clearly and
  list the commands/paths checked.
- The update does not include unrelated formatting churn.
- Implementation commit contains documentation changes only unless separately
  approved.

## Verification plan

- `git diff --check`.
- `rg -n "TODO|TBD|server.logs|watchdog|GIM-255|GIM-244|GIM-181" docs/BUGS.md`
  to confirm placeholders are intentional and watchdog mappings are present.
- If logs are available, run a small deterministic parser or `rg` summary to
  count incident classes and compare counts against the document.
- If roadmap/runbook files are touched, inspect `git diff -- docs/roadmap.md
  docs/runbooks/watchdog-handoff-alerts.md docs/BUGS.md`.
- No watchdog test suite is required for documentation-only changes. If any
  watchdog code is later approved, run `uv run pytest services/watchdog/`.

## Open questions

- Where is the authoritative Paperclip `server.logs` file or directory?
- Is there an existing `docs/BUGS.md` on another branch that should be merged
  instead of creating a new file from scratch?
- Should `docs/BUGS.md` stay as an operator-facing register, or should
  prevention items be split into `docs/superpowers/plans/` follow-up files?
- Which issue cohort should be treated as the canonical GIM-255 incident set
  for "no repeat alert" verification?
