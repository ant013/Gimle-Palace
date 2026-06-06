# GIM-947 Plan - Smooth iOS Library Onboarding

**Issue:** [GIM-947](/GIM/issues/GIM-947)
**Status:** Phase 1.1 formalized by CXCTO; awaiting plan-first review.
**Target branch:** `develop`
**Primary owner:** CXCTO for orchestration, CXInfraEngineer and CXPythonEngineer for implementation tasks.

## Goal

Make a fresh iOS library ingestible with one operator command:

```bash
palace ingest <github-url>
```

The command must clone or reuse the repo, resolve the Palace slug and repo
layout, emit SCIP, run the ingest cascade, register the project, embed useful
symbols, verify the graph state, and print a concise success summary.

## Assumptions

- The final user-facing command is `palace ingest <github-url>`. A shell script
  can be used internally, but final acceptance requires either a CLI subcommand
  or a documented executable named `palace` that exposes this command shape.
- HorizontalSystems SwiftPM kit repos follow the existing
  `/Users/Shared/Ios/HorizontalSystems/<KitName.Swift>` convention.
- CocoaPods/Xcode-only kits use an `Example/Podfile` plus
  `Example/<Name>.xcworkspace` layout unless the implementing issue proves a
  narrower, documented convention.
- `project analyze` already registers projects through
  `ProjectAnalysisService.start_run`; this epic must avoid duplicating that
  registration when using the Python orchestrator path.
- The legacy shell ingest path still needs explicit project registration if it
  remains part of the final command chain.
- Sequential-thinking MCP was not available in this runtime; decomposition is
  based on the issue context, codebase-memory graph search, and focused source
  review.

## Codebase Context

- `services/palace-mcp/src/palace_mcp/cli.py` currently exposes
  `project analyze`, not a top-level `ingest` command.
- `ProjectAnalysisService.start_run` already performs schema setup and
  `register_project` before storing the durable run.
- `_build_macbook_fallback_command` routes `uw-ios-app` to
  `scip_emit_uw_ios_app.sh` and other Swift projects to
  `scip_emit_swift_kit.sh`.
- `paperclips/scripts/ingest_swift_kit.sh` has a reusable `call_mcp` helper for
  invoking Palace MCP tools from shell.
- Existing child issues already cover the five implementation slices:
  [GIM-948](/GIM/issues/GIM-948), [GIM-949](/GIM/issues/GIM-949),
  [GIM-950](/GIM/issues/GIM-950), [GIM-951](/GIM/issues/GIM-951), and
  [GIM-952](/GIM/issues/GIM-952).
- [GIM-945](/GIM/issues/GIM-945) remains the Docker cache ownership prerequisite
  for reliable post-recreate embedding.

## Acceptance Criteria

- `palace ingest <github-url>` works for a fresh SwiftPM kit URL with zero
  follow-up operator commands.
- `palace ingest <github-url>` works for a fresh CocoaPods/Xcode-only kit URL
  with zero follow-up operator commands.
- The command registers the project before extractor or embedding work needs the
  `:Project` node.
- The command verifies a non-empty project graph: symbols `> 0`, successful
  required ingest phases, and embeddings `> 100` for projects with enough Swift
  symbol corpus.
- Extractors that are not applicable to Swift libraries are reported as
  structured `N/A` with a reason; applicable extractors must not silently return
  empty success.
- Final QA evidence includes one SwiftPM kit smoke and one CocoaPods/Xcode-only
  kit smoke from a fresh clone path.

## Task 1 - Plan-first review

**Owner:** CXCodeReviewer
**Dependencies:** This plan file exists.
**Affected files:** this plan.

- [ ] Verify the plan maps every child issue to a concrete acceptance check.
- [ ] Verify final command acceptance is not weakened from `palace ingest
  <github-url>` to a multi-command runbook.
- [ ] Verify final glue waits for all real prerequisites.

**Acceptance criteria:**

- CXCodeReviewer posts plan-first APPROVE or concrete requested changes on
  [GIM-947](/GIM/issues/GIM-947).

**Verification:**

```bash
test -f docs/superpowers/plans/2026-05-28-GIM-947-smooth-ios-library-onboarding.md
rg -n "palace ingest|GIM-948|GIM-952|CocoaPods|embedding" \
  docs/superpowers/plans/2026-05-28-GIM-947-smooth-ios-library-onboarding.md
```

## Task 2 - Auto-clone and slug-to-directory resolution

**Owner:** CXInfraEngineer
**Issue:** [GIM-948](/GIM/issues/GIM-948)
**Dependencies:** none.
**Affected paths:**

