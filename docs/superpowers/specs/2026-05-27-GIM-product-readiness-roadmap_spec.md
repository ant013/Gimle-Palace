# GIM Product Readiness Roadmap Spec

Date: 2026-05-27

Branch: `docs/GIM-product-readiness-roadmap-spec`

Target integration branch: `develop`

## Goal

Turn the current Gimle runtime-smoke and semantic-search work into a
repeatable product-ready operator path:

- clean Docker/image reproducibility, with no manual runtime patching and no
  repeated heavyweight ML dependency downloads;
- semantic search quality beyond raw vector lookup: deterministic ranking,
  source/dependency filtering, and reliable snippet/context hydration;
- full golden matrix checks for semantic quality and runtime regressions;
- install/config path for a powerful server, not only one developer MacBook;
- stable runbook for Neo4j, palace-mcp, model caches, repository mounts, Qodo
  backend, indexing, smoke, and semantic probes.

This spec is an umbrella roadmap contract. Each slice below should become a
separate Paperclip issue with its own implementation plan and normal
review/test/merge evidence.

## Context

Current state:

- `palace.code.semantic_search` v1 exists as a scoped vector-backed MCP tool.
- Runtime smoke has working evidence for `uw-ios-app` on MacBook:
  SCIP -> `symbol_index_swift` -> `dead_code` -> `embedding_symbol`.
- GIM-856 is the active Swift-kit smoke blocker. It should productize the
  Swift kit path so BitcoinKit-style repos use the iOS-oriented kit SCIP
  emitter rather than generic macOS `swift build`.
- Qodo model cache is large and expensive to re-download. Product runtime must
  support persistent local model/cache mounts and local-only mode.
- Recent smoke required manual runtime intervention: dependency pinning,
  copying source into a running container, and avoiding a stuck clean image
  rebuild. Product readiness means those interventions become first-class,
  tested behavior.

## Assumptions

- `origin/develop` remains the integration branch.
- Runtime productization starts after GIM-856 is merged to `develop` or is
  explicitly removed as a blocker by the operator.
- Qodo remains the default semantic embedding backend for self-hosted mode.
- Model files and embedding caches are stored outside source control and are
  never deleted by cleanup scripts unless explicitly requested.
- The first product server target is a single powerful host running Docker,
  Neo4j, palace-mcp, repo mounts, and local model cache. Multi-tenant SaaS is
  out of scope for this roadmap slice.
- MacBook remains the required host class for iOS/Xcode smoke. Server install
  can consume emitted SCIP artefacts or run non-Xcode project types, but does
  not need to perform iOS Xcode builds unless the server is also macOS with
  Xcode.

## Non-Goals

- No new LLM agent product UX in this roadmap. This is runtime/search substrate
  readiness.
- No hosted multi-tenant security boundary.
- No migration away from Neo4j.
- No requirement to support unbounded semantic embedding of every symbol by
  default. Bounded/indexed operation remains acceptable when limits are explicit
  and reported.
- No destructive cleanup of local model caches, repo clones, or evidence
  reports.

## Affected Areas

Likely touched areas across slices:

- `docker-compose.yml`
- `services/palace-mcp/Dockerfile` or compose build context
- `services/palace-mcp/pyproject.toml`
- `services/palace-mcp/uv.lock`
- `services/palace-mcp/src/palace_mcp/embeddings/`
- `services/palace-mcp/src/palace_mcp/code/find_semantic.py`
- `services/palace-mcp/src/palace_mcp/code/`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/smoke/`
- `services/palace-mcp/tests/code/`
- `services/palace-mcp/tests/smoke/`
- `services/palace-mcp/tests/embeddings/`
- `docs/runbooks/`
- `docs/superpowers/plans/`
- optional new `scripts/` or `paperclips/scripts/` operator helpers

## Roadmap Slices

The canonical roadmap unit is one row in this table. Do not create one
track-sized child for the whole umbrella unless the operator explicitly asks.

| Slice | Title | Depends On | Preferred Owner | Files In Scope | Output |
|---|---|---|---|---|---|
| PR0 | Product readiness contract lock | none | Claude CTO | spec/plan docs only | approved spec + issue DAG |
| PR1 | Clean Docker image reproducibility | GIM-856, PR0 | Claude Infra | Dockerfile/compose/pyproject/uv.lock | clean rebuild passes without manual container edits |
| PR2 | Persistent ML dependency and model cache strategy | PR1 | Claude Infra | compose/env/docs/embedding config | Qodo/HF/uv/cache mounts documented and tested |
| PR3 | Semantic ranking contract | PR0 | Claude PE | `find_semantic.py`, tests | deterministic ranking formula and tests |
| PR4 | Semantic filtering contract | PR3 | Claude PE | `find_semantic.py`, schema/query tests | first-party/dependency/generated/source-scope filtering |
| PR5 | Snippet/context provider hardening | PR3 | Claude PE + Codex CR | code context/snippet/Tantivy integration | reliable bounded snippets with safe path resolution |
| PR6 | Machine-readable golden matrix | PR3, PR4, PR5 | Claude QA | tests/fixtures/scripts | executable semantic quality matrix |
| PR7 | Runtime golden smoke matrix | GIM-856, PR1, PR2 | Codex/CX QA | smoke runner/recipes/reports | executable runtime smoke matrix |
| PR8 | Server install/config profile | PR1, PR2 | Claude Infra | compose/env/runbook/scripts | install path for powerful server |
| PR9 | Stable operator runbook | PR6, PR7, PR8 | Claude CTO + QA | docs/runbooks | copy-paste-safe runbook with cleanup policy |
| PR10 | End-to-end product readiness gate | PR6, PR7, PR8, PR9 | Codex/CX QA | reports only unless fixes needed | final evidence bundle and go/no-go |

### Parallelism Rules

- PR1 and PR3 can start in parallel after PR0, but PR7 waits for PR1/PR2 and
  GIM-856.
- PR3, PR4, and PR5 should stay on one Python owner lane unless a reviewer
  proves disjoint files; they all touch semantic search behavior.
- PR6 starts only after ranking/filtering/snippet contracts are locked enough
  to avoid rewriting the matrix.
- PR8 can start after PR1/PR2; it does not need PR6/PR7, but final runbook PR9
  depends on all of them.
- PR10 is a validation-only gate. It should not add product code except small
  fixes explicitly spun out from failed evidence.

## Slice Details

### PR0 — Product Readiness Contract Lock

Scope:

- Convert this umbrella spec into Paperclip-ready child issue descriptions.
- Record dependencies, owners, acceptance, and verification commands.
- Identify file overlap for parallel execution.

Acceptance:

- The parent roadmap issue has a structured status table with PR0-PR10.
- Every child issue has one slice id, dependency list, owner, branch naming
  convention, acceptance criteria, verification plan, and close requirement.
- The CEO/walker treats merged-to-`develop` SHA as the only done state.

Verification:

- Manual review of issue DAG against this spec.
- No implementation files changed in PR0.

### PR1 — Clean Docker Image Reproducibility

Problem:

Recent smoke required runtime pinning and source copy into a running container.
A product image must rebuild cleanly and start with the exact code and pinned
dependency stack.

Scope:

- Pin and test the ML stack required by Qodo in committed dependency files.
- Make `docker compose build palace-mcp` or the selected build command
  deterministic on a clean host with cache mounts.
- Ensure the built image imports `palace_mcp`, starts MCP, and exposes the
  current source code without `docker cp`.
- Add a lightweight image smoke check that validates:
  - dependency versions;
  - `PALACE_EMBEDDING_LOCAL_ONLY` is honored;
  - `palace_mcp.embeddings.qodo` can initialize against a local cache without
    network.

Acceptance:

- Fresh checkout + documented command builds the image without manual pip
  installs or source injection.
- The clean image starts and `/healthz` returns ok.
- Runtime dependency versions match committed pins.
- Failure to access a local model cache in local-only mode is reported as an
  actionable config error, not an implicit download/hang.

Verification:

- `docker compose build palace-mcp` or documented equivalent.
- `docker compose up -d neo4j palace-mcp`.
- `docker exec <palace-mcp> python -c 'import palace_mcp'`.
- `docker exec <palace-mcp> python -c` check for pinned versions.
- Focused Qodo local-only test in the container.

### PR2 — Persistent ML Dependency and Model Cache Strategy

Problem:

Qodo/HF model files and Python package downloads are large. Product operation
must not repeatedly download them or accidentally delete them during cleanup.

Scope:

- Define cache directories for:
  - HuggingFace/Qodo model cache;
  - uv/pip wheel cache where useful;
  - optional transformer/tokenizer cache;
  - Neo4j data volume.
- Add compose/env knobs for those caches.
- Add preflight checks that report cache presence, size, local-only status, and
  writeability.
- Define cleanup levels:
  - safe: temporary workdirs and build cache;
  - reclaim: stopped containers and unused app images;
  - destructive: volumes/model caches, only explicit operator approval.

Acceptance:

- Operator can configure cache paths with env vars or compose override.
- Preflight prints cache status without exposing secrets.
- Cleanup script/runbook never removes Qodo/HF model cache by default.
- Re-running smoke uses existing model cache in local-only mode.

Verification:

- Preflight test with cache present.
- Preflight test with cache missing in local-only mode.
- Documentation review for cleanup levels.

### PR3 — Semantic Ranking Contract

Problem:

Raw vector scores are not enough. Operators need stable ranking that prefers
useful first-party implementation symbols over generated/dependency/noise when
the semantic score is close.

Scope:

- Define a deterministic ranking formula with explicit weights and penalties.
- Include tie-breakers that produce total ordering:
  1. final score desc;
  2. source scope priority;
  3. symbol kind priority;
  4. project slug asc;
  5. qualified name asc.
- Keep raw vector score in output for debugging.
- Make ranking explainable per hit via optional `rank_features`.

Acceptance:

- Ranking formula is documented in code comments or spec docs.
- Unit tests prove stable ordering for equal/near-equal vector scores.
- First-party implementation beats dependency/generated accessor noise when
  vector scores are within the documented tolerance.
- Response includes enough debug fields to explain why a hit ranked where it
  did.

Verification:

- Focused unit tests with fake Neo4j/vector rows.
- Regression test for deterministic ordering across repeated calls.

### PR4 — Semantic Filtering Contract

Problem:

Semantic search must support default product search and explicit expert search.
Default search should not drown users in dependencies/generated code, but
operators must be able to search across app + kits + shared toolkits.

Scope:

- Support `source_scopes` or equivalent filter parameter.
- Define default scope set, likely first-party project/workspace code.
- Support explicit inclusion flags for dependency, generated, derived, SDK, or
  all scopes.
- Handle legacy symbols that lack `source_scope` by classifying through recipe
  roots during re-index, or by a documented migration fallback.
- Preserve explicit cross-project search by `projects=[...]`.

Acceptance:

- Default search returns useful first-party results for already indexed
  projects after migration/re-index path is applied.
- Explicit `projects` list can search `uw-ios-app` + kits + shared toolkit in
  one call.
- Unknown or legacy scope cannot silently make all defaults empty.
- Tests cover dependency exclusion, generated exclusion, explicit inclusion,
  and cross-project search.

Verification:

- Unit tests for scope predicates.
- Small fixture graph proving default and explicit filters.
- Migration/readiness check that reports counts by `source_scope`.

### PR5 — Snippet and Context Provider Hardening

Problem:

Semantic hits need source context. Context must be useful, bounded, safe, and
project-scoped.

Scope:

- Hydrate snippets from the hit's project + qualified name, not only global
  qualified name.
- Treat persisted `file_path` as untrusted.
- Resolve paths with `realpath` and require containment inside the resolved
  project root, not just a broad parent mount.
- Bound snippet line count and byte count.
- Return `context.available=false` with warning codes when snippet lookup is
  unavailable instead of failing the whole search.
- Optional usage preview must be project/commit scoped.

Acceptance:

- Snippet context appears for representative Swift symbols.
- Path traversal, absolute-path escape, and symlink escape are rejected.
- Missing source file returns a per-hit warning.
- Context hydration cannot read sibling repo secrets through broad parent
  mounts.

Verification:

- Unit tests for valid snippet, missing file, absolute escape, `..` escape,
  symlink escape.
- Fixture semantic search result with context.

### PR6 — Machine-Readable Golden Matrix

Problem:

Manual judgment is not enough for semantic quality. We need an executable
matrix that prevents fabricated or subjective QA evidence.

Scope:

- Add a JSON/YAML golden matrix with rows:
  - query;
  - projects;
  - source scope parameters;
  - expected qualified-name patterns;
  - expected file patterns;
  - disallowed/noise patterns;
  - minimum top-k hit count;
  - required snippet/context expectation.
- Add a runner that executes the matrix against a live or fixture graph and
  prints per-row top-k evidence.
- Include core product queries:
  - timers/schedulers;
  - transaction signing;
  - address validation;
  - balance refresh;
  - hex/data conversion across app + toolkit;
  - dead-code cluster lookup.

Acceptance:

- Matrix is machine-readable and committed.
- Runner exits non-zero on failed rows.
- Every row prints top-k evidence with project, qualified name, score,
  source_scope, file path, and context status.
- The matrix cannot pass silently with zero executed rows.

Verification:

- Fixture-mode CI test.
- Optional live-mode MacBook/server run with report artifact.

### PR7 — Runtime Golden Smoke Matrix

Problem:

Runtime smoke currently depends on ad hoc manual runs. Product readiness needs a
bounded matrix that can be repeated and compared.

Scope:

- Define a runtime smoke matrix for:
  - `uw-ios-app` on MacBook;
  - at least one Swift kit such as `bitcoin-kit`;
  - at least one non-Xcode project type if available;
  - embedding-only bounded rerun.
- Each row records:
  - repo branch/ref;
  - expected build/emission path;
  - expected SCIP existence/size;
  - extractor list;
  - bounded embedding limit;
  - expected minimum node/edge counts;
  - acceptable skips.
- Runner writes JSON and markdown summary.

Acceptance:

- Matrix distinguishes build/emission failure from extractor failure.
- `uw-ios-app` row covers SCIP -> symbol index -> dead code -> embeddings.
- Swift kit row proves iOS-oriented kit path, not generic macOS `swift build`.
- Bounded embedding row reports limit and does not appear as full coverage.

Verification:

- MacBook live run for Xcode rows.
- Server/non-Xcode run where applicable.
- Report artifact attached to issue.

### PR8 — Server Install and Config Profile

Problem:

Operators need to install Gimle on a powerful server without reverse
engineering local MacBook state.

Scope:

- Define supported server profile:
  - CPU/GPU assumptions;
  - disk requirements;
  - Docker/Compose requirements;
  - Neo4j memory settings;
  - model cache directory;
  - repo mount directory;
  - env file template.
- Add sample `.env.example` or documented env block for product server.
- Add compose override examples for:
  - model cache mount;
  - repo parent mount;
  - Neo4j memory;
  - palace-mcp port;
  - local-only embeddings.
- Define backup/restore boundaries for Neo4j and caches.

Acceptance:

- Fresh server can start Neo4j + palace-mcp with documented commands.
- Preflight reports missing model cache, repo mount, or Neo4j auth mismatch.
- No secret values are committed.
- Install docs separate MacBook Xcode smoke from server indexing/runtime.

Verification:

- Dry-run install validation.
- `docker compose config` succeeds with sample override.
- Health check commands pass on a configured host.

### PR9 — Stable Operator Runbook

Problem:

The operator path must not require reading chat history. It must explain exactly
how to start, verify, run, debug, and clean up.

Scope:

- Consolidate current runbooks into one product-ready operator path or a small
  linked set:
  - install;
  - first start;
  - model cache setup;
  - repo mounts;
  - smoke matrix;
  - semantic golden matrix;
  - common failures;
  - cleanup policy.
- Include copy-paste-safe commands.
- Include "do not delete" list:
  - Qodo/HF cache;
  - repo clones;
  - Neo4j data unless rebuilding intentionally;
  - evidence reports until issue close.

Acceptance:

- A new operator can run the documented happy path without chat history.
- Every command has expected output or success criteria.
- Troubleshooting covers:
  - Docker rebuild hangs on ML deps;
  - Neo4j auth/volume mismatch;
  - missing Xcode vs server-only runtime;
  - missing SCIP path;
  - local-only model cache failure;
  - semantic matrix underfill.

Verification:

- Docs review by one engineer who did not write the runbook.
- Dry-run of commands where safe.
- Live run evidence links to PR7/PR10.

### PR10 — End-to-End Product Readiness Gate

Scope:

- Run PR6 semantic golden matrix.
- Run PR7 runtime golden smoke matrix.
- Run server install/profile validation from PR8.
- Verify runbook PR9 against the final commands.
- Produce final go/no-go report.

Acceptance:

- Report clearly states:
  - exact commit SHA;
  - host type;
  - model cache path status without secrets;
  - Docker image id;
  - Neo4j database status;
  - runtime smoke matrix results;
  - semantic golden matrix results;
  - known limitations;
  - follow-up issues.
- No manual runtime source copy, manual pip install, or undocumented env tweak
  is needed for the passing path.
- Any failed row becomes a follow-up issue with owner and reproduction command.

Verification:

- Final evidence artifact attached to parent roadmap issue.
- Parent can close only after PR10 passes or the operator explicitly accepts
  remaining limitations.

## Global Acceptance Criteria

The umbrella roadmap is complete when:

- all PR0-PR10 slices are merged to `develop` or explicitly skipped by operator
  decision with rationale;
- clean Docker image build/start works from committed files;
- Qodo local-only mode works from a persistent cache without repeated model
  downloads;
- semantic search ranking/filtering/snippet behavior is deterministic and
  tested;
- golden semantic matrix and runtime smoke matrix are executable and produce
  evidence;
- server install/config runbook is usable without chat history;
- cleanup policy preserves expensive model caches and evidence by default.

## Verification Plan

Minimum commands expected across the roadmap:

```bash
docker compose config
docker compose build palace-mcp
docker compose up -d neo4j palace-mcp
curl -fsS http://localhost:8080/healthz
```

```bash
cd services/palace-mcp
uv run python -m pytest tests/embeddings tests/code tests/smoke
uv run ruff check src tests
```

```bash
# Names are intentionally placeholders until PR6/PR7 define exact runners.
uv run python -m palace_mcp.semantic_golden_matrix --matrix <matrix.json>
uv run python -m palace_mcp.runtime_smoke_matrix --matrix <matrix.json>
```

No slice may claim product readiness using only screenshots or prose. Every
passing claim must include command output, report path, or committed test.

## Open Questions

1. Should the product server target support GPU acceleration for Qodo now, or
   remain CPU-first with optional GPU follow-up?
2. Should runtime golden matrix run against a persistent Neo4j database or an
   isolated throwaway compose project by default?
3. What is the first official server repo set: only UW iOS + HS kits, or also
   bitcoin-core / evm-kit / dash-kit from the GIM-839 cascade?
4. Should golden matrix thresholds be initially strict `5/5` or pragmatic
   `4/5 with mandatory rows`?
5. Should server install produce a tarball/release bundle, or is git checkout +
   compose profile acceptable for v1?

