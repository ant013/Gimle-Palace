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
  The current implementation is in
  `services/palace-mcp/src/palace_mcp/code/find_semantic.py`, with public
  schema/contracts in `services/palace-mcp/src/palace_mcp/code/semantic_contract.py`
  and MCP registration in `services/palace-mcp/src/palace_mcp/mcp_server.py`.
  The older roadmap row for `services/palace-mcp/src/palace_mcp/code/semantic_search.py`
  is stale and must be corrected as part of this roadmap update.
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
- Product server v1 is CPU-first. GPU acceleration is allowed only as an
  optional follow-up profile, not a blocking requirement.
- Model files and embedding caches are stored outside source control and are
  never deleted by cleanup scripts unless explicitly requested.
- The first product server target is a single powerful host running Docker,
  Neo4j, palace-mcp, repo mounts, and local model cache. Multi-tenant SaaS is
  out of scope for this roadmap slice.
- Runtime matrices default to an isolated throwaway compose project. Persistent
  Neo4j is an operator option, not the default validation mode.
- The first official repo set is `uw-ios-app` plus HorizontalSystems kit repos
  needed by the smoke/golden rows. `bitcoin-core`, `evm-kit`, and `dash-kit`
  can remain advisory rows until the operator promotes them to required.
- Semantic golden rows are split into mandatory and advisory rows. Zero-result
  mandatory rows fail. Advisory rows can produce follow-up issues without
  blocking PR10.
- Distribution for v1 is git checkout plus documented compose profile and
  override files. Tarball/release packaging is a later productization slice.
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
- `services/palace-mcp/src/palace_mcp/code/semantic_contract.py`
- `services/palace-mcp/src/palace_mcp/code/`
- `services/palace-mcp/src/palace_mcp/code_router.py`
- `services/palace-mcp/src/palace_mcp/code_composite.py`
- `services/palace-mcp/src/palace_mcp/git/path_resolver.py`
- `services/palace-mcp/src/palace_mcp/mcp_server.py`
- `services/palace-mcp/src/palace_mcp/smoke/`
- `services/palace-mcp/scripts/`
- `services/palace-mcp/tests/code/`
- `services/palace-mcp/tests/code_graph/`
- `services/palace-mcp/tests/extractors/unit/`
- `services/palace-mcp/tests/extractors/integration/`
- `services/palace-mcp/tests/extractors/smoke/`
- `services/palace-mcp/tests/embeddings/`
- `services/palace-mcp/tests/git/`
- `docs/runbooks/`
- `docs/superpowers/plans/`
- optional new `scripts/` or `paperclips/scripts/` operator helpers

## Roadmap Slices

The canonical roadmap unit is one row in this table. Do not create one
track-sized child for the whole umbrella unless the operator explicitly asks.

| Slice | Title | Depends On | Preferred Owner | Files In Scope | Output |
|---|---|---|---|---|---|
| PR0 | Product readiness contract lock | none | Claude CTO | spec/plan docs only | approved spec + issue DAG |
| PR0a | Semantic-search architecture lock | PR0 | Claude PE + Codex CR | `find_semantic.py`, `semantic_contract.py`, roadmap docs | actual MCP/search/backend boundary and stale C6 roadmap row locked |
| PR1 | Clean Docker image reproducibility | GIM-856, PR0, PR0a if runtime boundary changes | Claude Infra | Dockerfile/compose/pyproject/uv.lock | clean rebuild passes without manual container edits |
| PR2 | Persistent ML dependency and model cache strategy | PR1 | Claude Infra | compose/env/docs/embedding config | Qodo/HF/uv/cache mounts documented and tested |
| PR3a | Semantic candidate backend decision | PR0a | Claude PE | semantic search docs/tests | dense vs sparse vs hybrid candidate strategy selected with evidence |
| PR3 | Semantic ranking contract | PR3a | Claude PE | `find_semantic.py`, tests | deterministic ranking formula and tests |
| PR4 | Semantic filtering contract | PR3 | Claude PE | `find_semantic.py`, schema/query tests | first-party/dependency/generated/source-scope filtering |
| PR5 | Snippet/context provider hardening | PR0a, PR3 | Claude PE + Codex CR | code context/snippet/path resolver integration | reliable bounded snippets with safe path resolution |
| PR6 | Machine-readable golden matrix | PR0a, PR3, PR4, PR5 | Claude QA | tests/fixtures/scripts | executable semantic quality matrix |
| PR7 | Runtime golden smoke matrix | GIM-856, PR1, PR2 | Codex/CX QA | smoke runner/recipes/reports | executable runtime smoke matrix |
| PR8 | Server install/config profile | PR1, PR2 | Claude Infra | compose/env/runbook/scripts | install path for powerful server |
| PR9 | Stable operator runbook | PR6, PR7, PR8 | Claude CTO + QA | docs/runbooks | copy-paste-safe runbook with cleanup policy |
| PR10 | End-to-end product readiness gate | PR6, PR7, PR8, PR9 | Codex/CX QA | reports only unless fixes needed | final evidence bundle and go/no-go |

