# GIM-128 Phase 1.1 pin truth

Date: 2026-05-03

Purpose: close the Phase 1.1 reproducibility gate for the rev3 Swift emitter plan. This document records the exact external dependency pins used by `docs/superpowers/plans/2026-04-30-GIM-128-ios-swift-extractor-rev2.md`.

## Locked pins

| Dependency | Pin | Verification |
| --- | --- | --- |
| `swiftlang/indexstore-db` | `4ee7a49edc48e94361c3477623deeffb25dbed0d` | `git ls-remote https://github.com/swiftlang/indexstore-db.git HEAD refs/heads/main` returned this SHA for both `HEAD` and `refs/heads/main`. |
| `scip-code/scip` `scip.proto` | tag `v0.7.1` | `git ls-remote --tags https://github.com/scip-code/scip.git refs/tags/v0.7.1` returned `9330cbd49aeb85aee026842770a61ad28e5c4093`. Downloaded `scip.proto` sha256: `387f91bea3357a6ab72ae6214c569bf33fddcd3c726a8eacfa1435d65ac347e8`; size: `32283` bytes. |
| `apple/swift-protobuf` | exact tag `1.37.0` | `git ls-remote --tags https://github.com/apple/swift-protobuf.git refs/tags/1.37.0` returned `81558271e243f8f47dfe8e9fdd55f3c2b5413f68`. |
| Homebrew `protobuf` | stable `34.1` | `brew info --json=v2 protobuf` returned stable `34.1`. Expected `protoc --version`: `libprotoc 34.1`. |
| Homebrew `swift-protobuf` | stable `1.37.0` | `brew info --json=v2 swift-protobuf` returned stable `1.37.0`. Expected `protoc-gen-swift --version`: `1.37.0`. |

## SCIP compatibility note

The deployed Python parser is generated from the `scip-code/scip` line:

```text
services/palace-mcp/src/palace_mcp/proto/scip_pb2.py:
go_package = github.com/scip-code/scip/bindings/go/scip/
```

That rules out the older `sourcegraph/scip` `v0.5.x` recommendation from the previous plan draft. The plan now vendors `scip-code/scip` `v0.7.1`.

## IndexStoreDB runtime caveat

This iMac workspace cannot prove Xcode 26 runtime reads:

```text
swift --version -> Apple Swift version 5.8.1
xcodebuild -version -> active developer directory is CommandLineTools, not Xcode
protoc/protoc-gen-swift -> not installed
```

Therefore Phase 1.1 locks an API-compatible `indexstore-db` SHA, but Task 3 remains the hard runtime proof. If `IndexStoreDB` at `4ee7a49edc48e94361c3477623deeffb25dbed0d` returns 0 USRs on the operator's Xcode 26 `Index.noindex/DataStore` after the diagnostic checklist, implementation must stop and return to spec rev4.

## Commands used

```bash
git ls-remote https://github.com/swiftlang/indexstore-db.git HEAD refs/heads/main
git ls-remote --tags https://github.com/scip-code/scip.git refs/tags/v0.7.1
curl -fsSLo scip.proto https://raw.githubusercontent.com/scip-code/scip/v0.7.1/scip.proto
shasum -a 256 scip.proto
git ls-remote --tags https://github.com/apple/swift-protobuf.git refs/tags/1.37.0
brew info --json=v2 swift-protobuf protobuf
```
