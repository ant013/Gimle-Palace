# GIM-262 - Audit-V1 S3 Per-Kit Ingestion Automation - Implementation Plan

**Issue:** GIM-262
**Spec:** `docs/superpowers/specs/2026-05-10-GIM-262-per-kit-ingestion-automation_spec.md`
**Branch:** `feature/GIM-262-per-kit-ingestion-automation-plan`
**Target branch:** `develop`
**Roadmap slice:** Audit-V1 S3
**Primary owner:** CXCTO for gates, CXInfraEngineer for implementation

## Operating Rules

- Keep the work in GIM-262. Do not create child issues unless there is a real
  external blocker that cannot be resolved by normal handoff.
- Every handoff comment must name the next assignee explicitly.
- If an agent completes its phase, assign the issue to the next phase owner.
- Fallback assignee is `CXCTO`.
- Do not implement S4/S5 batch ingestion in this issue.
- Do not touch unrelated watchdog or agent deployment work.

## Phase 0 - Source-Of-Truth Confirmation

**Owner:** CXCTO

- [ ] Confirm this spec and plan are the source of truth for GIM-262.
- [ ] Confirm the branch is based on current `origin/develop`.
- [ ] Resolve the four open questions in the spec or explicitly accept defaults:
  - first smoke target: small HS Kit unless operator overrides;
  - MCP call path: prefer generic `palace_mcp.cli tool call` if small, else
    script-local JSON-RPC helper;
  - repo base: follow current iMac HS mount convention;
  - unknown extractors: validate against `palace.ingest.list_extractors` when
    available, otherwise structured skip.
- [ ] Assign to `CXInfraEngineer`.

**Acceptance:** GIM-262 has a CTO comment approving implementation boundaries
and assignee is `CXInfraEngineer`.

## Phase 1 - Tooling Spike

**Owner:** CXInfraEngineer

Goal: remove ambiguity around bash-to-MCP calls before writing the orchestrator.

- [ ] Inspect `services/palace-mcp/src/palace_mcp/cli.py`.
- [ ] Choose one of:
  - extend CLI with a narrow generic MCP call surface, for example
    `python -m palace_mcp.cli tool call palace.memory.register_project --json ...`;
  - add a private helper used by the scripts to call the streamable HTTP MCP
    endpoint or JSON-RPC endpoint.
- [ ] Add focused tests if CLI code changes.
- [ ] Prove calls can reach:
  - `palace.memory.register_project`;
  - `palace.memory.add_to_bundle` or a no-bundle no-op path;
  - `palace.ingest.run_extractor`;
  - `palace.ingest.list_extractors` if used for validation.
- [ ] Commit this phase separately if code changes are needed.

**Acceptance:** implementation has one documented, tested MCP invocation
mechanism for the shell scripts.

## Phase 2 - `scip_emit_swift_kit.sh`

**Owner:** CXInfraEngineer

- [ ] Create `paperclips/scripts/scip_emit_swift_kit.sh`.
- [ ] Add `--help`.
- [ ] Validate slug with the same slug rules used by Palace projects.
- [ ] Resolve repo root from explicit flag or documented environment variable.
- [ ] Build/emit SCIP using the existing Swift SCIP emitter path.
- [ ] Copy `scip/index.scip` to the remote iMac target.
- [ ] Fail clearly when repo, build tool, emitter, SSH, or destination is
  unavailable.
- [ ] Keep defaults conservative and documented.

**Acceptance:** `bash -n` passes, `--help` works, invalid slug test fails before
path use, and at least dry-run or documented command output exists in the issue.

## Phase 3 - `ingest_swift_kit.sh`

**Owner:** CXInfraEngineer

- [ ] Create `paperclips/scripts/ingest_swift_kit.sh`.
- [ ] Add `--help`.
- [ ] Parse flags: `<kit-slug>`, `--bundle=`, `--extractors=`, `--mcp-url=`,
  `--repo-base=`, `--dry-run`.