### Parallelism Rules

- PR1 and PR0a can start in parallel after PR0. PR3 waits for PR3a, and PR7
  waits for PR1/PR2 and GIM-856.
- PR0a must run before semantic implementation slices. It locks the actual
  current backend boundary and removes stale roadmap ambiguity around C6.
- PR3, PR4, and PR5 should stay on one Python owner lane unless a reviewer
  proves disjoint files; they all touch semantic search behavior.
- PR6 starts only after ranking/filtering/snippet contracts are locked enough
  to avoid rewriting the matrix.
- PR8 can start after PR1/PR2; it does not need PR6/PR7, but final runbook PR9
  depends on all of them.
- PR10 is a validation-only gate. It should not add product code except small
  fixes explicitly spun out from failed evidence.

### File-Overlap Matrix

| Lane | Slices | Shared Files | Parallel Rule |
|---|---|---|---|
| Runtime image/config | PR1, PR2, PR8 | `docker-compose.yml`, Dockerfile, env examples, cache/runbook docs | one writer at a time unless the child issue proves disjoint files |
| Semantic behavior | PR0a, PR3a, PR3, PR4, PR5 | `find_semantic.py`, `semantic_contract.py`, code routing/context helpers, semantic tests | one Python owner lane; Codex may review but should not write concurrently |
| Semantic QA | PR6 | matrix fixtures/runners/tests | starts after behavior contract is stable |
| Runtime QA | PR7 | smoke scripts, recipes, reports | can run after PR1/PR2/GIM-856; avoid editing image config concurrently |
| Docs/runbook | PR9 | `docs/runbooks/`, roadmap/spec links | can draft early, finalizes after PR6-PR8 |
| Evidence gate | PR10 | reports only | validation-only |

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

### PR0a — Semantic-Search Architecture Lock

Problem:

The roadmap currently contains a stale C6 row for a future
`code/semantic_search.py`, while `palace.code.semantic_search` already exists
through `code/find_semantic.py` and `code/semantic_contract.py`. Product-quality
work must start from the real implementation boundary.

Scope:

- Document the current MCP route, schema, embedding backend, Neo4j vector query,
  and response contract.
- Decide which module owns candidate retrieval, ranking, filtering, snippets,
  and result serialization.
- Update the roadmap to mark stale C6 as superseded by G0.5.5 and point future
  quality work to PR3-PR6 in this spec.
- Record exact files in scope for PR3-PR6 so child issues cannot invent a second
  semantic-search stack.

Acceptance:

- Roadmap no longer claims `semantic_search.py` is the pending implementation
  file.
- PR3-PR6 child issue templates name the current source files they are allowed
  to edit or extend.
- The architecture note states whether candidate retrieval remains dense-only
  for v1 or proceeds to PR3a for a hybrid decision.

Verification:

- `rg -n "semantic_search|find_semantic|semantic_contract" services/palace-mcp/src`
  output is attached to the issue or summarized in the PR.
