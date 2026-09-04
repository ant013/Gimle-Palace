## Karpathy discipline

Think before coding • Minimum code • Surgical changes • Goal+criteria+verification.

### 1. Think Before Coding

Before implementation:

- State assumptions.
- If unclear, ask instead of guessing.
- If multiple interpretations exist, present options and wait — don't pick silently.
- If a simpler approach exists, say so. Push-back is welcome; blind execution is not.
- If you don't understand the task, stop and clarify.

### 2. Minimum Code

- Implement only what was asked.
- Don't add speculative features, flexibility, configurability, or abstractions.
- Three similar lines beat premature abstraction.
- Don't add error handling for impossible internal states (trust framework guarantees).
- Keep code as small as the task allows. 200 lines when 50 fits → rewrite.

Self-check: would a senior call this overcomplicated? If yes, simplify.

### 3. Surgical Changes

- Don't improve, refactor, reformat, or clean adjacent code unless required.
- Don't refactor what isn't broken — PR = task, not cleanup excuse.
- Match existing style.
- Remove only unused code introduced by your own changes.
- If unrelated dead code is found, mention it; don't delete silently.

Self-check: every changed line must trace directly to the task.

### 4. Goal, Criteria, Verification

Before work, define:

- Goal: what changes.
- Acceptance criteria: how "done" is judged.
- Verification: exact test, command, trace, or observation.

Examples:

- "Add validation" → write tests for invalid input, then make pass.
- "Fix the bug" → write a test reproducing it, then fix.
- "Refactor X" → tests green before and after.

For multi-step work:

```
1. [Step] → check: [exact verification]
2. [Step] → check: [exact verification]
```

Strong criteria → autonomous work. Weak ("make it work") → ask, don't assume.


## Wake & handoff basics

Paperclip heartbeat is **disabled** company-wide. Agent wake is event-driven only:
assignee PATCH, @mention, posted comment. Watchdog (`services/watchdog`) is the
safety net for missed wake events — it does not replace correct handoff
discipline.

### On every wake

1. **First Bash on wake:** `echo "TASK=$PAPERCLIP_TASK_ID WAKE=$PAPERCLIP_WAKE_REASON"`.
2. If `TASK` non-empty → `GET /api/issues/$PAPERCLIP_TASK_ID`. **Idle-exit immediately** if: HTTP 404; `status` ∈ {`done`, `cancelled`}; `assigneeAgentId != me` without fresh @-mention handoff to me. Otherwise → work. **Never resurrect** a stale issue from CLI memory.
3. `GET /api/agents/me` → any issue with `assigneeAgentId=me` and `in_progress`? → continue.
4. Comments / @mentions newer than `last_heartbeat_at`? → reply.

None of these → **exit immediately** with `No assignments, idle exit`.

### Stale-wake guards

Source of truth = Paperclip API now, not CLI session ("galaxy brain — ignore"). On idle wake do **NOT**: take unassigned/stale `todo`, self-checkout without handoff phrase, check git/logs "just in case", create issues for "discovered problems", reopen `done`/`cancelled`, write code "from memory". Stale-wake work triggers the server's `stranded_issue_recovery` / `stale_active_run_evaluation` services to emit fresh wake tasks — each new task re-runs the stale-TASK path and the loop never closes.

### @-mentions: trailing space after name

Paperclip's parser captures trailing punctuation into the name (e.g. `@Role:`
becomes `Role:`), the mention doesn't resolve, no wake is queued — **chain
silently stalls**.

**Right:** target-local role mention followed by a space.
**Wrong:** `@Role: need a fix`, `@Role;`, `(@Role)` — punctuation goes after
the space.

### Handoff: PATCH + comment with @mention + STOP

Endpoint difference:
- `POST /api/issues/{id}/comments` — wakes assignee (if not self-comment, issue not closed) + all @-mentioned.
- `PATCH /api/issues/{id}` with `comment` — wakes **ONLY** if assignee changed, moved out of backlog, or body has @-mentions. No-mention comment on PATCH **won't wake assignee** → silent stall.

**Rule:** handoff comment always includes `@NextAgent` (trailing space). Covers both paths.

### Self-checkout on explicit handoff

Got an @-mention with explicit handoff phrase (`"your turn"`, `"pick it up"`, `"handing over"`) and sender already pushed → `POST /api/issues/{id}/checkout` yourself, don't wait for formal reassign.

### HTTP 409 on close/update — execution lock conflict

`PATCH /api/issues/{id}` → **409** = another agent's execution lock. Holder is in `issues.execution_agent_name_key`. Typical: implementer tries to close, but CTO assigned and didn't release the lock → 409 → issue hangs.

