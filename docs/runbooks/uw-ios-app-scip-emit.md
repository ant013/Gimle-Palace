# UW iOS app SCIP emit — Track B runbook

## Scope (GIM-392)

The wallet app under `unstoppable-wallet-ios` is an Xcode app target, not a
SwiftPM kit, so `paperclips/scripts/scip_emit_swift_kit.sh` is the wrong
helper for it. This runbook documents the dedicated helper
`paperclips/scripts/scip_emit_uw_ios_app.sh`, which builds the app workspace
via `xcodebuild` on a Mac with full Xcode and emits SCIP from the resulting
DerivedData.

## Host requirements (Track B only)

- macOS Mac with full Xcode installed and selected
  (`xcode-select -p` must point at `/Applications/Xcode.app/...`,
  not `/Library/Developer/CommandLineTools`)
- iPhoneSimulator SDK matching the Xcode major version
- SSH access to the iMac mirror host (`imac-ssh.ant013.work` by default)

The iMac itself cannot satisfy this; full Xcode is not installable on
Intel macOS 13 (Apple dropped the Xcode 14+ upgrade path). See
`reference_imac_toolchain_limits` in operator memory.

## Default invocation

```bash
bash paperclips/scripts/scip_emit_uw_ios_app.sh \
  --repo-path /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios
```

This builds `Wallet.xcworkspace` with scheme `Development`, destination
`generic/platform=iOS Simulator`, writes DerivedData to
`<repo>/.palace-scip-derived-data-app`, emits SCIP to
`<repo>/scip/index.scip`, and copies it to
`imac-ssh.ant013.work:/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip`.

If `xcodebuild` exits non-zero only after writing index data, the helper keeps
going and emits SCIP from that populated `Index.noindex` tree.

## Live runtime evidence (2026-05-21, dev Macbook)

Operator dev Macbook, Xcode 26.3, iPhoneSimulator26.2.sdk, Swift 6.2.4,
`-destination 'generic/platform=iOS Simulator'`.

```bash
bash paperclips/scripts/scip_emit_uw_ios_app.sh \
  --repo-path /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --derived-data /tmp/uw-app-xcdd-gim392 \
  --output /tmp/gim392-scip/uw-ios-app.scip \
  --no-remote-copy
```

| Phase | Result |
|---|---|
| xcodebuild build (compile phase) | succeeded, 15235 index units, 257 MB `Index.noindex` |
| xcodebuild link phase | failed on `MoneroZano.xcframework` missing `x86_64` slice (see Known Issue below) |
| helper post-build behavior | detected populated `Index.noindex`, continued despite the non-zero `xcodebuild` exit |
| `palace-swift-scip-emit-cli` on DerivedData | succeeded, 55.8 MB SCIP, ~3 min |
| scp to iMac mirror | `/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip` |
| Total wall-clock | ~10 min (build 7:28 + emit ~3 min) |

The link-phase failure does **not** affect SCIP emit because IndexStoreDB
records are written during the swift compile phase, before linking.

## Known issues

### MoneroZano xcframework x86_64 missing

`MoneroZano.xcframework` (binary dep via `monerokit.swift`) ships only
arm64. `generic/platform=iOS Simulator` resolves to a fat target requiring
both arm64 and x86_64; the linker step fails on the missing slice. SCIP
emit succeeds regardless. To make the link phase succeed too, pass an
arm64-only destination:

```bash
--destination 'generic/platform=iOS Simulator,arch=arm64'
```

### Per-kit SCIP from the same DerivedData (bonus path)

The workspace build pulls every linked SwiftPM HS Kit into
`<derived-data>/SourcePackages/checkouts/<KitName>.Swift/`. Index units
reference source paths relative to that location. To emit a per-kit SCIP
from the workspace DerivedData, re-invoke the emitter with the SwiftPM
checkout path as `--project-root`:

```bash
EMITTER=services/palace-mcp/scip_emit_swift/.build/release/palace-swift-scip-emit-cli
DD=/tmp/uw-app-xcdd-gim392
for slug in EvmKit.Swift BitcoinCore.Swift BitcoinKit.Swift DashKit.Swift; do
  $EMITTER \
    --derived-data "$DD" \
    --project-root "$DD/SourcePackages/checkouts/$slug" \
    --output "/tmp/gim392-scip/${slug%.Swift}.scip"
done
```

In the 2026-05-21 evidence run the per-kit emit returned empty SCIP
(~100 B each) even with the SourcePackages path — this is a path-filter
edge case in `palace-swift-scip-emit-cli` and is tracked as a separate
follow-up, not blocking the app-level acceptance.

## Production mirror

After a successful Track B run, the production iMac mirror at
`/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip`
is updated and is available to palace-mcp for `uw-ios-app` bundle ingest.

The corresponding manifest entry is in
`services/palace-mcp/scripts/uw-ios-bundle-manifest.json`:

```json
{"slug": "uw-ios-app", "relative_path": "unstoppable-wallet-ios", "tier": "user"}
```
