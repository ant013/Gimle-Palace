# Runbook: Per-kit Swift ingestion

This runbook covers Audit-V1 S3 single-kit ingestion for one HorizontalSystems
Swift kit. It splits the flow into:

1. dev Mac SCIP generation and transfer;
2. iMac registration + extractor cascade.

The scripts are designed for the current HorizontalSystems mount convention:

- local HS repo root on the dev Mac;
- iMac bind-mount at `/Users/Shared/Ios/HorizontalSystems`;
- container-visible path `/repos-hs/<relative_path>`.

When a slug exists in
`services/palace-mcp/scripts/uw-ios-bundle-manifest.json`, the scripts reuse the
manifest's `relative_path`, `tier`, and `parent_mount`.

## Prerequisites

- Dev Mac:
  - `xcrun`, `swift`, `ssh`, `scp`
  - repo checkout with `services/palace-mcp/scip_emit_swift`
  - SSH trust to the iMac already provisioned
- iMac:
  - Gimle checkout with `docker compose` and `uv`
  - `palace-mcp` reachable at `http://localhost:8080/mcp`
  - HorizontalSystems repos mounted into the container as `/repos-hs`
- Shared:
  - target slug matches Palace slug rules: lowercase letters, numbers, hyphens

## Dev Mac: emit and copy SCIP

Example for `tron-kit`:

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit \
  --repo-root ~/HorizontalSystems \
  --remote-host imac-ssh.ant013.work \
  --remote-base /Users/Shared/Ios/HorizontalSystems
```

What it does:

- resolves `tron-kit` to `TronKit.Swift` via the manifest when available;
- builds the SwiftPM package with an explicit index-store path;
- builds `palace-swift-scip-emit` if needed;
- writes `scip/index.scip` inside the repo;
- copies that file to the remote repo's `scip/` directory.

Dry-run:

```bash
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit \
  --repo-root ~/HorizontalSystems \
  --dry-run
```

## iMac: register and ingest

Dry-run first:

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit \
  --bundle uw-ios \
  --dry-run
```

Live run:

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit \
  --bundle uw-ios
```

What it does:

- resolves `tron-kit` to `/repos-hs/TronKit.Swift`;
- verifies `/repos-hs/TronKit.Swift/scip/index.scip` exists before mutating state;
- merges `PALACE_SCIP_INDEX_PATHS` in `.env` with `jq`;
- recreates `palace-mcp` only when the env file changed;
- calls:
  - `palace.memory.register_project`
  - `palace.memory.register_bundle` when `--bundle` is set
  - `palace.memory.add_to_bundle` when `--bundle` is set
  - `palace.ingest.list_extractors`
  - `palace.ingest.run_extractor`
  - `palace.memory.get_project_overview`
- prints a final JSON summary.

Custom extractors:

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit \
  --extractors symbol_index_swift,git_history,dependency_surface
```

## Expected output

Dry-run ends with a JSON object similar to:

```json
{
  "stage": "dry-run",
  "status": "planned",
  "slug": "tron-kit",
  "parent_mount": "hs",
  "relative_path": "TronKit.Swift",
  "dry_run": true
}
```

Successful live runs end with:

- `"status":"ok"` when all executed extractors succeed;
- `"status":"partial_failure"` when at least one extractor fails;
- individual extractor items marked `"status":"skipped"` when the extractor is
  not registered.

## Troubleshooting

`invalid slug`

- Use a lowercase Palace slug such as `tron-kit`, not a repo directory such as
  `TronKit.Swift`.

`repo mount not found`

- Confirm the iMac checkout mounts `/Users/Shared/Ios/HorizontalSystems:/repos-hs:ro`.
- If the repo is not in the manifest, pass `--relative-path <repo-dir>`.

`SCIP index not found`

- Run the dev Mac emit step first.
- Confirm the file exists on the iMac host under
  `/Users/Shared/Ios/HorizontalSystems/<relative_path>/scip/index.scip`.

`PALACE_SCIP_INDEX_PATHS is not valid JSON`

- Fix the `.env` line manually first; the script refuses ad hoc repair.

`memory.register_project failed`

- Check `palace-mcp` reachability:

```bash
curl -fsS http://localhost:8080/healthz
```

- Then inspect the JSON summary's `project_registration` payload.

Extractor skipped

- This is expected when the extractor is not currently registered. The summary
  includes `"reason":"not_registered"`.

Extractor failed

- Re-run with a smaller `--extractors` set to isolate the first failure.
- Inspect the final JSON summary and `palace-mcp` logs for the failing
  extractor's `error_code` and `message`.

## Verification used for this slice

- `bash -n paperclips/scripts/scip_emit_swift_kit.sh`
- `bash -n paperclips/scripts/ingest_swift_kit.sh`
- `bash paperclips/scripts/scip_emit_swift_kit.sh --help`
- `bash paperclips/scripts/ingest_swift_kit.sh --help`
- `bash paperclips/scripts/tests/test_ingest_idempotency.sh`

The automated test is fixture-backed and validates:

- invalid slug rejection;
- missing repo failure;
- missing SCIP failure;
- dry-run does not mutate `.env`;
- `PALACE_SCIP_INDEX_PATHS` merge is idempotent;
- second live-style run does not trigger a second `palace-mcp` restart when the
  env entry is already present.
