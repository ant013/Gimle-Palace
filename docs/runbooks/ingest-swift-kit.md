# Runbook: Per-kit Swift ingestion

> See also: [Palace Operator Guide](operator-guide.md) for prerequisites,
> first-time setup, and common troubleshooting.
> For the registry-backed baseline first run, see
> [uw-ios-baseline-first-ingest.md](uw-ios-baseline-first-ingest.md).

---

## NATIVE ingest (current dev-Mac setup — no Docker) — USE THIS

The dev-Mac palace is **native** (Homebrew Neo4j + a launchd-managed uvicorn on
`:8765`, source `/Users/Shared/Ios/Gimle-Palace/services/palace-mcp/src` via the
`Gimle-Palace-native/.venv` editable install). Docker is dead. **Do not run the
CLI `palace-mcp project analyze` subcommand on native** — its
`ensure_project_analyze_runtime` does `docker compose up --force-recreate` and it
writes container `/repos-hs/...` SCIP paths the native server cannot read. Drive
the server-side MCP tool directly instead. Validated 2026-06-27 on
eip20-kit / tron-kit / uniswap-kit.

Topology (native):
- Source repos (code **and** SCIP): `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/<RepoDir>`
- Authoritative env (shell-sourced by `…/scripts/launch_native_macos.sh`):
  **`/Users/ant013/Android/Gimle-Palace-native/.env`** — NOT the Shared-root or
  `services/palace-mcp/.env`. SCIP paths here are **real absolute paths**, single-quoted JSON.
- MCP URL: `http://localhost:8765/mcp`
- Restart: `launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native`

### Steps (per kit, e.g. `tron-kit` → `TronKit.Swift`)

**1. Clone at the rev uw-ios-app pins** (so the kit matches the ingested app). Read the
revision from `unstoppable-wallet-ios/…/Package.resolved`, then:
```bash
cd /Users/Shared/Ios/Gimle-Repos/HorizontalSystems
git clone https://github.com/horizontalsystems/TronKit.Swift.git
git -C TronKit.Swift checkout <pinned-rev>
```

**2. Emit SCIP locally (no remote copy):**
```bash
cd /Users/Shared/Ios/Gimle-Palace
bash paperclips/scripts/scip_emit_swift_kit.sh tron-kit \
  --repo-root /Users/Shared/Ios/Gimle-Repos/HorizontalSystems \
  --no-remote-copy
# → writes /Users/Shared/Ios/Gimle-Repos/HorizontalSystems/TronKit.Swift/scip/index.scip
```
(Uses `xcrun` → the real Xcode toolchain; a stale `swift` on PATH does not matter.)

**3. Register the SCIP path in the NATIVE env** (real path, NOT `/repos-hs`). Back up first;
the value is single-quoted JSON on one line:
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("/Users/ant013/Android/Gimle-Palace-native/.env")
out=[]
for ln in p.read_text().splitlines():
    if ln.startswith("PALACE_SCIP_INDEX_PATHS="):
        d = json.loads(ln.split("=",1)[1].strip().strip("'"))
        d["tron-kit"] = "/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/TronKit.Swift/scip/index.scip"
        ln = "PALACE_SCIP_INDEX_PATHS='" + json.dumps(d) + "'"
    out.append(ln)
p.write_text("\n".join(out)+"\n")
PY
```

**4. Restart so the server reloads the env** (config reads `PALACE_SCIP_INDEX_PATHS`
from the process environment; no hot-reload):
```bash
launchctl kickstart -k gui/$(id -u)/work.ant013.palace-mcp-native
# wait for health: curl -s http://localhost:8765/health  → {"status":"ok"}
```
Batch tip: add **all** new kits' paths in step 3, then restart once.

**5. Start the durable analysis run via the MCP tool** (register + symbol_index_swift +
audit cascade + `embedding_symbol` are all in this one run):
```bash
/Users/ant013/Android/Gimle-Palace-native/.venv/bin/python -m palace_mcp.cli \
  tool call palace.project.analyze --url http://localhost:8765/mcp \
  --json '{"slug":"tron-kit","parent_mount":"hs","relative_path":"TronKit.Swift",
           "language_profile":"swift_kit","name":"tron-kit","bundle":"uw-ios","depth":"full"}'
