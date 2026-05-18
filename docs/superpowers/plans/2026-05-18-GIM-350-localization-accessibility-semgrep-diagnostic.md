# GIM-350: localization_accessibility semgrep diagnostics

> **For agentic workers:** Read only your assigned step. The issue body is context, not the working spec.

**Goal:** Make `localization_accessibility` semgrep failures self-diagnostic and fix the BitcoinCore failure path.

**Branch:** `feature/GIM-350-localization-accessibility-semgrep-diagnostic`
**Grounded on:** `GIM-334` BitcoinCore smoke follow-up, live MCP container on 2026-05-18.

**Assumptions:**
- `semgrep` can emit structured error JSON on stdout even when exiting 2; stderr may be empty.
- Exit 0 and 1 remain successful for this extractor because exit 1 means findings were present.
- The BitcoinCore failure reproduced through the extractor path is caused by a symlink under `.build/checkouts/RxSwift`, not by invalid rule YAML.
- Keep this scoped to `localization_accessibility`; do not change shared extractor runner behavior unless required by tests.

**Known reproduction evidence:**

```text
FILES 2191
RC 2
STDERR_LEN 0
STDOUT_LEN 567
Invalid scanning root: /repos-hs/BitcoinCore.Swift/.build/checkouts/RxSwift/Sources/RxCocoa/RxTextViewDelegateProxy.swift is a symbolic link.
```

---

## Step 1 — Plan-first review (CXCodeReviewer)

**Owner:** CXCodeReviewer
**Status:** DONE
**Depends on:** -

**Description:**
Review this plan before implementation. Confirm the implementation scope is limited to diagnostic surfacing and excluding generated/dependency checkout paths from semgrep target enumeration.

**Acceptance criteria:**
- [x] Plan maps every GIM-350 acceptance criterion to a concrete implementation or verification step.
- [x] No scope expansion into unrelated extractors or audit/report layers.
- [x] Review comment explicitly approves or requests changes.

**Affected files:**
- `docs/superpowers/plans/2026-05-18-GIM-350-localization-accessibility-semgrep-diagnostic.md`

**Verification:**
- Paperclip plan-first approval comment from CXCodeReviewer.

---

## Step 2 — Implement diagnostic classification (CXPythonEngineer)

**Owner:** CXPythonEngineer
**Status:** DONE
**Depends on:** Step 1

**Description:**
Update `run_semgrep` so non-0/1 semgrep exits preserve useful diagnostics from both streams. Parse stdout as semgrep JSON when possible and surface `errors[].message` in the raised extractor error. Classify non-success semgrep failures into:

- `semgrep_config_invalid` for rule/config or invalid scanning-root errors.
- `semgrep_target_error` for missing/unreadable target path errors.
- `semgrep_internal_error` for timeouts, crashes, malformed output, and unclassified semgrep failures.

Use the existing extractor error flow; add the smallest helper needed if the current exception type cannot carry the differentiated code.

**Acceptance criteria:**
- [x] Empty stderr no longer produces `semgrep exited 2:` with no body when stdout contains semgrep JSON errors.
- [x] Error code is differentiated as `semgrep_config_invalid`, `semgrep_target_error`, or `semgrep_internal_error`.
- [x] Existing successful behavior for exit 0 and 1 is unchanged.

**Affected files:**
- `services/palace-mcp/src/palace_mcp/extractors/localization_accessibility/rules/semgrep_runner.py`
- `services/palace-mcp/tests/extractors/unit/test_localization_accessibility.py`

**Verification:**
- `uv run pytest tests/extractors/unit/test_localization_accessibility.py -k semgrep` → `4 passed, 30 deselected, 1 warning`

---

## Step 3 — Exclude generated/dependency checkout targets (CXPythonEngineer)

**Owner:** CXPythonEngineer
**Status:** DONE
**Depends on:** Step 2

**Description:**
Adjust semgrep file target enumeration for directory scans to skip generated dependency checkout roots that are not project source. At minimum, exclude `.build/checkouts/` so BitcoinCore does not pass symlinked Swift files to semgrep. Keep the predicate local and explicit.

**Acceptance criteria:**
- [x] `.build/checkouts/**` files are not included in semgrep target arguments.
- [x] Existing test-file exclusions still apply.
- [x] BitcoinCore no longer fails on the RxSwift symlink path.

**Affected files:**
- `services/palace-mcp/src/palace_mcp/extractors/localization_accessibility/rules/semgrep_runner.py`
- `services/palace-mcp/tests/extractors/unit/test_localization_accessibility.py`

**Verification:**
- Unit test proving `.build/checkouts/...swift` is excluded.
- Local live runner check against `/Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift` returned `OK 0`.
- Reference MCP container command for the equivalent smoke:

```bash
docker exec gimle-palace-palace-mcp-1 sh -lc 'PATH=/app/.venv/bin:$PATH python - <<PY
import asyncio
from pathlib import Path
from palace_mcp.extractors.localization_accessibility.rules.semgrep_runner import run_semgrep

async def main():
    result = await run_semgrep(
        rules_dir=Path("/app/src/palace_mcp/extractors/localization_accessibility/semgrep_rules"),
        target=Path("/repos-hs/BitcoinCore.Swift"),
        timeout_s=180,
    )
    print("OK", len(result))

asyncio.run(main())
PY'
```

---

## Step 4 — Mechanical review (CXCodeReviewer)

**Owner:** CXCodeReviewer
**Status:** IN REVIEW
**Depends on:** Step 3

**Description:**
Review the implementation PR for minimal scope, correct tests, and merge readiness. Require CI evidence before approval.

**Acceptance criteria:**
- [ ] Unit tests cover stderr-empty/stdout-error diagnostics.
- [ ] Unit tests cover `.build/checkouts` exclusion.
- [ ] `gh pr checks <PR>` is green.
- [ ] PR diff is limited to the planned files unless implementation proves another file is necessary.

**Affected files:**
- PR review only.

**Verification:**
- GitHub PR `#216` opened against `develop`.
- GitHub PR review approval plus Paperclip compliance checklist.

---

## Step 5 — Live smoke (CXQAEngineer)

**Owner:** CXQAEngineer
**Status:** TODO
**Depends on:** Step 4

**Description:**
Run a live BitcoinCore smoke against the patched container/worktree. Verify `localization_accessibility` either completes successfully or fails with a diagnostic that names the actual next action.

**Acceptance criteria:**
- [ ] Live smoke output includes the extractor result for `bitcoin-core`.
- [ ] If semgrep fails, the message includes semgrep stdout JSON error detail instead of an empty trailing colon.
- [ ] If semgrep succeeds, the smoke records completion and finding count.
- [ ] QA evidence is posted before CTO merge.

**Affected files:**
- No source files expected.

**Verification:**
- QA comment with exact command and output.

---

## Step 6 — Merge gate (CXCTO)

**Owner:** CXCTO
**Status:** TODO
**Depends on:** Step 5

**Description:**
Merge only after CI is green, CXCodeReviewer approved, branch is merge-ready, and CXQAEngineer posted live smoke evidence.

**Acceptance criteria:**
- [ ] CI green.
- [ ] CXCodeReviewer approved.
- [ ] QA evidence present.
- [ ] PR merged to `develop`.

**Affected files:**
- Merge only.

**Verification:**
- `gh pr checks <PR>`
- `gh pr view <PR> --json mergeStateStatus,reviewDecision`
