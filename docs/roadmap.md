# Gimle-Palace Team Roadmap

**Last updated**: 2026-05-06 (rev2: audit-v1 plan — 3-reviewer synthesis)
**Owner**: Board (operator + Board Claude session)
**Primary goal**: Index Unstoppable Wallet ecosystem live (Android + iOS + EVM
contracts). Phase 1 ends when palace-mcp produces useful queries against the
real UW codebase end-to-end.

This file is the **single source of truth** for slice ownership and ordering
across the two paperclip teams (Claude and CX/Codex). Update on every slice
merge or scope change.

---

## Status legend

| Icon | Meaning |
|------|---------|
| ✅ | Merged to develop |
| 🚧 | In flight (active phase chain) |
| 📋 | Queued — assigned, ready to start |
| ⏸ | Deferred — has explicit reactivation trigger |
| 📦 | Backlog — no team yet, no trigger |

## Team domains

| Team | Default scope | Adapter |
|------|--------------|---------|
| **Claude** | Python-orchestration extractors, LLM-using extractors, watchdog/observability, product-tool composites, Slice spec authoring, infrastructure, runbooks | `claude_local` |
| **CX/Codex** | Native-compiled language extractors, SCIP indexer integration, custom scip-emit binaries, native LSP work | `codex_local` |

Roles within each team follow the standard 7-phase chain: CTO → CR → PE/MCP/Infra → CR → Opus → QA → CTO merge. See `paperclips/fragments/profiles/handoff.md` for atomic-handoff discipline.

CX team currently lacks BlockchainEngineer and SecurityAuditor parity — see E6 in §5.

---

## Phase 1 — UW launch path (priority)

When all rows below are ✅, palace-mcp can index the entire UW production ecosystem live and the operator runs queries against real source instead of fixtures. **Phase 2 does not start until Phase 1 closes.**

### CX queue (sequential, launch-critical)

| Order | Slice | Status | Issue | Files | Notes |
|-------|-------|--------|-------|-------|-------|
| 1 | Symbol index Swift (UW-iOS, custom emitter Option C) | ✅ | GIM-128 | `services/palace-mcp/scip_emit_swift/`, `extractors/symbol_index_swift.py`, `tests/extractors/fixtures/uw-ios-mini-project/` | Merged `4ff2b2f`. Custom emitter; canonical Sourcegraph SCIP protobuf output. |
| 2 | Symbol index C/C++/Obj-C (UW-iOS Pods, scip-clang) | ✅ | GIM-184 | `extractors/symbol_index_clang.py`, fixtures, compose mounts | Merged `80b4f38`. Final v1 scope is C/C++; Objective-C is a documented follow-up after `scip-clang` smoke showed `.m` unsupported as first-class input. |

**Launch boundary**: reached when both CX queue items above AND Claude queue C2 (Multi-repo SPM ingest, GIM-182) are ✅. As of 2026-05-04, all launch-critical implementation rows are merged; the remaining launch close gate is operator validation that real UW queries return expected results end-to-end.

### Claude queue (parallel, infra + tooling + launch-critical C2)

