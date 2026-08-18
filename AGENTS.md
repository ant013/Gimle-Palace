# Gimle Palace — Codex Agent Instructions

This file is the Codex-facing companion to `CLAUDE.md`. Keep it short and
operational: load detailed runbooks only when the task touches that area.

## Repository Rules

- Mainline is `develop`; `main` is release-stable only.
- All changes go through a feature branch and PR, including docs, specs,
  plans, role files, and agent instructions.
- Never commit directly to `develop` or `main`.
- Never force-push `develop` or `main`. On feature branches, use
  `--force-with-lease` only after fetching and only when you are the sole writer
  for the current phase.
- Feature branches are cut from `origin/develop` and PR back to `develop`.
- Primary repo stays on `develop`; Paperclip issue work happens in
  Paperclip-managed worktrees.
- Operator/Board writing uses a separate clone such as `~/<project>-board/` or
  `~/Android/<project>/`; never use `/Users/Shared/Ios/<project>/` for
  spec/plan writing.
- On the MacBook operator setup, Palace runs natively via launchd on
  `http://127.0.0.1:8765/mcp`. Do not start Docker, docker compose, Colima, or
  iMac deploy scripts unless the user explicitly asks for that legacy/remote
  path.
- Clean iOS repository copies live under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/`. Do not use
  `/Users/ant013/Ios/HorizontalSystems/` or working product checkouts for Palace
  sync/update jobs unless the user explicitly overrides this.

Before any git history or branch operation in a new run:

```bash
git fetch origin --prune
```

## Paperclip Workflow

Product slices larger than about 200 LOC or crossing multiple areas should go
through the Paperclip agent team. Canonical phases:

1. CTO formalizes spec/plan and assigns CodeReviewer.
2. CodeReviewer performs plan-first review and assigns implementer.
3. Implementer works TDD on `feature/GIM-<N>-<slug>` and pushes often.
4. CodeReviewer performs mechanical review with actual command output.
5. OpusArchitectReviewer performs adversarial review.
6. QAEngineer performs live iMac smoke with real MCP tool call, CLI, and direct
   invariant evidence.
7. Merger squash-merges to `develop` after CI and QA evidence are green.

Never leave an issue as `status=todo` between phases. Reassign explicitly to
the next agent and include an `@NextAgent ` mention with a trailing space after
the agent name.

## Working Discipline

- Keep changes surgical. Every changed line must trace to the task.
- Prefer existing project patterns over new abstractions.
- State assumptions when the task is ambiguous. If multiple interpretations
  materially change the implementation, ask before editing.
- For bug fixes, reproduce with a failing test or concrete command before the
  fix when feasible.
- For shared infrastructure, schema/storage, startup, runners, or MCP boundary
  changes, run the full relevant suite before handoff.
- Do not use mocked happy paths for external substrate where real substrate is
  feasible: DBs, subprocesses, filesystem-as-subject, protocol clients.
- Keep secrets in `.env`. Never paste real API keys, JWT secrets, bearer
  tokens, or private key material into docs, issues, logs, or PR comments.

## Verification Gates

Before implementation handoff, push the feature branch and include concrete
commit SHA(s), test output, and PR/branch link in the Paperclip comment.

Do not push a formatting/lint/test fix until the narrow local equivalent has
passed. This prevents burning full GitHub Actions minutes on avoidable red CI.
Minimum local pre-push checks:

- Python changes in `services/palace-mcp`: run `uv run ruff check` and
  `uv run ruff format --check` in `services/palace-mcp`, plus targeted pytest
  for the touched path.
- Watchdog changes: run `uv run ruff check src/ tests/`,
  `uv run ruff format --check src/ tests/`, and targeted pytest in
  `services/watchdog`.
- Paperclip bundle changes: run the touched script/test locally, or explain why
  the check cannot run before pushing.

Expected local checks for `services/palace-mcp` changes unless the task defines
a narrower equivalent:

```bash
uv run ruff check
uv run mypy src/
uv run pytest
```

Branch protection for `develop` expects:

- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` unless the PR has `micro-slice`

