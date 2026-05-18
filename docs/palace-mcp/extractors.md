# palace-mcp — Extractors + Bundles + ADR Reference

> Extracted from former root `CLAUDE.md` during UAA Phase H1 CLAUDE.md
> decompose (2026-05-17).

## Bundles (GIM-182)

A **bundle** is a virtual project aggregating per-member project indexes so that
`palace.code.find_references(project="<bundle>")` resolves across all members in
one call. Bundles use `group_id = "bundle/<name>"` (distinct from `"project/<slug>"`).

**uw-ios bundle:** `uw-ios-app` (UW iOS app) + 40 first-party HorizontalSystems Swift Kits.
Canonical member list: `services/palace-mcp/scripts/uw-ios-bundle-manifest.json`.

### Bundle MCP tools

- `palace.memory.register_bundle(name, description)` — create/update a Bundle node.
- `palace.memory.add_to_bundle(bundle, project, tier)` — add a member (idempotent).
- `palace.memory.bundle_members(bundle)` — list members with ProjectRef metadata.
- `palace.memory.bundle_status(bundle)` — freshness/health metrics (3-way failed_slugs split).
- `palace.memory.delete_bundle(name, cascade)` — remove bundle (not member :Project nodes).
- `palace.ingest.run_extractor(name, bundle=...)` — async kickoff; returns `run_id` < 100 ms.
- `palace.ingest.bundle_status(run_id)` — poll async ingest progress.

**Key invariants:**
- `register_parent_mount` is NOT a v1 tool; `parent_mount` is a param on `register_project`.
- Bundle ingest is async — `run_extractor(bundle=...)` returns `run_id` immediately.
- `failed_slugs` in `bundle_status` is split into 3: `query_failed_slugs` (transient),
  `ingest_failed_slugs` (last_run failed), `never_ingested_slugs` (no run yet).

Runbook: `docs/runbooks/multi-repo-spm-ingest.md`.

## Extractors

Palace-mcp ships a pluggable extractor framework under
`services/palace-mcp/src/palace_mcp/extractors/`. Each extractor writes
domain nodes/edges to Neo4j scoped by `group_id = "project/<slug>"` and is
invoked via MCP tool `palace.ingest.run_extractor(name, project)`.

### Registered extractors

- `heartbeat` — diagnostic probe. Writes one `:ExtractorHeartbeat` node per
  run. Use to verify the pipeline is alive before running heavy extractors.
- `symbol_index_python` — Python symbol indexer. Reads a pre-generated `.scip`
  file (produced by `npx @sourcegraph/scip-python` outside the container).
  Writes occurrences into Tantivy (full-text) and `:IngestRun` + checkpoints
  into Neo4j. 3-phase bootstrap: defs/decls → user uses → vendor uses.
  Query via `palace.code.find_references(qualified_name, project)`.
- `symbol_index_typescript` — TypeScript/JavaScript symbol indexer (GIM-104).
  Reads a pre-generated `.scip` file produced by `npx @sourcegraph/scip-typescript`.
  Handles `.ts`, `.tsx`, `.js`, `.jsx` in one pass via per-document language
  auto-detection. Same 3-phase bootstrap as `symbol_index_python`. Uses the
  same `PALACE_SCIP_INDEX_PATHS` env var — add the project slug with the path
  to the TypeScript SCIP file.
- `symbol_index_java` — Java/Kotlin symbol indexer (GIM-111).
  Reads a pre-generated `.scip` file produced by `npx @sourcegraph/scip-java`
  (requires Java 17+ and Gradle). Handles `.java`, `.kt`, `.kts` in one pass
  via per-document language auto-detection. Same 3-phase bootstrap as
  `symbol_index_python`. Uses `PALACE_SCIP_INDEX_PATHS` — set the project slug
  to the scip-java output path. scip-java symbol scheme: `semanticdb maven
  <package-name> <version> <descriptor>`.
- `symbol_index_solidity` — Solidity smart-contract symbol indexer (GIM-124).
  Reads a pre-generated `.scip` file produced by `python -m palace_mcp.scip_emit.solidity`
  (requires `slither-analyzer>=0.11.5` installed manually — not in pyproject.toml due to
  Rust/cbor2 transitive dep). Handles `.sol` files. Same 3-phase bootstrap as
  `symbol_index_python`. Uses `PALACE_SCIP_INDEX_PATHS` — set the project slug to the
  scip_emit/solidity output path. SCIP scheme: `scip-solidity ethereum <path> . <descriptor>`.
