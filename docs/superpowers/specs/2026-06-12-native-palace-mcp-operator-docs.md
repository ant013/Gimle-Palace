# Native palace-mcp operator docs cleanup

Grounded at `origin/develop` commit `2b0fa1b795d0b462a95ab2c1a8692639dd49952f`.

## Context

The live operator environment on this Mac is no longer the default Docker
compose `palace-mcp` + Neo4j stack:

- `palace-mcp` is launchd-managed as `work.ant013.palace-mcp-native`.
- Runtime env is read from `/Users/ant013/Android/Gimle-Palace-native/.env`.
- Neo4j is Homebrew-managed as `homebrew.mxcl.neo4j`.
- Native palace-mcp listens on `http://localhost:8765`.

The repo still contains valid Docker runbooks for iMac/server/CI/container
flows. The problem is that some operator-facing local docs and smoke helpers
still present Docker as the default for git-history and local extractor work,
which caused an incorrect recommendation to run `docker compose restart
palace-mcp` after adding `PALACE_GITHUB_TOKEN`.

## Assumptions

- Docker support remains valid for server/iMac/CI paths and must not be removed.
- Native macOS is the default for the current Apple Silicon operator machine.
- The cleanup should update actionable local-operator instructions, not
  historical specs, old plans, Paperclip baseline snapshots, or container-only
  deployment docs.
- `PALACE_GITHUB_TOKEN` remains optional and only affects git-history Phase 2
  PR/comment ingestion.

## Scope

Update current operator-facing docs/scripts so native macOS instructions are
the default where the current live environment is native:

- `docs/runbooks/git-history-harvester.md`
  - Tell operators to set `PALACE_GITHUB_TOKEN` in
    `/Users/ant013/Android/Gimle-Palace-native/.env` for native runs.
  - Replace `bash paperclips/scripts/imac-deploy.sh` restart guidance with
    `launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native`.
  - Mention Docker/iMac deployment as a separate legacy/server path, not the
    local default.
  - Use native Tantivy path examples consistent with
    `docs/runbooks/native-macos-palace-mcp.md`.

- `services/palace-mcp/scripts/smoke_git_history.py`
  - Update usage comments from `localhost:8000` Docker assumptions to native
    `localhost:8765`.
  - Point env-file guidance to the native `.env`.
  - Keep code changes minimal; if the script must remain Docker-compatible,
    prefer an env override such as `PALACE_MCP_URL` only if already consistent
    with nearby smoke helpers.

- `services/palace-mcp/scripts/smoke_code_ownership.py`
  - Apply the same native default / `PALACE_MCP_URL` override pattern so local
    extractor smoke helpers do not imply Docker compose is required.

- `docs/runbooks/native-macos-palace-mcp.md`
  - Add `PALACE_GITHUB_TOKEN=` to the sample native env block as optional.
  - Add a short note that env changes require launchd kickstart.

- `AGENTS.md`, `CLAUDE.md`, and `services/palace-mcp/README.md`
  - Make the current native macOS operator deploy path explicit.
  - Keep Docker iMac/server deployment documented as a separate path.

## Out Of Scope

- Rewriting Docker server install docs, iMac deploy scripts, CI checks,
  Docker compose profile docs, mount docs, or historical specs/plans.
- Removing Docker compose support.
- Changing extractor behavior or token handling in `palace_mcp.config`.
- Rotating or printing any real token values.

## Affected Areas

- Native operator runbooks.
- Git-history smoke helper comments and possibly configurable MCP URL.
- No database schema, MCP API, extractor logic, or deployment script behavior is
  expected to change.

## Acceptance Criteria

1. A local operator adding `PALACE_GITHUB_TOKEN` is directed to
   `/Users/ant013/Android/Gimle-Palace-native/.env`, not the repo `.env`.
2. The documented restart command for the native local service is:
   `launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native`.
3. Native health checks use `http://localhost:8765/healthz`.
4. Docker instructions remain only where the surrounding doc is explicitly
   about server/iMac/CI/container deployment.
5. A repo search for actionable git-history/native operator text no longer
   implies `docker compose restart palace-mcp` is the local default.
6. No secrets are printed, committed, or copied into docs.

## Verification Plan

- `rg -n "PALACE_GITHUB_TOKEN|git_history|docker compose.*palace-mcp|launchctl kickstart|localhost:8000|localhost:8765" docs/runbooks services/palace-mcp/scripts`
  to review remaining operator-facing guidance.
- `python -m py_compile services/palace-mcp/scripts/smoke_git_history.py` if the
  script code changes.
- If code behavior changes to support `PALACE_MCP_URL`, run the smoke script
  against the native service only after confirming the operator wants a live
  extractor run.
- No full test suite expected for documentation-only changes unless script
  behavior changes.

## Decisions

- `smoke_git_history.py` and `smoke_code_ownership.py` default to native
  `localhost:8765` and accept `PALACE_MCP_URL` for non-native runtimes.

## Open Questions

- Should `.env.example` remain Docker-specific, or should we add a separate
  `.env.native.example` for the launchd setup?