# → {"ok":true,"run_id":"…","status":"RUNNING"}  (returns immediately; runs async on server)
```

**6. Monitor.** `palace.project.analyze_status` exists but can error under heavy embedding
load — Neo4j is ground truth:
```bash
cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (s:Symbol) WHERE s.group_id='project/tron-kit'
   RETURN count(s) AS syms, count(s.embedding) AS emb"
# done when emb == syms (kits embed to 100%, like evm-kit 44662/44662)
```

Slug ↔ repo-dir come from `services/palace-mcp/scripts/uw-ios-bundle-manifest.json`
(`eip20-kit`→`Eip20Kit.Swift`, `tron-kit`→`TronKit.Swift`, `uniswap-kit`→`UniswapKit.Swift`).
`parent_mount` is `hs`; `language_profile` is `swift_kit`.

### Gotchas (native, learned 2026-06-27 on eip20/tron/uniswap)

- **Run kits STRICTLY SERIALLY — one analyze run at a time.** Two failure modes from
  concurrency on the single-process native server:
  - Concurrent `symbol_index_swift` collide on the shared Tantivy index — the loser writes
    **0 symbols** (no hard error; `continue_on_failure` then runs the rest of the cascade on an
    empty graph). Symptom: `count(Symbol)=0` while the run shows `last_completed_extractor`
    already past `symbol_index_swift`. Fix: `force_new=true` re-run, alone.
  - Concurrent `embedding_symbol` saturates the single uvicorn event loop → the server stops
    answering HTTP (`/health` times out, agents see **"Tools: (none)"** / MCP list-tools hangs).
    Data is fine (embeddings keep landing in Neo4j), but agents can't use palace until it drains.
  Wait for each run to reach a terminal status (e.g. `SUCCEEDED_WITH_FAILURES`) before starting
  the next. `ACTIVE_ANALYSIS_RUN_EXISTS` means the prior run for that slug is still active.
- **`SUCCEEDED_WITH_FAILURES` is the normal terminal status** for a kit ingested without
  Periphery/`.swiftinterface` artefacts — `public_api_surface`/`hot_path_profiler` report
  `MISSING_INPUT`, `cross_module_contract` is `SKIPPED`. Run `prepare_swift_kit_artifacts.sh`
  first if you need those audit extractors.
- **Verify with Neo4j, not the tools.** `palace.memory.list_projects` may omit a freshly
  registered kit (W9a `p.name` vs `p.slug` quirk) and scoped `semantic_search` on a small kit can
  return 0 (W3 global top-K starvation vs uw-ios-app's 248k) — both pre-existing query-layer bugs,
  NOT ingest failures. Ground truth: `MATCH (s:Symbol) WHERE s.group_id='project/<slug>'`. A
  `search_graph` name-pattern query is the most reliable agent-facing check.
- Don't run heavy ingests while agents need palace — embedding makes `:8765` unresponsive.

> **Why the legacy flow below fails on native:** it targets Docker (`/repos-hs` bind mount,
> `:8080`, `docker compose` recreate). The native server reads `PALACE_SCIP_INDEX_PATHS`
> literally and there is no `/repos-hs` (root symlinks are SIP-blocked on macOS), so container
> paths point at nothing. Keep the section below only for the historical iMac/Docker deploy.

---

## LEGACY: dev-Mac SCIP + iMac Docker registration (historical)

This runbook covers Audit-V1 S3 single-kit ingestion for one HorizontalSystems
Swift kit. It splits the flow into:

1. dev Mac SCIP generation and transfer;
2. iMac registration + extractor cascade.

The scripts are designed for the current HorizontalSystems mount convention:

- local HS repo root on the dev Mac;
- iMac bind-mount at `/Users/Shared/Ios/HorizontalSystems`;
- container-visible path `/repos-hs/<relative_path>`.

When the Docker runtime is `colima` and `/Users/Shared/...` is not shared into
the VM, `ingest_swift_kit.sh` stages the single repo under
`$HOME/.cache/palace/swift-kit-mounts/hs-stage` and recreates `palace-mcp`
with a temporary `/repos-hs-stage/<relative_path>` bind mount for the live
extractor run.

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
  --host-repo-base /Users/Shared/Ios/HorizontalSystems \
  --dry-run
```

