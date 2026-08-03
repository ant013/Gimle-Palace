# Forced full audit delivery-size recovery

Grounded in `origin/develop` at `8f59dee6abf69d4d8a1b5923f97b0a92ee54da17` and live incident `UNS-527`.

## Assumptions

- The authenticated user has authorized autonomous recovery of the Android audit delivery.
- `diff.patch` remains a required, digest-bound input for a `daily_delta`-compatible forced-full run.

## Scope

- Change only the diff-stat calculation in `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py` so it reads incrementally instead of imposing the generic 16 MiB whole-file limit.
- Add regression coverage in `paperclips/tests/test_uaudit_delivery_contract.py` for a digest-bound daily diff larger than 16 MiB.

## Acceptance criteria

- Ordinary bounded reads and all JSON/payload limits remain unchanged.
- Aggregation accepts a regular-file `diff.patch` larger than 16 MiB, preserves digest validation, and produces the deterministic summary.
- Symlink rejection and file-read errors remain fail-closed.

## Verification

- Run the focused UAudit delivery-contract tests.
- Run the full `paperclips/tests/test_uaudit_delivery_contract.py` suite and `git diff --check`.

## Open questions

- None: the failure is reproduced by the recorded 18,756,770-byte `diff.patch` in `UNS-527`.
