# GIM-1602 — public_api_surface `.swiftinterface` generation

Grounded in `origin/develop` at `204e0fa6a88a019617b3b00418223f9edc4a392e`.

## Assumptions

- GIM-1601 is complete, so DEFECT-6 is the only active child in the GIM-1574 walker sequence.
- `public_api_surface` ingestion already reads `.palace/public-api/swift/*.swiftinterface`; the missing piece is an operator wrapper that generates those artifacts per Swift kit.
- The existing `prepare_swift_kit_artifacts.sh` remains the canonical implementation for artifact preparation.

## Scope

- Add a public-API-only mode to the Swift kit artifact preparation script.
- Add `bench/regen-public-api.sh` as a thin operator wrapper for one kit slug.
- Add shell tests for wrapper argument forwarding and mode behavior.
- Update runbooks with the targeted regeneration path and troubleshooting notes.

## Affected Areas

- `paperclips/scripts/prepare_swift_kit_artifacts.sh`
- `paperclips/scripts/tests/test_prepare_artifacts.sh`
- `bench/regen-public-api.sh`
- `bench/tests/test_regen_public_api.sh`
- `docs/runbooks/swift-kit-prepare.md`
- `docs/runbooks/public-api-surface.md`

## Acceptance Criteria

- `bash bench/regen-public-api.sh evm-kit --dry-run` resolves the kit and prints `.swiftinterface` generation actions without Periphery work.
- A real run on a Swift kit writes one or more files under `.palace/public-api/swift/`, or fails with a concrete Swift/toolchain/build reason without clobbering unrelated artifacts.
- Existing Periphery-only behavior from GIM-1601 remains unchanged.
- Local shell tests pass for the prepare script and both bench wrappers.

## Verification Plan

- `shellcheck` on touched shell scripts when available.
- `bash bench/tests/test_regen_public_api.sh`
- `bash bench/tests/test_regen_periphery.sh`
- `bash paperclips/scripts/tests/test_prepare_artifacts.sh`
- Dry-run smoke for `bench/regen-public-api.sh evm-kit --dry-run`.
- Real operator smoke on an available Swift kit if host dependencies permit.

## Open Questions

- Some HorizontalSystems kits may require explicit Xcode toolchain path or iOS platform settings. If a real kit fails for package constraints, capture the exact failure and keep the script behavior deterministic.