**Do:**
1. `GET /api/issues/{id}` → read `executionAgentNameKey`.
2. Comment to the target-local lock holder: `"release execution lock on [UNS-5], I'm ready to close"`.
3. Alternative — if holder unavailable, `PATCH ... assigneeAgentId=<original-assignee>` → originator closes.
4. Don't retry close with the same JWT — without release, 409 keeps coming.

**Don't:** Direct SQL `UPDATE`, or create new issue copy.

Release (from holder): `POST /api/issues/{id}/release` → lock released, assignee can close via PATCH.


## Escalation to Board when blocked

If you cannot progress on an issue, do not improvise, pivot, or create preparatory issues. Escalate and wait.

### Escalate when

- Spec unclear or contradictory.
- Dependency, tool, or access missing.
- Required agent unavailable or unresponsive.
- Obstacle outside your responsibility.
- Execution lock conflict + lock-holder unresponsive (see §HTTP 409 in `universal/wake-and-handoff-basics.md`).
- Done/success criteria unclear.

### Escalation steps

1. PATCH `/api/issues/{id}` with `status=blocked`.
2. Comment with:
   - Exact blocker (not "stuck", but "can't X because Y").
   - What you tried.
   - What you need from Board.
   - `@Board ` with trailing space.
3. Wait for Board. Do not switch tasks without explicit permission.

### Do not

- Change scope via workaround.
- Create prep issues to stay busy.
- Do another role's work (CTO blocked on engineer ≠ writes code; engineer blocked on review ≠ self-reviews).
- Pivot to another issue without Board approval — old one stays in limbo.
- Close as "not actionable" without Board visibility.
- Treat a GitHub PR-author-cannot-self-approve block as a CR blocker — CR's substantive review is on Paperclip; merge action is CTO's per `universal/cto-merge-authority.md`.

### Comment format

```
@Board blocked:

**What's needed:** [quote from description]
**Blocker:** [specific reason progress is impossible]
**Tried:** [what was tested/attempted]
**Need from Board:** [decision/resource/unblock needed]
```

### Blocker self-check

- Blocked 2+ hours without escalation comment → process failure.
- Any workaround preserves scope → not a blocker.
- Concrete question for Board exists → real blocker.
- Only "kind of hard" → decompose further, not a blocker.


## Git: commit & push (implementer / qa)

### Fresh-fetch on wake

Every wake, before any git operation:
```
git fetch --all --prune
```
Stale local refs cause silent merge conflicts on push.

### Branch naming

Feature branches: `feature/UNS-N-<slug>` (e.g. `feature/IOS-12-add-swift-engineer`). Branch from `develop` (default `develop`).

### Commit format

- Conventional commits: `type(scope): subject`
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
- Subject ≤ 70 chars, imperative mood ("add X" not "added X")
- Body explains WHY, not WHAT (the diff shows what)

### Push (your own feature branch only)

```
git push -u origin feature/UNS-N-<slug>
```

