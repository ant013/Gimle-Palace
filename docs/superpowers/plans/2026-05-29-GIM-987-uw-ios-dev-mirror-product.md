# GIM-987 UW iOS Dev-Mirror Product — Walker Plan

> Walker driver for the spec at
> [`docs/superpowers/specs/2026-05-29-uw-ios-full-product-rev2.md`](../specs/2026-05-29-uw-ios-full-product-rev2.md).
>
> Owner: cxcto walker (agent `da97dbd9-6627-48d0-b421-66af0750eacf`).
> CEO orchestration: `10a4968e-...` per [[reference_gimle_no_autowake]].

## Goal

Land a fully usable Gimle dev-mirror for the Unstoppable Wallet iOS
ecosystem: 13 kits (8 already in graph + 5 to add) with every
language-applicable extractor green per kit, MacBook docker-compose
serving MCP on port 8765, cloudflared tunnel `gimle.ant013.work`
reachable from any network with WRITE tools bearer-gated and READ
tools public per Q9.

## Assumptions

- Rev2 spec (PR #347) is the authoritative source. If the spec
  evolves, walker re-reads on next iteration; this plan tracks the
  rev2 decisions verbatim.
- CXCTO is the walker. CEO is the dispatch hub. Codex queue carries
  bash / infra / cleanup / docker / runbook work (~66% of slices);
  Claude queue carries Python work in `services/palace-mcp/src/` and
  spec/design work (~33%).
- Per [[feedback_walker_sprint_protocol]] — ONE walker issue (this
  one), then CEO spawns CTO children. Do NOT bulk-POST every child
  upfront — open the **first parallel-safe batch** only, let CEO open
  follow-on batches as predecessors close.
- Per [[feedback_sequential_revised_multi_team]] — 2 teams with 2
  issues each in parallel is OK when file overlap is analysed up
  front. Block-A bash/infra (cxinfra) and Block-A Python
  (Claude pythonengineer) touch disjoint trees → safe to parallelise.

## Acceptance Criteria

For the walker as a whole:

1. `docs/superpowers/specs/2026-05-29-uw-ios-full-product-rev2.md`
   Block-A, Block-B, Block-C, Block-D, Block-F acceptance gates all
   green.
2. `paperclips/scripts/palace_extractor_smoke.sh <slug>` (Smoke A)
   passes on all 13 kits + `uw-ios-app` on both iMac and MacBook.
3. `paperclips/scripts/palace_tool_smoke.sh <slug>` (Smoke B) passes
   on all 13 kits + `uw-ios-app` against the MacBook MCP via both
   `http://localhost:8765/mcp` and `https://gimle.ant013.work/mcp`.
4. Write-tool call (`palace.ingest.run_extractor` etc.) without
   `Authorization: Bearer <token>` against the public endpoint returns
   401.
5. `:Author` nodes carry `email_hash`, not raw email.
6. Walker can re-run an ingest on any kit without doubling
   `count(:Symbol {group_id: $slug})` (MERGE + soft-delete proven).

For each child issue spawned by CEO:

- Acceptance is the per-task acceptance line in §4–§7 of the rev2 spec.
- Each PR carries `## QA Evidence` with the merged-to-develop SHA and
  the relevant smoke output.

## Plan

### Phase 1 — Foundation gate (parallel-safe first batch)

These six children can be spawned together by CEO immediately on
walker accept. They touch disjoint files and have no internal
dependencies.

1. **GIM-987-c1 (Codex / cxinfra)** — A1 Toolchain auto-detect
   - File: `paperclips/scripts/scip_emit_swift_kit.sh`
   - Work: read `<repo>/.swift-version` (follow symlinks), normalise
     to `swift-<X.Y.Z>-RELEASE`, pass `-toolchain` to `xcodebuild`.
     Hard-fail if toolchain missing. Add `--scheme-only-check` flag.
   - Check: invoking on a kit whose `.swift-version` says `5.8` with
     `swift-5.8.1-RELEASE` installed → builds under Swift 5.8.1;
     with `swift-5.8.1-RELEASE` missing → exits non-zero with
     explicit "toolchain not installed: …" message.

2. **GIM-987-c2 (Codex / cxinfra)** — A2 Per-kit cleanup
   - File: `paperclips/scripts/palace_ingest.sh`
   - Work: after successful ingest, `rm -rf <repo>/.palace-scip-build
     <repo>/.palace-scip-derived-data`. Add `--keep-build` debug flag.
   - Check: ingest a kit, `du -sh <repo>` < 50 MB after run.

3. **GIM-987-c3 (Claude / pythonengineer)** — A3 Symbol soft-delete + constraint
   - Files: `services/palace-mcp/src/palace_mcp/extractors/foundation/symbol_node_writer.py`, new migration script `services/palace-mcp/scripts/migrate_symbol_constraint.py`
   - Work: (a) dedup migration: `MATCH (a:Symbol),(b:Symbol) WHERE
     a.qualified_name = b.qualified_name AND a.group_id = b.group_id
     AND id(a) < id(b) DETACH DELETE b` in batches; (b) idempotent
     `CREATE CONSTRAINT symbol_unique IF NOT EXISTS FOR (s:Symbol)
     REQUIRE (s.qualified_name, s.group_id) IS UNIQUE` at startup;
     (c) end-of-ingest pass sets `deleted_at = $now` on `:Symbol`
     nodes in `group_id` not in current SCIP; clears `deleted_at`
     on MERGE-hit.
   - Check: unit test re-ingesting the same SCIP twice does not
     increase `count(:Symbol {group_id, deleted_at: null})`.
     Integration test: ingest SCIP A, then ingest SCIP B with one
     symbol removed → that symbol has `deleted_at` set.

4. **GIM-987-c4 (Claude / pythonengineer)** — A4 GIM-950 kit embeddings
   - Files: `services/palace-mcp/src/palace_mcp/extractors/embedding_symbol.py` (and any other extractor resolving mount paths from `repo_name`)
   - Work: unify mount-path resolution on slug throughout palace-mcp.
   - Check: `palace.ingest.run_extractor name=embedding_symbol project=hs-crypto-kit` returns `status=ok` with `nodes_written > 0`.
   - Hard cap: 3 days; escalate to walker if exceeded.

5. **GIM-987-c5 (Codex / cxinfra)** — A5 iMac rebuild
   - Ops on iMac; maintenance window after 22:00 UTC+5.
   - Work: `cd /Users/Shared/Ios/Gimle-Palace && git pull --ff-only origin develop && docker compose build palace-mcp && docker compose up -d palace-mcp`.
   - Check: `docker exec gimle-palace-palace-mcp-1 stat -c '%U:%G' /data/hf-cache` returns `appuser:appuser`. No more manual `chown` required after future ingests.
   - **Hard-gate before GIM-987-c10 (D3)**.

6. **GIM-987-c6 (Codex / cxinfra)** — C2 PALACE_SCIP_INDEX_PATHS dedup
   - File: `paperclips/scripts/ingest_swift_kit.sh`
   - Work: dedup the env var on each write — split on `:`, sort -u, rejoin.
   - Check: ingest the same kit twice → env var length is bounded.

### Phase 2 — Discovery + first kit add (after Phase 1 closes)

CEO spawns when GIM-987-c1 closes (A1 gates B-series):

7. **GIM-987-c7 (Codex / cxqa)** — A6a Discovery sweep
   - Files: new `paperclips/scripts/palace_extractor_coverage_2026-05-29.csv`, `paperclips/scripts/palace_extractor_baseline_g0c.txt`
   - Work: iterate each of the 8 in-graph kits, run each language-applicable extractor via `palace.ingest.run_extractor`, capture (slug, ext, status, nodes_written, message). Mark known G0c artefact slots per [[project_extractor_baseline_2026-05-22]].
   - Check: CSV + baseline file committed; one row per (kit, extractor) pair.

8. **GIM-987-c8 (Codex / cxinfra)** — B1 hs-extensions verify
   - Work: `palace_ingest.sh --github https://github.com/horizontalsystems/HsExtensions.Swift --skip-embedding`.
   - Check: `:Project {slug: "hs-extensions", language: "swift"}` exists, `count(:Symbol {group_id: "hs-extensions"}) > 0`.

### Phase 3 — Remaining SwiftPM kits + cleanup (parallel-safe)

CEO spawns when GIM-987-c7 + GIM-987-c8 close:

9. **GIM-987-c9 (Codex / cxinfra)** — B2 MarketKit
   - Work: ingest via wrapper; if GRDB still fails under 5.8.1, fall back to GRDB version pin via Package.swift override.
   - Check: `:Project {slug: "market-kit"}` in graph; Smoke A green.

10. **GIM-987-c10 (Codex / cxinfra)** — B3 BitcoinCashKit
    - Work: ingest via wrapper; fallback to HsCryptoKit pin if needed.
    - Check: `:Project {slug: "bitcoin-cash-kit"}` in graph; Smoke A green.

11. **GIM-987-c11 (Codex / cxinfra)** — C1 palace_cleanup.sh
    - File: new `paperclips/scripts/palace_cleanup.sh`
    - Check: `--dry-run` single-host under 30 s, dual-host (macbook + ssh-iMac) under 90 s.

12. **GIM-987-c12 (Codex / cxinfra)** — C4 graph orphan cleanup
    - File: extension of `palace_cleanup.sh` from c11.

### Phase 4 — Cocoapods pipeline

CEO spawns when GIM-987-c9 closes (so xcodebuild path is exercised first):

13. **GIM-987-c13 (Codex / cxinfra)** — B4a Cocoapods spike
    - File: new `docs/research/2026-05-29-cocoapods-scip-spike.md`
    - Check: research doc with DerivedData layout deltas, scheme detection differences, `pod install` failure modes (CDN timeout).

14. **GIM-987-c14 (Codex / cxinfra)** — B4b Cocoapods pipeline
    - Files: new `paperclips/scripts/scip_emit_cocoapods_kit.sh`, edit `paperclips/scripts/palace_ingest.sh` to detect `Podfile` vs `Package.swift` and route.
    - Check: `palace_ingest.sh --github <cocoapods-repo>` routes through the cocoa emitter.

15. **GIM-987-c15 (Codex / cxinfra)** — B5 component-kit ingest
    - Acceptance: `:Project {slug: "component-kit"}` in graph.

16. **GIM-987-c16 (Codex / cxinfra)** — B6 hd-wallet-kit-ios ingest
    - Acceptance: `:Project {slug: "hd-wallet-kit-ios"}` in graph (distinct from `hd-wallet-kit`).

### Phase 5 — MacBook dev-mirror

CEO spawns when GIM-987-c1, c2, c3, c5 (A1+A2+A3+A5) close; D-series can overlap Cocoapods Phase 4:

17. **GIM-987-c17 (Codex / cxinfra)** — D1 `docker-compose.dev-mac.yml`
    - File: new `docker-compose.dev-mac.yml`
    - Check: `docker compose -f docker-compose.dev-mac.yml up -d` brings up palace-mcp on `localhost:8765` + own Neo4j on a non-overlapping port; no `cpus` cap.

18. **GIM-987-c18 (Codex / cxinfra)** — D2 macbook bootstrap runbook
    - File: new `docs/runbooks/macbook-gimle-bootstrap.md`
    - Check: a fresh-mac walkthrough takes 30–60 min wall-clock.

19. **GIM-987-c19 (Claude / pythonengineer)** — D4a Bearer middleware on WRITE tools
    - File: new `services/palace-mcp/src/palace_mcp/auth.py`, edits to `mcp_server.py` tool registrations.
    - Work: middleware reads `PALACE_WRITE_TOKEN` env var; gates all `palace.ingest.*`, `palace.memory.add_to_bundle`, `palace.memory.delete_bundle`, `palace.memory.decide`, `palace.audit.run`, `palace.ops.unstick_issue`, `palace.project.analyze*`.
    - Check: unit test — write call without bearer → 401; with valid bearer → 200. Read call without bearer → 200.

20. **GIM-987-c20 (Codex / cxinfra)** — D4c GDPR env
    - Work: add `PALACE_OWNERS_HASH_EMAILS=1` to `docker-compose.dev-mac.yml`; one-line guard in `code_ownership` extractor that hashes when env set.
    - Check: `:Author` nodes ingested with env set carry `email_hash` not `email`.

21. **GIM-987-c21 (Codex / cxinfra)** — D4b Cloudflared tunnel
    - Files: new `services/cloudflared/dev-mac/config.yml`, launchd plist.
    - Check: `curl https://gimle.ant013.work/mcp/` → 406 from any network.
    - **Hard-gate after GIM-987-c19 (D4a) lands** — do NOT enable the launchd plist before bearer middleware is in place.

22. **GIM-987-c22 (Codex / cxinfra)** — D3 Fresh ingest of 13 kits on macbook
    - Work: `palace_ingest.sh --github` × 13 against `localhost:8765` MCP. Use `--skip-if-ingested` for resume.
    - Check: `palace.memory.list_projects` over MCP returns 13 swift projects.

### Phase 6 — Smoke acceptance + handover

CEO spawns when all prior phases close:

23. **GIM-987-c23 (Codex / cxqa)** — F-A Smoke A per-extractor
    - File: new `paperclips/scripts/palace_extractor_smoke.sh`
    - Check: green on all 13 kits + `uw-ios-app` on both iMac and MacBook.

24. **GIM-987-c24 (Codex / cxqa)** — F-B Smoke B per-tool with oracle
    - Files: new `paperclips/scripts/palace_tool_smoke.sh`, new `paperclips/scripts/palace_smoke_seeds.json`
    - Check: green on all 13 kits + `uw-ios-app` against both iMac and MacBook MCP endpoints.

25. **GIM-987-c25 (Claude / Board)** — E1 Scheduled-updates design doc
    - File: new `docs/superpowers/specs/2026-05-29-palace-scheduled-updates.md`
    - Check: design doc merged; no launchd job created.

## Verification Commands

- Block A done: `cat paperclips/scripts/palace_extractor_coverage_2026-05-29.csv | wc -l` ≥ 8×N where N = applicable extractor count; every non-G0c row has `status=ok`.
- Block B done: `cypher-shell "MATCH (p:Project) WHERE p.language = 'swift' RETURN count(p)"` returns 13.
- Block C done: `bash paperclips/scripts/palace_cleanup.sh --dry-run` returns 0 within 30 s (single host) / 90 s (dual host).
- Block D done: `curl -o /dev/null -w '%{http_code}' http://localhost:8765/mcp/` → 406; `curl -o /dev/null -w '%{http_code}' https://gimle.ant013.work/mcp/` → 406; write-without-bearer → 401.
- Block F done: `bash paperclips/scripts/palace_extractor_smoke.sh <slug>` and `palace_tool_smoke.sh <slug>` exit 0 on all 13 kits + `uw-ios-app`.

## Non-Goals

- Agent skills / decision-tree instructions (separate spec).
- A/B benchmark vanilla-vs-Gimle agent (depends on skills).
- Cloudflare Access browser-SSO policy (Q9 deferred; D4a bearer is the security floor).
- Scheduled-updates implementation (E1 design only this milestone).
- Broader UW kits beyond the 13-kit list (iterative-add-one mode after walker closes).
- iMac decommission (iMac stays primary for Paperclip agents).

## Walker discipline notes

- **Don't bulk-POST all 25 children.** Spawn Phase 1 (6 children) only at walker accept. CEO opens follow-on phases as predecessors close per the dependency graph above.
- **Hard gates**: A5 → D3; D4a → D4b; A1 → B-series; B4a → B4b.
- **Two-team file-overlap analysis** done for Phase 1: cxinfra touches `paperclips/scripts/*` + `services/cloudflared/*` + `docker-compose.dev-mac.yml`; pythonengineer touches `services/palace-mcp/src/palace_mcp/extractors/*`. No overlap → safe parallel.
- **False-done detection**: if a Codex agent marks a c-issue `done` without a merged PR referencing the c-issue ID, walker reopens with a Board comment per the rev1 → rev2 → GIM-984 / GIM-986 pattern observed 2026-05-28.
- **Slim per-kit retries**: a B-series ingest failure is *the kit's* problem, not a Block-B abort. Continue with remaining kits, then loop back to failed ones.
- **Stop signal**: any time the operator says "stop", pause spawning new children. In-flight children continue to completion; no new dispatches.
