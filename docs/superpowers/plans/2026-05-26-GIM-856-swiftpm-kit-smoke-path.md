# GIM-856 SwiftPM Kit Smoke Path

## Goal

Productize the HorizontalSystems Swift kit smoke path so iOS-oriented kits such as BitcoinKit.Swift do not rely on a generic macOS `swift build` path that can fail on package platform constraints before SCIP emission.

## Assumptions

- The intended kit recipe is the existing `paperclips/scripts/scip_emit_swift_kit.sh` path, not MacBook environment setup.
- Generic SwiftPM build remains useful only when the package is genuinely compatible with that host build target.
- `symbol_index_swift` should consume an explicit generated SCIP path when emission succeeds, and should fail with an actionable pre-extractor error when the recipe cannot produce one.

## Acceptance Criteria

- BitcoinKit smoke no longer fails with a macOS platform mismatch when using the intended kit recipe.
- Reports distinguish unsupported generic SwiftPM build from productized kit SCIP emission.
- Successful kit emission exposes the generated SCIP path to `symbol_index_swift`.
- A regression test covers platform mismatch handling before the extractor cascade.

## Plan

1. Confirm and encode recipe selection
   - Owner: CXCodeReviewer for plan review, then CXPythonEngineer for implementation.
   - Files: `services/palace-mcp/src/palace_mcp/cli.py`, existing runtime/recipe metadata.
   - Work: route HorizontalSystems Swift kit smoke through `scip_emit_swift_kit.sh` or an explicit documented recipe flag instead of defaulting to generic `swift build`.
   - Check: focused CLI/unit test shows BitcoinKit-style kit selects the kit SCIP recipe.

2. Add actionable platform-mismatch failure
   - Owner: CXPythonEngineer.
   - Files: project analyze CLI/reporting code and related tests.
   - Work: when generic SwiftPM build is selected for an iOS kit and platform mismatch is detected, fail before `symbol_index_swift` runs with a message that names the unsupported generic path and the kit recipe to use.
   - Check: regression fixture/test asserts the report message and no extractor cascade.

3. Wire generated SCIP path to symbol indexing
   - Owner: CXPythonEngineer.
   - Files: `paperclips/scripts/scip_emit_swift_kit.sh`, `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`, CLI settings/metadata path as needed.
   - Work: preserve or emit the generated SCIP file path in the same place `FindScipPath.resolve` expects, without adding a second indexing path.
   - Check: focused test proves a successful kit emit path is available to `symbol_index_swift`.

4. Validate and hand off through normal gates
   - Owner: CXPythonEngineer, then CXCodeReviewer, CodexArchitectReviewer, CXQAEngineer.
   - Work: run the smallest relevant test set plus the intended BitcoinKit kit-smoke command/report. Open PR to `develop`.
   - Check: PR includes `## QA Evidence` with command/report output and merged-to-develop SHA is recorded before closing GIM-856.

## Verification Commands

- `cd services/palace-mcp && uv run pytest tests/test_project_analyze_cli.py tests/extractors/unit/test_symbol_index_swift.py`
- Intended kit smoke command/report for BitcoinKit using `paperclips/scripts/scip_emit_swift_kit.sh` or the productized CLI recipe.

## Non-Goals

- Do not change MacBook host setup.
- Do not make generic macOS `swift build` the universal adapter path for iOS kits.
- Do not refactor unrelated extractor phases or SCIP parsing.
