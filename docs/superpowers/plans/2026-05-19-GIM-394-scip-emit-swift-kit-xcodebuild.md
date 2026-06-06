# GIM-394 Plan - scip_emit_swift_kit xcodebuild iOS Kits

**Issue:** GIM-394
**Branch:** `feature/GIM-394-scip-emit-swift-kit-xcodebuild`
**Status:** Phase 1.1 formalized by CXCTO; awaiting plan-first review.

## Goal

Replace the `scip_emit_swift_kit.sh` SwiftPM build path with an iOS
Simulator `xcodebuild` path so HorizontalSystems iOS-only SwiftPM kits can
produce real SCIP indexes without macOS platform fallback failures.

## Assumptions

- The target repos are SwiftPM kit repos with `Package.swift`.
- `xcodebuild` is available on the operator dev Mac where real SCIP emission
  runs.
- The kit build uses `-sdk iphonesimulator` with
  `-destination "generic/platform=iOS Simulator"`; it must not depend on a
  named simulator device being installed.
- For the named acceptance kits, default scheme inference from the repo
  directory basename works:
  - `EvmKit.Swift` -> `EvmKit`
  - `BitcoinCore.Swift` -> `BitcoinCore`
  - `DashKit.Swift` -> `DashKit`
  - `BitcoinKit.Swift` -> `BitcoinKit`
- `bitcoin-kit` stays out of the bundle manifest for this issue. Support it
  through the existing path bypass:

  ```bash
  bash paperclips/scripts/scip_emit_swift_kit.sh bitcoin-kit \
    --repo-path /Users/Shared/Ios/HorizontalSystems/BitcoinKit.Swift \
    --remote-relative-path BitcoinKit.Swift
  ```

- Sequential-thinking MCP is not available in this runtime; decomposition is
  based on the issue context, codebase-memory graph search, and focused source
  review.

## Codebase Context

- `paperclips/scripts/scip_emit_swift_kit.sh` currently creates
  `.palace-scip-index-store` with `xcrun swift build`, copies it into
  `.palace-scip-derived-data/Index.noindex/DataStore`, then invokes
  `palace-swift-scip-emit-cli --derived-data`.
- The failing part is the raw `xcrun swift build` package build. It is the only
  build step to replace for this issue.
- `paperclips/scripts/tests/test_ingest_idempotency.sh` already exercises
  invalid slug behavior for `scip_emit_swift_kit.sh`; extend shell coverage
  there or add a focused adjacent shell test.
- `docs/runbooks/ingest-swift-kit.md` describes the current SwiftPM build
  behavior and must not keep saying the script builds with raw `swift build`.

## Task 1 - Phase 1.2 plan-first review

**Owner:** CXCodeReviewer
**Dependencies:** Phase 1.1 formalization complete.
**Affected files:** this plan.

- [ ] Verify scope is limited to the emit script, focused shell tests, and
  matching runbook wording.
- [ ] Verify `bitcoin-kit` is supported by path bypass, not manifest expansion.
- [ ] Verify the plan requires real Kit evidence before merge.

**Acceptance criteria:**

- CXCodeReviewer posts plan-first APPROVE or concrete requested changes.
- If approved, the issue is handed to CXPythonEngineer for implementation.

**Verification:**

```bash
test -f docs/superpowers/plans/2026-05-19-GIM-394-scip-emit-swift-kit-xcodebuild.md
rg -n "xcodebuild|bitcoin-kit|real Kit|scip_emit_swift_kit" \
  docs/superpowers/plans/2026-05-19-GIM-394-scip-emit-swift-kit-xcodebuild.md
```

## Task 2 - Add focused dry-run coverage

**Owner:** CXPythonEngineer
**Dependencies:** Task 1 approved.
**Affected files:**

- `paperclips/scripts/tests/test_ingest_idempotency.sh` or
  `paperclips/scripts/tests/test_scip_emit_swift_kit.sh`

- [ ] Build a temporary fake SwiftPM repo with `Package.swift`.
- [ ] Mock required host commands if needed so the test is portable in CI.
- [ ] Run `scip_emit_swift_kit.sh --dry-run` against the fake repo.
- [ ] Assert dry-run output contains `xcodebuild`, `-derivedDataPath`, and
  `--derived-data`.
- [ ] Assert dry-run output no longer contains the old kit build command:
  `xcrun swift build --package-path "$LOCAL_REPO_PATH"`.
- [ ] Add a dry-run command covering `bitcoin-kit` with `--repo-path` and
  `--remote-relative-path BitcoinKit.Swift`.

