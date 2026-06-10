# GIM-1601 — dead_symbol_binary_surface Periphery Regen Path

Grounding commit: `3669b404` (`origin/develop` after GIM-1574 CX handoff fix).

## Assumptions

- `dead_symbol_binary_surface` consumes pre-generated Periphery artefacts; it
  should not invoke Periphery during extractor execution.
- GIM-1601 is limited to Periphery report and contract regeneration.
- `.swiftinterface` generation belongs to GIM-1602 and must not be required by
  the new `bench/regen-periphery.sh` entrypoint.
- Host live regeneration depends on the installed Swift/Xcode toolchain being
  compatible with the installed Periphery binary.

## Scope

- Add `bench/regen-periphery.sh <kit-slug>` as the operator entrypoint.
- Fix the existing prepare script's Periphery invocation to match the installed
  Periphery 3.7.4 CLI.
- Add `--periphery-only` to the prepare script so GIM-1601 does not mix in
  public API artefact generation.
- Document the regeneration and validation path.
- Cover the wrapper and prepare-script behavior with shell tests.

## Out Of Scope

- Generating `.swiftinterface` files.
- Changing extractor parsing, graph-write semantics, or project registration.
- Committing generated artefacts from external live clones.

## Acceptance Criteria

- `bench/regen-periphery.sh` forwards slug and options to the prepare script in
  Periphery-only mode.
- `prepare_swift_kit_artifacts.sh --periphery-only` writes only:
  - `periphery/periphery-3.7.4-swiftpm.json`
  - `periphery/contract.json`
- Dry-run path checks work against real local kit clones.
- Tests cover the new wrapper and periphery-only behavior.

## Verification Plan

- `shellcheck bench/regen-periphery.sh bench/tests/test_regen_periphery.sh paperclips/scripts/prepare_swift_kit_artifacts.sh paperclips/scripts/tests/test_prepare_artifacts.sh`
- `bash bench/tests/test_regen_periphery.sh`
- `bash paperclips/scripts/tests/test_prepare_artifacts.sh`
- Real dry-run checks for at least three locally present kits.
- One live Periphery run attempt, with exact host substrate failure recorded if
  Periphery and Swift/Xcode are incompatible.

## Open Questions

- Whether the operator host should pin a Periphery binary compatible with the
  currently selected Swift toolchain, or select/install a newer Xcode toolchain
  compatible with Periphery 3.7.4.