Live run:

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit \
  --bundle uw-ios \
  --host-repo-base /Users/Shared/Ios/HorizontalSystems
```

What it does:

- resolves `tron-kit` to host path `/Users/Shared/Ios/HorizontalSystems/TronKit.Swift`
  and container path `/repos-hs/TronKit.Swift`;
- verifies the host-side `scip/index.scip` exists before mutating state;
- on `colima`, stages the repo under `$HOME/.cache/palace/swift-kit-mounts`
  when `/Users/Shared/...` is not visible in the VM;
- merges `PALACE_SCIP_INDEX_PATHS` in `.env` with `jq`;
- recreates `palace-mcp` with the same `--env-file` the script updated;
- calls:
  - `palace.memory.register_project`
  - `palace.memory.register_bundle` when `--bundle` is set
  - `palace.memory.add_to_bundle` when `--bundle` is set
  - `palace.ingest.list_extractors`
  - `palace.ingest.run_extractor`
  - `palace.memory.get_project_overview`
- prints a final JSON summary.

### Default extractor set (GIM-283-2)

As of `feature/GIM-283-2-audit-coverage-gaps`, `DEFAULT_EXTRACTORS` contains all
17 entries that cover the full `swift_kit` audit profile plus infrastructure:

| Extractor | Category |
|-----------|----------|
| `symbol_index_swift` | infrastructure |
| `git_history` | infrastructure |
| `dependency_surface` | audit |
| `arch_layer` | audit |
| `error_handling_policy` | audit |
| `crypto_domain_model` | audit |
| `hotspot` | audit |
| `code_ownership` | audit |
| `cross_repo_version_skew` | audit |
| `public_api_surface` | audit |
| `cross_module_contract` | audit |
| `dead_symbol_binary_surface` | audit |
| `coding_convention` | audit |
| `localization_accessibility` | audit |
| `reactive_dependency_tracer` | audit |
| `testability_di` | audit |
| `hot_path_profiler` | audit |

Extractors that require optional helper inputs or artifacts can now finish with
non-failing diagnostics:

- `public_api_surface` without `.palace/public-api/...` → `MISSING_INPUT`
- `cross_module_contract` without `public_api_surface` facts → `SKIPPED`
- `hot_path_profiler` without `profiles/` traces → `MISSING_INPUT`
- `cross_repo_version_skew` without usable `:DEPENDS_ON` graph → `MISSING_INPUT`
- `reactive_dependency_tracer` without `reactive_facts.json` keeps its
  informational diagnostic path

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

- Confirm the iMac host repo exists under `/Users/Shared/Ios/HorizontalSystems`.
- Confirm the iMac checkout mounts `/Users/Shared/Ios/HorizontalSystems:/repos-hs:ro`.
- If the repo is not in the manifest, pass `--relative-path <repo-dir>`.

`palace-mcp runtime cannot see repo content`

- On `colima`, this means `/Users/Shared/...` is not shared into the VM.
- Re-run the script and let it stage the repo under
  `$HOME/.cache/palace/swift-kit-mounts`, or explicitly share the HS path into
  Colima if you want to keep using `/repos-hs`.

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
