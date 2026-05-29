# UW iOS Full Gimle Product — Spec rev2

> Status: rev2 draft, supersedes [rev1](2026-05-29-uw-ios-full-product.md).
> Date: 2026-05-29
> Grounded in: `develop @ 5e05bbd9` (PR #345 merged, post smooth-onboarding-sprint
> 2026-05-28 — 10 PRs landed #336-#345, 8 Swift projects in Palace).
> Verified against actual `services/palace-mcp/src/` at the same SHA.
> Author: Board (Claude Opus 4.7), revised after 5-voltAgent multi-axis
> review (architect / security / qa / performance / chaos) + manual
> cross-check.

## 0. Goal (reframed)

Land a **dev-mirror Gimle backend** for the Unstoppable Wallet iOS
ecosystem that meaningfully helps an agent (Claude Code on the
MacBook) write and reason about UW code: 13 kits, every extractor that
applies to a kit's language returns `status ∈ {ok, missing_input}`,
re-ingest is incremental and merge-safe, MacBook docker-compose on
port 8765 with a cloudflared tunnel for cross-device access.

**Explicitly not** a production-audit substrate ([[project_gimle_palace_not_production_ready]]
remains in force — for hard external audits operators still use
off-the-shelf MCPs). This spec scopes to *agent coding assistance*.

Upstream Swift build issues are in-scope and reduce to a single-line
toolchain pin (see §2). Incremental scheduled updates are designed but
not built this milestone. Skills/instructions for the consuming agent
and the A/B benchmark are out of this spec.

## 1. Decisions (Q1-Q10 locked, rev2 amendments inline)

| # | Decision | Rev2 amendment |
|---|---|---|
| Q1 | All applicable extractors green per kit (was "all 16") | "16" was outdated — registry now has 25+; per-kit acceptance is "all `applies_to_language(<kit-lang>)` extractors return `status ∈ {ok, missing_input}`" |
| Q2 | 13 kits in scope | unchanged |
| Q3 | Combo cleanup + MERGE-by-FQN | MERGE on `:Symbol` is **already implemented** (`symbol_node_writer.py:56`); 3-round eviction on `:SymbolOccurrenceShadow` is **already implemented** (`eviction.py`). Rev2 narrows A3 to *coexistence + soft-delete on `:Symbol`*, not net-new MERGE. |
| Q4 | Scheduled updates designed, not built | unchanged |
| Q5 | Agent on MacBook + all use-cases + docker + cloudflared | port 8765 (not 8080) |
| Q6 | iMac primary for Paperclip; MacBook dev-mirror; drift accepted | rev2 adds **`last_ingest_at` on every relevant MCP response** so the agent has a freshness signal |
| Q7 | Structural smoke + A/B benchmark; upstream Swift fixes obligatory | rev2 Block F is rewritten — split into Smoke A (per-extractor, write-side) and Smoke B (per-tool, read-side with seed oracle) |
| Q8 | Skills out of this spec | unchanged |
| Q9 | Cloudflared without auth for v1 | **amended to: read tools public OK; WRITE tools require bearer middleware + Service Token before D4 enable.** Operator's "harden later" intent applies to read-side; write-side exposure is unrecoverable once a single rogue ingest hits production. |
| Q10 | Toolchain auto-detect from `.swift-version` | rev2 makes it **hard-fail** (not silent fallback) when the pinned toolchain is missing, and normalises `5.8`/`5.8.1`/`swift-5.8.1-RELEASE` formats |

## 2. Root cause of the "upstream Swift fixes" class

Empirical finding 2026-05-29 (unchanged from rev1, included for self-contained reading):

```
.swift-version files (UW + kits) → 5.8
Xcode 26.3 bundled compiler     → Swift 6.2.4 ← xcodebuild uses this by default
Swiftly toolchains installed    → 5.8.1 (CLI default), 6.0.3, 6.1.2
```

`xcodebuild` runs under Swift 6.2.4 even though projects pin to 5.8.
MarketKit / BCH `SwiftCompile` failures in GRDB / secp256k1 are
toolchain mismatch, not broken upstream code. Single-line fix: pass
`-toolchain swift-5.8.1-RELEASE` (auto-detected). No forks, no
patches, no upstream PRs needed for the 13-kit list.

## 3. Scope — 13 kits

**Already in Palace (8):**
`uw-ios-app`, `bitcoin-kit`, `dash-kit`, `evm-kit`, `hd-wallet-kit`,
`hs-crypto-kit`, `hstoolkit`, `litecoin-kit`.

**To add (5):**

| Slug | Repo | Format | Currently-fails because |
|------|------|--------|-------------------------|
| `hs-extensions` | `HsExtensions.Swift` | SwiftPM | PR #345 closes path mismatch — verify E2E |
| `market-kit` | `MarketKit.swift` | SwiftPM | GRDB SwiftCompile under Swift 6.2 → A1 toolchain pin |
| `bitcoin-cash-kit` | `BitcoinCashKit.Swift` | SwiftPM | HsCryptoKit Schnorr compile under Swift 6.2 → A1 |
| `component-kit` | `component-kit-ios` | Cocoapods | No Cocoapods pipeline → B4 |
| `hd-wallet-kit-ios` | `hd-wallet-kit-ios` | Cocoapods | No Cocoapods pipeline → B4 |

Once these land, iterative-add-one mode kicks in for the broader UW
dep graph (`Eip20Kit`, `BinanceChainKit`, `ZcashKit`, etc.).

## 4. Block A — Robustness of existing 8 kits (gate)

| ID | Task | Type | Effort |
|----|------|------|--------|
| **A1** | Toolchain auto-detect from `.swift-version` in `scip_emit_swift_kit.sh`. Read `<repo>/.swift-version` (following symlinks), normalise the value (`5.8` → `swift-5.8.1-RELEASE` — pick the latest installed `5.8.x` patch), pass `-toolchain` to `xcodebuild`. **Hard-fail** with explicit error if the resolved toolchain is not installed; do NOT silently fall back to Xcode default (silent fallback masks corruption: kit ingests with partial/zero symbols and smoke can't tell). Add a `--scheme-only-check` flag that prints the resolved toolchain and exits 0 (useful in CI). | Board PR | 3 h |
| **A2** | Per-kit cleanup in `palace_ingest.sh`. After successful SCIP-emit + ingest, remove `<repo>/.palace-scip-build/` and `<repo>/.palace-scip-derived-data/`. Add `--keep-build` debug flag. | Board PR | 2 h |
| **A3** | **Coexistence of existing MERGE + eviction + new soft-delete marker.** Reality verified: `foundation/symbol_node_writer.py:56` already runs `MERGE (s:Symbol {qualified_name, group_id})`; `foundation/eviction.py` already runs 3-round eviction on `:SymbolOccurrenceShadow` (low-importance / per-symbol cap / global cap). The gap is on `:Symbol` itself — there is no signal that a previously-indexed symbol is gone from the latest SCIP. Add: (a) **explicit `CREATE CONSTRAINT symbol_unique IF NOT EXISTS FOR (s:Symbol) REQUIRE (s.qualified_name, s.group_id) IS UNIQUE`** at startup (idempotent, gated behind a one-shot dedup migration script that finds and merges existing duplicates first); (b) **soft-delete pass** at end of `symbol_index_swift` run — compute set of FQNs in new SCIP, set `deleted_at = $now` on `:Symbol` nodes in the same `group_id` that are absent from the new set; clear `deleted_at` on MERGE-hit if previously set. (c) document the invariant between `:Symbol.deleted_at` and `:SymbolOccurrenceShadow` eviction in [[reference_palace_mcp_tool_schemas]]: the two operate on different labels and do not overlap. | Python in palace-mcp | 1–2 days (was 1–2 rev1; reduced from reviewer's "4-6 days" because the heaviest piece is already implemented) |
| **A4** | Fix GIM-950 (kit-side `embedding_symbol` returns 0 nodes + `repo_not_mounted`). Hypothesis: extractor resolves mount path from `repo_name` instead of slug. Unify on slug end-to-end. **Hard cap: 3 days** — if exceeded, escalate. | Python in palace-mcp | 1–3 days |
| **A5** | Rebuild palace-mcp image on the iMac so PR #341 (`/data/hf-cache` pre-created as appuser) applies. **Hard-gate before D3** — same hf-cache bug would re-surface on MacBook fresh build otherwise. Maintenance-window protocol: announce in `#gimle-ops` Telegram (when plugin reachable), stop palace-mcp container for max 5 min during off-peak (after 22:00 UTC+5). | Ops on iMac | 30 min + 5 min window |
| **A6a** | **Discovery sweep.** Run all applicable extractors on the 8 existing kits + `uw-ios-app` via `palace.ingest.run_extractor`. Capture each `status` value. Output: `paperclips/scripts/palace_extractor_coverage_2026-05-29.csv` with rows `(kit, extractor, status, message)`. Document each `missing_input` as expected per [[project_extractor_baseline_2026-05-22]] (4 known G0c artefact slots) or as new finding. | QA-style | 2–3 h |
| **A6b** | **Fix budget.** For each finding from A6a that is *not* an expected `missing_input`, open a sub-issue with reproduction. Effort cap: 5 days unbudgeted; can defer individual extractor fixes to follow-up issues without blocking Block-B/C/D. | TBD per finding | 0–5 days |

**Block-A acceptance:** A6a CSV committed; every row is either `status ∈ {ok, missing_input}` *or* has a tracked sub-issue with severity assessment. Re-ingesting any kit does not increase `count(:Symbol {group_id: $slug, deleted_at: null})`. Macbook `du -sh <repo>` stays under 50 MB after ingest.

## 5. Block B — Add the 5 missing kits

Same table as rev1, with rev2 amendments:

| ID | Kit | Strategy | Effort |
|----|-----|----------|--------|
| **B1** | `hs-extensions` | After A1: `palace_ingest.sh --github ...`. Verify project registered with `language=swift` + symbol count > 0. | 30 min |
| **B2** | `market-kit` | After A1 (toolchain pin to 5.8.1): retry. Fallback if GRDB still fails: pin GRDB version via `Package.swift` override or `.palace-overrides.json` manifest. | 3–6 h |
| **B3** | `bitcoin-cash-kit` | After A1: retry. Fallback: pin HsCryptoKit to 1.3.2 via Package.swift override. | 2–4 h |
| **B4a** | **Cocoapods spike.** Before committing to a B4b design, manually walk `pod install + xcodebuild -workspace -scheme + SCIP emit` on `component-kit-ios` on the macbook. Document DerivedData layout deltas vs SwiftPM, scheme detection differences, network failure modes (`pod install` hits CocoaPods CDN — must have a `--timeout 300` and a retry). Output: `docs/research/2026-05-29-cocoapods-scip-spike.md`. | Board investigation | 0.5 day |
| **B4b** | **Cocoapods pipeline.** Based on B4a findings, write `paperclips/scripts/scip_emit_cocoapods_kit.sh`. Update `palace_ingest.sh` to detect `Podfile` vs `Package.swift` and route. | Board PR | 2–3 days |
| **B5** | `component-kit` | After B4b: first real run. | 1–2 h |
| **B6** | `hd-wallet-kit-ios` | After B4b: distinct slug from SwiftPM `hd-wallet-kit`. | 1–2 h |

**Block-B acceptance:** 13 kits in graph, A6a re-run gives `status ∈ {ok, missing_input}` for every applicable (kit, extractor) pair.

## 6. Block C — Cleanup infrastructure

| ID | Task | Effort |
|----|------|--------|
| **C1** | `paperclips/scripts/palace_cleanup.sh`. On-demand, defaults to `--dry-run`. Scans **macbook + iMac** (over ssh). Categories: orphan docker stacks (any compose project not prefixed `gimle-palace-`), hf-cache volumes attached to no running container, dangling SCIP files under `/Users/Shared/Ios/HorizontalSystems/*/scip/` with no matching `:Project` node, `/tmp/g*-*.log` and `/tmp/<role>-wake.log` older than 7 days, `.palace-scip-build/` and `.palace-scip-derived-data/` on macbook (in case A2 didn't run), broken slug → repo-dir symlinks. `--apply` actually deletes. | 4–6 h |
| **C2** | `PALACE_SCIP_INDEX_PATHS` dedup in `ingest_swift_kit.sh`. | 1 h |
| **C3** | Symlink reaper — folded into C1. | (in C1) |
| **C4** | Graph orphan cleanup. `:Project` with zero non-deleted symbol children older than 7 days → mark `graph_deleted_at`. | 1–2 h |

**Block-C acceptance:**
- `palace_cleanup.sh --dry-run` on a single host completes under **30 s**.
- On dual-host (macbook + ssh-iMac) under **90 s** (reviewer-corrected — ssh RTT + 41-dir find).
- `--apply` removes only items matching the listed categories.
- Disk accounting reports include **Tantivy volume + Neo4j volume**, not just checkout dirs (those are <5 GB; the real consumers are 2–8 GB Tantivy + 5–10 GB Neo4j).

## 7. Block D — MacBook dev-mirror

| ID | Task | Effort |
|----|------|--------|
| **D1** | `docker-compose.dev-mac.yml`. palace-mcp on `localhost:8765` + own Neo4j (separate named volumes `neo4j_data_dev` + `palace-hf-cache-dev`). Bind-mount `/Users/ant013/Ios/HorizontalSystems` → `/repos-hs`. **Do NOT inherit `cpus: 0.5` from iMac compose** — M1 Max is 20× underutilised at that cap; remove the limit (let Docker Desktop manage). Use same `palace-mcp` image as iMac (multiarch). | 1 day |
| **D2** | `docs/runbooks/macbook-gimle-bootstrap.md`. Step-by-step: clone → `cp .env.example .env` (with `PALACE_MCP_PORT=8765`, `NEO4J_PASSWORD=$(openssl rand -hex 32)`, fresh fine-grained `PALACE_GITHUB_TOKEN`, `chmod 600 .env`, FileVault precheck) → `docker compose -f docker-compose.dev-mac.yml up -d` → fresh ingest of 13 kits. Expected wall-clock: 30–60 min on M1 Max if A2 cleanup + A1 toolchain pin both land. | 0.5 day |
| **D3** | **Fresh ingest of all 13 kits** on macbook compose. Add `--skip-if-ingested <slug>` flag to `palace_ingest.sh` so a fail on kit-9 doesn't force re-run of the first 8 (idempotent, checks `:Project {slug} exists AND last_ingest_at within 24h`). Hard depends on A5 (iMac rebuild → MacBook gets same #341-clean image). | 1–3 h |
| **D4a** | **Bearer middleware on WRITE tools.** Mandatory before any D4b. New `services/palace-mcp/src/palace_mcp/auth.py` exposing a FastAPI dependency that gates all tools matching `palace.ingest.*`, `palace.memory.add_to_bundle`, `palace.memory.delete_bundle`, `palace.memory.decide`, `palace.audit.run`, `palace.ops.unstick_issue`, `palace.project.analyze*` on a bearer token read from `PALACE_WRITE_TOKEN` env var. Read tools (`palace.code.*`, `palace.git.*`, `palace.memory.lookup`, `palace.memory.get_project_overview`, `palace.memory.list_projects`, `palace.health.*`, `palace.ingest.bundle_status`, `palace.ingest.list_extractors`) remain open. | Board PR | 2 h |
| **D4b** | **Cloudflared tunnel.** `services/cloudflared/dev-mac/` with config pinning `gimle.ant013.work` → `http://localhost:8765`. Launchd plist for auto-start. Cloudflare Access Service Token created in Zero Trust dashboard; its client ID + secret stored in `.env` as `PALACE_WRITE_TOKEN` (same token validated by D4a middleware). Read traffic is unauth; write traffic carries the bearer. | 2–3 h |
| **D4c** | **GDPR mitigation.** Add `PALACE_OWNERS_HASH_EMAILS=1` env to `docker-compose.dev-mac.yml`. `code_ownership` extractor reads this and stores `:Author{email_hash: sha256(email)}` instead of plaintext when set. One-line guard in the extractor + one env var; closes EU contributor email exposure risk on the public read-side. | 1 h |
| **D5** | Smoke from external network. From phone on 5G: `curl https://gimle.ant013.work/mcp/` returns 406 (handshake). `curl -X POST https://gimle.ant013.work/mcp/ -d '{"method":"tools/call","params":{"name":"palace.ingest.run_extractor"...}}' → 401` (write blocked without token). `palace.code.list_functions project=bitcoin-kit limit=1` over MCP returns at least 1 row (functional, not just plumbing). | 15 min |

**Block-D acceptance:**
- `curl http://localhost:8765/mcp/` → 406 from macbook.
- `curl https://gimle.ant013.work/mcp/` → 406 from any network.
- `palace.memory.list_projects` over either endpoint → 13 swift projects.
- Write-tool call without `Authorization: Bearer <token>` → 401.
- `:Author` nodes carry `email_hash`, not raw `email`.

## 8. Block E — Scheduled-updates design (build deferred)

Unchanged from rev1: design doc only, build is deferred. Spec
addition: rollback / kill-switch / per-kit failure isolation.

`docs/superpowers/specs/2026-05-29-palace-scheduled-updates.md` skeleton:
- launchd job per host, daily 04:00 local.
- `palace_update_all.sh` iterates `:Project` slugs from local Neo4j.
- Per kit: `git fetch && git rev-parse origin/HEAD` vs local HEAD. If same → skip. If different → `git pull --ff-only` (fall back to `--no-ff` with operator alert), then `palace_ingest.sh --update <slug>` (uses A3 MERGE + soft-delete).
- **Per-kit failure isolated**: continue with remaining kits, accumulate failures, post summary at end.
- **Kill-switch**: presence of `~/.palace-updates-paused` skips the run entirely.
- **Rollback**: every run records to `:IngestRun` with `started_at`/`finished_at`/`per_kit_results`; operator can revert a bad ingest by deleting the latest `:IngestRun` and replaying the previous SCIP.

## 9. Block F — Smoke acceptance harness (REWRITTEN)

Two independent smokes, distinct concerns.

### 9.1 Smoke A — write-side per-extractor coverage

`paperclips/scripts/palace_extractor_smoke.sh <slug>` (new).

For the kit's language (read `:Project.language` from Neo4j), iterate
the language-applicable extractor set (registry filtered by
`applies_to_language(lang)`). For each extractor:

1. `palace.ingest.run_extractor name=<ext> project=<slug>` → capture full JSON response.
2. Assert `response.status ∈ {"ok", "missing_input"}`.
3. If `ok` — assert `response.nodes_written >= 0` (numeric, not null).
4. If `missing_input` — assert `<ext>` is in the documented G0c artefact list (`paperclips/scripts/palace_extractor_baseline_g0c.txt`, committed).

Output: per-kit row `(slug, ext, status, nodes_written, message)`.

**Done condition (Smoke A):** green on all 13 kits + `uw-ios-app`.

### 9.2 Smoke B — read-side per-tool correctness with oracle

`paperclips/scripts/palace_tool_smoke.sh <slug>` (new) + committed oracle
`paperclips/scripts/palace_smoke_seeds.json`:

```json
{
  "bitcoin-kit": {
    "seed_function_fqn": "BitcoinKit/TransactionSigner#sign(message:privateKey:).",
    "seed_class_fqn": "BitcoinKit/Transaction#",
    "expected_min_functions": 50,
    "expected_min_public_api": 20,
    "semantic_query_example": "sign transaction",
    "semantic_query_expected_substring": "sign"
  },
  "uw-ios-app": { ... },
  ...
}
```

Per tool, run with kit-specific seed, assert non-trivial result:

| # | Tool (verified to exist) | Assertion (not "status=ok") |
|---|---|---|
| 1 | `palace.memory.get_project_overview slug=<slug>` | `entity_counts.symbol_count >= expected_min_functions` |
| 2 | `palace.code.list_functions project=<slug> limit=5` | `len(functions) >= 5` AND `seed_function_fqn` in returned FQNs (if defined) |
| 3 | `palace.code.find_public_api project=<slug>` | `len >= expected_min_public_api` |
| 4 | `palace.code.semantic_search project=<slug> query=<semantic_query_example>` | `len >= 1` AND any result FQN contains `semantic_query_expected_substring` |
| 5 | `palace.code.find_references project=<slug> qualified_name=<seed_function_fqn>` | `len >= 0` (zero acceptable for leaf functions) AND no exception |
| 6 | `palace.code.find_dead_code project=<slug>` | response is a list (may be empty); not an error envelope |
| 7 | `palace.code.find_dead_symbols project=<slug>` | response is a list |
| 8 | `palace.code.find_hotspots project=<slug>` | response is a list |
| 9 | `palace.code.find_owners project=<slug>` | response is a list |
| 10 | `palace.code.find_cross_module_contracts project=<slug>` | response is a list |
| 11 | `palace.code.find_version_skew project=<slug>` | response is a list (may be empty) |
| 12 | `palace.code.find_idiom project=<slug>` | response is a list |
| 13 | `palace.code.test_impact project=<slug>` | response present (may be empty) |
| 14 | `palace.code.get_snippet_rich qualified_name=<seed_class_fqn> project=<slug>` | response has `.source_lines` len >= 1 |
| 15 | `palace.ingest.bundle_status run_id=<latest-run-id-for-slug>` | reports `finished_at`, `status == "ok"` |

**Note vs rev1:** tools removed because they don't exist as `palace.code.*` MCP tools (confirmed by grep of `services/palace-mcp/src/`):
- `palace.code.get_architecture` — no registration found
- `palace.code.trace_call_path` — no registration found (only docstring mention in roles prime)
- `palace.code.get_code_snippet` — exists as `palace.code.get_snippet_rich` (different signature; rev2 uses the real name)

**Done condition (Smoke B):** green on all 13 kits + `uw-ios-app`. Empty results are *allowed* where noted but assertions never accept "no-op response envelope passed validation" as success — this directly closes [[feedback_wire_test_tautological_assertions]].

## 10. Dependency graph / order of execution

```
A1 toolchain ────┬─→ A6a discovery sweep ─→ A6b fix budget
                 │
                 └─→ B1 hs-ext ─→ B2 market-kit ─→ B3 bitcoin-cash-kit
                 
A2 per-kit cleanup ──→ D3 macbook fresh ingest
                       ▲
A3 :Symbol soft-delete ┤ ─→ E1 incremental design
                       │
A4 GIM-950 fix ────────┤ ─→ A6a kit embedding coverage
                       │
A5 iMac rebuild ───── ▶│ Block D (hf-cache fix on both hosts)
                       │
B4a Cocoapods spike ─→ B4b pipeline ─→ B5 component-kit ─→ B6 hd-wallet-ios
                                                              │
C1..C4 (parallel) ─────────────────────────────────────────────┤
                                                              │
                              D1 compose ─→ D2 runbook ────────┤
                              D4a bearer ─→ D4b cloudflared ───┤ (D4a MUST land before D4b enable)
                              D4c email hash ─────────────────┤
                                                              ▼
                                                       F-A + F-B smokes
                                                              │
                                                              ▼
                                                       Spec DONE
```

**Critical path:** A1 → A3 → A4 → A6a/b → B2/B3 → B4a → B4b → B5/B6 → A5 → D1..D4 → F.

**Hard gates added in rev2:**
- A5 hard-gate before D3 (so MacBook gets clean image too).
- D4a hard-gate before D4b enable (write tools auth before tunnel open).
- A6a output (G0c exception list committed) before A6 acceptance can pass.

**Parallelisable:** C1–C4, E1, A4 (independent of A1/A2/A3 in different file).

## 11. Effort estimate (rev2 revision)

| Block | Effort | Notes |
|-------|--------|-------|
| A | 5–7 days | A1 3h, A2 2h, A3 1–2d, A4 1–3d (cap), A5 1h, A6a 3h, A6b 0–5d unbudgeted |
| B | 4–6 days | B1 30min, B2 6h, B3 4h, B4a 0.5d, B4b 2–3d, B5 2h, B6 2h |
| C | 1–2 days | unchanged |
| D | 3–4 days | D1 1d, D2 0.5d, D3 3h, D4a 2h, D4b 3h, D4c 1h, D5 15min |
| E | 3 h | design only |
| **Total focused** | **17–23 working days** | (was 13–18 in rev1; +4-5 days for security amendments, spike, baseline reality) |

Calendar with autonomous 30-min cycles, parallel bg-tasks, and the
usual unexpected-edge-case tax: **5–7 calendar weeks**.

Scope-cut protocol if calendar slips past 5 weeks:
1. First cut: A6b individual extractor fixes — defer to follow-up issues if more than 2 are non-trivial.
2. Second cut: B4–B6 Cocoapods to a separate Phase 1.b spec, ship Phase 1.a with 11/13 kits + 2 docs-only Cocoapods entries.
3. Third cut: defer A4 GIM-950 to its own spec, ship Block A without kit embeddings.

## 12. Out of scope (explicit)

- Agent skills / decision-tree instructions — separate spec.
- A/B benchmark — after skills.
- Cloudflared Access policy hardening *beyond* the write-token + email-hash baseline (per Q9; rev2 has the security floor needed to not be reckless).
- Scheduled-updates implementation — design only this milestone.
- Broader UW kits (`Eip20Kit`, `BinanceChainKit`, `ZcashKit`, etc.) — iterative-add-one after Block D.
- iMac decommission — iMac stays primary for Paperclip agents.
- **No non-public-source repos mounted on the MacBook compose until D4a permanent.** This guards against the "I'll just mount my private repo to test" temptation while the write side is still being hardened.

## 13. Open risks (rev2 mitigations)

1. **A3 dedup migration on populated graph** — duplicates pre-existing from CREATE-era runs will block `CREATE CONSTRAINT`. Mitigation: A3 sub-step "dedup-first migration script" runs `MATCH (a:Symbol), (b:Symbol) WHERE a.qualified_name = b.qualified_name AND a.group_id = b.group_id AND id(a) < id(b) DETACH DELETE b` in batches before the constraint creation. Verify on a Neo4j dump from iMac (not on prod live) — operator memory [[reference_palace_neo4j_creds]] forbids wipe-on-auth-fail; same care here. Snapshot before migration is mandatory; rollback = `neo4j-admin load`.
2. **B2 MarketKit GRDB still fails under 5.8.1** — fall back to GRDB version pin via Package.swift override (add 2–4 h). If even that fails, fall back to building only `MarketKit` target (skip `GRDB-Package` scheme); SCIP coverage on MarketKit's own code is still useful even without GRDB symbols.
3. **B4 Cocoapods pipeline net-new** — B4a spike is the mitigation. Hard 0.5-day cap; if discoveries spike beyond 0.5 day, B4b moves to a separate spec and Phase 1.a ships with 11/13.
4. **D4a/b/c security floor incomplete** — write-token covers DoS and unauthorized ingest, but does not stop a stolen token from causing damage. Acceptable for "dev mirror primarily used by one operator" per Q5; Cloudflare Access policy (browser SSO) is the next harden step post-milestone.
5. **Drift between iMac and MacBook graphs** — accepted by Q6. Mitigation: every MCP response that returns symbol data includes `palace_last_ingest_at` (per-project). Agent prompt (out of this spec, in Phase 2) will be told to check this before trusting results. No host-level sync this milestone.
6. **A5 maintenance window** — palace-mcp offline for ~5 min during rebuild. Mitigation: announce in `#gimle-ops` Telegram (when plugin reachable) + execute off-peak (after 22:00 UTC+5 per [[user_timezone]]). [[reference_claude_process_idle_hang]] noted: any agent runs in flight may hang on lost MCP — operator may need to kill PIDs post-rebuild.

## 14. Where this spec lives

- This file: `docs/superpowers/specs/2026-05-29-uw-ios-full-product-rev2.md`.
- Rev1 (superseded, kept for audit): `docs/superpowers/specs/2026-05-29-uw-ios-full-product.md`.
- Meta-issue: **GIM-987** (open *after* rev2 merges) — "Full UW iOS Gimle dev-mirror product", checklist by block, links to per-task child issues.
- Per-task child issues open on Block-A/B/C/D acceptance gates.

## 15. Diff against rev1

Concrete changes between rev1 and rev2, indexed by reviewer finding for traceability:

| Reviewer finding | Rev1 said | Rev2 says |
|---|---|---|
| S1 (Architect F1 / Performance F1 / Chaos F2) — A3 wrong label, effort underestimated | A3 = "replace CREATE with MERGE on :Symbol; soft-delete absent FQNs"; 1–2 days | A3 = "coexist with existing MERGE + eviction.py; add constraint + dedup migration + soft-delete on :Symbol only"; 1–2 days (verified against code) |
| S2 (QA F1/F2 + Architect F5) — Block F tautological + non-existent tools | Single mixed smoke; "run-status ok" assertions; 3 wrong tool names | Two split smokes (A: write-side per-extractor; B: read-side per-tool with seed oracle); real assertions; tool names verified against actual `tool_decorator` registry |
| S3 (Security F1/F2/F3 + Chaos F5) — D4 cloudflared without auth CRITICAL | "D4 no auth for v1; harden later" | D4a bearer middleware on WRITE tools (`palace.ingest.*` etc.) is *mandatory before* D4b enable; D4c `PALACE_OWNERS_HASH_EMAILS=1` for GDPR floor |
| S4 (Architect F4 + Chaos F6) — drift no contract | "Drift accepted" with no signal | Same Q6 stance, but every MCP response carrying symbol data includes `palace_last_ingest_at` so the agent has a freshness signal |
| Architect F2 — A5 not in critical path | A5 listed but ungated | A5 hard-gate before D3 added to §10 |
| Architect F6 / Chaos F4 — B4 Cocoapods needs spike | "B4 2–3 days" single task | Split into B4a (0.5d spike) + B4b (2–3d impl); `pod install --timeout 300` mandated |
| Performance F5/F6 — C1 "30s" unrealistic; measures wrong path | "under 30s; du -sh checkouts" | Split single-host (30s) vs dual-host ssh (90s); accept criteria measure Tantivy + Neo4j volumes |
| Performance F7 — D1 inherits cpus: 0.5 | (silent) | Explicit "do NOT inherit cpus: 0.5 from iMac compose" |
| Chaos F1 — A3 partial-failure death spiral | (silent) | Explicit "REMOVE s.deleted_at on MERGE-hit if previously set" in A3 |
| Chaos F3 — A1 silent fallback corruption | "warn and fall back" | Hard-fail with explicit error; `--scheme-only-check` flag for CI |
| Chaos F7 — D3 no resume | Sequential | Add `--skip-if-ingested <slug>` flag to `palace_ingest.sh` |
| Chaos F9 — A5 idle-hang risk | (silent) | Mention [[reference_claude_process_idle_hang]] in risk #6 |
| QA F4 — A6 dual role | Single "discovery + acceptance" task | Split A6a (discovery, 2-3h) + A6b (fix budget, 0-5d unbudgeted) |
| QA F6 — D5 plumbing only | "curl 406" | Plumbing 406 + functional `palace.code.list_functions` returning data + 401 on write-without-token |
| Memory conflict with [[project_gimle_palace_not_production_ready]] | "production-ready milestone" | Reframed §0 to "dev-mirror for agent coding assistance, not production audit substrate" |
| Memory conflict with [[reference_palace_neo4j_creds]] | "verify on shadow neo4j" (no procedure) | Risk #1 mitigation: snapshot before migration is mandatory; rollback = `neo4j-admin load` from snapshot |
| Calendar 3–4 weeks underestimate | 13–18 working days, 3–4 weeks calendar | 17–23 working days, 5–7 weeks calendar; scope-cut protocol added |
| Branch naming (`g987-product-spec` vs `feature/GIM-987-...`) | (not addressed) | Acknowledged: CTO rename at squash time per [[reference_feature_branch_flow]]; cosmetic, not blocking |
| Tool names that reviewer claimed missing but actually exist | (3 used correctly in rev1) | Same 3 retained (verified): `palace.code.semantic_search`, `palace.code.find_dead_code`, `palace.code.find_idiom` — reviewer's grep was incomplete |

Pushed back on (not adopted into rev2):
- Reviewer's "A3 target should be `:SymbolOccurrenceShadow`": that label already has 3-round eviction; A3's concern is `:Symbol`-level lifecycle, which is the real gap.
- Reviewer's "Calendar 5-7 weeks unconditional": rev2 uses 5–7 as the upper bound *if every risk materialises*; base scenario is closer to 4-5.