**Acceptance criteria:**

- The test fails against the current script because the dry-run still prints
  the raw SwiftPM kit build.
- Invalid slug behavior remains covered.

**Verification:**

```bash
bash paperclips/scripts/tests/test_ingest_idempotency.sh
# or, if split into a new focused file:
bash paperclips/scripts/tests/test_scip_emit_swift_kit.sh
```

## Task 3 - Replace kit build with xcodebuild

**Owner:** CXPythonEngineer
**Dependencies:** Task 2 failing test.
**Affected files:**

- `paperclips/scripts/scip_emit_swift_kit.sh`

- [ ] Keep the existing emitter build step unchanged.
- [ ] Add a minimal `--scheme <name>` option, defaulting to the repo basename
  with a trailing `.Swift` suffix removed.
- [ ] Replace the kit `xcrun swift build` and manual index-store copy with:

  ```bash
  xcodebuild \
    -scheme "$SCHEME_NAME" \
    -configuration Debug \
    -sdk iphonesimulator \
    -destination "generic/platform=iOS Simulator" \
    -derivedDataPath "$DERIVED_DATA" \
    SYMROOT="$SCRATCH_PATH" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    build
  ```

- [ ] Keep `palace-swift-scip-emit-cli --derived-data "$DERIVED_DATA"` pointed
  at the xcodebuild-derived data directory.
- [ ] Remove only the obsolete standalone `INDEX_STORE` path and copy step.
- [ ] Preserve existing slug validation, repo resolution, dry-run, metadata,
  and `scp` behavior.

**Acceptance criteria:**

- `--dry-run` prints the xcodebuild command and the emitter command.
- `--dry-run` prints `-sdk iphonesimulator` and the generic simulator
  destination without a named simulator device.
- `--dry-run` does not mutate repo state.
- `--repo-path` plus `--remote-relative-path` supports `bitcoin-kit` without a
  manifest entry.
- The script still fails early on invalid slug.

**Verification:**

```bash
bash -n paperclips/scripts/scip_emit_swift_kit.sh
bash paperclips/scripts/scip_emit_swift_kit.sh --help
bash paperclips/scripts/tests/test_ingest_idempotency.sh
```

## Task 4 - Update operator wording

**Owner:** CXPythonEngineer
**Dependencies:** Task 3 complete.
**Affected files:**

- `docs/runbooks/ingest-swift-kit.md`

- [ ] Replace the current claim that `scip_emit_swift_kit.sh` builds with
  explicit index-store `swift build`.
- [ ] Document that the emit step now uses `xcodebuild` with an iOS Simulator
  destination.
- [ ] Include the `bitcoin-kit` bypass command with `--repo-path` and
  `--remote-relative-path`.

**Acceptance criteria:**

- Runbook matches script behavior.
- No broader ingest or bundle scope is added.

**Verification:**

```bash
rg -n "swift build|xcodebuild|bitcoin-kit|--remote-relative-path" \
  docs/runbooks/ingest-swift-kit.md
```

## Task 5 - Review, PR, and live evidence

**Owner:** CXCodeReviewer, CodexArchitectReviewer, CXQAEngineer, CXCTO
**Dependencies:** Tasks 2-4 complete.
**Affected files:** PR evidence and issue comments only, unless review requests
focused fixes.

- [ ] CXPythonEngineer opens PR to `develop` and includes QA Evidence.
- [ ] CXCodeReviewer runs mechanical checks and validates plan acceptance.
- [ ] CodexArchitectReviewer performs adversarial review on the xcodebuild
  boundary and script failure semantics.
- [ ] CXQAEngineer or operator captures at least one real Kit smoke, with
  BitcoinCore preferred.
- [ ] Before merge, record whether `evm-kit`, `bitcoin-core`, `dash-kit`, and
  `bitcoin-kit` each produced a non-empty `.scip`; any unavailable live run must
  be explicitly named and owned before closure.

**Acceptance criteria:**

- The PR includes evidence for:
  - `bash -n paperclips/scripts/scip_emit_swift_kit.sh`
  - help output
  - focused shell tests
  - at least one real Kit `.scip` generation and remote copy
- Final issue closure is allowed only after the remaining named Kit acceptance
  checks are either complete or split into first-class follow-up/blocker issues.

**Verification:**

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh bitcoin-core \
  --repo-root /Users/Shared/Ios/HorizontalSystems

test -s /Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift/scip/index.scip
```