- `symbol_index_swift` — Swift symbol indexer (GIM-128).
  Reads a pre-generated `.scip` file emitted by
  `services/palace-mcp/scip_emit_swift` from Apple IndexStoreDB on a dev Mac.
  Handles `.swift` occurrences with the same 3-phase bootstrap as the other
  SCIP-backed extractors. Uses `PALACE_SCIP_INDEX_PATHS` — merge-gate fixture
  slug is `uw-ios-mini`; optional real-source follow-up slug is `uw-ios`.
- `dependency_surface` — Dependency Surface Extractor (GIM-191). Parses declared
  + resolved deps from SPM (`Package.swift` + `Package.resolved` v2/v3), Gradle
  (`gradle/libs.versions.toml` + per-module `build.gradle.kts`), and Python
  (`pyproject.toml` PEP 621 + `uv.lock`). Writes `:ExternalDependency` nodes +
  `:DEPENDS_ON` edges. Single-phase; no SCIP file or env vars needed.
  See `docs/runbooks/dependency-surface.md`.
- `git_history` — Git history harvester (GIM-186). Walks pygit2 commit
  history (Phase 1) + GitHub GraphQL PR/comment data (Phase 2). Foundation for
  6 historical extractors (#11/#12/#26/#32/#43/#44). Per-project incremental
  refresh; checkpoint in `:GitHistoryCheckpoint`. Requires `PALACE_GITHUB_TOKEN`
  env var for Phase 2 (PR data); Phase 1 (commits) runs without it. Full re-walk
  on force-push detected automatically. See `docs/runbooks/git-history-harvester.md`.
- `code_ownership` — Code ownership extractor (GIM-216, Roadmap #32). Reads
  `:Author` / `:Commit` / `:TOUCHED` from `git_history` (GIM-186) + does
  per-file `pygit2.blame` on HEAD. Writes `(:File)-[:OWNED_BY]->(:Author)`
  edges with `weight = α × blame_share + (1-α) × recency_churn_share`
  (α default 0.5, env `PALACE_OWNERSHIP_BLAME_WEIGHT`). Per-file
  incremental refresh via `:OwnershipCheckpoint`. Sidecar
  `:OwnershipFileState` for `find_owners` empty-state diagnostics.
  `.mailmap`-aware via pygit2 (no custom parser). Query via
  `palace.code.find_owners(file_path, project, top_n=5)`.
- `coding_convention` — Coding convention extractor (GIM-238, Roadmap #6).
  Scans Swift + Kotlin source files directly from the mounted repo and derives
  per-module dominant style choices plus outliers for 7 heuristic rule kinds:
  type naming, test naming, protocol/interface naming, ADT pattern, error
  modeling, collection initialization, and computed-vs-lazy property style.
  Writes `:Convention`, `:ConventionViolation`, and extractor-scoped
  `:IngestRun` rows. See `docs/runbooks/coding-convention.md`.
- `hotspot` — Code-Complexity × Churn Hotspot extractor (GIM-195, Roadmap #44).
  Walks repo with stop-list, calls `lizard` per-batch (50 files), aggregates
  per-function CCN to per-file `ccn_total`, joins with `git_history`'s
  `(:Commit)-[:TOUCHED]->(:File)` graph for churn count in a configurable
  window (default 90 days), writes Tornhill log-log `hotspot_score` on `:File`
  + new `:Function` nodes. Query via `palace.code.find_hotspots(project)` for
  top-N hotspots and `palace.code.list_functions(project, path)` for per-
  function complexity. Requires `git_history` to have run first (otherwise
  churn = 0).
- `hot_path_profiler` — Runtime hot-path profiler extractor (GIM-276,
  Roadmap #17). Reads committed trace artifacts from `/repos/<slug>/profiles/`
  and currently supports normalized Instruments JSON fixtures plus Perfetto
  `.pftrace` input. Resolves hot samples onto existing `:Function` nodes,
  writes `:HotPathSample`, `:HotPathSummary`, and unresolved trace rows, and
  exposes audit output via `audit/templates/hot_path_profiler.md`. Track A
  merge-gate fixture lives under
  `services/palace-mcp/tests/extractors/fixtures/hot-path-fixture/profiles/`.
- `reactive_dependency_tracer` — Swift-first reactive state/effect extractor
  (GIM-217, Roadmap #3). Reads pre-generated `reactive_facts.json` from repo
  root, writes `ReactiveComponent` / `ReactiveState` / `ReactiveEffect` /
  `ReactiveDiagnostic` plus exact correlation edges to `SymbolOccurrenceShadow`
  and `PublicApiSymbol` when those backing facts exist. v1 does not execute a
  live Swift helper and treats Kotlin/Compose only as structured skip evidence.
  See `docs/runbooks/reactive-dependency-tracer.md`.
- `localization_accessibility` — Localization & Accessibility extractor (GIM-275,
  Roadmap #9). Parses `.xcstrings` / `Localizable.strings` (iOS) and
  `res/values*/strings.xml` (Android) for per-locale key counts and coverage
  relative to English base. Runs 5 semgrep rules to detect hard-coded string
  literals in SwiftUI, UIKit, and Compose, plus missing a11y labels on SwiftUI
  `Image()` and Compose `Modifier.clickable`. Writes `:LocaleResource`,
  `:HardcodedString`, and `:A11yMissing` nodes. No `.scip` file or env vars
  needed. Supports `.gimle/loc-allowlist.txt` for product-name exceptions.
  See `docs/runbooks/localization-accessibility.md`.
- `cross_repo_version_skew` — Cross-repo version skew (GIM-218, Roadmap #39).
  Reads `:Project-[:DEPENDS_ON]->:ExternalDependency` from `dependency_surface`
  (GIM-191) — fully read-only; writes only one `:IngestRun` per call. Hybrid:
  small extractor (audit/observability via `:IngestRun` extras) + live MCP
  tool `palace.code.find_version_skew` for real-time aggregation. Project
  mode finds intra-module skew via `r.declared_in`; bundle mode aggregates
  across `:Bundle{name}-[:HAS_MEMBER]` members. See limitations in
  `docs/runbooks/cross-repo-version-skew.md`.

### `palace.code.manage_adr` v2 — ADR read/write/supersede/query (GIM-274)

Native `@mcp.tool` (not CM subprocess). Files live in `docs/postulates/<slug>.md`
(env `PALACE_ADR_BASE_DIR`). Neo4j = projection layer (`:AdrDocument`, `:AdrSection`).
Schema bootstrapped in server lifespan via `ensure_adr_schema()`.

**4 modes:**
- `read(slug)` — read file + project to graph (idempotent).
- `write(slug, section, body, decision_id?)` — idempotent section upsert via SHA-256;
  optional `decision_id` creates `(:Decision)-[:CITED_BY]->(:AdrDocument)`.
- `supersede(old_slug, new_slug, reason)` — marks old ADR superseded; banner + graph edge.
- `query(keyword?, section_filter?, project_filter?)` — Cypher-only graph search.

**6-section format:** PURPOSE / STACK / ARCHITECTURE / PATTERNS / TRADEOFFS / PHILOSOPHY.

**File/graph drift:** call `read(slug)` to re-project manually edited files.

See `docs/runbooks/manage-adr-v2.md` for full usage, drift recovery, decision bridge,
and iMac smoke test.

### Operator workflow: Dependency surface

No env vars required. Extractor reads files directly from the mounted repo.

1. Ensure repo mounted in `docker-compose.yml` at `/repos/<slug>`.
2. Run the extractor:
   ```
   palace.ingest.run_extractor(name="dependency_surface", project="gimle")
   ```
3. Query results:
   ```cypher
   MATCH (p:Project {slug: "gimle"})-[r:DEPENDS_ON]->(d:ExternalDependency)
   RETURN d.purl, r.scope, r.declared_in ORDER BY d.purl
   ```

### Operator workflow: Reactive dependency tracer

1. Ensure the target repo contains a pre-generated `reactive_facts.json` at repo
   root. v1 does not launch SwiftSyntax or any helper binary from the extractor.
2. Run the extractor:
   ```
   palace.ingest.run_extractor(name="reactive_dependency_tracer", project="<slug>")
   ```
3. Verify resulting graph slices with the Cypher snippets in
   `docs/runbooks/reactive-dependency-tracer.md`.
4. If the run emits `swift_helper_unavailable`, `swift_parse_failed`, or
   `symbol_correlation_unavailable`, use the troubleshooting section in the
   runbook instead of retrying with a live helper path.

### Operator workflow: Java/Kotlin symbol index

1. Generate `.scip` file outside the container (requires Java 17+ and Gradle):
   ```bash
   cd /repos/your-java-project
   gradle wrapper && ./gradlew compileKotlin compileJava
   npx @sourcegraph/scip-java index --output ./scip/index.scip
   ```

2. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={"your-project":"/repos/your-project/scip/index.scip"}
   ```

3. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_java", project="your-project")
   ```

### Operator workflow: Android symbol index (modern Compose + KSP + multi-module)

Android projects (e.g., `unstoppable-wallet-android`) use scip-java with the real
Android Gradle Plugin classpath. Requires semanticdb-kotlinc 0.5.0 (NOT 0.6.0 — breaks
on Kotlin 2.1+ with `AbstractMethodError`). AGP 9+ is not yet supported by scip-java
auto-mode; pin to AGP ≤8.13.x until upstream fixes (GIM-127; Sourcegraph issue #864).

1. Clone target project on iMac:
   ```bash
   git clone https://github.com/horizontalsystems/unstoppable-wallet-android.git \
     /Users/Shared/Android/unstoppable-wallet-android
   cd /Users/Shared/Android/unstoppable-wallet-android
   # Pin to last pre-AGP-9 commit if on master:
   git checkout c0489d5a33f5da441f07b1f685d42b25b805ffd1
   ```

2. Generate `.scip` outside container (requires JDK 17+ + Gradle 8.x + semanticdb-kotlinc 0.5.0):
   ```bash
   cd /Users/Shared/Android/unstoppable-wallet-android
   # See fixture REGEN.md for the exact regen.sh command sequence
   bash services/palace-mcp/tests/extractors/fixtures/uw-android-mini-project/regen.sh
   ```

3. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "uw-android":"/repos/uw-android/scip/index.scip"}
   ```

4. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_java", project="uw-android")
   ```

5. Query (after GIM-126 lands; currently use `palace.memory.lookup`):
   ```
   palace.code.find_references(qualified_name="WalletDao", project="uw-android")
   ```

### Operator workflow: iOS Swift symbol index

Swift indexing uses the custom emitter package at
`services/palace-mcp/scip_emit_swift`, which reads Apple IndexStoreDB and emits
canonical SCIP protobuf for the Python-side `symbol_index_swift` extractor.

Track A is the merge gate and uses the committed fixture:

1. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "uw-ios-mini":"/repos/uw-ios-mini/scip/index.scip"}
   ```

2. Run the extractor on the committed fixture:
   ```
   palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios-mini")
   ```

3. Query references once the ingest succeeds:
   ```
   palace.code.find_references(qualified_name="UwMiniCore WalletStore", project="uw-ios-mini")
   ```

Track B is optional real-source follow-up on a dev Mac:

1. Clone the real project on the operator host:
   ```bash
   git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git \
     /Users/Shared/Ios/unstoppable-wallet-ios
   ```

2. Build and emit SCIP on the dev Mac with the locked toolchain described in:
   `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md`

3. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "uw-ios":"/repos/uw-ios/scip/index.scip"}
   ```

4. Run the extractor on the real-source index:
   ```
   palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios")
   ```

### Operator workflow: Python symbol index

1. Generate `.scip` file outside the container:
   ```bash
   cd /repos/gimle
   npx @sourcegraph/scip-python index --output ./scip/index.scip
   ```

2. Set env var for palace-mcp container in `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={"gimle":"/repos/gimle/scip/index.scip"}
   ```

3. Run the extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_python", project="gimle")
   ```

4. Query references:
   ```
   palace.code.find_references(qualified_name="register_code_tools", project="gimle")
   ```

### Operator workflow: Hotspot extractor

No external `.scip` file or container env file required. The extractor
walks the mounted repo directly and reads commit data from the Neo4j
graph populated by `git_history`.

1. Ensure the repo is mounted in `docker-compose.yml` at `/repos/<slug>`.
2. Run `git_history` first (so `:Commit -[:TOUCHED]-> :File` exists):
   ```
   palace.ingest.run_extractor(name="git_history", project="<slug>")
   ```
3. Run hotspot:
   ```
   palace.ingest.run_extractor(name="hotspot", project="<slug>")
   ```
4. Query top-N:
   ```
   palace.code.find_hotspots(project="<slug>", top_n=20)
   ```
5. For per-function detail on a specific file:
   ```
   palace.code.list_functions(project="<slug>", path="<file>", min_ccn=10)
   ```

**Configurable env vars** (in `.env`, all optional with sane defaults):

| Variable | Default | Notes |
|----------|---------|-------|
| `PALACE_HOTSPOT_CHURN_WINDOW_DAYS` | `90` | Tornhill recommends 90 or 180 |
| `PALACE_HOTSPOT_LIZARD_BATCH_SIZE` | `50` | Files per lizard subprocess |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_S` | `30` | Per-batch subprocess timeout |
| `PALACE_HOTSPOT_LIZARD_TIMEOUT_BEHAVIOR` | `drop_batch` | `drop_batch` or `fail_run` |

**Trade-off — window changes break idempotency**: changing
`PALACE_HOTSPOT_CHURN_WINDOW_DAYS` between runs overwrites
`:File.churn_count`, `:File.complexity_window_days`, and
`:File.hotspot_score`. Idempotency invariant 4 (zero net writes on
re-run) holds only when window is unchanged.

### Operator workflow: Code ownership

Prereq: GIM-186 `git_history` extractor must have run for the project.

1. Run the extractor:
   ```
   palace.ingest.run_extractor(name="code_ownership", project="gimle")
   ```
2. Query owners:
   ```
   palace.code.find_owners(file_path="services/palace-mcp/...", project="gimle", top_n=5)
   ```

Optional: place `.mailmap` in the repo root to dedupe split identities
(standard git format — see `git help check-mailmap`).

Tunable knobs (`.env`):
- `PALACE_OWNERSHIP_BLAME_WEIGHT` (default 0.5) — α in scoring formula
- `PALACE_OWNERSHIP_MAX_FILES_PER_RUN` (default 50000)
- `PALACE_OWNERSHIP_WRITE_BATCH_SIZE` (default 2000)
- `PALACE_MAILMAP_MAX_BYTES` (default 1 MiB)

Limitations:
- File renames lose history pre-rename (pygit2 blame is path-bound)
- Submodules and binary files are skipped (`no_owners_reason='binary_or_skipped'`)
- Bundle support is not yet wired (run per-project for HS Kits)
- PII: any caller with `palace.code.*` permissions can enumerate
  contributor emails. See `docs/runbooks/code-ownership.md` for trust model.

### Running an extractor

From Claude Code (or any MCP client connected to palace-mcp):

```
palace.ingest.list_extractors()
palace.ingest.run_extractor(name="heartbeat", project="gimle")
```

Response shape (success):
```json
{"ok": true, "run_id": "<uuid>", "extractor": "heartbeat",
 "project": "gimle", "duration_ms": 42,
 "nodes_written": 1, "edges_written": 0, "success": true}
```

Error envelope on failure:
```json
{"ok": false, "error_code": "invalid_slug | unknown_extractor |
 project_not_registered | repo_not_mounted | extractor_config_error |
 extractor_runtime_error | unknown", "message": "<short>",
 "extractor": "...", "project": "...", "run_id": "..."}
```

### Adding a new extractor

1. Create `src/palace_mcp/extractors/<name>.py` with a class inheriting
   `BaseExtractor`. Declare `name`, `description`, `constraints`, `indexes`
   class attributes. Implement `async def extract(self, ctx) -> ExtractorStats`.
2. Import and register in `registry.py`:
   ```python
   from palace_mcp.extractors.<name> import <ClassName>
   EXTRACTORS["<name>"] = <ClassName>()
   ```
3. Unit test in `tests/extractors/unit/test_<name>.py` (mock driver).
4. Integration test in `tests/extractors/integration/test_<name>_integration.py`
   (real Neo4j via testcontainers or compose reuse).

### Extractor foundation substrate (GIM-101a)

All production extractors build on `extractors/foundation/`:

| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic v2 schemas: `SymbolOccurrence`, `IngestCheckpoint`, `EvictionRecord`, … |
| `errors.py` | `ExtractorErrorCode` (18 codes) + `ExtractorError(Exception)` dataclass |
| `identifiers.py` | `symbol_id_for(qname)` — signed-i64 blake2b hash (overflow-safe) |
| `importance.py` | `BoundedInDegreeCounter` + `importance_score()` 5-component formula |
| `tantivy_bridge.py` | `TantivyBridge` async context manager wrapping tantivy-py |
| `schema.py` | `ensure_custom_schema()` — idempotent Neo4j schema with drift detection |
| `checkpoint.py` | `write_checkpoint`, `reconcile_checkpoint`, `create_ingest_run` |
| `eviction.py` | 3-round eviction (`run_eviction`) — never deletes def/decl |
| `circuit_breaker.py` | `check_phase_budget`, `check_resume_budget` — hard caps |
| `synthetic_harness.py` | Deterministic 70M-occurrence stress generator |

**Phase bootstrap order (per phase start):**
1. `check_resume_budget(previous_error_code)` — block budget-exceeded restarts
2. `ensure_custom_schema(driver)` — idempotent schema bootstrap
3. `check_phase_budget(nodes_written_so_far, ...)` — hard cap pre-flight
4. Process occurrences → `tantivy_bridge.add_or_replace_async()`
5. `write_checkpoint(driver, ...)` — after Tantivy commit
6. On restart: `reconcile_checkpoint(checkpoint, actual_doc_count)` — verify integrity

**Tantivy volume** (docker-compose): named volume `palace-tantivy-data` at
`/var/lib/palace/tantivy` inside container. Service runs as uid 1000 (non-root).
`entrypoint.sh` checks write access and fails fast on ownership mismatch.

**GDS plugin caveat**: eviction rounds 1-3 use standard Cypher (`DETACH DELETE`),
not GDS algorithms. GDS is optional — eviction works without it.

### Extractor env vars (GIM-101a)

All vars in `PalaceSettings` (config.py), prefix `PALACE_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `PALACE_MAX_OCCURRENCES_TOTAL` | 50 000 000 | Global hard cap across all projects |
| `PALACE_MAX_OCCURRENCES_PER_PROJECT` | 10 000 000 | Per-project hard cap |
| `PALACE_IMPORTANCE_THRESHOLD_USE` | 0.05 | Round-1 eviction floor for `use` nodes |
| `PALACE_MAX_OCCURRENCES_PER_SYMBOL` | 5 000 | Round-2 per-symbol cap |
| `PALACE_RECENCY_DECAY_DAYS` | 30.0 | Half-life for recency_decay() |
| `PALACE_TANTIVY_INDEX_PATH` | (required) | Host path for Tantivy index |
| `PALACE_TANTIVY_HEAP_MB` | 100 | Tantivy writer heap in MB |
| `PALACE_SCIP_INDEX_PATHS` | `{}` | JSON map `{slug: path}` for SCIP extractors |

### Operator workflow: Cross-repo version skew

Prereq: `dependency_surface` (GIM-191) has run for the target project /
every member of the target bundle.

1. Run the extractor (writes one :IngestRun per call):
   ```
   palace.ingest.run_extractor(name="cross_repo_version_skew", project="uw-android")
   # or for a bundle:
   palace.ingest.run_extractor(name="cross_repo_version_skew", bundle="uw-ios")
   ```

2. Query skew:
   ```
   palace.code.find_version_skew(bundle="uw-ios", min_severity="minor", top_n=20)
   ```

Tunable knobs (`.env`):
- `PALACE_VERSION_SKEW_TOP_N_MAX` (default 500)
- `PALACE_VERSION_SKEW_QUERY_TIMEOUT_S` (default 30)

Limitations:
- Project mode for canonical-Gradle / SPM / Python projects finds zero
  intra-module skew (aliases / single manifest = same version per scope).
  Use bundle-of-1 for forward compatibility.
- Compares resolved_version only; declared-constraint skew is followup.
- Calendar versions / git-shas / custom schemes classify as 'unknown'.
- No Renovate "latest version" data; no OWASP CVE enrichment.

### Known limitations

- **`palace.memory.health()` shows only paperclip ingest runs**, not
  extractor runs (`memory/health.py:46` hardcodes `source="paperclip"`).
  Query extractor runs via `palace.memory.lookup(entity_type="IngestRun",
  filters={"source": "extractor.<name>"})`. UI-friendly health grouping
  is a followup.
- **No scheduler** — extractor runs are manual via MCP tool. Cron trigger
  is a followup.
- **No concurrent runs** — palace-mcp's event loop serializes MCP tool
  calls. A heavy extractor blocks other tools during its run.