Force-push: ONLY `--force-with-lease`, ONLY when you are the sole writer of the current phase. Bare `--force` is forbidden on every branch including features (eats teammate's commits).

`develop` and `main` reject force-push at branch protection (no exceptions). CTO merge action is gated separately — see `universal/cto-merge-authority.md`.

### Post-commit verification

Before `git push`, run the project's verification commands. For Python services:
```
uv run ruff check && uv run mypy src/ && uv run pytest
```

For other targets, see project AGENTS.md. Don't push commits that fail local checks — CI will block, and you'll loop.


## Worktree discipline (implementer / reviewer / qa)

### Per-team isolated worktree

Each agent runs in its own workspace under `<team_workspace_root>/<AgentName>/workspace/`. This directory is the agent's `cwd`. **Do not** `cd` outside it for git operations — every commit/push originates from this worktree.

### Never remove shared workspace dirs

Workspaces under `<team_workspace_root>/<AgentName>/workspace/` are persistent: branch rotates per slice, the directory does not. **Never** `git worktree remove <AgentName>/workspace` — you'll wipe in-progress state of another agent if you happen to share the team_workspace_root.

### Cross-branch carry-over forbidden

Switching branches inside an agent worktree drags uncommitted changes across branches and contaminates the next slice. Discipline:
- Before switching branch: commit or stash.
- Before starting a new feature branch: `git status --short` must be clean.

### Operator vs production checkout

The `production_checkout` path (e.g. `/Users/ant013/Android/Gimle-Palace-serving`) is the iMac deploy target. Stay on `develop` (typically `develop`) there — never check out feature branches in production_checkout. Discovered in UNS-48: feature checkout in production_checkout caused QA to test stale code.


## Pre-work: codebase-memory first

Before reading any code file, query the codebase-memory MCP graph:

- `search_graph(name_pattern=...)` to find functions/classes/routes by symbol name
- `trace_path(function_name, mode=calls)` for call chains
- `get_code_snippet(qualified_name)` to read source (NOT `cat`)
- `query_graph(...)` for complex Cypher patterns

Fall back to `Grep`/`Read` only when the graph lacks the symbol (text-only content, config files, recent commits). If the project is unindexed, run `index_repository` first.

Reading files cold without graph context invites missing call sites and dead-code mistakes.


## Pre-work: sequential-thinking

For tasks with 3+ logical steps, branching paths, or unclear dependencies, invoke `mcp__sequential-thinking__sequentialthinking` BEFORE writing code or tests:

- Decompose the task into ordered steps.
- Surface assumptions explicitly.
- Identify which steps can run in parallel vs. must serialize.

Skip for trivial mechanical edits (rename, format, single-line fix). Use for: new feature, refactor across files, anything touching async/state machines.


## Pre-work: existing field semantics

Before renaming, removing, or repurposing a field on an existing data structure (Pydantic model, Cypher node label, JSON schema, env var):

1. **Find all readers** via `search_graph` + `trace_path(... mode=data_flow)`.
2. **Find all writers** (often more than readers — backfill scripts, migrations, fixtures).
3. **Document the migration** in PR description: old → new mapping, deprecation window, rollback.
4. **Add backwards-compat shim** if external API surface (MCP tool args, REST endpoint params) — at least one release cycle.

Renaming a field that's referenced in saved Neo4j data without migration loses that data. Renaming an MCP tool arg without shim breaks every caller silently.


## Handoff basics (iron rule)

**Every wake ends in one of two states:**

1. `status=done`, OR
2. **Atomic handoff** to next target-local agent (or your target-local CTO if
   next is unknown).

No third option. `assignee=me, status=in_progress|todo` between phases = chain dies silently.

### Atomic handoff procedure

ONE POST + ONE PATCH + STOP, **in this exact order**:

1. **POST** comment `/api/issues/{id}/comments` (strict format below). MUST happen BEFORE the PATCH.
2. **PATCH** `/api/issues/{id}` with `{ "assigneeAgentId": "<uuid>", "status": "<new>" }`
3. **STOP.** No loop, no status-check, no follow-up pickup, no post-handoff summary.

**Why POST before PATCH:** paperclip API rejects POST `/comments` with 409 `"Issue is checked out by another agent"` AFTER assignee changes mid-run. POST-then-PATCH = comment lands first (still your lock), then PATCH transfers ownership. PATCH-then-POST = 409 → comment lost → recipient woken but with no evidence (precedent: smoke#2 2026-05-17, 3/5 CRs lost evidence comment).

POST + PATCH is the only reliable wake mechanism. Mention in POST wakes by mention; PATCH wakes by reassign.

### Fallback: unknown recipient -> target-local CTO

Phase chain unclear? **Handoff to your target-local CTO** (`reportsTo` in
manifest). If you ARE CTO and don't know -> escalate Board per
`universal/escalation-board.md`. NEVER drop the issue. Do not cross from a
Codex/CX lane to bare Claude-side roles, or from a Claude lane to CX-prefixed
roles.

### Comment format — STRICT

Comment **MUST end with**:

```
[@<RecipientName>](agent://<recipient-uuid>?i=<icon>) your turn.
```

That is the **LAST sentence**. Nothing after — no TL;DR, no "let me know if…". **Period. STOP writing.**

Evidence/context goes ABOVE:

```markdown
## Phase N.M complete — [brief result]

[Evidence / artifacts / commits / links]

[@<NextAgent>](agent://<NextAgent-UUID>?i=<icon>) your turn.
```

**Why so strict:** writing past `your turn.` triggers SIGTERM (paperclip session limit) — comment lost, recipient never wakes, chain stalls (precedents: `UNS-bootstrap`, `UNS-bootstrap` 8h stall).

### Formal vs plain @-mention

Use **formal** `[@<Role>](agent://<uuid>?i=<icon>)` — machine-verifiable if
assignee PATCH flakes. Resolve the concrete UUID from the local roster for your
target/team.

Examples:
- OK: `[@<TargetLocalReviewer>](agent://<uuid>?i=<icon>) your turn.`
- Wrong: plain `@<Role> your turn` with trailing prose.
- Wrong: `@<Role>:` because `@Role:` breaks parser — see
  `universal/wake-and-handoff-basics.md`.
- Wrong: `Reassigning to @<Role> for review.` because it has no `your turn.`
  and no formal mention.

### Cross-team handoff

Do not cross teams during normal phase handoff. A Codex/CX issue stays on
CX/Codex roles; a Claude issue stays on Claude roles. Cross-team escalation
requires explicit operator instruction.

### Self-checkout on explicit handoff

If sender's comment has `"your turn"` / `"pick it up"` / `"handing over"` AND assignee is already you → `POST /api/issues/{id}/checkout`.

### Comment ≠ handoff (iron rule)

"Reassigning…" in comment body does **not** execute handoff. ONLY `PATCH` with `assigneeAgentId` wakes the next agent. Without PATCH, issue stalls indefinitely.

### Verify after PATCH

`GET /api/issues/{id}` immediately after PATCH. Mismatch → retry once. Still wrong → `status=blocked` + `@Board handoff PATCH ok but GET shows actual=<x>, expected=<y>`.

If POST returned non-2xx → STOP. Don't PATCH (would orphan the issue without context). Escalate Board.

### Watchdog safety net

If your PATCH was authored by a SIGTERM'd run, paperclip may suppress the wake. Watchdog (`services/watchdog`) detects stuck `in_review` + null-execution_run and recovers. Not a primary mechanism — author handoffs correctly.


## Daily Version-Branch Crypto Audit Stage (iOS)

For `mode=daily_crypto_audit`, set `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py`; read the immutable `$RUN/run-context.json`, prepared inputs, validated prior sidecars/markers, their human MD, and the iOS repo. Audit wallet, chain, signing, transaction, key-management, address, fee, and balance semantics in the bound FROM..TO range.

Write human evidence to `$RUN/crypto.md`. Atomically publish `$RUN/crypto.findings.json` as the strict v1 envelope: exact copied `run_binding`; `stage="crypto"`; `source_agent="UWICryptoAuditor"`; `audit_status=complete|partial|blocked`; structured findings; typed `{text,material}` limitations; status-valid `block_reason`. Every finding has exactly `severity,file,line,area,title,evidence,impact,recommendation,needs_runtime_verification`; location is either relative file+positive line+null area or null file/line+nonempty area. Finding prose, limitation text and non-null blocked reason are Russian; complete/partial use null block reason. Do not count, deduplicate, or add schema fields.

Severity is `Critical|Block|Important|Observation`. The helper canonicalizes known aliases with a Russian `material=false` warning. Fix a recoverable sidecar format/schema error without changing binding/evidence, then retry `validate-stage` exactly once. Never PATCH the issue to `blocked` or request Board approval for a recoverable output error.

Run `python3 "$HELPER" validate-stage --run-dir "$RUN" --sidecar "$RUN/crypto.findings.json"`; only it creates digest-bound `status/crypto.done.json`. Validation failure or `blocked` PATCHes issue blocked and stops without a completion message. Otherwise comment ready, PATCH `339e9d3f-48c0-4348-a8da-5337e6f29491` with `mode=daily_infra_audit`, and stop. Never send Telegram or update state/cursors.



## UAudit Runtime Scope

- Paperclip company: UnstoppableAudit (`UNS`).
- Runtime agent: `UWICryptoAuditor`.
- Platform scope: `ios`.
- Primary codebase-memory project: `Users-Shared-UnstoppableAudit-repos-ios-unstoppable-wallet-ios`.
- iOS repo: `/Users/Shared/UnstoppableAudit/repos/ios/unstoppable-wallet-ios`.
- Android repo: `/Users/Shared/UnstoppableAudit/repos/android/unstoppable-wallet-android`.
- Required base MCP: `codebase-memory`, `context7`, `serena`, `github`, `sequential-thinking`.
- UAudit project MCP addition: `neo4j`.
- **Execution host is iMac only.** Run repos, cursors, locks, helpers and delivery
  locally; never SSH back to `imac-ssh.ant013.work`. External operators use
  `ssh -p 2222 "${IMAC_HOST:-imac-ssh.ant013.work}"`; port `22` is forbidden.

## Daily control-plane recovery

For `mode=daily_*`, set `HELPER=/Users/Shared/UnstoppableAudit/runs/.uaudit-tools/uaudit_delivery_contract.py`. Once its durable artifact is valid, retry a failed handoff comment once and run `python3 "$HELPER" record-operational-warning --run-dir "$RUN" --code paperclip-comment --text <Russian-warning>`. Then PATCH the exact next assignee anyway; a comment-only failure never blocks a daily audit, requests Board, or reruns a valid stage. Without a comment, the recipient derives the sole next mode from run markers. Retry a failed PATCH once; only failed ownership transfer may block.

After a verified receipt and `cursor.done`, the same warning rule means a final comment failure cannot delay `workflow.done` or release of the matching lock. Post Status/Evidence/Blockers/Next owner when possible.

## Report Delivery

Non-delivery roles save Markdown in the writable artifact root and hand off to
`UWAInfraEngineer` (`UWIInfraEngineer` for iOS-only
issues). Do not call Telegram/bot/plugin notification actions.
