# Runbook: uw-ios-baseline first ingest

Grounded in `origin/develop` plan `docs/superpowers/plans/2026-06-06-GIM-1500-palace-mcp-namespace-unification.md` at `87ec642d5a7d1faa169eb5ad58f917cac778ccaf`.

## Scope

This runbook records the real first-ingest command for the already-registered
`uw-ios-baseline` project.

- Slug: `uw-ios-baseline`
- Registry values: `parent_mount=baseline`, `relative_path=uw-baseline-871c0e8`
- MCP URL assumption: `http://localhost:8080/mcp`

## Required assumptions

- Run from the Gimle Palace repo root on the iMac with the repo `.env` file in place.
- `palace-mcp` is reachable at `http://localhost:8080/mcp`.
- The baseline mirror is bind-mounted into the container as `/repos-baseline:ro`.
- The host-side baseline repo exists at
  `<host-base>/uw-baseline-871c0e8` and already contains `scip/index.scip`.

If the host bind source is not `/Users/Shared/Ios/baseline`, keep the same
container path `/repos-baseline` and change only `HOST_BASE` below.

## First-ingest command

```bash
HOST_BASE=/Users/Shared/Ios/baseline

bash paperclips/scripts/ingest_swift_kit.sh uw-ios-baseline \
  --host-repo-base "$HOST_BASE" \
  --repo-base /repos-baseline \
  --parent-mount baseline \
  --relative-path uw-baseline-871c0e8 \
  --skip-artefact-check
```

This is the canonical Phase 1.5 command because `bench/ingest-fresh-replay.sh`
does not exist on `develop`, while `ingest_swift_kit.sh` already supports the
required slug + explicit mount-path form.

## Manual verification calls

After the ingest finishes, run the two checks referenced by the approved plan.

Project overview:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.memory.get_project_overview \
  --url http://localhost:8080/mcp \
  --json '{"slug":"uw-ios-baseline"}'
```

Expected: `entity_counts` shows non-zero files and symbols.

Slug-form passthrough search:

```bash
uv run --directory services/palace-mcp python -m palace_mcp.cli tool call \
  palace.code.search_code \
  --url http://localhost:8080/mcp \
  --json '{"project":"uw-ios-baseline","pattern":"HD"}'
```

Expected after the namespace slice is deployed: at least one hit for `HD`.

## Validation used for this slice

```bash
bash -n paperclips/scripts/ingest_swift_kit.sh

bash paperclips/scripts/ingest_swift_kit.sh uw-ios-baseline \
  --host-repo-base /tmp/uw-baseline-fixture \
  --repo-base /repos-baseline \
  --parent-mount baseline \
  --relative-path uw-baseline-871c0e8 \
  --env-file ./.env \
  --dry-run \
  --skip-artefact-check
```