- Docs-only diff unless source comments are required to pin the contract.

### PR1 — Clean Docker Image Reproducibility

Problem:

Recent smoke required runtime pinning and source copy into a running container.
A product image must rebuild cleanly and start with the exact code and pinned
dependency stack.

Scope:

- Pin base images by digest or by immutable tag plus an explicit digest-migration
  process.
- Pin and test the ML stack required by Qodo in committed dependency files.
- Require a frozen dependency install path, such as `uv sync --frozen` or the
  project-local equivalent, and report dependency lockfile identity in evidence.
- Make `docker compose build palace-mcp` or the selected build command
  deterministic on a clean host with cache mounts.
- Split heavyweight ML dependency layers so rebuilds do not repeat model/package
  downloads when source code changes.
- Add build timeouts/retry policy for known slow ML dependency steps and emit
  timeout-labeled logs.
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
- Fresh-host scratch rebuild command and pass/fail criteria are documented.
- The clean image starts and `/healthz` returns ok.
- Runtime dependency versions match committed pins.
- Failure to access a local model cache in local-only mode is reported as an
  actionable config error, not an implicit download/hang.
- Health/liveness and signal handling are sufficient for compose to stop and
  restart the service cleanly.

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
- Define env precedence and mount contract for `PALACE_HF_CACHE_DIR`,
  `PALACE_QODO_CACHE_DIR`, `UV_CACHE_DIR`, and any compose override variables.
- Add compose/env knobs for those caches.
- Add preflight checks that report cache presence, size, local-only status, and
  writeability.
- Model-cache status must be reported as one of:
  `absent`, `present`, `stale`, or `readonly`.
- Local-only mode with a missing, invalid, world-writable, or mixed-owner cache
  fails fast. It must not silently download from the network.
- Record cache provenance without secrets: model id, source, revision, cache
  root, and integrity/version marker.
- Define cleanup levels:
  - safe: temporary workdirs and build cache;
  - reclaim: stopped containers and unused app images;
  - destructive: volumes/model caches, only explicit operator approval.
- Cleanup implementation must use realpath guards, refuse empty paths, `/`, `$HOME`,
  and paths outside app-owned directories, and run in dry-run mode by default.
- Do not use broad wildcard cleanup such as `docker volume prune` in the product
  runbook.

Acceptance:

- Operator can configure cache paths with env vars or compose override.
- Preflight prints cache status without exposing secrets.
- Cleanup script/runbook never removes Qodo/HF model cache by default.
- Re-running smoke uses existing model cache in local-only mode.

Verification:

- Preflight test with cache present.
- Preflight test with cache missing in local-only mode.
- Preflight test with readonly or unsafe cache ownership.
- Documentation review for cleanup levels.

### PR3a — Semantic Candidate Backend Decision

Problem:

Ranking improvements cannot compensate for a weak candidate set. We need an
explicit v1 decision for dense-only, sparse-only, or hybrid candidate retrieval
before locking ranking thresholds.

Scope:

- Compare dense vector candidate retrieval, sparse/Tantivy candidate retrieval
  if available, and hybrid retrieval on a small dev query set.
- Measure latency, candidate recall, implementation risk, and operational
  dependencies.
- Choose the v1 strategy and document follow-up work if hybrid is deferred.

Acceptance:

- Decision note records the selected backend strategy and rejected alternatives.
- Candidate pool size is fixed and deterministic for PR3/PR6 tests.
- Query normalization, tokenizer/model revision, and candidate sort order are
  documented.

Verification:

- Dev-matrix comparison report with per-query top-k candidates.
- No PR3 ranking work starts without this decision or explicit operator waiver.

### PR3 — Semantic Ranking Contract

Problem:

Raw vector scores are not enough. Operators need stable ranking that prefers
useful first-party implementation symbols over generated/dependency/noise when
the semantic score is close.

Scope:

- Define a deterministic ranking formula with explicit weights and penalties.
- Define exact numeric quality metrics for semantic search:
  `Recall@k`, `Precision@k`, `MRR` or `nDCG@k`, scope-leak rate, context
  availability rate, and determinism hash match rate.
- Include tie-breakers that produce total ordering:
  1. final score desc;
  2. source scope priority;
  3. symbol kind priority;
  4. project slug asc;
  5. qualified name asc.
- Keep raw vector score in output for debugging.
- Make ranking explainable per hit via optional `rank_features`.
- Pin model/tokenizer identity, query normalization, candidate pool size, and
  explicit sort after every filter.

Acceptance:

- Ranking formula is documented in code comments or spec docs.
- Ranking formula has concrete weights, penalties, caps, and tolerance. Two
  implementers must derive the same ordering from the same input rows.
- Unit tests prove stable ordering for equal/near-equal vector scores.
- First-party implementation beats dependency/generated accessor noise when
  vector scores are within the documented tolerance.
- Response includes enough debug fields to explain why a hit ranked where it
  did.
- Determinism test produces the same ordered qualified-name hash across repeated
  runs on the same graph snapshot.

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
- Report scope-leak counts in semantic matrix output.

Acceptance:

- Default search returns useful first-party results for already indexed
  projects after migration/re-index path is applied.
- Explicit `projects` list can search `uw-ios-app` + kits + shared toolkit in
  one call.
- Unknown or legacy scope cannot silently make all defaults empty.
- Tests cover dependency exclusion, generated exclusion, explicit inclusion,
  and cross-project search.
- Explicit expert search can include dependency/generated/SDK scopes without
  changing the product default.

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
- Reuse or extend `palace_mcp.git.path_resolver`; do not add a second ad hoc
  path-containment implementation.
- Treat persisted `file_path` as untrusted.
- Resolve paths with `realpath` and require containment inside the resolved
  project root, not just a broad parent mount.
- Reject absolute persisted paths, `..` segments, and symlink escapes before
  reading source.
- Bound snippet line count and byte count.
- Return `context.available=false` with warning codes when snippet lookup is
  unavailable instead of failing the whole search.
- Optional usage preview must be project/commit scoped.
- Snippets are commit- or digest-scoped. Stale source must be reported as
  `context.status=stale_source` rather than silently mixing source from another
  checkout.
- Track snippet usefulness metrics: context availability rate, warning-code
  counts, and average returned line/byte size.

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
  - row class: `mandatory`, `advisory`, or `no_answer`;
  - source scope parameters;
  - `must_match_all_in_top_n`;
  - `must_match_any_in_top_n`;
  - `must_not_match_in_top_n`;
  - expected qualified-name and file patterns;
  - disallowed/noise qualified-name and file patterns;
  - `min_hits`;
  - `max_noise_hits`;
  - minimum top-k hit count;
  - `required_context_status`;
  - `row_pass_rule`.
- Add a runner that executes the matrix against a live or fixture graph and
  prints per-row top-k evidence.
- Split semantic eval into:
  - dev rows that implementers may inspect and tune against;
  - locked holdout rows authored or approved by someone not changing ranking;
  - live probe rows used for operator acceptance.
- Include core product queries:
  - timers/schedulers;
  - transaction signing;
  - address validation;
  - balance refresh;
  - hex/data conversion across app + toolkit;
  - dead-code cluster lookup.
- Include noisy/typo, symbol-ish, acronym/alias, cross-project ambiguous,
  generated/dependency collision, paraphrase, and no-answer rows.

Acceptance:

- Matrix is machine-readable and committed.
- Runner exits non-zero on failed rows.
- Every row prints top-k evidence with project, qualified name, score,
  source_scope, file path, and context status.
- The matrix cannot pass silently with zero executed rows.
- Runner reports numeric quality metrics: recall/precision at k, MRR or nDCG,
  scope-leak rate, context availability rate, and determinism hash match rate.
- Holdout results are reported separately from dev results.
- Required rows cannot be waived by prose; failures must either block PR10 or
  create an operator-approved follow-up issue.

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
- Start from existing runtime assets where possible, especially
  `services/palace-mcp/scripts/smoke_uw_ios_bundle.py` and
  `paperclips/scripts/scip_emit_swift_kit.sh`.
