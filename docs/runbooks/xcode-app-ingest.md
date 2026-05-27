# Runbook: Xcode app ingestion

> See also: [Palace Operator Guide](operator-guide.md) for prerequisites,
> first-time setup, and common troubleshooting.

This runbook covers ingestion of an Xcode application repo (not a SwiftPM kit)
into palace-mcp. The canonical example is `uw-ios-app`
(`unstoppable-wallet-ios`).

Unlike kit ingestion, Xcode apps:
- Use `.xcworkspace` / `.xcodeproj` — no `Package.swift` at root.
- Require `scip_emit_uw_ios_app.sh` (or equivalent) to build the SCIP index
  with full Xcode on a dev Mac.
- Do **not** go through the artefact gate (no Periphery/swiftinterface required).

Mount convention:
- iMac host repo: `/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios`
- Container path: `/repos-hs/unstoppable-wallet-ios`

## Prerequisites

**Dev Mac:**
- Full Xcode installed (`xcode-select -p` must NOT point at CommandLineTools)
- `unstoppable-wallet-ios` checked out locally
- SSH trust to the iMac already provisioned

**iMac:**
- Gimle checkout with `docker compose` and `uv`
- `palace-mcp` reachable at `http://localhost:8080/mcp`
- `/Users/Shared/Ios/HorizontalSystems` bind-mounted into palace-mcp as `/repos-hs`

## Phase 1 — emit SCIP on the dev Mac

```bash
bash paperclips/scripts/scip_emit_uw_ios_app.sh \
  --repo-path /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --workspace Wallet.xcworkspace \
  --scheme Development \
  --remote-host imac-ssh.ant013.work \
  --remote-base /Users/Shared/Ios/HorizontalSystems
```

What it does:
- Builds the workspace with an explicit index-store path
- Invokes `palace-swift-scip-emit-cli` to write `scip/index.scip` inside the repo
- Copies that file via `scp` to the iMac replica

Dry-run (no changes):
```bash
bash paperclips/scripts/scip_emit_uw_ios_app.sh \
  --repo-path /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --dry-run
```

## Phase 2 — copy SCIP manually (if not using --remote-host)

If the remote-copy step in Phase 1 is skipped (`--no-remote-copy`), copy
the SCIP file manually:

```bash
scp /Users/ant013/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip \
    imac-ssh.ant013.work:/Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios/scip/index.scip
```

## Phase 3 — ingest on the iMac

Dry-run first to validate paths without touching state:

```bash
bash paperclips/scripts/ingest_xcode_app.sh \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --workspace Wallet.xcworkspace \
  --slug uw-ios-app \
  --dry-run
```

Live run:

```bash
bash paperclips/scripts/ingest_xcode_app.sh \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --workspace Wallet.xcworkspace \
  --slug uw-ios-app
```

With bundle membership:

```bash
bash paperclips/scripts/ingest_xcode_app.sh \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --workspace Wallet.xcworkspace \
  --slug uw-ios-app \
  --bundle uw-ios
```

What it does:
- Validates `.xcworkspace` / `.xcodeproj` present; hard-errors if `Package.swift` found
- Validates `scip/index.scip` exists and is non-empty
- Auto-derives `parent_mount=hs` from the `HorizontalSystems` path
- Merges `PALACE_SCIP_INDEX_PATHS` in `.env` with `jq`
- Recreates `palace-mcp` with the updated env
- Calls:
  - `palace.memory.register_project`
  - `palace.memory.register_bundle` (when `--bundle` is set)
  - `palace.memory.add_to_bundle` (when `--bundle` is set)
  - `palace.ingest.list_extractors`
  - `palace.ingest.run_extractor` (all 17 extractors by default)
  - `palace.memory.get_project_overview`
- Prints a final JSON summary

Custom extractor set:

```bash
bash paperclips/scripts/ingest_xcode_app.sh \
  --repo-path /Users/Shared/Ios/HorizontalSystems/unstoppable-wallet-ios \
  --slug uw-ios-app \
  --extractors symbol_index_swift,git_history,dependency_surface
```

## Phase 4 — verify

Confirm nodes are present in Neo4j:

```cypher
MATCH (n:Function {group_id:"project/uw-ios-app"})
RETURN count(n) AS fn_count
```

Expected: > 5000 for the full Wallet app.

Check multi-tenant isolation — a query against `bitcoin-core` must be
unaffected:

```cypher
MATCH (n {group_id:"project/bitcoin-core"})
RETURN count(n)
```

Should return the same count as before the ingest.

## Expected output

Dry-run ends with:

```json
{
  "stage": "dry-run",
  "status": "planned",
  "slug": "uw-ios-app",
  "parent_mount": "hs",
  "relative_path": "unstoppable-wallet-ios",
  "dry_run": true
}
```

Successful live run ends with `"status":"ok"`.  Partial failures are
`"status":"partial_failure"` with individual extractor items marked
`"status":"failed"`.

## Troubleshooting

**`Package.swift found … use ingest_swift_kit.sh instead`**
- This repo is a SwiftPM kit; use `ingest_swift_kit.sh`.

**`no .xcworkspace or .xcodeproj found`**
- Confirm the repo root has the workspace directory (not just the file inside it).
- Pass `--workspace Wallet.xcworkspace` explicitly if auto-detection fails.

**`SCIP index not found`**
- Run Phase 1 (SCIP emit) first.
- Confirm the file exists: `ls -lh <repo>/scip/index.scip`

**`SCIP index is empty`**
- The xcodebuild or emitter step failed silently. Re-run Phase 1 with verbose output.

**`palace-mcp runtime cannot see repo content`**
- On `colima`, `/Users/Shared/...` may not be shared into the VM.
- Re-run and let the script stage under `$HOME/.cache/palace/xcode-app-mounts`,
  or share the path into Colima explicitly.

**`PALACE_SCIP_INDEX_PATHS is not valid JSON`**
- Fix the `.env` line manually, then re-run.

**Extractor skipped**
- Expected when the extractor is not registered. `"reason":"not_registered"` in the summary.

**Extractor failed**
- Re-run with `--extractors symbol_index_swift` to isolate.
- Check `palace-mcp` logs: `docker compose logs palace-mcp | tail -100`

## Verification used for this slice

```bash
bash -n paperclips/scripts/ingest_xcode_app.sh
bash paperclips/scripts/ingest_xcode_app.sh --help
bash paperclips/scripts/tests/test_ingest_xcode_app.sh
```
