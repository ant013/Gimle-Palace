# Sprint S1 (D) — Audit Orchestration

**Goal**: ship the audit pipeline framework — workflow, agent roles,
report format, composite MCP tool — into which any extractor's data
plugs in without code changes to the orchestration layer.

**Wall-time**: ~3 weeks calendar (≈8-10 paperclip slices, mostly
sequential because each refines the contract for the next).

**Driver**: `palace.audit.run(project="tronkit-swift")` returns a
structured markdown audit report.

**Definition of Done**:
1. New role files for `Auditor` + `AuditSynthesizer` agents deployed.
2. New MCP composite tool `palace.audit.run` registered in server.
3. Markdown report template at `services/palace-mcp/src/palace_mcp/audit/report_template.md`.
4. Per-extractor section templates at
   `services/palace-mcp/src/palace_mcp/extractors/*/audit_section_template.md`
   for: `hotspot`, `dead_symbol_binary_surface`, `dependency_surface`,
   `code_ownership` (post-GIM-216), `cross_repo_version_skew`
   (post-GIM-218), `public_api_surface`, `cross_module_contract`.
   `git_history` and `symbol_index_*` produce no audit section
   directly (they feed others).
5. End-to-end synthetic test: seed graph with known fixture data,
   run orchestrator, assert report contains expected per-extractor
   sections in correct order with severity-graded findings.
6. Workflow doc: `docs/runbooks/audit-orchestration.md`.

**NOT in this sprint** (deferred to S6+):
- Cron / on-merge trigger.
- JSON / Cypher snapshot export.
- LLM-bearing agent roles.
- Per-domain split into Quality / Dependency / Historical agents.

---

## Slices (small, ≤30min each for impl by paperclip team)

### S1.1 — Audit deliverable spec

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-audit-deliverable-format.md`
**Plan file**: `docs/superpowers/plans/<date>-GIM-NN-audit-deliverable-format.md`

**Scope**: define the markdown structure of the audit report.

What the spec answers:
- Section list (overview from `audit-v1-overview.md` §1).
- Severity rank: `critical | high | medium | low | informational`.
  Per-extractor mapping documented (e.g., `hotspot.score >= 0.8` =
  high; `cross_repo_version_skew.severity = 'major'` = high).
- Per-section length budget (Executive ≤500 words; per-domain
  ≤2000 words).
- Empty-section behaviour: when an extractor has no findings,
  section reads "No findings — extractor X ran at <run_id> on
  <head_sha>, scanned N files, found 0 issues."
- Blind-spot disclosure: explicit list of extractors NOT yet merged
  with rationale.
- Provenance trailer format.

**Why first**: every subsequent slice references this spec for
section templates.

---

### S1.2 — Per-extractor section template files

**Files** (one per extractor):
- `services/palace-mcp/src/palace_mcp/extractors/hotspot/audit_section_template.md`
- `.../dead_symbol_binary_surface/audit_section_template.md`
- `.../dependency_surface/audit_section_template.md`
- `.../code_ownership/audit_section_template.md` (created in GIM-216 slice)
- `.../cross_repo_version_skew/audit_section_template.md` (created in GIM-218 slice)
- `.../public_api_surface/audit_section_template.md`
- `.../cross_module_contract/audit_section_template.md`

**Format**: Jinja-like template (or plain Python f-string) with
slots for: `top_n_findings`, `summary_stats`, `provenance_run_id`,
`provenance_completed_at`. Each ships with its OWN extractor PR —
adding a future extractor is "drop a new template file" + register
in the synthesizer's discovery loop.

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-audit-section-templates.md`

**Scope**: define the template contract (what variables synthesizer
provides, what each extractor must emit). All 7 templates above are
authored in this slice.

**Out of scope**: rendering logic (S1.3); discovery from `:IngestRun`
(S1.4).

---

### S1.3 — Markdown rendering engine

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/__init__.py`
- `services/palace-mcp/src/palace_mcp/audit/renderer.py`
- `services/palace-mcp/src/palace_mcp/audit/report_template.md`
- `tests/audit/unit/test_audit_renderer.py`

**Scope**: pure-function renderer. Inputs: extractor outputs (already
fetched). Output: complete markdown string.

- Reads top-level template (`report_template.md`) which has slots
  for executive, per-section, blind-spots, provenance.
- For each known extractor name, looks up `extractors/<name>/audit_section_template.md`,
  renders with that extractor's data.
- Severity sort: in-section findings sorted critical → low; sections
  ordered by max severity first (critical-bearing sections precede
  low-only).

**Test fixtures**: hand-crafted extractor output dicts; assert
markdown matches golden file.

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-audit-renderer.md`
**Plan file**: matching `plans/`.

---

