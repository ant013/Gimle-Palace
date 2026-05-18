# GIM-262 - Audit-V1 S3 Per-Kit Ingestion Automation - Specification

**Document date:** 2026-05-10
**Status:** Draft for review
**Issue:** GIM-262
**Branch:** `feature/GIM-262-per-kit-ingestion-automation-plan`
**Companion plan:** `docs/superpowers/plans/2026-05-10-GIM-262-per-kit-ingestion-automation.md`
**Source sprint file:** `docs/superpowers/sprints/C-ingestion-automation.md`
**Roadmap slice:** Audit-V1 S3
**Target branch:** `develop`

## 1. Goal

Ship a small, operator-safe automation layer that turns one HorizontalSystems
Swift Kit into an ingest-ready Palace project with SCIP, project registration,
optional bundle membership, extractor cascade execution, health checks, and a
runbook.

Primary operator target:

```bash
bash paperclips/scripts/ingest_swift_kit.sh <kit-slug>
```

Supporting dev-Mac target:

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh <kit-slug>
```

This is the bridge from completed extractor work to S4/S5 audit smoke and scale.
The objective is to reduce per-Kit setup from manual multi-step work to a repeatable
scripted path.

## 2. Assumptions

- The operator provides SSH trust between the dev Mac and iMac before using the
  SCIP transfer script. This task does not automate host trust.
- The iMac has a Palace checkout, Docker Compose environment, and local MCP
  service matching current Gimle deployment conventions.
- Kit repositories live under an operator-known HorizontalSystems root on the
  dev Mac and are mounted or copied to an iMac path visible to `palace-mcp`.
- `symbol_index_swift`, `git_history`, `dependency_surface`,
  `public_api_surface`, `dead_symbol_binary_surface`, `hotspot`,
  `cross_module_contract`, `code_ownership`, `cross_repo_version_skew`, and
  `crypto_domain_model` are the intended S3 cascade. Missing extractors are
  structured skips, not hard script failures.
- `palace_mcp.cli` currently exists for audit subcommands, but not necessarily
  for arbitrary MCP tool calls. Implementation must verify whether to extend it
  with a generic `tool call` subcommand or use a local JSON-RPC curl helper.

## 3. Scope

In scope:

- `paperclips/scripts/scip_emit_swift_kit.sh`
  - Validate a Kit slug.
  - Locate or clone the Kit repository using explicit operator config.
  - Build enough to emit SCIP.
  - Generate `scip/index.scip`.
  - Transfer the generated index to the iMac target path.
  - Re-run idempotently by overwriting/replacing the SCIP artifact.

- `paperclips/scripts/ingest_swift_kit.sh`
  - Validate slug and required tools.
  - Verify repo mount and SCIP file presence.
  - Update `PALACE_SCIP_INDEX_PATHS` safely using `jq` and atomic file replace.
  - Recreate `palace-mcp` when config changes.
  - Register the project through MCP.
  - Optionally add the project to a bundle when `--bundle=<name>` is supplied.
  - Execute the extractor cascade with structured skip/fail summary.
  - Run final health/status checks.

- `paperclips/scripts/tests/test_ingest_idempotency.sh`
  - Exercise repeatability against a fixture or explicitly configured smoke Kit.
  - Verify the second run does not duplicate project/bundle state and preserves a
    successful summary.

- `docs/runbooks/ingest-swift-kit.md`
  - Operator setup.
  - Dev Mac command path.
  - iMac command path.
  - Troubleshooting for mount drift, missing SCIP, JSON config errors, MCP
    failures, and extractor skips.

- Minimal helper code only if needed to make scripts call MCP tools safely.

Out of scope:

- Multi-Kit batch mode.
- Automatic discovery of all 41 Kits.
- Automatic SSH trust provisioning.
- New extractor implementation.
- S4/S5 full bundle smoke.
- Broad refactor of existing MCP CLI or deployment scripts beyond the narrow
  generic call/helper needed by S3.

## 4. Affected Files And Areas

Expected new or changed files:

- `paperclips/scripts/scip_emit_swift_kit.sh`
- `paperclips/scripts/ingest_swift_kit.sh`
- `paperclips/scripts/tests/test_ingest_idempotency.sh`
- `docs/runbooks/ingest-swift-kit.md`
- Potentially `services/palace-mcp/src/palace_mcp/cli.py` if the implementation
  extends it with a generic MCP tool-call surface.
- Potentially focused CLI tests under `services/palace-mcp/tests/cli/` if the
  generic call surface is added.

Reference files:

- `docs/superpowers/sprints/C-ingestion-automation.md`
- `docs/runbooks/multi-repo-spm-ingest.md`
- `services/palace-mcp/src/palace_mcp/cli.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- Existing smoke scripts under `services/palace-mcp/scripts/`