CodeReviewer approval requires both a full Paperclip compliance comment and a
GitHub PR approval.

## Deployment

Default MacBook operator runtime is native `palace-mcp` on port `8765`, managed
by `~/Library/LaunchAgents/work.ant013.palace-mcp-native.plist`. After updating
the local service source, restart that launchd job and verify:

```bash
launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native
curl -sf http://127.0.0.1:8765/healthz
```

The iMac deploy path below is legacy/remote production only. Do not run it for
MacBook native work unless the user explicitly asks for iMac deployment.

After a PR squash-merges to `develop`, rebuild and restart `palace-mcp` on the
iMac only when that remote deployment was requested:

```bash
bash paperclips/scripts/imac-deploy.sh
```

After a release-cut merges to `main`, update live agent role files on the iMac:

```bash
bash paperclips/scripts/imac-agents-deploy.sh
```

Paperclip reads rendered `AGENTS.md` files fresh on each agent run; no restart
is required for role-file updates.

## MCP And Project Tools

For MacBook native operation, use `http://127.0.0.1:8765/mcp`. `palace-mcp`
must not manage Docker as a side effect of CLI analysis. If runtime management is
needed for a legacy Docker path, it must be selected explicitly with
`project analyze --manage-runtime`.

`palace-mcp` exposes read-only git tools mounted under `/repos/<slug>`:

- `palace.git.log`
- `palace.git.show`
- `palace.git.blame`
- `palace.git.diff`
- `palace.git.ls_tree`

Mounted project slugs currently documented in `CLAUDE.md`:

- `gimle`
- `oz-v5-mini`
- `uw-android`

Extractor framework lives under:

```text
services/palace-mcp/src/palace_mcp/extractors/
```

Run extractors through MCP:

```text
palace.ingest.list_extractors()
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```

Registered extractor families include heartbeat plus SCIP-backed Python,
TypeScript/JavaScript, Java/Kotlin, and Solidity symbol indexers. For exact
SCIP generation commands, env vars, caveats, and registered extractor details,
read `CLAUDE.md` section `Extractors` before acting.

## API Access

Before calling Paperclip, watchdog, JWT, or operator API endpoints, read
[`API.md`](API.md). It is the authoritative local runbook for endpoint paths,
auth headers, wake-up rules, issue blocking, and known Paperclip gotchas. Do
not rediscover endpoints by grepping old specs unless `API.md` is missing the
needed contract.

## UAudit Live Operations

The local `Gimle-Palace` checkout is development-only. For every request about
current UAudit logs, state, runs, or data, connect first to the iMac through
`ssh imac-ssh.ant013.work`; do not search the local checkout or present its
contents as live evidence. Read
[`docs/paperclip-operations/uaudit-imac-operations.md`](docs/paperclip-operations/uaudit-imac-operations.md)
before the first command: it defines the iMac preflight, canonical runtime
paths, period semantics, and secret-safe authentication fallback. Never copy,
print, or pre-load credentials unless the SSH preflight has actually failed.

## Docs And References

- Specs: `docs/superpowers/specs/YYYY-MM-DD-<slug>.md`
- Plans: `docs/superpowers/plans/YYYY-MM-DD-GIM-<N>-<slug>.md`
- Postmortems: `docs/postmortems/YYYY-MM-DD-<incident>.md`
- Research: `docs/research/`
- Agent fragments: `paperclips/fragments/shared/fragments/`
- Branch/deploy rollback: `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md`
- Deploy details: `paperclips/scripts/imac-deploy.README.md`
- Agent deploy details: `paperclips/scripts/imac-agents-deploy.README.md`

When editing specs or plans, cite the commit SHA or branch state the artifact is
grounded in. Do not rely on a vague "current develop" reference.

## When Blocked

Do not improvise around unclear specs, missing access, unavailable dependencies,
or execution-lock conflicts. Mark the Paperclip issue `blocked`, comment with
what is blocked, what was tried, what decision/resource is needed, and mention
`@Board ` with the trailing space.
