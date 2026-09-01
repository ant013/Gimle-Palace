# macOS Watchdog No-TTY Process Discovery

Date: 2026-09-02
Status: APPROVED
Branch: `fix/macos-watchdog-no-tty-scan`
Baseline: `14e4a5865b7b19093004c8dec7fbb565c72f089c` (`origin/develop`)
Trigger: Glitcherry DX-005 / GLA-9 Phase 1 `NOT_READY`

## Goal

Make the production macOS watchdog enumerate detached Paperclip agent processes
that have no controlling terminal, without weakening the exact Claude/Codex
command signatures or any Codex parent, identity, API-correlation, threshold, or
pre-signal guard introduced by PR #578.

## Reproduction and assumptions

GLA-9 proved the same live process through two read-only views:

- `ps -axo pid=,ppid=,etime=,stat=,args=` enumerated exactly one direct
  `/usr/local/bin/codex exec ...` child of the Paperclip API server;
- the production sampler, `ps -ao pid,etime,time,command`, omitted that PID, and
  both watchdog status and `scan_idle_hangs` reported zero Codex candidates.

On macOS, the `x` selector includes processes without a controlling terminal.
Paperclip launches its Codex worker detached, so the production scan must include
that selector. The live command and environment contain sensitive material;
tests and diagnostics must assert only process presence, classification, and
sanitized identity fields.

## Scope

### In scope

- Use the all-process/no-TTY selector in the shared watchdog process sampler on
  macOS and supported Unix hosts.
- Use the same sampler semantics for safe status/runtime-shape counts so status
  cannot disagree with hang discovery solely because of process selection.
- Add a regression test that proves the subprocess command includes `x` and a
  detached Codex row reaches the existing exact classifier.
- Preserve all PR #578 fail-closed correlation and pre-signal behavior.

### Out of scope

- Changing `hang_etime_min`, CPU/stream thresholds, daemon cadence, signal grace,
  cooldowns, or maximum actions per tick.
- Broadening the Codex signature beyond executable basename `codex` followed by
  subcommand `exec`.
- Sending a signal during implementation or deployment canary.
- Changing Paperclip agents, issue history, Glitcherry repositories, or product
  roadmap state.

## Affected files and areas

- `services/watchdog/src/gimle_watchdog/detection.py`
  - production `ps` invocation used by `scan_idle_hangs`.
- `services/watchdog/src/gimle_watchdog/__main__.py`
  - status sampler, only if it separately constructs a narrower `ps` command.
- `services/watchdog/tests/test_detection.py`
  - subprocess invocation and detached-process regression coverage.
- `services/watchdog/tests/test_cli.py`
  - status count consistency if the CLI has a separate invocation.
- `services/watchdog/README.md`
  - only if the operator-visible process selection contract needs one sentence.

No other service, Paperclip bundle, or product file is in scope.

## Acceptance criteria

1. The production scan command includes processes without controlling terminals.
2. A detached Paperclip-shaped `codex exec` row is enumerated and classified as
   Codex before the existing age/idle filters.
3. Status and hang discovery use equivalent all-process selection and no longer
   disagree for the same live no-TTY Codex PID.
4. Unrelated or malformed Codex commands still fail classification; existing
   parent, allowlisted identity, configured-company, active-run, and pre-signal
   guards are unchanged.
5. Existing Claude behavior remains green.
6. No test, log, or status output exposes a full command, raw environment, bearer
   token, or API key.
7. Focused tests reproduce the old command omission before the fix and pass after
   it; the full watchdog suite, Ruff, format check, mypy, and `git diff --check`
   pass.
8. After merge and iMac deployment, a read-only canary reports exactly one live
   Codex command shape for GLA-9 or its separately authorized successor, without
   signalling it.

## Verification plan

From `services/watchdog`:

```bash
uv run pytest tests/test_detection.py tests/test_cli.py
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
```

From the repository root:

```bash
git diff --check
```

Deployment verification:

- fast-forward the iMac live checkout to the merged `origin/develop` SHA;
- sync the existing watchdog environment and restart the single launchd job;
- verify the deployed SHA, one watchdog PID, unchanged config hash/posture, and
  `Paperclip agent command shapes: ... codex=1` while an exact young run exists;
- do not use `SIGSTOP` until a fresh retained corrective issue explicitly arms
  one exact PID.

## Risks and rollback

- **Wider enumeration increases candidates.** Existing exact command signatures
  and Codex correlation gates remain mandatory; regression tests cover unrelated
  Codex sessions.
- **Platform flag drift.** Use the already supported `ps` dialect and test the
  exact argument vector rather than parsing shell text.
- **Deployment regression.** Fast-forward or revert the single merged commit,
  restart launchd, and verify one watchdog process. GLA-9 remains immutable
  `NOT_READY` evidence regardless of rollback.

## Open questions

None. The user-authorized corrective objective and GLA-9 evidence determine the
smallest change: add no-TTY enumeration, test it, deploy it, and requalify in a
new retained issue.
