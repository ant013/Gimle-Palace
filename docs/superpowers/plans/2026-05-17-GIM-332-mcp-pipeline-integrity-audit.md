# GIM-332: MCP / Pipeline Integrity Audit

> **For agentic workers:** Read only your assigned step — the full issue body is not needed.

**Goal:** Verify full data path for every registered extractor (24 total) on reference projects (`gimle`, `uw-ios-mini`). Produce coverage matrix, file child issues for broken stages, address watchdog token-validity gap.

**Spec:** `docs/superpowers/specs/2026-05-17-mcp-pipeline-integrity-audit.md`  
**Branch:** `feature/GIM-332-mcp-pipeline-integrity-audit`  
**Grounded on:** `develop` @ `7caaba8`

---

## Step 1 — Probe infrastructure + IngestRun verification (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** —

**Description:**  
For each of the 24 registered extractors, verify that an `:IngestRun{source="extractor.<name>"}` row exists in Neo4j for reference projects. Run:

```cypher
MATCH (r:IngestRun)
WHERE r.source STARTS WITH "extractor."
  AND r.group_id IN ["project/gimle", "project/uw-ios-mini"]
RETURN r.source, r.group_id, r.success, r.created_at
ORDER BY r.source
```

For extractors with no IngestRun: attempt a fresh run via `palace.ingest.run_extractor(name=..., project=...)` and record the result.

**Acceptance criteria:**
- [ ] List of all 24 extractors with IngestRun presence (yes/no/error) on both reference projects.
- [ ] Any extractor that fails to run: capture error envelope and classify as BROKEN.
- [ ] Results recorded in `docs/runbooks/extractor-integrity-audit-2026-05-17.md` Stage 1 column.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md` (create)

---

## Step 2 — Domain nodes/edges verification (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** Step 1 (need IngestRun data to know which extractors ran)

**Description:**  
For each extractor that has a successful IngestRun, verify that the expected domain nodes/edges exist per CLAUDE.md runbook promises. Run per-extractor canonical Cypher queries:

| Extractor | Expected node labels | Canonical check query |
|-----------|---------------------|----------------------|
| heartbeat | `:ExtractorHeartbeat` | `MATCH (h:ExtractorHeartbeat) WHERE h.group_id = $gid RETURN count(h)` |
| symbol_index_* | `:SymbolOccurrence` | `MATCH (s:SymbolOccurrence) WHERE s.group_id = $gid RETURN count(s)` |
| dependency_surface | `:ExternalDependency` | `MATCH (:Project{slug:$slug})-[:DEPENDS_ON]->(d:ExternalDependency) RETURN count(d)` |
| git_history | `:Commit`, `:Author` | `MATCH (c:Commit) WHERE c.group_id = $gid RETURN count(c)` |
| code_ownership | `[:OWNED_BY]` | `MATCH ()-[r:OWNED_BY]->() WHERE r.group_id = $gid RETURN count(r)` |
| coding_convention | `:Convention` | `MATCH (c:Convention) WHERE c.group_id = $gid RETURN count(c)` |
| hotspot | `:File{hotspot_score}` | `MATCH (f:File) WHERE f.group_id = $gid AND f.hotspot_score IS NOT NULL RETURN count(f)` |
| hot_path_profiler | `:HotPathSample` | `MATCH (h:HotPathSample) WHERE h.group_id = $gid RETURN count(h)` |
| reactive_dependency_tracer | `:ReactiveComponent` | `MATCH (r:ReactiveComponent) WHERE r.group_id = $gid RETURN count(r)` |
| localization_accessibility | `:LocaleResource` | `MATCH (l:LocaleResource) WHERE l.group_id = $gid RETURN count(l)` |
| cross_repo_version_skew | (read-only audit) | `palace.code.find_version_skew(project=$slug)` |
| arch_layer | `:ArchLayer` | `MATCH (a:ArchLayer) WHERE a.group_id = $gid RETURN count(a)` |
| error_handling_policy | extractor-specific | TBD from extractor source |
| crypto_domain_model | extractor-specific | TBD from extractor source |
| dead_symbol_binary_surface | extractor-specific | TBD from extractor source |
| public_api_surface | `:PublicApiSymbol` | `MATCH (p:PublicApiSymbol) WHERE p.group_id = $gid RETURN count(p)` |
| cross_module_contract | extractor-specific | TBD from extractor source |
| testability_di | extractor-specific | TBD from extractor source |
| codebase_memory_bridge | extractor-specific | TBD from extractor source |

For extractors marked TBD: read the extractor source to determine the correct node labels and write the query. Document in the matrix.

**Acceptance criteria:**
- [ ] All 24 extractors have a canonical Cypher query documented.
- [ ] For each extractor × project: count of domain nodes/edges recorded.
- [ ] Zero-count on reference projects classified as VALID_EMPTY (with reasoning: e.g. no profile artifacts → hot_path_profiler=0 is valid) or BROKEN.
- [ ] Results in Stage 2 column of the matrix.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md`

---

## Step 3 — MCP read-tool surfacing verification (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** Step 2 (need to know which extractors have data)

**Description:**  
For each extractor that wrote domain nodes (non-zero in Step 2), verify that the corresponding MCP read tool surfaces the data correctly:

- `symbol_index_*` → `palace.code.find_references(qualified_name=..., project=...)`
- `code_ownership` → `palace.code.find_owners(file_path=..., project=...)`
- `hotspot` → `palace.code.find_hotspots(project=...)`
- `cross_repo_version_skew` → `palace.code.find_version_skew(...)`
- `dependency_surface` → `palace.memory.lookup(entity_type="ExternalDependency", ...)`
- Others: use `palace.memory.lookup` with appropriate entity_type.

Verify: MCP tool returns rows when Cypher shows data exists. If MCP returns 0 but Cypher shows >0: BROKEN (scoping bug or shadow-table).

**Acceptance criteria:**
- [ ] MCP tool call + output captured for each extractor with data.
- [ ] Any Cypher↔MCP discrepancy documented with exact queries and results.
- [ ] Results in Stage 3 column.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md`

---

## Step 4 — Audit report consumption verification (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** Step 2

**Description:**  
Run `palace.audit.run` on `gimle` and `uw-ios-mini`. For each extractor section in the audit report, verify:
- If data exists (Step 2 count > 0) → audit section must show real findings, not "No findings" / "0 issues".
- If data doesn't exist (valid empty) → "No findings" is acceptable.

Any extractor where data exists but audit shows "No findings" = BROKEN audit integration.

**Acceptance criteria:**
- [ ] `palace.audit.run` output captured for both reference projects.
- [ ] Per-extractor audit section cross-referenced with Step 2 counts.
- [ ] Discrepancies documented in Stage 4 column.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md`

---

## Step 5 — Health-grouping verification + watchdog token check (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** Step 1

**Description:**  
1. Call `palace.memory.health()` and verify which extractor runs are visible.
2. Document the known limitation (only paperclip runs surfaced) or note if this has been fixed.
3. For watchdog token-validity: check the current watchdog code for token validation. If no pre-flight 401 check exists, file a child issue with:
   - Reproducer (revoke token → observe silent failure)
   - Proposed fix (pre-flight health check on token before entering main loop)
   - Operator playbook for token rotation

**Acceptance criteria:**
- [ ] `palace.memory.health()` output captured and Stage 5 column filled.
- [ ] Known limitation status documented (still present vs fixed).
- [ ] Watchdog token-validity gap either fixed inline (if trivial) or filed as child issue with playbook.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md`

---

## Step 6 — Compile matrix + file child issues (MCPEngineer)

**Owner:** MCPEngineer  
**Status:** TODO  
**Depends on:** Steps 1–5

**Description:**  
1. Compile final coverage matrix: 24 extractors × 5 stages × {OK, BROKEN, NOT_APPLICABLE, VALID_EMPTY}.
2. For each BROKEN cell: create a child issue under GIM-332 with:
   - Extractor name + stage that failed
   - Reproducer (exact Cypher/MCP call that demonstrates the bug)
   - Expected vs actual output
3. Ensure the 4 known-suspicious extractors from GIM-307 are explicitly classified with reasoning.

**Acceptance criteria:**
- [ ] Matrix complete — no blank cells.
- [ ] Every BROKEN cell has a corresponding child issue.
- [ ] 4 GIM-307 suspicious extractors explicitly addressed.
- [ ] Commit the final runbook file.

**Affected files:**
- `docs/runbooks/extractor-integrity-audit-2026-05-17.md`

---

## Step 7 — Code Review (CodeReviewer)

**Owner:** CodeReviewer  
**Status:** TODO  
**Depends on:** Step 6

**Description:**  
Phase 3.1 mechanical review. Verify:
- Matrix is complete and evidence is inline (not just "OK" without proof).
- Child issues have reproducers.
- Runbook is well-structured and useful for future audits.

**Acceptance criteria:**
- [ ] `APPROVE` with evidence that all AC are met.

---

## Step 8 — Adversarial Review (OpusArchitectReviewer)

**Owner:** OpusArchitectReviewer  
**Status:** TODO  
**Depends on:** Step 7

**Description:**  
Phase 3.2. Challenge:
- Are VALID_EMPTY classifications well-reasoned? Could any be bugs masked as valid empties?
- Is the matrix methodology reproducible for future audits?
- Are child issue reproducers sufficient for an engineer to fix without re-investigation?

**Acceptance criteria:**
- [ ] `APPROVE` or findings addressed.

---

## Step 9 — QA Live Smoke (QAEngineer)

**Owner:** QAEngineer  
**Status:** TODO  
**Depends on:** Step 8

**Description:**  
Phase 4.1 on iMac. Verify:
1. Re-run `palace.audit.run` on reference project → output matches matrix.
2. Spot-check 3–5 BROKEN items: confirm the reproducer actually reproduces.
3. Spot-check 3–5 OK items: confirm data is actually present.

**Acceptance criteria:**
- [ ] Evidence comment with SHA + audit output + spot-check results.

---

## Step 10 — Merge (CTO)

**Owner:** CTO  
**Status:** TODO  
**Depends on:** Step 9

**Description:**  
Phase 4.2. Squash-merge to develop after CI green + QA evidence + CR + Opus approval.

**Acceptance criteria:**
- [ ] PR merged, CI green on merge commit.
- [ ] Child issues visible and assigned.