- Runtime rows must include exact repo refs, host class, compose profile,
  runner version, and expected stage sequence.
- Allowed skips must use explicit skip codes and cannot hide missing product
  stages.

Acceptance:

- Matrix distinguishes build/emission failure from extractor failure.
- `uw-ios-app` row covers SCIP -> symbol index -> dead code -> embeddings.
- Swift kit row proves iOS-oriented kit path, not generic macOS `swift build`.
- Bounded embedding row reports limit and does not appear as full coverage.
- Passing rows include a product-surface probe and an invariant graph query, not
  only `/healthz`.

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
  - CPU-first assumptions and optional GPU follow-up boundary;
  - disk requirements;
  - Linux kernel minimum;
  - Docker/Compose requirements;
  - Neo4j memory settings;
  - model cache directory;
  - repo mount directory;
  - env file template.
- Define compose profiles and service matrix for `server`, `smoke`, `macbook`,
  `ci`, and `cache-warm`.
- Add sample `.env.example` or documented env block for product server.
- Add compose override examples for:
  - model cache mount;
  - repo parent mount;
  - Neo4j memory;
  - palace-mcp port;
  - local-only embeddings.
- Define backup/restore boundaries for Neo4j and caches.
- Repositories are mounted read-only by default. Baseline server profile must
  not mount `/var/run/docker.sock`, `$HOME`, `~/.ssh`, or broad secret-bearing
  parent directories.
- Neo4j defaults to internal-only networking. Host admin access, when needed,
  binds to loopback only. Auth must be enabled, and startup/preflight fails on
  default password, missing password, or auth-disabled configuration.
- Define UID/GID and file-permission expectations for repo and cache mounts.

Acceptance:

- Fresh server can start Neo4j + palace-mcp with documented commands.
- Preflight reports missing model cache, repo mount, or Neo4j auth mismatch.
- No secret values are committed.
- Install docs separate MacBook Xcode smoke from server indexing/runtime.
- Preflight reports Neo4j exposure mode and auth status without printing
  passwords or tokens.

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
- Consolidate or link existing `docs/runbooks/ingest-swift-kit.md` instead of
  duplicating conflicting kit-smoke instructions.
- Include "do not delete" list:
  - Qodo/HF cache;
  - repo clones;
  - Neo4j data unless rebuilding intentionally;
  - evidence reports until issue close.
- Include safe, reclaim, and destructive cleanup commands. Destructive cleanup
  requires an explicit flag and confirmation; dry-run is the default.
- Never instruct operators to paste raw `docker compose config`, full `.env`,
  auth headers, model tokens, or secret values into issues or Telegram.

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
  - graph snapshot id;
  - registered projects and refs;
  - host type;
  - runner version;
  - matrix schema version;
  - embedding backend;
  - model id and digest or immutable revision;
  - model cache path status without secrets;
  - Docker image id;
  - Neo4j database fingerprint and exposure/auth status;
  - Neo4j database status;
  - runtime smoke matrix results;
  - semantic golden matrix results;
  - known limitations;
  - follow-up issues.
- No manual runtime source copy, manual pip install, or undocumented env tweak
  is needed for the passing path.
- Any failed row becomes a follow-up issue with owner and reproduction command.
- Evidence artifacts are redacted. They must not include raw compose output,
  full env files, auth headers, tokens, or secret values.

Verification:

- Final evidence artifact attached to parent roadmap issue.
- Parent can close only after PR10 passes or the operator explicitly accepts
  remaining limitations.

## Evidence, Gates, and Artifact Contract

`/healthz` is required for runtime readiness but is never sufficient by itself.
Every passing slice that claims product behavior must include at least one
product-surface probe and one invariant check relevant to the slice. Examples:
semantic query transcript plus top-k JSON for PR3-PR6, graph count/query for
extractor smoke, and compose/service health plus MCP call for runtime rows.

