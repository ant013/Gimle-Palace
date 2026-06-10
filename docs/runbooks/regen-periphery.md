# Runbook: regenerate Periphery fixtures for `dead_symbol_binary_surface`

Use this when a Swift kit reports:

```text
RUN_FAILED
error_code=periphery_fixtures_missing
```

The supported operator entrypoint is:

```bash
bash bench/regen-periphery.sh <kit-slug>
```

This wrapper delegates to
`paperclips/scripts/prepare_swift_kit_artifacts.sh`, so it refreshes both:

- `periphery/periphery-3.7.4-swiftpm.json`
- `periphery/contract.json`

and the paired `.swiftinterface` artefacts that the Swift-kit ingest path keeps
in sync.

## Prerequisites

1. Full Xcode must be installed and selected. Command Line Tools alone are not
   enough for these iOS kits.

   ```bash
   xcodebuild -version
   xcode-select -p
   ```

2. Periphery must be on `PATH`.

   ```bash
   periphery version
   ```

3. The HorizontalSystems repos must exist under the configured repo base
   (default: `/Users/Shared/Ios/HorizontalSystems`).

   ```bash
   ls /Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift
   ```

## Regenerate fixtures

Examples:

```bash
bash bench/regen-periphery.sh bitcoin-core
bash bench/regen-periphery.sh dash-kit
bash bench/regen-periphery.sh litecoin-kit
```

Useful options:

```bash
# Validate resolution only
bash bench/regen-periphery.sh bitcoin-core --dry-run

# Override repo base if the kits live elsewhere
bash bench/regen-periphery.sh bitcoin-core --repo-base /absolute/base/path
```

## File-level verification

After each run, verify the Periphery files exist:

```bash
repo=/Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift
test -f "$repo/periphery/periphery-3.7.4-swiftpm.json"
test -f "$repo/periphery/contract.json"
jq -r '.tool_output_schema_version' "$repo/periphery/contract.json"
```

Expected:

- the JSON report exists;
- `contract.json` exists;
- `tool_output_schema_version` matches `periphery-json-X.Y.Z`.

## Re-run `palace project analyze`

Re-run analysis after regen to confirm `dead_symbol_binary_surface` no longer
fails on missing input:

```bash
cd services/palace-mcp
uv run python -m palace_mcp.cli project analyze \
  --repo-path /Users/Shared/Ios/HorizontalSystems/BitcoinCore.Swift \
  --slug bitcoin-core \
  --language-profile swift_kit \
  --depth quick \
  --report-out /tmp/bitcoin-core-report.md \
  --summary-out /tmp/bitcoin-core-summary.json
```

Then inspect the outputs:

```bash
sed -n '1,80p' /tmp/bitcoin-core-summary.json
rg -n "dead_symbol_binary_surface|periphery_fixtures_missing|DeadFinding" /tmp/bitcoin-core-report.md /tmp/bitcoin-core-summary.json
```

Success criteria for this defect:

- `dead_symbol_binary_surface` does not report `periphery_fixtures_missing`;
- at least one regenerated kit produces `:DeadFinding` data;
- rerunning the wrapper after source changes refreshes both the report and
  contract files in place.

## Failure modes

- `error: Unknown option '--project-root'`
  The old Periphery CLI invocation is stale. Use the current repo version of
  `prepare_swift_kit_artifacts.sh`.

- `xcode-select: error: tool 'xcodebuild' requires Xcode`
  Full Xcode is missing or not selected. Install/select Xcode, then rerun.

- `swift package describe` or `periphery scan` exits non-zero
  Treat this as substrate/tooling failure first: fix Xcode selection, package
  resolution, or repo health before blaming the extractor.