- `paperclips/scripts/prepare_repo.sh` or a narrowly named adjacent script
- focused shell tests under `paperclips/scripts/tests/`
- runbook wording only if needed

- [ ] Given a GitHub URL, clone into the HorizontalSystems base path if missing.
- [ ] Derive the Palace slug from the repository or kit directory convention.
- [ ] Create or refresh the slug symlink idempotently.
- [ ] Print machine-readable resolved values for downstream chaining.

**Acceptance criteria:**

- Fresh MarketKit-style URL produces repo path plus slug symlink.
- Re-running is a no-op except for safe symlink refresh.
- Invalid or unsupported URLs fail before filesystem mutation.

**Verification:**

```bash
bash -n paperclips/scripts/prepare_repo.sh
bash paperclips/scripts/prepare_repo.sh --help
bash paperclips/scripts/tests/test_prepare_repo.sh
```

## Task 3 - Register projects from the shell ingest path

**Owner:** CXPythonEngineer
**Issue:** [GIM-949](/GIM/issues/GIM-949)
**Dependencies:** none.
**Affected paths:**

- `paperclips/scripts/ingest_swift_kit.sh`
- `paperclips/scripts/tests/test_ingest_idempotency.sh` or adjacent focused test
- possibly `docs/runbooks/ingest-swift-kit.md`

- [ ] Add one idempotent `palace.memory.register_project` call before extractor
  execution when the shell path is used.
- [ ] Pass slug, name, language, parent mount, relative path, and repo URL when
  available.
- [ ] Avoid a second registration path when `project analyze` already performs
  registration.

**Acceptance criteria:**

- Fresh shell ingest creates the `:Project` node before embedding.
- `palace.memory.list_projects` returns the new slug.
- `embedding_symbol` no longer fails with `project_not_registered` for the
  newly ingested kit.

**Verification:**

```bash
bash -n paperclips/scripts/ingest_swift_kit.sh
bash paperclips/scripts/tests/test_ingest_idempotency.sh
cd services/palace-mcp && uv run pytest tests/test_project_analyze.py tests/test_project_analyze_cli.py
```

## Task 4 - Make `embedding_symbol` kit-friendly

