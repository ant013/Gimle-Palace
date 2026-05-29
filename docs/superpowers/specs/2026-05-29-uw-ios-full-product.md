# UW iOS Full Gimle Product — Spec

> Status: draft, awaiting GIM-987 meta-issue acceptance
> Date: 2026-05-29
> Grounded in: `develop @ 5e05bbd9` (PR #345 merged, post smooth-onboarding-sprint
> 2026-05-28 — 10 PRs landed #336-#345, 8 Swift projects in Palace).
> Author: Board (Claude Opus 4.7), captured from interactive operator dialog.

## 0. Goal

Land a fully usable Gimle backend for the Unstoppable Wallet iOS ecosystem:
**13 kits × 16 extractors green**, with a MacBook dev-mirror reachable from
agents both locally (`localhost:8765`) and externally
(`gimle.ant013.work`). Upstream Swift build issues are in-scope and must be
fixed via toolchain pinning. Incremental updates are designed but not built
this milestone. Skills/instructions for the consuming agent and the A/B
benchmark are explicitly out of this spec.

## 1. Decisions

Locked during the Q1-Q10 clarification dialog 2026-05-29:

| # | Decision |
|---|---|
| Q1 | **All 16 extractors must be green per kit** — includes fixing GIM-950 (kit-side `embedding_symbol` returns 0 nodes). |
| Q2 | **13 kits in scope** — 8 already in Palace + 5 to add (`HsExtensions.Swift`, `MarketKit.swift`, `BitcoinCashKit.swift`, `component-kit-ios`, `hd-wallet-kit-ios`). Iterative add-one-and-measure mode kicks in after these land. |
| Q3 | **Combo cleanup** — per-kit auto-cleanup of macbook build artefacts + on-demand `palace_cleanup.sh` for iMac/global state. **Re-ingest uses MERGE-by-qualified-name** so subsequent runs don't duplicate symbol nodes; stale symbols (not in new SCIP) get `deleted_at` soft-delete. |
| Q4 | **Scheduled incremental updates are designed in this spec, not built.** Build is deferred until the operator activates it. |
| Q5 | **Primary consumer is the agent on the MacBook**, all four use-cases (semantic search, structural nav, code review, refactor) considered equal priority. MCP lives in a local docker-compose on MacBook + a cloudflared tunnel for cross-device access. **Port is 8765, not 8080.** |
| Q6 | **iMac stays primary for Paperclip agents**; MacBook is a dev mirror. Both maintain own Neo4j; drift is accepted. MacBook seeds via **fresh ingest from git** to validate the full smooth-onboarding cascade end-to-end. |
| Q7 | **Acceptance = structural smoke per kit + A/B benchmark** (benchmark depends on skills, hence deferred). Upstream Swift fixes are **obligatory** — if a kit doesn't build, we fix it, never skip. |
| Q8 | Agent skills / decision-tree instructions = **out of this spec**. Separate, longer design discussion. |
| Q9 | Cloudflared auth = **none for the initial deploy**; operator will harden post-landing. |
| Q10 | Toolchain handling = **auto-detect from each repo's `.swift-version` file** in `scip_emit_swift_kit.sh`. |

## 2. Root cause of the "upstream Swift fixes" class

Empirical finding 2026-05-29:

```
.swift-version files (UW + kits) → 5.8
Xcode 26.3 bundled compiler     → Swift 6.2.4 ← xcodebuild uses this by default
Swiftly toolchains installed    → 5.8.1 (CLI default), 6.0.3, 6.1.2
```

Every `xcodebuild` invocation in the current `scip_emit_swift_kit.sh` runs
under **Swift 6.2.4** even though the projects pin to 5.8. MarketKit and
BitcoinCashKit hit `SwiftCompile` failures in GRDB / secp256k1 because of
that mismatch, not because of broken upstream code.

The "upstream Swift fix" reduces to a single line — pass `-toolchain
swift-5.8.1-RELEASE` to `xcodebuild` (or `TOOLCHAINS=...` env var),
auto-detected from `.swift-version`. No forks, no patches, no PRs upstream
are needed for the 13-kit list.

This is captured in Block A, task A1.

## 3. Scope — 13 kits

**Already in Palace (8):**
`uw-ios-app`, `bitcoin-kit`, `dash-kit`, `evm-kit`, `hd-wallet-kit`,
`hs-crypto-kit`, `hstoolkit`, `litecoin-kit`.

**To add (5):**

| Slug | Repo | Format | Why-it-currently-fails |
|------|------|--------|------------------------|
| `hs-extensions` | `HsExtensions.Swift` | SwiftPM | PR #345 closes path mismatch — needs end-to-end verify |
| `market-kit` | `MarketKit.swift` | SwiftPM | GRDB SwiftCompile under Swift 6.2 — fix via A1 |
| `bitcoin-cash-kit` | `BitcoinCashKit.Swift` | SwiftPM | HsCryptoKit transitive Schnorr compile under Swift 6.2 — fix via A1 |
| `component-kit` | `component-kit-ios` | Cocoapods | No Cocoapods pipeline yet — B4 |
| `hd-wallet-kit-ios` | `hd-wallet-kit-ios` | Cocoapods | No Cocoapods pipeline yet — B4 (note: distinct from SwiftPM `hd-wallet-kit` already in graph) |

Once all 13 are green, the next phase is **iterative-add-one** for the
broader UW dependency graph (Eip20Kit, BinanceChainKit, ZcashKit, etc.) — each
addition is a forcing function that measures whether the smooth-onboarding
cascade really is "one command per kit".

## 4. Block A — Robustness of existing 8 kits (gate)

| ID | Task | Type | Effort |
|----|------|------|--------|
| **A1** | Toolchain auto-detect from `.swift-version` in `scip_emit_swift_kit.sh`. Read `cat .swift-version` from `$LOCAL_REPO_PATH`; if a Swiftly-installed `swift-<v>-RELEASE` exists, pass `-toolchain` to `xcodebuild`; otherwise fall back to Xcode default with a warning. | Board PR | 2 h |
| **A2** | Per-kit cleanup in `palace_ingest.sh`. After successful SCIP-emit + ingest, remove `<repo>/.palace-scip-build/` and `<repo>/.palace-scip-derived-data/`. Add `--keep-build` debug flag. | Board PR | 2 h |
| **A3** | **MERGE-by-qualified-name** in `symbol_index_swift` extractor (and any other symbol-writing extractor). Replace `CREATE (s:Symbol)` with `MERGE (s:Symbol {qualified_name: $qn, project: $slug})`. Compute the set of FQNs present in the new SCIP; symbols present in graph but absent from the new SCIP get `s.deleted_at = $now`. May require a `CREATE CONSTRAINT` on `(qualified_name, project)` for MERGE performance. | Python in palace-mcp | 1–2 days |
| **A4** | Fix GIM-950 (kit-side `embedding_symbol` returns 0 nodes + `repo_not_mounted`). Hypothesis: extractor resolves the mount path from `repo_name` (e.g. `HsExtensions.Swift`) instead of slug (`hs-extensions`), so it looks under `/repos-hs/HsExtensions.Swift` when the symlink lives at `/repos-hs/hs-extensions`. Unify on slug end-to-end. | Python in palace-mcp | 1–2 days |
| **A5** | Rebuild palace-mcp image on the iMac so PR #341 (`/data/hf-cache` pre-created as appuser) actually applies. Eliminates the recurring manual `docker exec -u root … chown -R appuser:appuser /data/hf-cache` step after every ingest recreate. | Ops on iMac | 30 min |
| **A6** | Run all 16 extractors on the 8 existing kits + `uw-ios-app`. For each kit, capture which extractors fail with which error. Open one sub-issue per real failure (not per kit). | QA-style | 2–4 h |

**Block-A acceptance:** all 8 existing kits + `uw-ios-app` pass 16/16
extractors green on the iMac instance; re-ingesting any kit does not
increase its `count(Symbol)` (MERGE works); macbook `du -sh` of any kit's
local checkout stays under 50 MB after ingest (build artefacts cleaned).

## 5. Block B — Add the 5 missing kits

| ID | Kit | Strategy | Effort |
|----|-----|----------|--------|
| **B1** | `hs-extensions` | After A1 lands: `palace_ingest.sh --github https://github.com/horizontalsystems/HsExtensions.Swift --skip-embedding`. Verify the project ends up registered with `language=swift` and the runtime preflight no longer errors on the 3-name mismatch. | 30 min |
| **B2** | `market-kit` | After A1: re-ingest. Toolchain pin to 5.8.1 should clear the GRDB compile failure. If not, triage which GRDB Swift feature crashes the compiler and pin GRDB to the last known-good version via `Package.swift` override in a local fork OR document the workaround in the kit's `.palace-overrides.json` manifest (new). | 3–6 h |
| **B3** | `bitcoin-cash-kit` | After A1: re-ingest. Same toolchain fix expected to clear the transitive HsCryptoKit compile failure. Fallback: pin HsCryptoKit to 1.3.2 (same version that works standalone) via Package.swift override. | 2–4 h |
| **B4** | Cocoapods pipeline (GIM-951) | New `paperclips/scripts/scip_emit_cocoapods_kit.sh`: `pod install` into a scratch dir → `xcodebuild -workspace <Kit>.xcworkspace -scheme <Kit>` with the same toolchain auto-detect from A1 → SCIP emit from workspace's DerivedData. Update `palace_ingest.sh` to detect `Podfile` vs `Package.swift` and route to the right emitter. | 2–3 days |
| **B5** | `component-kit` | After B4: first Cocoapods kit through the new pipeline. Validates B4 end-to-end. | 1–2 h |
| **B6** | `hd-wallet-kit-ios` | After B4: second Cocoapods kit. Distinct slug from the existing SwiftPM `hd-wallet-kit` already in the graph. | 1–2 h |

**Block-B acceptance:** 13 kits in the graph, each with 16/16 extractors green.

## 6. Block C — Cleanup infrastructure

| ID | Task | Effort |
|----|------|--------|
| **C1** | `paperclips/scripts/palace_cleanup.sh`. On-demand script, defaults to `--dry-run`. Scans macbook + iMac (via ssh) and reports each garbage class with sizes: orphan docker stacks (any compose project not prefixed `gimle-palace-`), hf-cache volumes attached to no running container, dangling SCIP files at `/Users/Shared/Ios/HorizontalSystems/*/scip/` with no matching `:Project` node, `/tmp/g839-*.log` and `/tmp/<role>-wake.log` older than 7 days, `.palace-scip-build/` and `.palace-scip-derived-data/` directories on macbook (in case A2 didn't run). `--apply` actually deletes. | 4–6 h |
| **C2** | `PALACE_SCIP_INDEX_PATHS` dedup in `ingest_swift_kit.sh`. The env var grows linearly today; on enough kits it will exceed the env-size limit. Dedup on each write. | 1 h |
| **C3** | Symlink reaper. Symlinks under `/Users/Shared/Ios/HorizontalSystems/<slug>` whose target no longer exists → remove. Part of C1. | folded into C1 |
| **C4** | Graph orphan cleanup. `:Project` nodes with zero symbol children older than 7 days → soft-delete (`graph_deleted_at`). Cypher script invoked from C1 under `--apply --graph`. | 1–2 h |

**Block-C acceptance:** `palace_cleanup.sh --dry-run` completes in under
30 s and lists every category with sizes; `--apply` removes only items
matching the listed categories without touching active data;
`du -sh /Users/ant013/Ios/HorizontalSystems/` post-cleanup stable under 5 GB.

## 7. Block D — MacBook dev-mirror

| ID | Task | Effort |
|----|------|--------|
| **D1** | `docker-compose.dev-mac.yml`. palace-mcp bound to **`localhost:8765`** + its own Neo4j (separate named volume from iMac to avoid collision if someone scp's data over). Bind-mount `/Users/ant013/Ios/HorizontalSystems` → `/repos-hs`. Persistent named volumes for `neo4j_data_dev` + `palace-hf-cache-dev`. Use the same `palace-mcp` image as iMac (multi-arch already supported). | 1 day |
| **D2** | `docs/runbooks/macbook-gimle-bootstrap.md`. Step-by-step: clone repo → `cp .env.example .env` (with `PALACE_MCP_PORT=8765` and a fresh `NEO4J_PASSWORD`) → `docker compose -f docker-compose.dev-mac.yml up -d` → fresh ingest of the 13 kits via `palace_ingest.sh --github` × 13. Document expected wall-clock: ~30–60 min on M1 Max. | 0.5 day |
| **D3** | Fresh ingest of all 13 kits on the MacBook docker-compose. This *is* the end-to-end validation of Blocks A and B. | 1–2 h (sequential), faster if A2 cleanup keeps disk |
| **D4** | `services/cloudflared/dev-mac/`. Tunnel config pinned to `gimle.ant013.work` → `http://localhost:8765`. Launchd plist for auto-start. **No auth for the initial deploy** (operator explicitly deferred Q9); add a `TODO-HARDEN` block in the plist comment. | 2–3 h |
| **D5** | Smoke from an external host. From a phone on 5G: `curl https://gimle.ant013.work/mcp/` returns 406 (handshake OK). From the macbook: `palace.memory.list_projects` over MCP returns 13 kits. | 15 min |

**Block-D acceptance:** `curl http://localhost:8765/mcp/` returns 406 from
the macbook; `curl https://gimle.ant013.work/mcp/` returns 406 from any
network; calling `palace.memory.list_projects` against either endpoint
returns 13 swift-language projects.

## 8. Block E — Scheduled-updates design (build deferred)

| ID | Task | Effort |
|----|------|--------|
| **E1** | Design doc `docs/superpowers/specs/2026-05-29-palace-scheduled-updates.md`. Sketch: launchd job on each Palace host runs `paperclips/scripts/palace_update_all.sh` daily at 04:00 local; the script does `git fetch origin && git pull --ff-only` per kit checkout, and re-runs `palace_ingest.sh --update <slug>` only on kits whose `git rev-parse HEAD` changed. Merge-by-FQN (A3) makes the re-ingest incremental; soft-delete handles dropped symbols. On failure: append to `/var/log/palace-update.log` and optionally post to Telegram via the existing plugin (gated on `PALACE_UPDATE_TG_ENABLED=1`). | 2–3 h |
| **E2** | **Not built this milestone.** A meta-issue is opened with the design doc; activation happens when the operator says go. | — |

**Block-E acceptance:** design doc merged into `docs/superpowers/specs/`;
meta-issue (GIM-988 placeholder) opened with pointer; no launchd job is
created on either host.

## 9. Block F — Smoke acceptance harness (Q7-A)

`paperclips/scripts/palace_smoke_per_kit.sh <slug>` (new). For each
extractor, run the matching MCP tool against the slug and assert a
non-empty / sane result:

```
1.  palace.memory.get_project_overview   → entity_counts.* > 0
2.  palace.code.list_functions           → len ≥ 1
3.  palace.code.find_public_api          → len ≥ 1
4.  palace.code.semantic_search          → len ≥ 1 with query="example"
5.  palace.code.find_references          → run-status ok
6.  palace.code.find_dead_code           → run-status ok (count may be 0)
7.  palace.code.find_hotspots            → run-status ok
8.  palace.code.find_owners              → run-status ok
9.  palace.code.find_cross_module_contracts → run-status ok
10. palace.code.find_version_skew        → run-status ok
11. palace.code.find_idiom               → run-status ok
12. palace.code.get_architecture         → at least one module
13. palace.code.test_impact              → run-status ok (may be empty)
14. palace.code.trace_call_path          → run-status ok on a known seed
15. palace.code.get_code_snippet         → returns ≥ 1 line on a known FQN
16. palace.ingest.bundle_status          → reports ingestion finished_at < 24h
```

Done condition for the spec: script green on all 13 kits + `uw-ios-app`,
on both iMac and MacBook instances.

## 10. Dependency graph / order of execution

```
A1 toolchain ────┬─→ A6 16/16 on 8 kits
                 │
                 └─→ B1 hs-ext ─→ B2 market-kit ─→ B3 bitcoin-cash-kit
                                                              │
A2 per-kit cleanup ─────────────────────────────→ D3 macbook fresh ingest
                                                              ▲
A3 merge-by-FQN ──┬─→ A6 re-ingest test                       │
                  └─→ E1 incremental design                   │
                                                              │
A4 GIM-950 fix ──→ A6 embedding_symbol green on kits          │
                                                              │
A5 iMac rebuild ──→ Block D (so #341 applies on iMac too)     │
                                                              │
B4 cocoa-pipeline ──→ B5 component-kit ─→ B6 hd-wallet-ios ───┘
                                                              │
C1..C4 (parallel, no deps) ────────────────────────────────────┤
                                                              │
                                  D1 compose ─→ D2 runbook ───┤
                                                              ▼
                                                          F smoke
                                                              │
                                                              ▼
                                                       Spec DONE
```

**Critical path:** A1 → A3 → A4 → B2/B3 → B4 → B5/B6 → D1..D5 → F.

**Parallelisable:** A5, C1–C4, E1.

## 11. Effort estimate

| Block | Effort |
|-------|--------|
| A | 4–5 days (A3 + A4 dominate — Python in palace-mcp) |
| B | 5–7 days (B4 Cocoapods + B2 MarketKit triage) |
| C | 1–2 days |
| D | 2–3 days |
| E | 3 h (design only) |
| **Total focused effort** | **13–18 working days** |

With 30-min autonomous cycles, parallel bg tasks, and the usual edge-case
debugging surprises, realistic calendar time is **3–4 weeks**.

## 12. Out of scope (explicit)

- Agent skills / decision-tree instructions — separate spec.
- A/B benchmark — after skills.
- Cloudflared `gimle.ant013.work` auth (Access policy, service tokens) —
  after Block D lands; deferred per Q9.
- Scheduled-updates implementation — design only this milestone.
- Broader UW kits (`Eip20Kit`, `BinanceChainKit`, `ZcashKit`, etc.) —
  iterative-add-one mode after Block D.
- iMac decommission — iMac stays primary for Paperclip agents.

## 13. Open risks

1. **A4 (GIM-950) may take longer than 1–2 days.** The extractor may use
   `repo_name` in more places than the obvious mount lookup. Budget a
   3-day cap; escalate if exceeded.
2. **B2 MarketKit GRDB compile may still fail under Swift 5.8.1.** If the
   toolchain pin alone doesn't fix it, fall back to pinning GRDB itself
   via Package.swift override (add 2–4 h).
3. **B4 Cocoapods pipeline is net-new.** SCIP emit from `.xcworkspace`
   uses a different DerivedData layout than SwiftPM; the existing
   `palace-swift-scip-emit-cli` may need flag changes. Budget for the
   discovery cost.
4. **D4 cloudflared without auth exposes the UW source code graph
   publicly.** The operator accepted the risk for the initial deploy;
   harden ASAP after landing. Add `TODO-HARDEN` comment in the plist.
5. **A3 MERGE-by-FQN may require schema migration on existing graphs.**
   Without a unique constraint on `(qualified_name, project)`, MERGE is
   O(n) per write. Add the constraint up front and verify migration on a
   shadow neo4j before running on prod.

## 14. Where this spec lives

- This file: `docs/superpowers/specs/2026-05-29-uw-ios-full-product.md`.
- Meta-issue: **GIM-987** (to be opened) — "Full UW iOS Gimle product",
  checklist by block, links to per-task child issues.
- Per-task child issues opened on Block-A/B/C/D acceptance gates.