Every child issue must define:

- blocking CI jobs;
- required live runs;
- artifact paths;
- who may mark the slice done;
- waiver rule;
- follow-up issue rule.

Raw verification artifacts must be redacted before posting to Paperclip,
GitHub, Telegram, or long-lived docs. Do not post raw `docker compose config`,
full `.env`, auth headers, secret values, model tokens, or full host directory
trees. Reports should include allowlisted status fields and normalized paths
where possible.

## Matrix Row Schema

Semantic matrix rows must include these fields unless a row explicitly declares
why a field is not applicable:

- `id`
- `class`: `mandatory`, `advisory`, or `no_answer`
- `query`
- `projects`
- `source_scopes`
- `top_k`
- `must_match_all_in_top_n`
- `must_match_any_in_top_n`
- `must_not_match_in_top_n`
- `expected_file_patterns`
- `disallowed_file_patterns`
- `min_hits`
- `max_noise_hits`
- `required_context_status`
- `row_pass_rule`

Runtime matrix rows must include:

- `id`
- `host_class`
- `repo`
- `ref`
- `compose_profile`
- `required_stage_sequence`
- `expected_artifacts`
- `min_graph_counts`
- `embedding_limit`
- `allowed_skip_codes`
- `row_pass_rule`

Matrix runners must print per-row pass/fail, top-k or stage evidence, and a
machine-readable summary. They must exit non-zero when a mandatory row fails or
when zero rows execute.

## Provenance Contract

Final PR6/PR7/PR10 artifacts must include:

- `commit_sha`
- `graph_snapshot_id`
- `registered_projects`
- `repo_refs`
- `embedding_backend`
- `model_id`
- `model_digest_or_version`
- `neo4j_db_fingerprint`
- `runner_version`
- `matrix_schema_version`
- `docker_image_id`
- `compose_profile`
- `host_class`

The report may include cache roots and normalized mount names, but not tokens,
auth headers, full `.env` contents, or broad host directory listings.

## Security and Trust Boundary Defaults

- Repo mounts are read-only by default.
- Baseline server profile does not mount `/var/run/docker.sock`, `$HOME`,
  `~/.ssh`, or broad secret-bearing parent directories.
- Neo4j is internal-only by default. Optional host admin access binds to
  loopback only, requires auth, and reports exposure mode without secrets.
- Model caches must not be world-writable or mixed-owner in local-only mode.
- Snippet file paths stored in Neo4j are untrusted input. Reads must resolve
  against the registered project root and reject escapes before opening files.
- Cleanup tools run dry-run by default and refuse app-unsafe target paths.

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

Minimum local/runtime commands expected across the roadmap:

```bash
docker compose config
docker compose build palace-mcp
docker compose up -d neo4j palace-mcp
curl -fsS http://localhost:8080/healthz
```

```bash
cd services/palace-mcp
uv run python -m pytest tests/embeddings tests/code tests/code_graph tests/git tests/extractors/unit tests/extractors/integration tests/extractors/smoke
uv run ruff check src tests
```

PR6 and PR7 must define exact runner paths before implementation starts. A
child issue may not close with placeholder command names. If a runner path is
created by the slice, that path and its expected JSON fields become part of the
slice acceptance.

No slice may claim product readiness using only screenshots or prose. Every
passing claim must include command output, report path, or committed test.

## Closed Scope Decisions

1. Server profile is CPU-first; GPU is follow-up.
2. Runtime matrices default to an isolated throwaway compose project.
3. V1 required repo set is `uw-ios-app` plus the HorizontalSystems kit repos
   needed by the matrix. Other repos start advisory.
4. Golden matrix uses mandatory/advisory/no-answer rows instead of a global
   `4/5` or `5/5` threshold.
5. V1 installation is git checkout plus compose profile/override. Packaging is
   follow-up.
6. `palace.code.semantic_search` quality work extends the current
   `find_semantic.py` / `semantic_contract.py` implementation unless PR0a
   explicitly decides otherwise.