### S1.4 — Extractor discovery via `:IngestRun`

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/discovery.py`
- `tests/audit/integration/test_audit_discovery.py`

**Scope**: query `:IngestRun` for the latest successful run per
`extractor_name` for a given `project`/`bundle`. Return a dict
`{extractor_name: {run_id, completed_at, exit_reason, ...extras}}`.

This is the load-bearing piece that makes the post-v1 paved path
work — adding a new extractor with `extractor_name='X'` automatically
shows up in `discovery()` output without any orchestrator change.

**Cypher**:
```cypher
MATCH (r:IngestRun {project: $project, success: true})
WITH r.extractor_name AS name, r
ORDER BY r.completed_at DESC
WITH name, head(collect(r)) AS latest
RETURN name, latest.run_id AS run_id,
       latest.completed_at AS completed_at,
       latest // for properties
```

**Out of scope**: per-extractor data fetch (S1.5).

---

### S1.5 — Per-extractor data fetchers

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/fetchers.py`
- `tests/audit/integration/test_audit_fetchers.py`

**Scope**: for each known extractor, a function that fetches its
audit-relevant data given `(project, bundle, run_id)`. Examples:

- `fetch_hotspot(driver, project, top_n) → list[HotspotFinding]`
  uses `palace.code.find_hotspots` underneath.
- `fetch_ownership(driver, project, top_n) → list[OwnerSummary]`
  uses `palace.code.find_owners` per high-hotspot file.
- `fetch_version_skew(driver, project_or_bundle, min_severity) → list[SkewGroup]`
  uses `palace.code.find_version_skew`.
- `fetch_dead_symbols(driver, project) → list[DeadSymbol]`
- `fetch_public_api(driver, project) → PublicApiSummary`
- `fetch_cross_module(driver, project) → list[ContractDiff]`
- `fetch_crypto_domain(driver, project) → list[CryptoFinding]` —
  added in S2 once #40 lands.

Each fetcher has an `extractor_name` constant tying it to discovery.

**Out of scope**: agent-level synthesis (S1.6); composite MCP tool
(S1.8).

---

### S1.6 — Auditor agent role file

**Files**:
- `paperclips/roles/auditor.md`
- `paperclips/roles-codex/auditor.md` (CX-side parity)
- `paperclips/dist/codex/auditor.md` (compiled)
- `paperclips/scripts/deploy-agents.sh` — add `auditor` to AGENT_NAMES

**Scope**: role prompt for a multi-domain auditor. The agent:
- Receives a project/bundle + a fetcher-output bundle.
- Returns per-domain markdown sub-reports (Quality / Dependencies /
  Ownership).
- Does NOT make subjective judgment beyond what extractors already
  say (severity comes from extractor; agent describes WHY a finding
  is high-severity in plain language).
- Hard rule: NO inventing findings — only re-narrate what fetchers
  returned.

**UUID**: assigned at deploy. Update `reference_agent_ids.md` memory.

---

### S1.7 — AuditSynthesizer agent role file

**Files**:
- `paperclips/roles/audit-synthesizer.md`
- `paperclips/roles-codex/audit-synthesizer.md`
- `paperclips/dist/codex/audit-synthesizer.md`
- `paperclips/scripts/deploy-agents.sh` — add to AGENT_NAMES

**Scope**: role prompt for the final-report-assembler. The agent:
- Receives sub-reports from Auditor + OpusArchitectReviewer +
  SecurityAuditor + BlockchainEngineer.
- Calls `audit/renderer.py` (via composite tool wrapper) to produce
  the final markdown.
- Returns ONE deliverable: the markdown blob.

The synthesizer is intentionally thin — most logic lives in the
Python renderer. The agent role exists so the workflow remains a
paperclip-team pattern (handoff-able, auditable in `:IngestRun`)
rather than a hidden Python call.

---

