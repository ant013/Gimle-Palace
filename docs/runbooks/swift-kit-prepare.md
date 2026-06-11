# Runbook: Swift kit artefact preparation

Covers running `prepare_swift_kit_artifacts.sh` to produce the artefacts that
the palace-mcp extractor cascade requires before ingest.

## Why this exists

`ingest_swift_kit.sh` runs an extractor gate that rejects kits missing their
required artefacts:

| Artefact | Required by extractor |
|---|---|
| `periphery/periphery-3.7.4-swiftpm.json` | `dead_symbol_binary_surface` |
| `periphery/contract.json` | `dead_symbol_binary_surface` |
| `.palace/public-api/swift/*.swiftinterface` | `public_api_surface` |

Run the prepare script once per kit before the first ingest, and re-run
whenever a new Periphery scan or updated interface snapshot is needed.

## Prerequisites

### Periphery

Install Periphery on the Mac where the kit repos live:

```bash
# Homebrew (recommended)
brew install periphery

# Or direct download from GitHub releases
curl -L https://github.com/peripheryapp/periphery/releases/download/3.7.4/periphery.zip \
  -o /tmp/periphery.zip
unzip /tmp/periphery.zip -d /usr/local/bin/
chmod +x /usr/local/bin/periphery
```

Verify:

```bash
periphery version
# Periphery 3.7.4
```

### Xcode command-line tools

Swiftinterface emission requires `xcrun` and `swift build`. Full Xcode or
Command Line Tools are both sufficient.

```bash
xcode-select -p  # should point at Xcode.app or CLT path
xcrun swift --version
```

### Package.swift settings

The kit must be a valid SwiftPM package with at least one library target.
Swiftinterface files are only emitted for `library` products, not executables.

If `.swiftinterface` emission fails, check:

1. Package has `products: [ .library(name: ..., targets: [...]) ]`
2. Swift tools version ≥ 5.4 (required for stable library evolution support)
3. No fatal build errors beyond link-phase failures (link failures are OK —
   the compiler emits interfaces during the compile phase before linking)

## Running the prepare script

### By slug (manifest lookup)

```bash
bash paperclips/scripts/prepare_swift_kit_artifacts.sh \
  --slug bitcoin-core
```

Resolves `bitcoin-core` → `BitcoinCore.Swift` via the manifest, then uses
`PALACE_SWIFT_KIT_HOST_REPO_BASE`
(default: `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`) as the base.

### By explicit path

```bash
bash paperclips/scripts/prepare_swift_kit_artifacts.sh \
  --repo-path /Users/Shared/Ios/Gimle-Repos/HorizontalSystems/BitcoinCore.Swift
```

### Dry-run (validate without mutating)

```bash
bash paperclips/scripts/prepare_swift_kit_artifacts.sh \
  --repo-path /path/to/Kit.Swift \
  --dry-run
```

### Refresh only public API snapshots

Use the bench wrapper when only `public_api_surface` inputs need regeneration:

```bash
bash bench/regen-public-api.sh evm-kit
```

This calls `prepare_swift_kit_artifacts.sh --public-api-only`, so it skips
Periphery and refreshes only:

```text
.palace/public-api/swift/*.swiftinterface
```

Dry-run a kit without mutating it:

```bash
bash bench/regen-public-api.sh evm-kit --dry-run
```

Use `bench/regen-periphery.sh` for the opposite focused path: refreshing only
the Periphery report and contract without touching `.swiftinterface` files.

For iOS-only Swift packages, the script first tries the SwiftPM build path and
then falls back to an Xcode iOS Simulator build:

```text
xcodebuild -scheme <library> \
  -destination "generic/platform=iOS Simulator" \
  SWIFT_EMIT_MODULE_INTERFACE=YES \
  ONLY_ACTIVE_ARCH=YES ARCHS=arm64
```

This fallback avoids macOS platform constraint failures from `swift build` and
does not enable full `BUILD_LIBRARY_FOR_DISTRIBUTION`, which can fail inside
third-party dependencies before the root kit emits its interface.

## Output artefacts

After a successful run, the following files are written into the kit repo:

```
BitcoinCore.Swift/
  periphery/
    contract.json                     ← Periphery run metadata
    periphery-3.7.4-swiftpm.json      ← Dead-symbol scan results
  .palace/
    public-api/
      swift/
        BitcoinCore.swiftinterface    ← Module interface snapshot(s)
```

The `contract.json` captures the actual Periphery version used and sets
`tool_output_schema_version` to `"periphery-json-<version>"`. The ingest gate
validates this field on every run.

## Per-artefact troubleshooting

### Periphery scan fails

**Symptom:** `periphery scan` exits non-zero.

**Common causes and fixes:**

| Cause | Fix |
|---|---|
| Package has unresolvable dependencies | `swift package resolve` first |
| Xcode scheme not generated | `xcrun xcodebuild -list -package-path .` once |
| `Package.resolved` out of date | Delete and re-resolve |
| Missing SDK (iOS-only package on macOS) | Add `--skip-build` flag to periphery or build with iOS Simulator SDK |

Full Periphery scan command (for manual diagnosis):

```bash
cd /path/to/Kit.Swift
periphery scan \
  --quiet \
  --format json \
  --disable-update-check \
  > periphery/periphery-3.7.4-swiftpm.json
```

### contract.json schema_version rejected

**Symptom:** ingest exits with `tool_output_schema_version '...' is not valid`.

**Cause:** Either an integer value (old format, pre-GIM-757) or a malformed
string.

**Fix:** Re-run `prepare_swift_kit_artifacts.sh` which writes
`"periphery-json-<version>"` in the correct string format.

### No .swiftinterface files emitted

**Symptom:** prepare script exits `no .swiftinterface files emitted`.

**Diagnosis steps:**

1. Confirm the package has at least one `.library` product:

   ```bash
   grep -A 5 'products:' Package.swift
   ```

2. Try a manual build with verbose output:

   ```bash
   xcrun swift build -c release -Xswiftc -enable-library-evolution -v 2>&1 | head -50
   ```

3. Check `.build/release/` for `*.swiftinterface` files — if they exist but
   the script missed them, open an issue (the search uses `find` with `-name`).

4. For iOS-only packages that fail to build on macOS without a simulator:
   use `bench/regen-public-api.sh`. It falls back to an Xcode iOS Simulator
   build and copies the root package `.swiftinterface` automatically.

5. If the package scheme name differs from the library target name, override it:

   ```bash
   PALACE_SWIFT_KIT_XCODEBUILD_SCHEME=CustomScheme \
     bash bench/regen-public-api.sh evm-kit
   ```

### Artefacts exist but ingest gate still fails

**Symptom:** `ingest_swift_kit.sh` fails the artefact gate even though
`prepare_swift_kit_artifacts.sh` ran successfully.

**Possible cause:** `--host-repo-base` points to a different path than where
the prepare script wrote artefacts.

```bash
# Verify paths match
ls /Users/Shared/Ios/Gimle-Repos/HorizontalSystems/BitcoinCore.Swift/periphery/
ls /Users/Shared/Ios/Gimle-Repos/HorizontalSystems/BitcoinCore.Swift/.palace/public-api/swift/
```

Use `--skip-artefact-check` as a temporary escape hatch while investigating:

```bash
bash paperclips/scripts/ingest_swift_kit.sh bitcoin-core --skip-artefact-check
```

## Re-running after a Periphery upgrade

When Periphery is upgraded, the `tool_output_schema_version` in `contract.json`
changes (e.g., `periphery-json-3.7.4` → `periphery-json-3.9.0`). The ingest
gate validates the format, not a specific version, so any `periphery-json-X.Y.Z`
string passes.

Re-run the prepare script after upgrading to refresh both the scan results and
the contract.json metadata.

## Related scripts

- `paperclips/scripts/scip_emit_swift_kit.sh` — SCIP index emission (separate step)
- `bench/regen-public-api.sh` — focused `.swiftinterface` regeneration
- `bench/regen-periphery.sh` — focused Periphery artifact regeneration
- `paperclips/scripts/ingest_swift_kit.sh` — full ingest (runs extractors)
- `docs/runbooks/ingest-swift-kit.md` — end-to-end ingest runbook
- `docs/runbooks/dead-symbol-binary-surface.md` — extractor internals
