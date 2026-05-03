# uw-ios-mini-project — Fixture Regen Instructions

## Status

This directory is the repo-side scaffold for the GIM-128 iOS Swift fixture.
The actual mini-project sources and `scip/index.scip` still need to be generated
on a dev Mac with modern Xcode. Until then, the real-fixture tests skip safely.

## Source

- Repository: `https://github.com/horizontalsystems/unstoppable-wallet-ios`
- Branch tracked: `master`
- License: MIT

## Toolchain pins

Pinned in [docs/research/2026-05-03-gim-128-phase-1-1-pin-truth.md](/private/tmp/gim128-worktree/docs/research/2026-05-03-gim-128-phase-1-1-pin-truth.md):

- `swiftlang/indexstore-db` revision `4ee7a49edc48e94361c3477623deeffb25dbed0d`
- `scip-code/scip` tag `v0.7.1`
- `apple/swift-protobuf` `1.37.0`
- `protoc` `34.1`
- `protoc-gen-swift` `1.37.0`

## Expected outputs

- Fixture source tree under this directory
- Committed binary SCIP at `scip/index.scip`
- Oracle counts and branch notes added back into this file after the first successful regen
- Handoff evidence capturing the exact toolchain versions and regenerated files

## Dev-Mac regen flow

1. Build the Swift emitter:

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift build -c release
```

2. Stage the fixture source tree in this directory.

3. From this directory, run:

```bash
bash regen.sh
```

4. Verify `scip/index.scip` parses through the Python parser and update this file with:

- document count
- DEF count
- USE count
- vendor-use count
- generated-code branch (`A` or `B-2`)
- any pinned upstream commit/SHA used for vendored mini-project files

## Handoff evidence checklist

Include these exact facts in the issue/PR handoff comment for the regen pass:

- `git rev-parse HEAD` for the repo commit that produced the artifact
- `protoc --version` and confirm it is `libprotoc 34.1`
- `protoc-gen-swift --version` and confirm it is `1.37.0`
- confirm `services/palace-mcp/scip_emit_swift/Package.swift` still pins `apple/swift-protobuf` to exact `1.37.0`
- list which files were regenerated or verified:
  - `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip`
  - `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md`
  - any staged fixture source files added under `uw-ios-mini-project/`

## Operator note

This runner cannot complete the dev-Mac proof:

- `swift --version` is `5.8.1`
- `xcrun swift test` fails because the active command-line tools install cannot resolve a usable macOS SDK platform path
- `protoc` and `protoc-gen-swift` are not installed here

Use a dev Mac with current Xcode for the actual fixture generation pass.
