# UW iOS SCIP Emit Runtime — 2026-05-19

## Scope Decision

Issue: `GIM-376`

Board decision on 2026-05-19 reduced M1.2 acceptance to a **4-kit smoke scope**
on iMac and moved the wallet app emit path out of this slice:

- `evm-kit` → `EvmKit.Swift`
- `bitcoin-core` → `BitcoinCore.Swift`
- `bitcoin-kit` → `BitcoinKit.Swift`
- `dash-kit` → `DashKit.Swift`

`uw-ios-app` remains the main bundle goal, but it is **not** a SwiftPM kit and
cannot run through `paperclips/scripts/scip_emit_swift_kit.sh`. Board selected
option A: keep M1.2 kit-only and open a follow-up issue for an
`xcodebuild`-based app helper.

## Acceptance Used For This Slice

On iMac, acceptance evidence for M1.2 is:

1. `paperclips/scripts/scip_emit_uw_ios_bundle.sh --dry-run --scope=smoke`
   runs cleanly across the 4 approved SwiftPM kits.
2. The wrapper emits aggregate JSON with per-kit status.
3. Real wall-clock runtime for actual SCIP generation is **deferred to the
   operator dev Macbook** because iMac cannot emit Xcode/Swift indexes reliably
   under the current toolchain constraints.

## Verification Used

```bash
bash -n paperclips/scripts/scip_emit_swift_kit.sh
bash -n paperclips/scripts/scip_emit_uw_ios_bundle.sh
bash paperclips/scripts/scip_emit_uw_ios_bundle.sh --dry-run --scope=smoke
```

## iMac Smoke Command

```bash
bash paperclips/scripts/scip_emit_uw_ios_bundle.sh --dry-run --scope=smoke
```

## Measured iMac Smoke Result

The dry-run completed successfully on iMac.

```json
{
  "duration_seconds": 1,
  "meets_success_threshold": true,
  "members": [
    {
      "manifest_match": true,
      "slug": "evm-kit",
      "status": "ok"
    },
    {
      "manifest_match": true,
      "slug": "bitcoin-core",
      "status": "ok"
    },
    {
      "manifest_match": false,
      "slug": "bitcoin-kit",
      "status": "ok"
    },
    {
      "manifest_match": true,
      "slug": "dash-kit",
      "status": "ok"
    }
  ],
  "members_failed": 0,
  "members_ok": 4,
  "members_total": 4,
  "scope": "smoke"
}
```

## Interpretation

- `--scope=smoke` is functioning and targets the 4 Board-approved SwiftPM repos.
- All 4 local repos resolved and the reused per-kit helper accepted each one in
  dry-run mode.
- `bitcoin-kit` is a **manifest mismatch**: it is part of the approved smoke
  set and exists at `/Users/Shared/Ios/HorizontalSystems/BitcoinKit.Swift`, but
  it is not present in `services/palace-mcp/scripts/uw-ios-bundle-manifest.json`.
  Smoke mode records that with `"manifest_match": false` instead of silently
  dropping it.

## Track B Deferral: Real Runtime On Dev Macbook

The actual SCIP emit runtime measurement is deferred to the operator dev
Macbook. That is the correct host for real Swift/Xcode index generation.

Operator command:

```bash
bash paperclips/scripts/scip_emit_uw_ios_bundle.sh --scope=smoke
```

Expected outcome:

- emits SCIP for the 4 smoke kits;
- prints aggregate JSON summary to stdout;
- returns exit `0` when all 4 succeed.

When the operator runs the real command on the dev Macbook, append the measured
wall-clock runtime and the final JSON payload to this runbook.

## Follow-Up Required

- `uw-ios-app` requires a separate helper, e.g. `scip_emit_uw_ios_app.sh`,
  built around the Xcode workspace at
  `/Users/Shared/Ios/unstoppable-wallet-ios/UnstoppableWallet/UnstoppableWallet.xcworkspace`.
- Full-bundle inventory remains broader than this M1.2 smoke slice. The
  manifest is informational for that larger inventory, but M1.2 acceptance is
  only the 4-kit smoke scope above.
