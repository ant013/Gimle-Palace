# Sprint G — Project-Specialist Agent (rev3.2, 2026-05-21)

> **Filename note**: this file lives at `G-ios-specialist-agent.md` during draft; **rename to `G-project-specialist-agent.md` at commit** (language-agnostic per G-D3). Cross-references in `roadmap-patch.md` already use the new name.
>
> **Status**: final draft for Board commit.
>
> **Rev3.2 (2026-05-21 night)** — incorporates 6 voltagent reviews (architect / qa / research / competitive / trend / security) + 2 SymDex code-level deep-dives + empirical Cypher diagnostic + operator Q1-Q6 decisions. Major changes vs rev3.1: (a) G0b: defense-in-depth enforcement (Python wrapper + Neo4j APOC trigger, not mixin alone), data-migration script for `path → file_path`, multi-tenant isolation tests; (b) G0.5: Qodo-Embed-1-1.5B (Apache 2.0, self-hosted) as default with `EmbeddingBackend` interface — no Voyage lock-in, no source-code-to-third-party; (c) **G0f** new sub-sprint (security foundation, 2 weeks) gating external pilots only — internal/operator use unblocked; (d) G2 split: Phase 1 synthetic / Phase 2 real PR corpus; (e) G0d retains Periphery mandatory (operator decision Q3 — Swift project ⇒ macOS guaranteed); (f) Neo4j GDS Community Edition tolerated now with explicit "swap to own Johnson's SCC before first paying client" risk (operator decision Q2); (g) G1 audit gets Sourcegraph Amp comparison column; (h) dynamic-dispatch root-set extractor + fixture tests added to G0d.
>
> Wall-time rev3.2: **13-17 weeks** (internal use ready at G4; external pilot adds G0f = +2 weeks gated).
>
> Industry references throughout: SymDex ([github.com/husnainpk/SymDex](https://github.com/husnainpk/SymDex), MIT), AgentSpec ([arxiv 2503.18666](https://arxiv.org/abs/2503.18666)), Cursor rules ([cursor.com/docs/rules](https://cursor.com/docs/rules)), SWE-agent ([NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf)), Aider repo-map ([aider.chat/docs/repomap.html](https://aider.chat/docs/repomap.html)), Qodo-Embed-1 ([huggingface.co/Qodo/Qodo-Embed-1-1.5B](https://huggingface.co/Qodo/Qodo-Embed-1-1.5B)), Neo4j vector search ([neo4j.com/developer/genai-ecosystem/vector-search](https://neo4j.com/developer/genai-ecosystem/vector-search/)), Periphery ([github.com/peripheryapp/periphery](https://github.com/peripheryapp/periphery)), Neo4j GDS SCC ([neo4j.com/docs/graph-data-science](https://neo4j.com/docs/graph-data-science/current/algorithms/strongly-connected-components/)), Meta SCARF ([FSE 2023 — dl.acm.org/doi/10.1145/3611643.3613871](https://dl.acm.org/doi/10.1145/3611643.3613871)), Sourcegraph Amp ([amplifilabs.com](https://amplifilabs.com/post/sourcegraph-amp-agent-accelerating-code-intelligence-for-ai-driven-development)).

## Goal

Build a paperclip agent role (`project-specialist`, language-agnostic) that **cannot bypass** consulting Gimle (symbol discovery / call graph / find_idiom / ADRs / conventions / semantic search / dead-code detection) before writing code. Emit PRs that follow project idiom rather than blank-page generation. **Designed from day one to ship as a product** to teams beyond ourselves (operator decision G-D3).

## Driver

When `project-specialist` is asked "add NewChainKit to UW iOS" (or equivalent task in any client codebase), the resulting PR (a) cites existing patterns it modelled on, (b) follows project conventions on first try, (c) introduces no duplicates of existing helpers, (d) avoids touching dead clusters, (e) merges with ≤1 CR change-request round.

**Exit condition**: ≥80% of pilot tasks meet (a)-(e) across N≥20 paired runs per task type.

## Wall-time

Sum of critical-path sprints (G3 runs ‖ G2/G2.5 — does not extend critical path):

| Path | Optimistic | Conservative |
|---|---|---|
| **Internal** (G0 + G0.5 + G1 + G2 + G2.5 + G4) | **9 weeks** | **13 weeks** |
| **External pilot** (+ G0f 2 weeks, can run ‖ G4) | **11 weeks** | **15 weeks** |

Breakdown: G0 (2-3w) + G0.5 (1w) + G1 (1w) + G2 (2-3w) + G2.5 (1-2w) + G4 (2-3w) = 9-13w internal; +G0f (2w) = 11-15w external.

## Sprint sequence (rev3.2)

| ID | Sprint | Wall-time | Depends on | Team | Status |
|----|--------|-----------|------------|------|--------|
| **G0** | Substrate readiness — 5 sub-sprints | ~2-3 weeks (G0a sequential → G0b ‖ G0c → G0d → G0e) | nothing | Board + Infra + Claude PE | 🚧 G0a partial (3/5 kits ingested 2026-05-21; bitcoin-kit pending diagnose, uw-ios-app pending) |
| **G0.5** | Semantic embeddings layer (Neo4j vector + Qodo-Embed-1-1.5B self-hosted, `EmbeddingBackend` abstraction) | ~5-6 days | G0 | Claude PE | 📋 |
| **G1** | Capability audit — comparative baseline (Gimle / SymDex / Sourcegraph Amp / grep) on 7 capabilities | ~1 week | G0.5 | Board + Claude | 📋 |
| **G2** | Recipe pilot — Phase 1 synthetic / Phase 2 real PR corpus, 3-arm A/B with N≥20 paired runs | ~2-3 weeks | G1 | Board + Claude | 📋 |
| **G2.5** | Domain-preflight middleware enforcement (blocks write_file without preflight palace.* calls citing real returned symbols) | ~1-2 weeks | G2 | Claude PE | 📋 |
| **G3** | Measurement loop — gaming-resistant metrics, language-agnostic | ~1 week | G1 (‖ G2/G2.5) | Claude PE | 📋 |
| **G4** | Roll-out — 4 more recipe types (each includes `find_dead_code` pre-check) | ~2-3 weeks | G2.5 + G3 | Claude + CX | 📋 |
| **G0f** | **Security foundation** — multi-tenant auth + isolation + secret scrubbing + build sandbox + audit log (**gates external pilots only**, not internal use) | ~2 weeks | G3 (concurrent OK) | Claude PE + security review | 📋 |
| **G5** | Optional extractors — scaffolding, test pattern, diagram, route discovery | ~2-3 weeks | G4 (on metric trigger) | per slice | 📦 |

**Parallelisation**: G3 ‖ G2/G2.5 (independent infra). G0f can start any time after G3 design closes, runs alongside G4 if external pilot timing demands.

**Gating**:
- G0.5 starts only when G0e verification matrix passes: ≥13/15 testable extractors return reasonable project-linked node counts, AND both input-conditional extractors (`hot_path_profiler`, `localization_accessibility`) emit no errors when their input is absent
- G2 starts only if G1 audit shows ≥4/7 capabilities scoring `acceptable`
- **External pilot starts only after G0f closes** (internal use does not wait)

**Extractor inventory (17 total, denominator standardised)**:

15 testable extractors (hard pass/fail with non-zero threshold): `symbol_index_swift`, `arch_layer`, `git_history`, `code_ownership`, `coding_convention`, `crypto_domain_model`, `cross_module_contract`, `cross_repo_version_skew`, `dead_code` (G0d, replaces shallow `dead_symbol_binary_surface`), `dependency_surface`, `error_handling_policy`, `hotspot`, `public_api_surface`, `reactive_dependency_tracer`, `testability_di`.

2 input-conditional extractors (passes with 0 nodes when input absent): `hot_path_profiler` (requires `profiles/`), `localization_accessibility` (kit may lack UI strings).

---

## G0 — Substrate readiness (mega-sprint)

**Exit criterion (= product readiness gate for internal use)**: on a clean checkout of any supported Swift kit, run `prepare_*.sh && ingest_*.sh` → resulting Neo4j graph passes G0e verification matrix where each of 14 extractors returns reasonable, project-linked, semantically valid nodes for that kit.

### G0a — Activate ingest for remaining kits + uw-ios-app

**Status today (2026-05-21 night)**:
- `bitcoin-core` ✅ done (31649 Symbol-equivalent nodes per JSON, schema linking pending G0b)
- `evm-kit` ✅ done (14409 symbol nodes, partial_failure only on missing artefacts)
- `dash-kit` ✅ done (6301 symbol nodes)
- `bitcoin-kit` ⚠ silent (need diagnose — possible mid-flight kill)
- `uw-ios-app` 📋 pending (needs `/private/tmp` path quirk per [GIM-392 runbook](../runbooks/xcode-app-scip-emit.md))

**Remaining tasks**: diagnose bitcoin-kit; run uw-ios-app; snapshot via `snapshot_neo4j_uw_ios.sh`.

**Wall-time**: 1 day operator-time.

### G0b — Schema linking fix (defense-in-depth enforcement)

**Empirical scope (Cypher audit 2026-05-21)**: only 1 of 14 extractors (`reactive_dependency_tracer`) tags `group_id` correctly. ~14,000+ untagged nodes for bitcoin-core alone. Plus property naming inconsistency: `:File` uses `n.path`, `:Symbol` uses `n.file_path`. Root cause: no common write chokepoint; each extractor wrote its own pattern.

**Operator decision Q4 (defense-in-depth)**: enforce at **two** independent layers.

#### Layer 1 — Python wrapper (`ScopeTaggedWriter`)

```python
# services/palace-mcp/src/palace_mcp/extractors/foundation/scope_tagging.py

from typing import Final
from neo4j import Transaction, AsyncTransaction

# Allowlist defends against label-injection through caller-controlled strings.
ALLOWED_LABELS: Final[frozenset[str]] = frozenset({
    "Symbol", "Function", "File", "Module", "Class", "Struct", "Protocol",
    "ConventionViolation", "Convention", "CatchSite", "ErrorFinding",
    "Commit", "Author", "OwnershipFileState",
    "ExternalDependency", "CryptoFinding", "DiPattern", "TestDouble",
    "Layer", "ArchRule", "ArchViolation",
    "Hotspot", "ReactiveDiagnostic", "PublicApiSymbol", "CrossModuleContract",
    "VersionSkew", "DeadFinding", "DeadCluster",
    "HotPath", "I18nFinding", "HardcodedString", "LocaleResource",
})

class ScopeTaggedWriter:
    """All extractor node writes go through this. group_id required.

    `group_id` format: "project/<slug>" (e.g. "project/bitcoin-core").
    See [[reference-palace-neo4j-creds]] for tenant scoping conventions.
    """

    def __init__(self, *, default_group_id: str | None = None,
                 remove_legacy_path: bool = False):
        # default_group_id eliminates kwarg burden at every call-site.
        # remove_legacy_path=True after migration window completes (Step 3).
        self._default_group_id = default_group_id
        self._remove_legacy_path = remove_legacy_path

    def write_node(self, tx: Transaction, label: str, props: dict,
                   *, group_id: str | None = None) -> "Result":
        scope = group_id or self._default_group_id
        if not scope:
            raise ValueError(f"group_id required for label {label}")
        if label not in ALLOWED_LABELS:
            raise ValueError(f"label {label!r} not in ALLOWED_LABELS")
        if "cm_id" not in props:
            raise ValueError(f"cm_id required in props for label {label}")
        props["group_id"] = scope
        # Standardise file-path property naming during migration window.
        if "path" in props and "file_path" not in props:
            props["file_path"] = props["path"]
        if self._remove_legacy_path and "path" in props:
            del props["path"]
        return tx.run(
            f"MERGE (n:{label} {{cm_id: $cm_id}}) SET n += $props",
            cm_id=props["cm_id"], props=props,
        )
```

Refactor 11 broken extractors to use `ScopeTaggedWriter`. graphiti-core path (used by `reactive_dependency_tracer`) already tags `group_id` via graphiti's native semantics → keep as-is.

#### Layer 2 — Neo4j APOC trigger (DB-side guard)

```cypher
CALL apoc.trigger.add('require_group_id',
  'UNWIND $createdNodes AS n
   WITH n WHERE NOT (n:Bundle OR n:Project OR n:IngestRun OR n:IngestCheckpoint)
   CALL apoc.util.validate(
     n.group_id IS NULL,
     "node label=%s cm_id=%s missing required group_id",
     [labels(n)[0], coalesce(n.cm_id, "<none>")]
   ) YIELD value
   RETURN value',
  {phase:'before'}
);
```

Pattern: `validate(<predicate>, <message>, <args>)` aborts the transaction in `before` phase when predicate is true. Any write that bypasses `ScopeTaggedWriter` (e.g. direct cypher-shell, future extractor written without inheritance) is **rejected at DB layer**. Defense-in-depth.

Verified against APOC 5.x semantics: `before`-phase triggers abort the entire tx on validation failure. Bundle / Project / IngestRun / IngestCheckpoint nodes are infrastructural and intentionally exempt (some pre-date tenant scoping).

#### Layer 3 — Read-path scoping wrapper (preview, full in G0f)

`ScopedCypherSession` wrapper that injects `WHERE n.group_id = $authz_scope` into every MCP-tool read query. Initial single-tenant: scope is hardcoded `"project/<slug>"`. Multi-tenant evolution in G0f.

#### Data migration: `path → file_path`

Existing nodes in production Neo4j have only `path`. Migration uses `apoc.periodic.iterate` to avoid full-graph locks; restricts to labels that carry file references; provides rollback via Neo4j snapshot.

```cypher
// Step 1 (idempotent): copy path to file_path where missing.
// Batch-iterated to avoid lock-up on prod graph (~14000 nodes for bitcoin-core alone).
CALL apoc.periodic.iterate(
  'MATCH (n) WHERE (n:Symbol OR n:File OR n:Function OR n:Module)
     AND n.path IS NOT NULL AND n.file_path IS NULL
   RETURN n',
  'SET n.file_path = n.path',
  {batchSize: 1000, parallel: false}
) YIELD batches, total, errorMessages
RETURN batches, total, errorMessages;

// Step 2 (deprecation window, 30 days):
// dual-read in Audit-V1 fetcher: `coalesce(n.file_path, n.path)`
// new writes only set file_path (ScopeTaggedWriter aliases automatically)

// Step 3 (post-window, ONLY after dual-read deprecated):
// requires ScopeTaggedWriter(remove_legacy_path=True) flipped first
CALL apoc.periodic.iterate(
  'MATCH (n) WHERE (n:Symbol OR n:File OR n:Function OR n:Module)
     AND n.path IS NOT NULL AND n.file_path IS NOT NULL
   RETURN n',
  'REMOVE n.path',
  {batchSize: 1000, parallel: false}
) YIELD batches, total, errorMessages
RETURN batches, total, errorMessages;
```

**Rollback**: pre-migration Neo4j snapshot via `neo4j-admin database dump` taken before Step 1; restore with `neo4j-admin database load` rewinds any state. Step 3 has no in-place rollback path — only snapshot restore.

Script: `paperclips/scripts/migrate_path_to_file_path.sh` with `--dry-run`, `--apply-step-1`, `--apply-step-3`, `--rollback-snapshot` flags. Audit-V1 fetcher gets dual-read `coalesce(n.file_path, n.path)` until Step 3 completes.

#### Tests (mandatory before G0b merge)

1. **Unit**: `ScopeTaggedWriter.write_node(..., group_id=None)` raises ValueError
2. **Unit**: `ScopeTaggedWriter.write_node(..., group_id="x")` sets property
3. **Property-based**: enumerate all extractor classes in `extractors/`, assert each call site uses `ScopeTaggedWriter` or `graphiti` runtime — catches extractor-by-copy
4. **Integration**: APOC trigger rejects raw `MERGE (n:Symbol {cm_id: "x"})` without group_id
5. **Multi-tenant isolation**: after ingesting bitcoin-core + evm-kit, `MATCH (n:Function {group_id:"project/bitcoin-core"}) RETURN count(n)` equals single-kit count (no cross-contamination)
6. **Migration**: `migrate_path_to_file_path.sh --dry-run` on production snapshot reports exact node count to be touched
7. **Audit-V1 regression baseline**: capture current counts before merge; assert post-merge counts unchanged for non-group_id-related queries

**Tasks**:

| Day | Task |
|---|---|
| 1 | Schema audit spike — grep all `properties=` and `SET n.` in `extractors/`; surface ALL property inconsistencies (not just `path`/`file_path`); right-size remaining days |
| 2 | `ScopeTaggedWriter` framework + Layer 1 unit tests; APOC trigger + Layer 2 integration test |
| 3 | Refactor `symbol_index_swift.py` + `scip_parser.py` shared substrate (biggest blast radius; touches Python/TS/Java/Kotlin/Solidity/Clang indexers indirectly) |
| 4 | Refactor `git_history`, `code_ownership` (combined ~3300 untagged nodes for bitcoin-core) |
| 5 | Refactor `coding_convention`, `error_handling_policy`, `testability_di` (~1146 untagged) |
| 6 | Refactor remaining 5: `arch_layer`, `crypto_domain_model`, `hotspot`, `localization_accessibility`, `dependency_surface` |
| 7 | `IngestRun`/`IngestCheckpoint` schema cleanup; migration script + dual-read backport in Audit-V1 fetcher |
| 8 | Re-run bitcoin-core + 3 kits full ingest; G0e matrix dry-run |

**Wall-time**: 7-8 days (expanded from rev3.1's 5-7 after architect + qa empirical findings).

**Owner**: Claude PE.

### G0c — Missing artefacts pipeline

**Decision Q3**: Periphery mandatory, no SCIP-only fallback. Swift project ⇒ macOS + Xcode guaranteed.

**New script**: `paperclips/scripts/prepare_swift_kit_artifacts.sh`

| Step | Tool | Output | Failure mode |
|---|---|---|---|
| 1 | `periphery scan --project=<...>.xcworkspace` | `periphery/periphery-<version>-swiftpm.json` | fail-loud with installation guide |
| 2 | `swift build -Xswiftc -emit-module-interface -Xswiftc -enable-library-evolution` | `.palace/public-api/swift/*.swiftinterface` | fail-loud (or doc Package.swift settings) |
| 3 | (optional) Instruments XCTest profiling | `profiles/*.json` | skip gracefully if operator doesn't supply |

After `prepare_*.sh` succeeds, `ingest_*.sh` runs all extractors with full input coverage. Update `ingest_*.sh` to refuse start if `prepare_*.sh` not run (no silent skip).

**Test cases**:
- Stale Periphery artefact (wrong version): assert pipeline reports version-mismatch error, doesn't proceed
- Missing `prepare_*.sh` run: `ingest_*.sh` fails with actionable error

**Wall-time**: 3-5 days.

**Owner**: Claude PE.

### G0d — Deep dead-code extractor (genuine moat)

**Decision Q3**: monolithic, no G0d.1/G0d.2 split.
**Decision Q2**: Neo4j GDS Community for SCC now; risk-tagged for own Johnson's SCC swap before first paying client.

#### Algorithm (rev3.2 enhanced)

```
INPUTS:
- SCIP symbol/call graph (Symbol + REFERENCES/CALLS/EXTENDS/CONFORMS edges)
- Periphery output (single-symbol unused baseline)
- Public API surface (.swiftinterface from G0c)
- Dynamic-dispatch root set (NEW — see below)

STEP 1 — Identify public entry seeds:
- public/open modifier
- .swiftinterface symbols
- Test target references
- App target references
- Framework conventions (@main, @objc @main, ApplicationDelegate, etc.)

STEP 1b — Dynamic-dispatch root set extractor (NEW, addresses Swift dynamic surface):
- Scan IBOutlet/IBAction targets (Storyboard XML, .xib files)
- Scan `#selector(...)` literals (Swift source)
- Scan `NSClassFromString` arguments
- Scan Info.plist class-name strings
- Scan SwiftUI @AppStorage/@SceneStorage/EnvironmentKey/PreferenceKey types
- Scan @objc/@objcMembers/dynamic/NSManaged annotations
- Scan @propertyWrapper / @attached macro attributions
- Scan Codable synthesis usage points
- Scan Swift macros (#expand sites) expanded code refs
- Add all above as additional reachability seeds

STEP 2 — Reachability BFS from union(public seeds, dynamic seeds)
Mark non-reachable as dead-candidates

STEP 3 — Extension chain pass:
For each dead-candidate Type:
  Find Extension nodes targeting it
  For each Extension:
    If methods/properties only → mark dead
    If adds protocol conformance:
      Check if protocol referenced via existential anywhere (Array<P>, any P, [P])
      If yes → Extension ALIVE for dispatch
      Else → dead

STEP 4 — SCC analysis (Neo4j GDS gds.alpha.scc):
Run on dead-candidate subgraph
Cluster size ≥3 → "dead cluster" finding
Cluster covering ≥50% of module top-level types → "dead module"

STEP 5 — Severity rank:
- critical: dead module
- high: SCC ≥3 classes
- medium: extension chain
- low: single symbol

STEP 6 — git_history enrichment:
- last_modified_at, last_referenced_externally (via git_history extractor)
- safe_to_delete_score = f(age, churn, no_external_refs, annotation_risk_flags)
- Cap < 1.0 for symbols with @objc/dynamic/NSManaged/property wrapper/macro
```

#### Output schema

Each finding has stable `finding_id` (UUID) for downstream PR-comment linking and `created_at` ISO-8601 timestamp. `members[].kind` enum: `class | struct | enum | protocol | actor | function | extension`. Severity enum: `critical | high | medium | low`. Schema is generic across all four finding kinds.

```json
[
  {
    "finding_id": "fd_a1b2c3...",
    "kind": "dead_scc_cluster",
    "severity": "high",
    "project": "bitcoin-core",
    "created_at": "2026-05-21T22:30:00Z",
    "members": [
      {"qualified_name": "BitcoinCore.LegacyAdapter", "kind": "class", "file_path": "Sources/.../LegacyAdapter.swift"},
      {"qualified_name": "BitcoinCore.LegacyManager", "kind": "class", "file_path": "Sources/.../LegacyManager.swift"}
    ],
    "size": 8,
    "reachable_from_public_surface": false,
    "reachable_from_dynamic_dispatch": false,
    "git_last_external_ref": "2024-03-15",
    "safe_to_delete_score": 0.92,
    "evidence_query": "MATCH (n:DeadFinding {finding_id: 'fd_a1b2c3...'})-[:DEAD_SYMBOL]->(s) RETURN s"
  },
  {
    "finding_id": "fd_d4e5f6...",
    "kind": "dead_module",
    "severity": "critical",
    "project": "bitcoin-core",
    "created_at": "2026-05-21T22:30:00Z",
    "members": [...],
    "size": 22,
    "module_coverage_ratio": 0.85,
    "safe_to_delete_score": 0.97,
    "evidence_query": "..."
  },
  {
    "finding_id": "fd_g7h8i9...",
    "kind": "dead_extension_chain",
    "severity": "medium",
    "project": "bitcoin-core",
    "created_at": "2026-05-21T22:30:00Z",
    "target_dead_type": "BitcoinCore.LegacyAdapter",
    "dead_extensions": [
      {"qualified_name": "BitcoinCore.LegacyAdapter+Helpers", "kind": "extension", "file_path": "..."}
    ],
    "protocol_conformance_checks": [
      {"protocol": "SomeProtocol", "used_via_existential": false}
    ],
    "safe_to_delete_score": 0.78,
    "evidence_query": "..."
  }
]
```

#### Tests (fixture-based, mandatory before G0d merge)

1. `@objc dynamic` method never called in SCIP — assert `safe_to_delete_score ≤ 0.3`, severity `low`
2. `class WalletEntity: NSManagedObject` with zero SCIP callers — excluded from dead-candidate set
3. Class used only via `Mirror(reflecting:)` — `safe_to_delete_score ≤ 0.5`
4. Extension adding protocol conformance to existential-used protocol — assert ALIVE even if target type dead
5. SwiftUI `@AppStorage` wrapper type with no static refs — excluded from dead-candidate set (added to dynamic seeds in Step 1b)

#### MCP tool

`palace.code.find_dead_code(project, min_severity="medium", include_test_only=False)`

**Wall-time**: 7-9 days (expanded from rev3.1 for dynamic-dispatch extractor + fixture tests).

**Owner**: Claude PE.

**Productization risk-tag**: SCC via Neo4j GDS Community has Commons Clause licensing limitation for commercial product. Before first paying client, swap to **own Johnson's SCC implementation** (Python, ~2-3 days work, no licensing entanglement). This is a **gate** before commercial GTM, not a blocker for internal use.

#### Future enhancements — G0d.v2 symbol-level refactoring analyzer (post-G0d, ~5-7 weeks)

Operator design 2026-05-23. Not in current G0d scope; tracked for sprint after G0d ships and produces evidence of false-positive rate on UW iOS app.

**Motivation.** Periphery and reach-from-roots SCIP analysis are both **coarse-grained**: they answer "is this symbol referenced anywhere?" with a single yes/no. They cannot distinguish meaningful use-classes that matter for refactoring decisions:

- `let vc = OldViewController(...)` — class used as actual screen
- `let route: OldViewController.Route = .send` — class used only as namespace for a nested type
- `func handle(_ obj: as? OldViewController)` — class used as cast target only
- `class Sub: OldViewController { }` — class used as superclass only
- `OldViewController.shared.foo()` — class used for singleton/static access only

Each pattern implies a different refactoring action. A merge-blocking deletion candidate is different from a "extract nested types, then delete container" candidate.

**Proposed architecture.**

1. **Ref-kind classifier** (new pre-processor, ~1-2 weeks). For each SCIP occurrence, parse the surrounding AST via SwiftSyntax (Apple's official parser) and annotate the reference with a kind label:
   - `:USED_AS_CONSTRUCTOR` (FunctionCallExpr where callee is the type)
   - `:USED_AS_NAMESPACE` (MemberAccessExpr.base where the resolved member is a nested type/static)
   - `:USED_AS_CAST` (`as?` / `as!` / `as`)
   - `:USED_AS_INHERITANCE` (InheritanceClause)
   - `:USED_AS_PROTOCOL_CONSTRAINT` (generic where-clause or `: Proto`)
   - `:USED_AS_TYPE_ANNOTATION` (let/var/param type)
   - `:USED_AS_KEYPATH` (`\Type.member` literal)

   These become typed Neo4j edges instead of the current single `:REFERENCES` collapse.

2. **Dynamic-root extractor** (~3-5 days). Parse non-source roots that SCIP doesn't see:
   - `*.storyboard` / `*.xib` — XML, `customClass=` attributes feed root set
   - `Info.plist` Principal class, scene delegates
   - `*.entitlements` background modes referencing classes
   - DI container registrations (project-specific: Swinject `container.register`, etc.)
   - Combine / KVO subscription targets via grep + AST (best-effort)

3. **Container-vs-children classifier** (~1 week). New `:DeadFinding` confidence state:

   ```
   DEAD_CONTAINER_LIVE_CHILDREN
   ├── container_symbol: OldViewController (qname)
   ├── live_nested_symbols: [OldVC.Route, OldVC.State]
   ├── live_nested_consumers: [AppCoordinator, FeatureX]
   ├── suggested_action: "extract nested types, then re-run reachability"
   └── deletion_safe: false
   ```

   Distinct from `DEAD_DELETION_SAFE` (no refs at all of any kind) and `DEAD_RUNTIME_GATED` (only dynamic-root refs).

4. **Refactoring-candidate MCP tool** (~3-5 days). New `palace.code.list_refactoring_candidates` tool that returns the container-with-live-children findings grouped by suggested action.

5. **False-positive audit on UW** (~1 week). Compare classifier output vs operator manual review on ~50 sampled symbols. Calibrate confidence thresholds. Anti-pattern allowlist via inline annotation: `// dead-code:retain reason="<reason>"`.

**Risks not in plain G0d.**

- **Mirror / KeyPath / @dynamicMemberLookup / Combine subscribers** create runtime references invisible to both SCIP and SwiftSyntax. Mitigate via explicit retention annotations + Combine/Mirror pattern detection (heuristic, best-effort, high false-negative tolerance).
- **scip-swift** does not currently emit ref-kind info — our annotator runs **on top of** SCIP, not via SCIP itself. If scip-swift gains symbol-role richness upstream, our annotator becomes thinner.
- Implementation cost is ~5-7 weeks qualified, **not** a 2-day extension to G0d. Schedule accordingly.

**Trade with current G0d shape.**

G0d v1 (current spec) ships first — gives baseline DeadFinding set + dynamic-dispatch root suppression. G0d.v2 layers on top: same `:DeadFinding` nodes get reclassified into refined confidence states + new typed edges. No throw-away work in v1.

**Owner candidates.** Claude PE + Claude Research Agent (SwiftSyntax integration is non-trivial; research-first plan recommended before implementation).

### G0e — Verification matrix (product readiness gate)

#### Per-extractor verification

Each extractor query specifies exact label + acceptance threshold. All queries use `n` as the bound pattern variable for consistency. 2 of 17 extractors classified input-conditional (pass with 0 nodes when input absent); 15 testable.

| Extractor | Acceptance query | Expected (bitcoin-core) | Class |
|---|---|---|---|
| `symbol_index_swift` | `MATCH (n:Function {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 1000 | testable |
| `symbol_index_swift` (semantic) | `MATCH (n:Function {group_id:"project/bitcoin-core"}) WHERE n.qualified_name IS NULL RETURN count(n)` | = 0 | testable (semantic spot-check — counts hollow nodes; same extractor, separate gate) |
| `arch_layer` | `MATCH (n:Layer {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 3 | testable |
| `git_history` | `MATCH (n:Commit {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 100 | testable |
| `code_ownership` | `MATCH (n:Author {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 1 | testable |
| `coding_convention` | `MATCH (n:ConventionViolation {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 50 | testable |
| `crypto_domain_model` | `MATCH (n:CryptoFinding {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 5 | testable |
| `cross_module_contract` | `MATCH (n:CrossModuleContract {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 10 | testable |
| `cross_repo_version_skew` | `MATCH (n:VersionSkew {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 1 | testable |
| `dead_code` (G0d) | `MATCH (n:DeadFinding {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 1 | testable |
| `dependency_surface` | `MATCH (n:ExternalDependency {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 5 | testable |
| `error_handling_policy` | `MATCH (n:CatchSite {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 50 | testable |
| `hotspot` | `MATCH (n:Hotspot {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 10 | testable |
| `public_api_surface` | `MATCH (n:PublicApiSymbol {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 20 | testable |
| `reactive_dependency_tracer` | `MATCH (n:ReactiveDiagnostic {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 100 | testable |
| `testability_di` | `MATCH (n:DiPattern {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 10 | testable |
| `hot_path_profiler` | `MATCH (n:HotPath {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 0 if no `profiles/` supplied | input-conditional (passes on no-error if input absent) |
| `localization_accessibility` | `MATCH (n:I18nFinding {group_id:"project/bitcoin-core"}) RETURN count(n)` | ≥ 0 (kit may lack UI strings) | input-conditional |

**Exit gate**: **≥ 13/15 testable extractors pass** (15 = all testable rows above, semantic spot-check counted as gate on `symbol_index_swift` not a separate extractor), AND **both input-conditional extractors emit no errors** when input absent.

#### Cross-extractor coherence (exact Cypher)

1. **CatchSite ↔ Function**: `MATCH (c:CatchSite {group_id:"project/bitcoin-core"}) WHERE NOT exists((c)-[:IN_FUNCTION]->(:Function {group_id:"project/bitcoin-core"})) RETURN count(c)` expected = 0
2. **PublicApiSymbol ↔ Symbol**: `MATCH (p:PublicApiSymbol {group_id:"project/bitcoin-core"}) WHERE NOT (p)-[:SYMBOL_REF]->(:Symbol {group_id:"project/bitcoin-core"}) RETURN count(p)` expected = 0
3. **DeadFinding ↔ Symbol**: `MATCH (d:DeadFinding {group_id:"project/bitcoin-core"})-[:DEAD_SYMBOL]->(s) WHERE s.group_id <> "project/bitcoin-core" RETURN count(d)` expected = 0

#### Multi-tenant isolation (mandatory)

After ingesting bitcoin-core + evm-kit:
```cypher
MATCH (n:Function {group_id:"project/bitcoin-core"}) RETURN count(n)
```
must equal the single-kit ingest count (no evm-kit contamination via property collision).

#### Semantic validity spot-checks

- Functions named "BitcoinCore.start" exist + are reachable
- Top-10 `find_idiom("adapter-creation")` results all `kind="class"` (no garbage labels)
- `find_dead_code` returns at least 1 finding (catches G0d ran)

**G0 reopen budget**: 2 iteration rounds max. If 3rd needed, escalate to operator: defer Phase 2 vs accept partial.

**Wall-time**: 2-3 days.

**Owner**: Board (queries) + Claude (any patches discovered).

---

## G0.5 — Semantic embeddings layer

**Decision Q5**: Qodo-Embed-1-1.5B default (Apache 2.0, self-hosted, no source-to-third-party). `EmbeddingBackend` interface for future swaps (Qwen2.5-Coder-Embed, Voyage, OpenAI as alternatives).

### Design

```python
# sentence-transformers >= 2.7 required for `prompt=` kwarg.
from typing import Protocol, runtime_checkable

@runtime_checkable
class EmbeddingBackend(Protocol):
    @property
    def dim(self) -> int: ...
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...

class QodoEmbed1Backend:
    """Default Qodo-Embed-1-1.5B, Apache 2.0, self-hosted."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer("Qodo/Qodo-Embed-1-1.5B")
        self._dim = self._model.get_sentence_embedding_dimension()  # 1536

    @property
    def dim(self) -> int:
        return self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, prompt="search_document: ").tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], prompt="search_query: ")[0].tolist()


def assert_index_dim_matches(backend: EmbeddingBackend, neo4j_session) -> None:
    """Fail-loud before any write if HNSW index dim != backend dim."""
    result = neo4j_session.run(
        "SHOW VECTOR INDEXES YIELD name, options "
        "WHERE name = 'symbolSemanticIdx' RETURN options"
    ).single()
    if result is None:
        return  # index not created yet — first write will create it
    indexed_dim = result["options"]["indexConfig"]["vector.dimensions"]
    if indexed_dim != backend.dim:
        raise RuntimeError(
            f"backend dim={backend.dim} but HNSW index dim={indexed_dim}; "
            f"reindex required before switching backends"
        )
```

Asymmetric retrieval prefixes per SymDex pattern (MIT attribution in source).

### Acceptance

1. New extractor `services/palace-mcp/src/palace_mcp/code/semantic/` post-processes after `symbol_index_swift`
2. `CREATE VECTOR INDEX symbolSemanticIdx FOR (s:Symbol) ON s.embedding OPTIONS {indexConfig: {'vector.dimensions': 1536, 'vector.similarity_function': 'cosine'}}`
3. `MATCH (s:Symbol) WHERE s.embedding IS NOT NULL RETURN count(s)` ≥ 30000 post bitcoin-core re-ingest
4. New tool `palace.code.search_semantic(query, repos=[], limit=10)`
5. Sanity: query "blockchain transaction adapter" → ≥3 sensible top-5 (manual operator verify)
6. Latency: median <1500ms on bitcoin-core scale (30K symbols, 1536d, HNSW) — slower than Voyage but acceptable for self-hosted privacy gain

### Wall-time

5-6 days (1 extra day vs rev3.1 for self-hosted model serving infra).

### Bonus: `palace.code.context_pack` (SymDex-inspired)

Token-budgeted wrapper: `palace.code.context_pack(query, max_tokens=8000)` returns `search_semantic` top-K + `get_snippet_rich` (callers + ADRs + idiom matches) trimmed to budget.

---

## G1 — Capability audit (rev3.2: 4-column comparison)

7 capabilities verified with **4-column** comparative baseline:

| Capability | Reference questions |
|---|---|
| Symbol-precise discovery | "where is BitcoinCore.start defined", "list subclasses of BaseAdapter", "find enums with `.pending` case" |
| Call graph (`trace_path`) | "what calls BitcoinCore.start", "trace sendTransaction cross-module" |
| Architectural memory (`query_adr`) | "why multiple Adapters per chain", "SwiftUI migration rationale" |
| Idiom detection (`find_idiom`) | "idiomatic MultiSwap provider", "test fixture pattern for kits" |
| Convention codification | "diff violates rules?", "list `async_cancel` violations in bitcoin-core" |
| Rich context (`get_snippet_rich`) | "show EvmKit.send with callers + ADRs + idiom matches" |
| **Semantic search** | "find Swift class wrapping blockchain adapter behavior", "find fee rate estimation helper", "find async cancellable network request pattern" |

**Comparative columns**: Gimle / SymDex / **Sourcegraph Amp** (rev3.2 addition per competitive-analyst) / grep+ripgrep.

**Grading**: `acceptable / partial / broken` per question, operator + Board manual verify, captured in `docs/runbooks/2026-05-XX-gimle-capability-audit-v1.md` for regression replay.

---

## G2 — Recipe pilot (rev3.2: phased real corpus)

**Decision Q6**: Phase 1 synthetic first, Phase 2 real PR corpus.

### Pilot task

"Add NewChainKit Adapter to UW iOS" — bounded scope, 30+ existing patterns, clear semantic search target.

### Phase 1: synthetic (5-7 days)

3-arm A/B with N≥10 paired runs:

| Arm | Setup |
|---|---|
| A. Recipe + Gimle | Mandatory pre-flight recipe |
| B. No recipe, Gimle tools | Tools available; tests model-native grounding |
| C. No recipe, fake-Gimle | Negative control |

### Phase 2: real PR corpus (5-7 days)

Operator-provided 10-15 recent UW iOS PRs. Replay each on throwaway branch. Same 3 arms, N≥20 per arm per task.

### Recipe template

```markdown
# MANDATORY Gimle pre-flight for "<task type>"

Before any write_file action, you MUST execute and cite results from:

1. palace.code.search_semantic(query="<task-description>", repos=["bitcoin-core","evm-kit",...])
2. palace.code.search_graph(name_pattern="*<X>*", label="Class")
3. For top 3 matches: palace.code.get_snippet_rich(qn)
4. palace.code.find_idiom(kind="<X>-creation")
5. palace.code.find_dead_code(project="...", min_severity="medium") — avoid dead clusters
6. palace.memory.query_adr(scope="...")
7. Write 1-page "what I found" citing snippet matches

Anti-gaming: ≥1 symbol from steps 1-2 results MUST appear as referenced class/function in PR diff. CR rejects PR if absent (automated check).
```

### Deliverable

`docs/runbooks/2026-05-XX-recipe-pilot-results.md` with Phase 1 + Phase 2 tables.

---

## G2.5 — Domain-preflight middleware enforcement

**Rev3.2 reframe** (trend-analyst recommendation): not "generic AgentSpec-style enforcement" (will be commoditized) but **domain-specific preflight gating** — the value is mandatory consultation of Gimle's specific tools, which are unique.

### Design

```
agent
  → call: write_file / Edit / create_pr
    → middleware intercept
      → check: has agent made ≥N palace.* calls in current run?
      → check: did planned write reference symbols from preflight results?
      → DENY with reason if either fails
      → ALLOW + log otherwise
```

### Acceptance

1. New service `services/palace-mcp/src/palace_mcp/middleware/preflight_gate.py`
2. Per-recipe configurable: N pre-flight calls, result-utilization check
3. DENY = structured `MCPError`
4. `--bypass-preflight-gate` requires signed approval token + `:BypassEvent` audit node (G0f preview)
5. >90% gate satisfaction on first try after 1 week pilot

**Wall-time**: 7-10 days.

**Owner**: Claude PE.

---

## G3 — Measurement loop (rev3.2: gaming-resistant)

### Metrics

| Metric | Definition (concrete) | Anti-gaming |
|---|---|---|
| **Symbol utilization rate** | ≥1 symbol name from Gimle query results appears as referenced class/function in PR diff | Empty queries can't fake match |
| **Idiom match score** | Jaccard overlap of qualified symbol names in `find_idiom` result vs PR diff symbol references | Deterministic, threshold validated on 10 known-good + 10 known-bad historical PRs |
| **Fabrication count (pre-merge CI gate)** | symbols in PR diff absent from graph AND absent from PR's declared 'new files' list | Pre-merge prevents pollution; distinguishes new from hallucinated |
| **Time-to-CLEAN** | First push → mergeStateStatus=CLEAN on **fixed task corpus** (10-15 historical UW PRs) | Reproducible baseline |
| **Review rounds** | # CR change-request rounds on same corpus | Same baseline |

### Infrastructure

- New tool `palace.agent.metrics(task_id) -> {symbol_utilization, idiom_score, fabrication, time_to_clean, review_rounds}`
- Reads MCP tool logs + PR body + diff + GitHub review API
- JSON dump output
- **Language-agnostic** (productization)

**Wall-time**: 1 week, parallel with G2/G2.5.

---

## G4 — Roll-out (rev3.2: 5 recipes total, dead-code aware)

| Task type | Recipe focus |
|---|---|
| Add new HS Kit Adapter (G2 pilot) | Done |
| Add new SwiftUI screen module | Module/ViewModel/View patterns + styling idiom |
| Add new test suite for existing class | Mock + fixture discovery (test pattern G5 candidate) |
| Refactor existing class | Callers awareness, idiom preservation, **dead-code avoidance check** |
| Bug fix with regression test | Similar bugs (git_history + semantic), existing tests in vicinity |

Each recipe ~2-3 days. A/B vs baseline. Reuse G3 metrics.

**Rev3.2 addition**: each recipe explicitly calls `palace.code.find_dead_code` pre-check.

---

## G0f — Security foundation (rev3.2 new, **gates external pilots only**)

**Decision Q1**: external pilot waits for G0f; internal use unblocked.

### Scope (gating external client pilot)

#### F1 — Multi-tenant tenant boundary decision

Two options to choose at sprint start:
- **(a) Per-tenant Neo4j database** (Neo4j 4+ multi-database) — strong isolation, slight ops overhead
- **(b) Per-tenant Docker container** (palace-mcp + Neo4j per tenant) — strongest isolation, higher resource cost

ADR captured. Default: (a) for SaaS, (b) for on-prem.

#### F2 — MCP tool auth

Tenant-scoped API key with claim. Every tool call's `group_id` derived from the **token**, never from caller-supplied parameter. Token rotation + revocation.

#### F3 — Read-path enforcement

`ScopedCypherSession` wrapper injects `WHERE n.group_id = $authz_scope` into every read query. Ban raw driver access in tool handlers.

#### F4 — Secret scrubbing

Pre-write filter on `literal_value` / `message` / `path` properties:
- Entropy threshold (>4.5 bits per char ≈ likely secret)
- `detect-secrets`-style regex (AWS keys, JWT, RSA blocks, etc.)
- Configurable per-tenant denylist
- Redaction recorded in node metadata for audit

Closes "secrets-in-graph" risk for `coding_convention` / `error_handling_policy` / `crypto_domain_model`.

#### F5 — Build-tool sandbox

`prepare_swift_kit_artifacts.sh` and ingest pipeline run inside per-tenant container with:
- No network egress except tenant-scoped artifact cache
- Filesystem allowlist (no write outside `/tmp/<tenant>/`)
- seccomp profile documented
- Resource limits (CPU/RAM/disk)

#### F6 — Bypass governance

`--bypass-preflight-gate` requires:
- Signed approval token
- Time-bounded (max 1 hour)
- `:BypassEvent` audit node with actor/reason/scope
- Alert to operator on activation

#### F7 — Audit log

Every MCP read/write emits `{actor, tenant, tool, params_hash, timestamp}` to append-only store (separate from main graph).

#### F8 — Embedding backend privacy contract

For external clients:
- Qodo-Embed-1 default (self-hosted, no third-party transfer) ✅ already addressed in G0.5
- If client opts in to remote embedding (Voyage / OpenAI), explicit DPA + retention=0 contract + per-tenant token

#### F9 — Threat model document

STRIDE pass on G0-G5 surface. Explicit mentions: cross-tenant disclosure, tenant ADR poisoning, build-tool RCE, secret harvesting.

#### F10 — Deployment target

Explicit "iMac = dev/internal only; production = isolated VPS or client on-prem container" with CIS-baseline hardening.

### Wall-time

2 weeks. Can run concurrent with G4 if external pilot timing demands.

### Owner

Claude PE + security review (consider invoking voltagent-qa-sec:security-auditor at G0f close before any external pilot).

---

## G5 — Optional extractors

Conditional on G3 metrics showing real gap:

1. **Scaffolding from pattern** — `palace.code.scaffold(pattern_qn, new_name, slot_substitutions)`
2. **Test pattern lookup** — `palace.code.find_test_pattern(class_qn)`
3. **Visual diagram** (SymDex-inspired) — `palace.code.diagram(scope)` returns mermaid
4. **HTTP route discovery** (SymDex-inspired) — `palace.code.find_routes` for backend client productization

Each = 1-2 weeks per slice.

---

## Out of scope (rev3.2)

- Kotlin / Solidity / JS specialist recipes — follow iOS pilot validation. Generic infrastructure (G0.5, G2.5, G3, G0d, G0f) supports all languages; only recipes are language-specific.
- LLM-bearing extractors (Audit-V1 AV1-D4: defer post-v1)
- Audit-V1 reviewer roles (lives in `D-audit-orchestration.md`)
- External agent productization sales motion (capabilities ready post-G3 + G0f; GTM separate)

---

## Critical decision points (rev3.2 — all closed)

| ID | Question | Operator decision 2026-05-21 |
|---|---|---|
| G-D1 | Recipe hard-coded per role or dynamic? | hard-coded for v1, dynamic at G4 if 5+ recipes |
| G-D2 | Pilot task fake or real? | **Phase 1 synthetic + Phase 2 real PR corpus** (Q6) |
| G-D3 | Productization explicit goal? | YES — generic from day one |
| G-D4 | Middleware enforcement? | YES — G2.5 strict gate |
| G-D5 | Full breadth or narrow to 3 moats? | FULL BREADTH |
| G-D6 | SymDex companion or build own semantic? | BUILD OWN in G0.5 (Qodo-Embed-1) |
| G-D7 | G0 size — single sprint or full substrate? | FULL SUBSTRATE (G0a-e mega-sprint) |
| G-D8 | Deep dead-code algorithm | TRANSITIVE + extension chain + SCC + dynamic-dispatch root set |
| G-D9 | **Embedding model** (rev3.2) | **Qodo-Embed-1-1.5B, self-hosted** (Q5) |
| G-D10 | **GDS licensing for productization** (rev3.2) | **Use GDS Community now; swap to own Johnson's SCC before first paying client** (Q2) |
| G-D11 | **G0d split for non-Xcode clients** (rev3.2) | **No split — Periphery mandatory** (Q3, "Swift project ⇒ macOS guaranteed") |
| G-D12 | **G0b enforcement layer** (rev3.2) | **Defense-in-depth: Python wrapper + Neo4j APOC trigger** (Q4) |
| G-D13 | **Security timing** (rev3.2) | **G0f gates external pilots only; internal use unblocked** (Q1) |

---

## Industry references

| Area | Reference |
|---|---|
| Runtime enforcement | [AgentSpec — arxiv 2503.18666](https://arxiv.org/abs/2503.18666) |
| Rules-as-system-prompt | [Cursor rules](https://cursor.com/docs/rules) |
| Symbol-precise retrieval | [Sourcegraph Cody anatomy](https://sourcegraph.com/blog/anatomy-of-a-coding-assistant) |
| Code-graph product (productization comparable) | [Sourcegraph Amp](https://amplifilabs.com/post/sourcegraph-amp-agent-accelerating-code-intelligence-for-ai-driven-development) |
| Repo-map + PageRank | [Aider repo-map](https://aider.chat/docs/repomap.html) |
| Structured navigation | [SWE-agent NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf) |
| Code embedding model (default) | [Qodo-Embed-1-1.5B (Apache 2.0)](https://huggingface.co/Qodo/Qodo-Embed-1-1.5B) |
| Vector index | [Neo4j vector search](https://neo4j.com/developer/genai-ecosystem/vector-search/) |
| Comparable product | [SymDex](https://github.com/husnainpk/SymDex) — patterns adopted + anti-patterns avoided |
| Dead-code baseline | [Periphery](https://github.com/peripheryapp/periphery) |
| SCC graph algorithm | [Neo4j GDS — SCC](https://neo4j.com/docs/graph-data-science/current/algorithms/strongly-connected-components/); Johnson 1975 (own implementation at productization time) |
| Industrial dead-code SOTA | [Meta SCARF — FSE 2023](https://dl.acm.org/doi/10.1145/3611643.3613871) |
| LLM-as-judge | [CodeAgent — arxiv 2402.02172](https://arxiv.org/pdf/2402.02172) |
| SWE benchmark | [SWE-bench](https://www.swebench.com/original.html) |

---

## Risks (rev3.2)

| Risk | Likelihood | Mitigation |
|---|---|---|
| G0 takes 3 weeks not 2 (more property inconsistencies than 2 known) | MED | G0b Day 1 spike enumerates ALL inconsistencies; right-size before commit |
| Audit-V1 schema collision on G0b merge | MED | Dual-read window in fetcher (`n.file_path OR n.path`) for 30 days; full regression suite before merge |
| Neo4j GDS Community Commons Clause blocks productization | HIGH (foreseen) | Use now (internal); swap to own Johnson's SCC before first paying client (~2-3 days) (G-D10) |
| Periphery fails on client's Xcode version | MED | `prepare_*.sh` version-checks Periphery output, fails loud with installation guide |
| G0d false-positive rate on UW iOS @objc/dynamic surface | MED-HIGH | Dynamic-dispatch root set extractor (Step 1b); fixture tests for @objc/NSManaged/Mirror/SwiftUI wrappers (mandatory before G0d merge) |
| G0.5 self-hosted Qodo-Embed slower than Voyage (1500ms vs 100ms latency) | LOW | Acceptable for productization privacy gain; pre-warm cache; future GPU acceleration if needed |
| Embedding pipeline self-hosted resource cost | LOW | Qodo-Embed-1-1.5B fits on single GPU or CPU at sub-second latency for query path |
| Audit-V1 PE contention | HIGH | G0b sequence after Audit-V1 S2.3 (~July 2026); G0a + G0c can start operator-time pre-S2.3 |
| External pilot leak (cross-tenant disclosure) | HIGH if pilot starts pre-G0f | G0f gates external pilot (G-D13) |
| Voyage API change / pricing pivot | LOW (we're not using it as default) | `EmbeddingBackend` interface allows swap; not on default path |
| Frontier models auto-ground by Q4 2026; recipes obsolete | MED | G2 arm B tests model-native grounding; G2.5 reframe focuses on domain-specific palace.* enforcement (not generic gate) |
| G0d false-positive rate on UW iOS app's UIKit/ObjC surface | MED | Dynamic-dispatch root set extractor (G0d Step 1b); HS Kits (bitcoin-core/evm-kit/etc.) are mostly pure Swift with low ObjC interop → expected FP rate 5-15% per research-analyst review; UW iOS app (UIKit-heavy) higher 20-35% — G0e measures empirically |
| Sourcegraph Amp / Cursor / Copilot ship transitive dead-code in 6-12 months | MED | G0d 12-18 month moat window; defensible via writable ADR + multi-repo + git_history enrichment combo |

---

## Filename note at commit

Rename `G-ios-specialist-agent.md` → `G-project-specialist-agent.md` (language-agnostic per G-D3). Update cross-references in roadmap-patch.md before merge.

— Rev3.2 author: Board (Anton + Claude session, 2026-05-21 night)