### S1.8 — `palace.audit.run` composite MCP tool

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/run.py`
- `services/palace-mcp/src/palace_mcp/server.py` — register tool
- `tests/audit/integration/test_audit_run_e2e.py`

**Scope**: composite tool that:
1. Validates args (`project` XOR `bundle`, regex on slugs, `depth` ∈ {`quick`, `full`}).
2. Calls `audit/discovery.py` for available extractors.
3. Calls `audit/fetchers.py` for each.
4. Returns the raw fetched data + computed report.

**Args**:
- `project: str | None`
- `bundle: str | None`
- `depth: str = "full"` — `quick` skips deep cross-Kit analysis;
  `full` enables it for bundle mode.

**Returns**:
```json
{
  "ok": true,
  "report_markdown": "# Audit report — tronkit-swift\n...",
  "fetched_extractors": ["hotspot", "dead_symbol_binary_surface", ...],
  "blind_spots": ["crypto_domain_model: NOT MERGED", "code_smell: BLIND"],
  "provenance": {...},
  "agent_subreports": {
    "Auditor": "...",
    "OpusArchitectReviewer": "...",
    "SecurityAuditor": "...",
    "BlockchainEngineer": "..."
  }
}
```

`agent_subreports` are populated when the tool is invoked from a
paperclip workflow that pre-collected them. Direct CLI/MCP-client
invocation can pass `--skip-agents` and get a synthesizer-only output
(useful for smoke testing, raw data review).

**Out of scope**: triggering the paperclip workflow itself (S1.9).

---

### S1.9 — Workflow trigger + paperclip handoff sequence

**Files**:
- `paperclips/scripts/audit-workflow-launcher.sh`
- `docs/runbooks/audit-orchestration.md`

**Scope**: define the manual-trigger sequence:

1. Operator runs `bash paperclips/scripts/audit-workflow-launcher.sh tronkit-swift`.
2. Script creates a paperclip issue: title
   `audit: <slug>`, assigned to `Auditor` (NEW agent UUID).
3. Auditor wakes, calls `palace.audit.run(project=<slug>, --skip-agents)` to
   get raw data, writes its sub-report, hands off to
   `OpusArchitectReviewer` + `SecurityAuditor` + `BlockchainEngineer`
   in parallel (4-agent dispatch).
4. Each of the 3 reviewers reads raw data via direct MCP queries +
   writes their sub-report into the issue thread as a comment.
5. After all 3 done, Auditor (or `audit-workflow-launcher.sh` polling)
   detects readiness and reassigns to `AuditSynthesizer`.
6. Synthesizer combines all sub-reports + raw data into the final
   markdown via `palace.audit.run(--render-only)`. Posts as final
   comment + closes issue.

**Out of scope**: cron triggers, on-merge CI, multi-tenant ACL
(deferred per AV1-D3, AV1-D4, broader trust-model slice).

---

### S1.10 — End-to-end smoke harness

**Files**:
- `services/palace-mcp/tests/audit/smoke/test_audit_e2e.sh`
- `services/palace-mcp/tests/audit/fixtures/audit-mini-project/` — synthetic
  graph with all 7 extractor outputs pre-seeded.

**Scope**: verify the full pipeline against a synthetic fixture
without requiring real extractors to have run. Catches integration
breaks early.

The fixture is hand-crafted Cypher that creates 7 successful
`:IngestRun` records + per-extractor output nodes/edges. Smoke runs
`palace.audit.run` against it, asserts the rendered markdown
matches a golden file.

This is also the regression gate for "post-v1 paved path": when
adding extractor X in S6+, the developer adds a new fixture entry,
re-runs smoke, sees the new section appear in the golden file.

---

## Slice ordering rationale

| Slice | Why this position |
|-------|--------------------|
| 1.1 deliverable spec | defines contracts for all later slices |
| 1.2 templates | needed before renderer (1.3) can be tested |
| 1.3 renderer | pure function, testable in isolation, blocks 1.5/1.8 |
| 1.4 discovery | low-risk Cypher slice; can run parallel with 1.3 |
| 1.5 fetchers | needs discovery (1.4) and renderer (1.3) for tests |
| 1.6 Auditor role | independent of Python work; can run early |
| 1.7 Synthesizer role | similar |
| 1.8 composite tool | needs fetchers (1.5) ready |
| 1.9 workflow | needs roles (1.6, 1.7) deployed |
| 1.10 smoke | last — verifies end-to-end |

Parallelisation hint: 1.1 → (1.2, 1.4, 1.6, 1.7) all parallel →
1.3 → 1.5 → 1.8 → 1.9 → 1.10.

## Decision points to resolve in S1.1 brainstorm

- AV1-D1 (markdown only?) — confirm.
- AV1-D2 (agent set) — confirm or split Auditor.
- AV1-D3 (manual trigger only?) — confirm.
- Severity rank scheme: 5-level vs 3-level. Default 5.
- Empty-section verbosity: full disclosure vs hide-empty. Default
  full.
- Per-extractor template ownership: who edits when extractor X
  changes its output schema? Default: extractor's own slice owner.

## Risks

| Risk | Mitigation |
|------|------------|
| Per-extractor templates drift from extractor output schema | Smoke test (1.10) uses synthetic fixture matching real schema; CI fails if template's expected fields don't appear in fetcher output. |
| Auditor agent invents findings beyond what extractors report | Hard rule in role prompt + sub-report integration test that asserts every claim in agent output traces back to a fetcher row. |
| Synthesizer report bloat | 500-word executive cap + per-section length budget enforced by renderer. Truncation with "(N more findings — see full audit data)" trailer. |
| New extractor in S6+ breaks paved path | 1.10 smoke updated as part of every new extractor slice. Renderer is template-driven; no orchestrator code touches per-extractor specifics. |

## Cross-references

- Overview: `audit-v1-overview.md`
- Roadmap: `docs/roadmap.md` §"Audit-V1"
- B-min slice (parallel): `B-audit-extractors.md`
- C ingestion (parallel): `C-ingestion-automation.md`
- Smoke (after S1+S2+S3): `E-smoke.md`