**Owner:** CXPythonEngineer
**Issue:** [GIM-950](/GIM/issues/GIM-950)
**Dependencies:** none.
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py`
- focused embedding extractor tests under `services/palace-mcp/tests/`
- related profile or candidate-selection helpers if the existing extractor uses
  shared selection code

- [ ] Reproduce the zero-node success for a SwiftPM kit fixture or mocked graph.
- [ ] Change candidate selection so useful kit symbols qualify, or split a
  clearly named kit mode if a single selector would degrade app behavior.
- [ ] Preserve current `uw-ios-app` behavior.

**Acceptance criteria:**

- SwiftPM kit fixture writes `nodes_written > 0`.
- Existing app fixture still writes the expected app candidates.
- Empty-success is only allowed when the report includes a structured reason.

**Verification:**

```bash
cd services/palace-mcp && uv run pytest tests/embeddings tests/extractors/unit/test_embedding_symbol.py
```

## Task 5 - Add CocoaPods/Xcode-only kit ingestion

**Owner:** CXInfraEngineer
**Issue:** [GIM-951](/GIM/issues/GIM-951)
**Dependencies:** none, but coordinate registration behavior with
[GIM-949](/GIM/issues/GIM-949).
**Affected paths:**

- new `paperclips/scripts/scip_emit_cocoapods_kit.sh` or equivalent minimal
  extension to an existing Xcode ingest script
- new or updated ingest wrapper for CocoaPods/Xcode-only kits
- focused shell tests under `paperclips/scripts/tests/`
- runbook covering `hd-wallet-kit-ios` and `component-kit-ios`

- [ ] Detect the standard `Example/Podfile` and workspace layout.
- [ ] Run `pod install` only in the intended Podfile directory.
- [ ] Build with `xcodebuild` for iOS Simulator and emit SCIP from derived data.
- [ ] Feed the generated SCIP into the same ingest and registration path as
  SwiftPM kits.

**Acceptance criteria:**

- `hd-wallet-kit-ios` can produce SCIP, ingest, register, and verify from the
  CocoaPods/Xcode path.
- `component-kit-ios` is either verified or explicitly blocked by a concrete
  repo-layout mismatch captured in its issue.

**Verification:**

```bash
bash -n paperclips/scripts/scip_emit_cocoapods_kit.sh
bash paperclips/scripts/scip_emit_cocoapods_kit.sh --help
bash paperclips/scripts/tests/test_cocoapods_kit_ingest.sh
```

## Task 6 - Docker cache ownership prerequisite

**Owner:** CXPythonEngineer
**Issue:** [GIM-945](/GIM/issues/GIM-945)
**Dependencies:** existing workspace switch blocker on that issue.
**Affected paths:** `services/palace-mcp/Dockerfile` or compose/runtime setup.

- [ ] Ensure `/data/hf-cache` is writable by the runtime app user after a volume
  recreate.
- [ ] Keep the fix in [GIM-945](/GIM/issues/GIM-945); do not duplicate it in
  this epic.

**Acceptance criteria:**

- A recreated Palace runtime can run embedding without manual `docker exec
  chown`.

**Verification:**

```bash
docker compose down -v palace-mcp
docker compose up -d palace-mcp
docker compose exec palace-mcp test -w /data/hf-cache
```

## Task 7 - Final one-command glue

**Owner:** CXInfraEngineer
**Issue:** [GIM-952](/GIM/issues/GIM-952)
**Dependencies:** [GIM-948](/GIM/issues/GIM-948),
[GIM-949](/GIM/issues/GIM-949), [GIM-950](/GIM/issues/GIM-950),
[GIM-951](/GIM/issues/GIM-951), and [GIM-945](/GIM/issues/GIM-945).
**Affected paths:**

- `services/palace-mcp/src/palace_mcp/cli.py` for `palace ingest`, or a
  documented executable shim plus tests
- `paperclips/scripts/palace_ingest.sh` only if used as the internal
  orchestrator
- focused CLI/shell integration tests
- final runbook update

- [ ] Expose the final one-command entry point.
- [ ] Chain repo preparation, recipe detection, SCIP emission, ingest,
  registration, embedding, and verification.
- [ ] Print `<slug>: ingested N symbols, M embeddings, K extractors OK`.
- [ ] Fail with a clear next action when a library layout is unsupported.

**Acceptance criteria:**

- Fresh SwiftPM URL succeeds with no extra operator command.
- Fresh CocoaPods/Xcode-only URL succeeds with no extra operator command.
- Summary includes symbol count, embedding count, and extractor status.

**Verification:**

```bash
cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py
bash paperclips/scripts/palace_ingest.sh --help
palace ingest https://github.com/horizontalsystems/MarketKit.Swift
palace ingest https://github.com/horizontalsystems/hd-wallet-kit-ios
```

## Task 8 - Review, QA, and CTO closeout

**Owner:** CXCodeReviewer, CodexArchitectReviewer, CXQAEngineer, CXCTO
**Dependencies:** Tasks 2 through 7 merged or ready in one PR chain.
**Affected paths:** PR evidence and issue comments; code only for review fixes.

- [ ] CXCodeReviewer performs mechanical review with required checks and plan
  acceptance mapping.
- [ ] CodexArchitectReviewer performs adversarial review on command boundaries,
  script idempotency, and unsupported-layout behavior.
- [ ] CXQAEngineer runs live smoke for one SwiftPM kit and one CocoaPods/Xcode
  kit from a fresh clone path.
- [ ] CXCTO merges only after CR approve, QA pass, and green required checks.

**Acceptance criteria:**

- PR evidence maps back to every [GIM-947](/GIM/issues/GIM-947) acceptance
  criterion.
- No child issue remains open unless it is explicitly split out and the umbrella
  acceptance is narrowed by Board approval.

**Verification:**

```bash
gh pr checks <PR>
gh pr diff <PR> | grep -E '^(<<<<<<<|=======|>>>>>>>)'
```

## Dependency Graph

- [GIM-948](/GIM/issues/GIM-948), [GIM-949](/GIM/issues/GIM-949),
  [GIM-950](/GIM/issues/GIM-950), and [GIM-951](/GIM/issues/GIM-951) can run in
  parallel.
- [GIM-945](/GIM/issues/GIM-945) is independent, but final embedding acceptance
  depends on it.
- [GIM-952](/GIM/issues/GIM-952) is blocked by all four feature subtasks plus
  [GIM-945](/GIM/issues/GIM-945).
- [GIM-947](/GIM/issues/GIM-947) closes only after [GIM-952](/GIM/issues/GIM-952)
  has live QA evidence for both library families.

## Non-Goals

- Do not broaden the epic into general multi-language repository onboarding.
- Do not require manual post-command `register_project`, `chown`, symlink, or
  embedding commands.
- Do not hide unsupported extractors behind successful zero-node reports.
- Do not replace existing `project analyze` durable run semantics unless the
  final command deliberately delegates to them.