| Order | Slice | Status | Issue | Files | Notes |
|-------|-------|--------|-------|-------|-------|
| C1 | Watchdog handoff detector (Phase 1 alert-only) | ✅ | GIM-181 | `services/watchdog/*` | Detective half of atomic-handoff strategy; merged `f2f05c4` |
| C2 | Multi-repo SPM ingest (full slice — Claude end-to-end) | ✅ | GIM-182 | `services/palace-mcp/src/palace_mcp/{memory/bundle.py,code/find_references.py,ingest/runner.py,git/path_resolver.py}`, `services/palace-mcp/scripts/`, `docs/runbooks/multi-repo-spm-ingest.md` | Merged `f2696fa`. Originally split (Claude=spec, CX=impl); operator decision 2026-05-03 reassigned to Claude end-to-end. |
| C3 | Watchdog handoff detector — Opus nudge follow-up | ✅ | GIM-183 | `services/watchdog/*` | 3 follow-ups merged `365c9c4` (PR #81): server-Date anchoring, 4 missing JSONL events emitted, e2e lifecycle test. |
| C4 | Git History Harvester (Extractor #22) — Phase 2 prereq | ✅ | GIM-186 | `services/palace-mcp/src/palace_mcp/extractors/git_history/`, `services/palace-mcp/tests/extractors/{unit,integration,fixtures}/`, runbook | Merged `b0dd44d`. Foundation for 6 historical extractors (#11/#12/#26/#32/#43/#44) — all now unblocked. |
| C5 | iMac post-merge auto-deploy | 📋 | TBD | `paperclips/scripts/imac-deploy-listener.{sh,plist}`, webhook handler | Removes manual `imac-deploy.sh` step after every merge |
| C6 | `palace.code.semantic_search` | 📋 | TBD | `services/palace-mcp/src/palace_mcp/code/semantic_search.py` | Deferred Slice 5 of original USE-BUILT; vector or hybrid search composite |

C2 (GIM-182) and C4 (GIM-186) are now ✅. C3/C5/C6 are independent and not launch-blocking.

### Already merged (Phase 1 foundation)

| Slice | Issue | Note |
|-------|-------|------|
| Symbol index Python | GIM-102 | Foundation dogfood; first content extractor on 101a substrate |
| Symbol index TS/JS | GIM-104 | Lang-agnostic `scip_parser` extracted |
| Symbol index Java/Kotlin | GIM-111 + GIM-127 | UW-Android validated, fixture pinned to UW@c0489d5a3 (pre-AGP-9) |
| Symbol index Solidity v1 | GIM-124 | DEFs only; USE-occurrences deferred to Phase 2 |
| Watchdog mechanical | GIM-67/69/79/80 | `scan_died_mid_work` + `scan_idle_hangs` |
| Atomic-handoff fragment | PR #77 (`9262aca`) | Preventive companion to GIM-181 |
| Watchdog handoff detector (alert-only) | GIM-181 (`f2f05c4`) | Detective half of atomic-handoff strategy; 3 Opus nudge follow-ups closed in GIM-183 |
| Watchdog handoff detector — Opus nudge follow-ups | GIM-183 (`365c9c4`) | Server-Date anchoring + 4 JSONL events + e2e lifecycle test |
| Symbol index Swift (UW-iOS) | GIM-128 (`4ff2b2f`) | First-party HS Kits indexed via custom emitter; CX queue item 1 closed |
| Symbol index C/C++ (UW-iOS native) | GIM-184 (`80b4f38`) | `scip-clang` C/C++ extractor merged; Objective-C follow-up documented out of v1 |
| Multi-repo SPM ingest | GIM-182 (`f2696fa`) | First-party HS Kits resolved via bundle; UW iOS multi-repo path unblocked |
| Paperclip team workspace isolation | PR #76 | Two team roots under `/Users/Shared/Ios/worktrees/{claude,cx}/` |
| Paperclip shared CM discipline | PR #75 | Both teams share `repos-gimle` CM project + `palace.memory.decide` writes |
| Codex/CX team build target | PR #73-74 | Codex team operational with 9 roles |

---

## Audit-V1 — first product release (current focus)

**Goal**: ship a working audit pipeline end-to-end — pick `tronKit-swift`,
get a complete audit report from a paperclip agent team, MCP fully
populated. After v1 ships, every additional extractor is a tiny isolated
slice that just enriches MCP without touching workflow.

**Definition of Done for v1 (rev3):**
1. `palace.audit.run(project="tronkit-swift")` returns a structured
   markdown report (synchronous data+render, no agent involvement).
2. `audit-workflow-launcher.sh tronkit-swift` triggers a multi-agent
   audit via Paperclip child issues; final report posted to parent.
3. The same commands work on `bitcoinkit-swift` and any other Swift Kit.
4. After v1, adding extractor X = (a) implement `audit_contract()` on
   extractor class, (b) add template file, (c) re-run — no orchestrator
   or agent changes needed (enforced by `BaseExtractor.audit_contract()`
   pattern).
5. Audit report ships **with populated** Architecture Layering (extractor
   #1) and Error Handling Policy (extractor #7) sections — these are
   NOT blind spots in v1 (rev3, AV1-D7 flipped from "yes/blind-spot" to
   "no/included"; +6w to envelope).

### Sprint sequence (rev3 — #1 + #7 included; 18w envelope)

| ID | Sprint | Detail file | Wall-time | Depends on | Team |
|----|--------|-------------|-----------|------------|------|
| **S0** ✅ | Foundation prerequisites (IngestRun unify, composite tools, audit-mode prompts) | [`D-audit-orchestration.md` §S0](superpowers/sprints/D-audit-orchestration.md) | ~1 week | nothing | PE (S0.1+S0.2) ‖ any (S0.3) | `0a02ade` |
| **S1 (D)** | Audit Orchestration — workflow + agents + report format + tool | [`D-audit-orchestration.md`](superpowers/sprints/D-audit-orchestration.md) | ~3-4 weeks | S0 | PE |
| **S2.1 (B-min)** | Audit-critical extractor: `crypto_domain_model` (#40) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~2 weeks | S1.6 frees PE + semgrep spike | Claude PE |
| **S2.2 (B+1)** | Architecture Layer extractor (#1) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~3 weeks | S2.1 frees PE | Claude PE |
| **S2.3 (B+7)** | Error Handling Policy extractor (#7) | [`B-audit-extractors.md`](superpowers/sprints/B-audit-extractors.md) | ~3 weeks | S2.2 frees PE (or ‖ if a 2nd Claude engineer is free) | Claude PE |
| **S3 (C)** | Per-Kit ingestion automation | [`C-ingestion-automation.md`](superpowers/sprints/C-ingestion-automation.md) | ~1 week | S1.9 (palace_mcp.cli) | Infra (‖ S1) |
| **S4 (E)** | Smoke on tronKit-swift + bitcoinKit-swift | [`E-smoke.md`](superpowers/sprints/E-smoke.md) | ~1 week | S0 + S1 + S2.1 + S2.2 + S2.3 + S3 (GIM-216 ✅ merged `2d6e6c1`; GIM-218 ✅ merged `603c840`) | QA + operator |
| **S5 (F)** | Scale to 41 HS Kits + uw-ios-app | [`F-scale.md`](superpowers/sprints/F-scale.md) | ~3 weeks | S4 | operator + Infra |
| **S6+** | Iterative extractor backlog (#2, #34, etc — #1/#7 NOT here in rev3) | TBD per slice | ongoing | post-v1 | per slice |

**Rev3 critical path** (sequential, single Claude PE): S0 (1w) → S1 (3-4w, PE-bound) →
S2.1 (2w PE) → S2.2 (3w PE, #1 Arch Layer) → S2.3 (3w PE, #7 Error Handling) →
S4 (1w) → S5 (3w) = **~17-18 weeks**.
S3 runs ‖ S1 (different engineer).
GIM-218 contingency closed: extractor merged `603c840` 2026-05-07.
**Parallel S2.2 ‖ S2.3 option**: if a second Claude engineer becomes available
after S2.1 (different files: arch_layer/* vs error_handling/*), max(3w, 3w) = 3w
collapses to **~14-15 weeks** total. Operator-chosen 18w envelope tolerates the
sequential path with ~0-1w margin; parallelisation is upside, not gating.

### Path justification (rev2 — incorporates team allocation)

- **S0 first**: prerequisite foundation fixes (IngestRun schema unification,
  missing composite tools, audit-mode agent prompts). Without S0, S1.4
  discovery misses half the extractors (OPUS-CRITICAL-1) and S1.5 fetcher
  has no tools to call (CR-CRITICAL-3).
- **S1 after S0**: defines the product surface. PythonEngineer-bound.
- **S2.1 after S1.6** (rev2 change): S2.1 also needs PE. Rev1 claimed S1‖S2
  parallel — impossible with one PE (CTO-MEDIUM-1). S2.1 starts when S1.6
  (`audit_contract()` implementations) frees PE. Requires completed semgrep
  spike (S2-prereq). S2.1 = `crypto_domain_model` (#40).
- **S2.2 after S2.1** (rev3): Architecture Layer extractor (#1). Reuses
  the semgrep / tree-sitter substrate from S2.1 prereq spike. Deterministic
  (no LLM); writes `:Module/:Layer/:ArchViolation`. Critical for
  blockchain-audit "wallet-core must not import UI", "Kit X must not
  depend on Kit Y" findings.
- **S2.3 after S2.2** (rev3): Error Handling Policy extractor (#7). Heuristic
  (semgrep + ast-grep + detekt rules). Writes `:CatchSite/:ErrorPolicy`.
  Critical for crypto-Kits — swallowed errors in signing/balance paths
  → potential lost funds.
- **S3 ‖ S1**: InfraEngineer domain, no file overlap. Ingestion automation
  shrinks per-Kit setup from ~30 min to ~3 min. Needs `palace_mcp.cli`
  from S1.9 (or `curl` shim until then).
- **S4 after S0+S1+S2.{1,2,3}+S3**: real smoke on tronKit-swift +
  bitcoinKit-swift. Measurable acceptance criteria (rev2, CR-MED-4)
  + per-extractor sections required for #1 + #7 (rev3, AV1-D7 flip).
- **S5 last**: scaling to 41 Kits. 3 weeks (rev2, padded from 2 — OPUS-MEDIUM-1).
- **S6+ post-v1**: each new extractor plugs in via `audit_contract()` —
  no orchestrator/agent changes.

### Critical decision points (rev2 — pre-S0 start)

| ID | Question | Default | Impact of non-default | When |
|----|----------|---------|----------------------|------|
| AV1-D1 | Report format: markdown only, or also JSON? | markdown only | JSON adds ~1 slice to S1.3 | S1.1 brainstorm |
| AV1-D2 | Agent set: reuse 3 + 1 new Auditor, NO Synthesizer? (rev2) | reuse 3 + Auditor, no Synth | Adding Synth = +1 agent role + token cost per audit | S1 brainstorm |
| AV1-D3 | Trigger: manual only for v1? | manual; cron/CI in S6+ | Cron adds ~2 slices | S1 brainstorm |
| AV1-D4 | LLM extractors deferred to post-v1? | yes | If no → +12 weeks for Ollama infra | After S4 |
| AV1-D5 | SCIP emit Track A/B preserved? | yes | Single-machine = simpler but slower | S3 brainstorm |
| AV1-D6 | Max tokens per agent per audit run? (rev2) | 50K in / 10K out | Higher = richer sub-reports but more cost | S1.1 brainstorm; measured in S4 |
| AV1-D7 | Blind spots #1 (Arch Layer) + #7 (Error Handling) acceptable for v1? (**rev3 — flipped**) | **NO — both extractors INCLUDED in v1; envelope expanded 12w → 18w** | If yes (revert to rev2) → 12w envelope, sections shipped as blind spots in §9 | Resolved pre-rev3 (operator decision 2026-05-07) |

### In-flight slices feeding v1

- **GIM-216** code_ownership — ✅ merged `2d6e6c1` 2026-05-06. Feeds Ownership report section in S4. `palace.code.find_owners` registered at `mcp_server.py:850`.
- **GIM-218** cross_repo_version_skew — ✅ merged `603c840` 2026-05-07. Feeds Dependencies §5 of audit report. `palace.code.find_version_skew` registered via `register_version_skew_tools()` at `mcp_server.py:790`. **Rev2 contingency closed** — extractor landed before contingency trigger fired; no blind-spot fallback needed.

### Post-v1 slice intake protocol (rev2 — `audit_contract()` paved path)

After v1 ships, adding extractor X follows the **paved path**:

1. Board+Claude session: brainstorm + spec rev1 + 4-agent audit + spec rev2.
2. Paperclip team: standard 7-phase chain.
3. Implementer adds `audit_contract()` method to extractor class + template file.
4. iMac deploy: `bash paperclips/scripts/imac-deploy.sh`.
5. Per-existing-Kit re-ingest: `bash scripts/ingest_swift_kit.sh <slug> --extractors=X`.
6. Re-run `palace.audit.run(project=<slug>)` — report includes new section
   automatically because the generic fetcher discovers it via `:IngestRun`
   and calls `audit_contract()` for query + template.

The pipeline is **extractor-name-agnostic** — discovery enumerates from the
graph, fetcher dispatches via `audit_contract()`, renderer loads the template.
No hardcoded lists anywhere in the orchestrator (rev2 fix for CTO-CRITICAL-1,
OPUS-CRITICAL-2).

---

### Archived Phase 2-6 backlog

Moved to [`docs/roadmap-archive.md`](roadmap-archive.md) in rev2
(OPUS-LOW-1: HTML comments are invisible to search/grep/agent tools).
Re-activate individual rows via S6+ intake protocol.

<!-- rev3 (2026-05-07): inline HTML-commented duplicate of Phase 2-6
     fully removed; canonical content lives in docs/roadmap-archive.md.
     This closes OPUS-LOW-1 — search/grep/agent tools no longer need
     to peek inside HTML comments to see archived rows. -->


---

## Parallelization rules

Per `feedback_parallel_team_protocol.md` (operator-codified 2026-05-03).

1. **No file overlap** between active parallel slices on the same shared file.
2. **One issue = one team end-to-end.** Don't mix Claude and CX agents within a single slice's phase chain.
3. **Smoke-first** before introducing new parallel patterns.
4. **Forbidden if both touch any of**:
   - same extractor under `services/palace-mcp/extractors/*`
   - same fixture under `services/palace-mcp/tests/extractors/fixtures/*`
   - `docker-compose.yml`, `.env.example`, `CLAUDE.md`
   - same spec file or plan file under `docs/superpowers/specs|plans/`
5. **Additive shared-file edits** (registry registration line, compose mount line, env-var line) are tolerated when both teams promise additive-only changes; merge-order conflicts resolve trivially.

## Atomic-handoff discipline

Per `paperclips/fragments/profiles/handoff.md` (PR #77, `9262aca`):

> ALWAYS hand off by PATCHing `status + assigneeAgentId + comment` in one API call, then GET-verify the assignee; @mention-only handoff is invalid.

Watchdog Phase 1 (GIM-181, merged `f2f05c4`) landed the **detective** half — alerts when an agent fails this rule. Three Opus nudge follow-ups tracked as GIM-183.

---

## Update protocol

When a slice merges to `develop`:

1. Move the row from 🚧 / 📋 to ✅.
2. If a dependent unblocks → annotate that row.
3. Promote next CX or next Claude item one position up if its predecessor closed.
4. Commit roadmap update on a small `docs(roadmap):` PR or alongside the merging slice's spec/plan PR.

Avoid editing during active phase chains — wait for the slice merge so the file matches the latest develop tip.

---

## Open questions

- **Audit-V1 decision points** — see `Audit-V1 — first product release` section above for AV1-D1..AV1-D7 (rev2 adds D6 token budget + D7 blind spot acceptance). Resolve pre-S0 start.
- **Phase 1 real-query validation** — launch-critical rows are merged; S4 smoke is the de facto launch validation.
- **LLM infrastructure** — 6 extractors require LLM. Decision per AV1-D4: post-v1.
- **Archived Phase 2-6 backlog** — moved to `docs/roadmap-archive.md` (rev2). Re-activate via S6+ intake protocol.
- ~~GIM-218 contingency~~ (rev2) — **closed in rev4**: GIM-218 merged `603c840` 2026-05-07; version-skew shipped, no blind-spot fallback needed.
