# CocoaPods Kit Ingest

Use this flow for HorizontalSystems libraries that ship an `Example/Podfile`
plus `Example/<Name>.xcworkspace` instead of `Package.swift`.

## Preconditions

- Full Xcode is selected:
  `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`
- `pod` is installed and available on `PATH`
- The target repo exists under `/Users/Shared/Ios/HorizontalSystems`
- `palace-mcp` is reachable from this checkout

## hd-wallet-kit-ios

This repo exposes one shared scheme, `HdWalletKitTests`, so the helper can
auto-detect it:

```bash
bash paperclips/scripts/ingest_cocoapods_kit.sh hd-wallet-kit-ios \
  --repo-base /repos-hs \
  --host-repo-base /Users/Shared/Ios/HorizontalSystems
```

What the wrapper does:

- maps repo `hd-wallet-kit-ios` to Palace project slug `hd-wallet-kit`
- runs `pod install` only in `Example/`
- builds `Example/HdWalletKit.xcworkspace` for the iOS Simulator
- emits `scip/index.scip` in the repo
- reuses `ingest_swift_kit.sh` for registration and extractor execution

## component-kit-ios

This repo has multiple shared schemes, but `ComponentKitExample` matches the
workspace heuristic and is auto-selected:

```bash
bash paperclips/scripts/ingest_cocoapods_kit.sh component-kit-ios \
  --repo-base /repos-hs \
  --host-repo-base /Users/Shared/Ios/HorizontalSystems
```

If a future CocoaPods repo exposes multiple ambiguous schemes, pass one
explicitly:

```bash
bash paperclips/scripts/ingest_cocoapods_kit.sh some-kit-ios \
  --scheme SomeKitExample
```
