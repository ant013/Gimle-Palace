# Gimle Palace — Developer Guide

## Branch Flow

Single mainline: `develop`. Feature branches cut from develop, PR'd back.
`main` is an optional release-stable reference.

```
feature/GIM-N-<slug>    (all work: code, spec, plan, research, docs)
      │
      ▼  PR → squash-merge (CI green + CR paperclip APPROVE + CR GitHub review + QA evidence present)
develop                   (integration tip; iMac deploys from here)
      │
      ▼  .github/workflows/release-cut.yml (label `release-cut` on a merged PR, or workflow_dispatch)
main                      (stable release ref — tags live here)
```

**Iron rules:**
- Every change — product code, spec, plan, research, postmortem, role-file, CLAUDE.md itself — goes through a feature branch + PR. Zero direct human commits to `develop` or `main`.
- Force push forbidden on `develop` / `main`; on feature branches only `--force-with-lease` AND only when you are the sole writer of the current phase (see `git-workflow.md` fragment).
- Branch protection on develop + main: admin-bypass disabled. All required checks must pass for PR merge. `main` accepts push only from `github-actions[bot]` via `release-cut.yml`.
- Feature branches live in paperclip-managed worktrees; primary repo stays on `develop`.
- **Operator/Board checkout location:** a separate clone, typically `~/<project>-board/` or `~/Android/<project>/`. Never use the production deploy checkout (`/Users/Shared/Ios/<project>/`) for spec/plan writing.

**Spec + plan location:** `docs/superpowers/specs/` and `docs/superpowers/plans/` on the feature branch. After squash-merge they land on develop. Main gets them only when `release-cut.yml` Action runs.

**Required status checks on develop:**
- `lint`
- `typecheck`
- `test`
- `docker-build`
- `qa-evidence-present` (verifies PR body has `## QA Evidence` with SHA, unless `micro-slice` label)

**CR approval path:** CR posts full compliance comment on paperclip issue AND `gh pr review --approve` on the GitHub PR (the GitHub review satisfies branch-protection's "Require PR reviews" rule).

**Release-cut procedure:** to update `main`:
1. Add label `release-cut` to a merged develop PR, OR
2. Run `gh workflow run release-cut.yml`.

The Action fast-forwards `main` to `origin/develop` using `RELEASE_CUT_TOKEN` (GitHub App or PAT with `contents: write`). No human pushes `main`, ever.

See also:
- `paperclips/fragments/shared/fragments/git-workflow.md` — per-agent rules.
- `docs/runbooks/2026-04-19-meta-workflow-migration-rollback.md` — if branch protection or the new workflows cause a block and need to be reverted.

## Docker Compose Profiles

Services use explicit profile opt-in:

```bash
docker compose --profile review up -d    # palace-mcp + neo4j
docker compose --profile analyze up -d   # analyze mode
docker compose --profile full up -d      # full mode
```

No profile → no services start (intentional — forces explicit opt-in).

## Environment

Copy `.env.example` to `.env` and fill real values before starting
compose. Required at minimum: `NEO4J_PASSWORD`.

`PALACE_DEFAULT_GROUP_ID` (default `project/gimle`) namespaces all
Issue/Comment/Agent/IngestRun nodes. Do **not** change casually — it
determines which rows ingest writes against and GC scopes on.

## Docs layout

- `docs/superpowers/specs/YYYY-MM-DD-<slug>.md` — design specs (Board
  output). Revisions keep the old file with a deprecation banner at
  the top; new revisions add `-rev3` suffix.
- `docs/superpowers/plans/YYYY-MM-DD-GIM-<N>-<slug>.md` — TDD
  implementation plans, one per issue. `GIM-NN` placeholder is
  swapped for the real issue number when CTO formalizes in Phase 1.1.
- `docs/postmortems/YYYY-MM-DD-<incident>.md` — one file per incident
  in the three-gate analysis format established by GIM-48.
- `docs/research/` — external library verification, competitive
  analysis, extractor inventory, etc. Treat older research docs as
  historical; verify library APIs against the installed version
  before reusing any claim.

## Paperclip team workflow

Product slices of meaningful size (>200 LOC or cross-cutting) go
through the paperclip agent team rather than being implemented
inline. Canonical phase sequence:

- **1.1 Formalize** (CTO) — verify Board's spec+plan paths, swap the
  `GIM-NN` placeholder, reassign to CodeReviewer.
- **1.2 Plan-first review** (CodeReviewer) — validate every task has
  concrete test+impl+commit; flag gaps; APPROVE → reassign to
  implementer.
- **2 Implement** (MCPEngineer / PythonEngineer / …) — TDD through
  plan tasks on `feature/GIM-<N>-<slug>`; push frequently.
- **3.1 Mechanical review** (CodeReviewer) — paste
  `uv run ruff check && uv run mypy src/ && uv run pytest` output in
  APPROVE; no "LGTM" rubber-stamps.
- **3.2 Adversarial review** (OpusArchitectReviewer) — poke holes;
  findings addressed before Phase 4.
- **4.1 Live smoke** (QAEngineer) — on iMac; real MCP tool call + CLI
  + direct Cypher invariant. Evidence comment authored by
  QAEngineer.
- **4.2 Merge** — squash-merge to develop after CI green. No admin
  override.

Phase-handoff discipline is encoded in the shared-fragment
`phase-handoff.md` (submodule `paperclip-shared-fragments`, wired
into every role's `AGENTS.md`). Reassign explicitly between phases —
`status=todo` between phases is forbidden.

## Operator auto-memory

The operator's Claude Code session maintains an auto-memory store
alongside this repo. A fresh session should look there for current
slice status, paperclip API tokens, known library pitfalls, incident
lessons, and deploy notes. The repo itself assumes operator memory
exists but does not reference any single memory file by path.

## Mounting project repos for palace.git.*

`palace-mcp` exposes 5 read-only git tools (`palace.git.log`, `.show`,
`.blame`, `.diff`, `.ls_tree`). Each tool takes a `project` slug that
must correspond to a directory bind-mounted at `/repos/<slug>` inside
the container.

**Currently mounted projects (docker-compose.yml):**

| Slug    | Host path                     | Mount                    |
|---------|-------------------------------|--------------------------|
| `gimle` | `/Users/Shared/Ios/Gimle-Palace` | `/repos/gimle:ro`     |

**To add a new project:**
1. Add a bind-mount entry to `docker-compose.yml` under `palace-mcp.volumes`:
   ```yaml
   - /path/to/your/repo:/repos/your-slug:ro
   ```
2. Restart the `palace-mcp` container (`docker compose --profile review up -d --force-recreate palace-mcp`).
3. Optionally register the project in Neo4j via `palace.memory.register_project` so
   it appears in `palace.memory.health` without the `git_repos_unregistered` warning.

**Security notes:**
- All bind-mounts are read-only (`:ro`).
- `git` commands run with a sanitized environment (`GIT_CONFIG_NOSYSTEM=1`,
  `PATH=/usr/bin:/bin`, no `HOME` git config) — the container cannot write
  to or exfiltrate credentials from mounted repos.
- Only whitelisted git verbs (`log`, `show`, `blame`, `diff`, `ls-tree`,
  `cat-file`) are executed; write verbs are blocked at the subprocess layer.

## Pinning

When editing specs or plans, always reference the commit SHA or
branch state the artefact is grounded in — do not assume "current
develop" still means what it meant when a future reader lands here.
Cite a predecessor slice's merge SHA in spec headers.