## 5. Script Contracts

### 5.1 `scip_emit_swift_kit.sh`

Required behavior:

- Usage:

  ```bash
  bash paperclips/scripts/scip_emit_swift_kit.sh <kit-slug> \
    [--repo-root=<path>] \
    [--remote-host=<ssh-host>] \
    [--remote-base=<path>]
  ```

- Reject invalid slugs before using them in paths.
- Avoid implicit downloads unless an explicit repo URL/config is provided.
- Produce a deterministic target:

  ```text
  <repo>/scip/index.scip
  ```

- Copy the artifact to:

  ```text
  <remote-base>/<kit-slug>/scip/index.scip
  ```

- Exit non-zero on build/scip/copy failure.
- Print a concise summary with source path, destination path, and artifact size.

### 5.2 `ingest_swift_kit.sh`

Required behavior:

- Usage:

  ```bash
  bash paperclips/scripts/ingest_swift_kit.sh <kit-slug> \
    [--bundle=<bundle>] \
    [--extractors=a,b,c] \
    [--mcp-url=http://localhost:8000/mcp] \
    [--repo-base=<path>] \
    [--dry-run]
  ```

- Reject invalid slugs.
- Fail fast when required host tools are missing (`jq`, Docker Compose, Python,
  MCP caller helper).
- Confirm `<repo-base>/<kit-slug>/scip/index.scip` exists before changing MCP
  runtime state.
- Merge the slug into `PALACE_SCIP_INDEX_PATHS` as JSON, preserving existing
  entries.
- Use atomic write for `.env` update.
- Recreate `palace-mcp` only when env/config changed or when explicitly forced.
- Register project idempotently.
- Add bundle membership idempotently when requested.
- Run the cascade in fixed order unless `--extractors=` overrides it.
- Treat missing/unregistered extractors as `skipped`.
- Treat failed extractor execution as `failed` while continuing to later
  extractors unless the failure prevents later health checks.
- Print final machine-readable JSON summary plus readable log lines.

## 6. Acceptance Criteria

1. `scip_emit_swift_kit.sh --help` documents all flags and exits zero.
2. `ingest_swift_kit.sh --help` documents all flags and exits zero.
3. Invalid slugs are rejected by both scripts before path construction.
4. `.env` JSON merge preserves existing `PALACE_SCIP_INDEX_PATHS` entries.
5. Re-running `ingest_swift_kit.sh <slug>` is idempotent for project
   registration and bundle membership.
6. Missing SCIP file fails before `.env`, Docker, or MCP state changes.
7. Missing extractor names produce structured skips, not shell crashes.
8. Extractor failures are represented in the final summary with name, status,
   and error text.
9. One real or fixture-backed end-to-end smoke is documented with command output
   in the issue before close.
10. Runbook includes both happy path and troubleshooting path.

## 7. Verification Plan

Docs/spec review:

- Compare this spec and companion plan against
  `docs/superpowers/sprints/C-ingestion-automation.md`.
- Confirm no S4/S5 batch scope slipped into S3.

Local checks:

- `bash -n paperclips/scripts/scip_emit_swift_kit.sh`
- `bash -n paperclips/scripts/ingest_swift_kit.sh`
- `bash paperclips/scripts/scip_emit_swift_kit.sh --help`
- `bash paperclips/scripts/ingest_swift_kit.sh --help`
- `bash paperclips/scripts/tests/test_ingest_idempotency.sh` or a documented
  fixture substitute if the script requires iMac services.

MCP/CLI checks:

- If `palace_mcp.cli` is extended, run the focused CLI tests.
- Verify one MCP call path for `palace.memory.register_project`.
- Verify one MCP call path for `palace.ingest.list_extractors` or equivalent
  registry introspection.

Live smoke:

- Run one end-to-end Kit path on iMac/dev-Mac setup, preferably a small HS Kit.
- Capture final summary showing project registration, SCIP path, extractor
  statuses, and health check result.

## 8. Open Questions

1. Which Kit is the first live smoke target for S3: `tronkit-swift`,
   `bitcoinkit-swift`, or a smaller fixture Kit?
2. Should `ingest_swift_kit.sh` extend `palace_mcp.cli` with a generic MCP tool
   caller, or use a private script-local JSON-RPC helper?
3. What is the canonical iMac repo base for single Kit ingestion:
   `/Users/Shared/Ios/HorizontalSystems`, `/repos-hs`, or a new per-Kit mount?
4. Should `--extractors=` reject unknown extractor names up front using
   `palace.ingest.list_extractors`, or run and report skips from the MCP layer?

## 9. Review Gate

No implementation edits should start until this spec and companion plan are
reviewed in GIM-262. After approval, the implementation should stay inside one
issue unless a real external blocker appears.