- [ ] Preflight required host tools.
- [ ] Verify SCIP file exists before mutations.
- [ ] Merge `PALACE_SCIP_INDEX_PATHS` using `jq`.
- [ ] Write `.env` atomically.
- [ ] Recreate `palace-mcp` only when required.
- [ ] Register project idempotently.
- [ ] Add bundle membership idempotently when supplied.
- [ ] Run extractor cascade:
  - `symbol_index_swift`
  - `git_history`
  - `dependency_surface`
  - `public_api_surface`
  - `dead_symbol_binary_surface`
  - `hotspot`
  - `cross_module_contract`
  - `code_ownership`
  - `cross_repo_version_skew`
  - `crypto_domain_model`
- [ ] Continue on individual extractor failure and report final status.
- [ ] Produce a final JSON summary.

**Acceptance:** dry-run shows intended mutations without changing state; normal
run produces structured summary and never crashes on a missing extractor.

## Phase 4 - Idempotency Test And Runbook

**Owner:** CXInfraEngineer

- [ ] Add `paperclips/scripts/tests/test_ingest_idempotency.sh`.
- [ ] Test invalid slug behavior.
- [ ] Test `.env` JSON merge behavior with a temporary env file or fixture mode.
- [ ] Test second-run behavior for project/bundle operations through mocked or
  fixture-backed MCP calls where possible.
- [ ] Create `docs/runbooks/ingest-swift-kit.md`.
- [ ] Include one happy path, one dry-run path, and troubleshooting sections.

**Acceptance:** script tests pass locally or blocked live-only parts are clearly
documented with reason and alternate verification.

## Phase 5 - Implementation Review

**Owner:** CXCodeReviewer

- [ ] Review shell safety:
  - quoting;
  - `set -euo pipefail` behavior;
  - no unsafe unquoted slug/path expansion;
  - no destructive cleanup outside temp files;
  - no accidental broad Docker restart;
  - no secret leakage in logs.
- [ ] Review idempotency and failure semantics.
- [ ] Review MCP call boundaries and timeout behavior.
- [ ] Verify S3 scope only.
- [ ] Assign to `CXQAEngineer` if accepted, otherwise assign back to
  `CXInfraEngineer` with required fixes.

**Acceptance:** review comment with approve/fix list and next assignee.

## Phase 6 - QA

**Owner:** CXQAEngineer

- [ ] Run syntax checks:
  - `bash -n paperclips/scripts/scip_emit_swift_kit.sh`
  - `bash -n paperclips/scripts/ingest_swift_kit.sh`
- [ ] Run help commands.
- [ ] Run focused script tests.
- [ ] Run CLI tests if CLI was changed.
- [ ] Run one live or fixture-backed end-to-end smoke.
- [ ] Paste exact command summary and pass/fail result into GIM-262.
- [ ] Assign to `CXCTO`.

**Acceptance:** QA comment contains evidence for all acceptance criteria or a
small, explicit residual-risk list.

## Phase 7 - CTO Closeout And Merge

**Owner:** CXCTO

- [ ] Confirm S3 acceptance criteria are met.
- [ ] Confirm no S4/S5 work slipped in.
- [ ] Confirm roadmap needs either no change or a small status update.
- [ ] Merge according to Gimle branch discipline.
- [ ] Mark GIM-262 done.

**Acceptance:** code merged to `develop`, GIM-262 closed, next roadmap issue can
start at S4 smoke.

## Expected Agent Sequence

1. `CXCTO` approves spec/plan and assigns `CXInfraEngineer`.
2. `CXInfraEngineer` implements Phases 1-4 and assigns `CXCodeReviewer`.
3. `CXCodeReviewer` reviews and assigns either `CXInfraEngineer` for fixes or
   `CXQAEngineer` for verification.
4. `CXQAEngineer` verifies and assigns `CXCTO`.
5. `CXCTO` merges and closes.

No child issues are expected for this work.
