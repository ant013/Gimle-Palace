# Gimle Palace — Developer Guide

## Branch Flow

```
feature/* → develop (PR, CodeReviewer sign-off required)
develop → main (release PR, CTO approval required)
```

**Rules:**
- All work in feature branches cut from `develop`:
  `git checkout -b feature/GIM-N origin/develop`
- PRs open against `develop`, never `main`.
- `main` holds meta (specs, plans, research, postmortems); `develop`
  holds product code + plan-files.
- Force-push to `main`/`develop` is forbidden.
- **No admin CI override on merge.** Branch protection requires all
  four checks (`lint`, `typecheck`, `test`, `docker-build`) green
  before squash-merge. Rule enforced after the GIM-48 incident — see
  `docs/postmortems/2026-04-18-GIM-48-n1a-broken-merge.md`.

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

## Pinning

When editing specs or plans, always reference the commit SHA or
branch state the artefact is grounded in — do not assume "current
develop" still means what it meant when a future reader lands here.
Cite a predecessor slice's merge SHA in spec headers.
