# Audit-V1 S1 — Audit Orchestration — Specification

**Document date:** 2026-05-07
**Status:** Draft · S0 merged (`0a02ade` on develop, 2026-05-07)
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Claude
**Slice ID:** S1 (Audit-V1 sprint sequence, rev3) — sub-divides into S1.1 .. S1.10
**Companion plan:** `2026-05-07-audit-v1-s1-orchestration_plan.md`
**Source sprint file:** `docs/superpowers/sprints/D-audit-orchestration.md` §S1 (rev2)
**Branch:** `feature/GIM-233-audit-v1-s1-orchestration` cut from develop (S0 merged `0a02ade`)

---

## 0. Blocker note (per operator's "не придумывать" rule)

S1 has **hard prerequisites in S0** that have not yet merged:

- **Blocked-on-S0.1**: S1.4 (Extractor discovery via `:IngestRun`) reads
  the unified `extractor_name`/`project` schema. Until S0.1 lands, the
  discovery Cypher cannot be written against a stable contract.
- **Blocked-on-S0.2** (REVISED in rev4): S1.5 (Generic fetcher) does
  **NOT** depend on S0.2. The fetcher uses **direct Cypher** via
  `audit_contract().query` (per spec §3.5 code sample below). The
  composite MCP tools from S0.2 are an **agent-facing** surface for
  ad-hoc queries during S1.9 workflows; the in-process fetcher
  bypasses MCP entirely and reads Cypher directly via the Neo4j
  driver. Therefore S1.5 has no S0.2 dependency. **S1.9** (workflow
  launcher) DOES depend on S0.2 — domain agents call the composite
  tools when posting sub-reports.
- **Blocked-on-S0.3**: S1.7 (Auditor role) and S1.9 (workflow launcher)
  hand work to 3 reused agents whose audit-mode prompts S0.3 authors.
  Until S0.3 lands, the workflow can be drafted but smoke-tested only
  against placeholder agent prompts.

**This spec captures S1 design at the level achievable WITHOUT S0
merged**, namely:
- High-level shape of S1.1 .. S1.10 (covered in §3 below).
- Module boundaries / file paths.
- Public API of `palace.audit.run` (the synchronous tool).
- Workflow shape of `audit-workflow-launcher.sh`.

**S1 details that depend on S0 outputs are explicitly marked
`<<DEPENDS ON S0.x>>` in the plan companion** rather than guessed.
After S0 merges, this spec can be refined to rev2 with concrete
schema citations; until then those parts are best-effort sketches.

---

## 1. Goal

Ship the audit pipeline framework — workflow + agent roles + report
format + composite MCP tool — into which any extractor's data plugs
in via `audit_contract()` without orchestration-layer code changes.

**Definition of Done (S1, post-merge of S0):**

1. New role file `paperclips/roles/auditor.md` (and CX mirror) deployed.
2. Audit-mode prompt sections appended to 3 reused role files
   (already done in S0.3; S1 only consumes them).
3. New synchronous MCP composite tool `palace.audit.run` registered.
4. Async workflow launcher `paperclips/scripts/audit-workflow-launcher.sh`
   with Paperclip child-issue dispatch.
5. Markdown report template at
   `services/palace-mcp/src/palace_mcp/audit/report_template.md`.
6. Per-extractor section templates at
   `services/palace-mcp/src/palace_mcp/audit/templates/<name>.md`
   for the 7 extractors enumerated in S1.6.
7. End-to-end synthetic-fixture smoke test (S1.10).
8. Operator runbook `docs/runbooks/audit-orchestration.md`.

## 2. Why now / why this scope

Audit-V1's product surface is two commands:
- `palace.audit.run(project=<slug>)` — synchronous, returns a markdown
  report directly.
- `bash audit-workflow-launcher.sh <slug>` — async multi-agent run via
  Paperclip child issues; final report posted to parent.

S1 builds both. It is the largest sprint in the rev3 critical path
(3-4 weeks, single Claude PE) and dominates the calendar between S0
finish and S2.1 start.

S1's design is shaped by 3 reviewer findings on rev1:
- **CTO-CRITICAL-1 / OPUS-CRITICAL-2**: replace 7 hard-coded
  `fetch_X()` functions with one generic fetcher dispatching on
  `BaseExtractor.audit_contract()`.
- **CTO-CRITICAL-2**: split the synchronous MCP tool from the async
  agent workflow — they have different latency contracts and failure
  modes.
- **OPUS-HIGH-1**: use Paperclip child issues for parallel agent
  dispatch instead of a custom serial harness.

## 3. Scope — sub-slices S1.1 .. S1.10

Compact catalogue. Detailed steps live in the plan companion. Each
sub-slice is a separate commit on the S1 branch (or its own paperclip
issue if operator splits S1 into multiple chains for parallelism).

### 3.1 S1.1 — Audit deliverable specification (~1h)

Defines contracts every later slice references:
- Section list of the markdown report (10 sections; see
  `audit-v1-overview.md` §1).
- Severity rank: `critical | high | medium | low | informational`.
- Per-extractor severity mapping table.
- Per-section length budget.
- Token budget per agent (per AV1-D6: 50K in / 10K out default).
- Empty-section rendering: `"No findings — extractor X ran at <run_id>
  on <head_sha>, scanned N files, found 0 issues."`
- Blind-spot disclosure rules.
- Provenance trailer format.
- `BaseExtractor.audit_contract()` schema (rev2 from
  `audit-v1-overview.md`).
- `:IngestRun` schema contract (consumes S0.1 unification).

### 3.2 S1.2 — Per-extractor section templates (~2-3h)

7 Jinja2 templates under
`services/palace-mcp/src/palace_mcp/audit/templates/`:
- `hotspot.md`, `dead_symbol_binary_surface.md`,
  `dependency_surface.md`, `code_ownership.md`,
  `cross_repo_version_skew.md`, `public_api_surface.md`,
  `cross_module_contract.md`.

Each receives `findings`, `summary_stats`, `provenance_run_id`,
`provenance_completed_at` per S1.1 contract. Templates are
data-driven; severity sort done before rendering.

### 3.3 S1.3 — Renderer + `audit_contract()` base class (~3-4h)

- `services/palace-mcp/src/palace_mcp/audit/__init__.py`,
  `audit/renderer.py`, `audit/report_template.md`.
- `services/palace-mcp/src/palace_mcp/extractors/base.py` —
  add `audit_contract() → AuditContract | None`.

Renderer pipeline:
1. Read top-level `report_template.md`.
2. For each extractor with non-None `audit_contract()`, load
   `audit_contract().template_path`, render with fetched data.
3. Severity sort: in-section findings sorted critical → low; sections
   ordered by max-severity first.

Tests: golden-file match against hand-crafted extractor output dicts.

### 3.4 S1.4 — Discovery via `:IngestRun` (~1-2h, ‖ S1.3)

`audit/discovery.py`. Cypher queries `:IngestRun` for the latest
successful run per `extractor_name` for a given `project` (or
`bundle`). After S0.1 lands, discovery uses unified schema directly.

`<<DEPENDS ON S0.1 — schema contract>>`

### 3.5 S1.5 — Generic fetcher (~2-3h)

`audit/fetcher.py`. Single generic fetcher (not 7 hardcoded
`fetch_X`):

```python
async def fetch_audit_data(driver, discovery_result, extractor_registry):
    results = {}
    for name, run_info in discovery_result.items():
        ext = extractor_registry.get(name)
        if not ext or not ext.audit_contract():
            continue
        contract = ext.audit_contract()
        raw = await driver.execute_query(contract.query, project=run_info.project)
        parsed = contract.response_model.model_validate(raw)
        results[name] = AuditSectionData(...)
    return results
```

**(rev4 correction)**: Fetcher uses **direct Cypher** through
`audit_contract().query` — NOT MCP composite tools. Composite tools
serve agent-facing ad-hoc queries during S1.9; the in-process fetcher
goes directly via the Neo4j driver to avoid serialisation overhead.

`<<NO S0.2 dependency>>` — S0.2 dependency moves to S1.9 (workflow
launcher), where domain agents query MCP composites.

### 3.6 S1.6 — Implement `audit_contract()` × 7 (~4-6h)

For each of 7 extractors, implement `audit_contract()` returning
query, response model, template path. **(rev4 correction)**: each
extractor's `audit_contract().query` cites the **extractor's own
Cypher source** (e.g., for hotspot, the existing query in
`extractors/hotspot/extractor.py`), NOT S0.2 composite tools. S0.2
composite tools wrap the **same** underlying Cypher for MCP-client
consumption; `audit_contract()` is for in-process fetcher consumption
and uses raw Cypher.

**Rev4 PE-freed boundary correction**: The S1.6 commit does NOT free
PE to start S2.1 — S1.7 / S1.8 / S1.9 / S1.10 are still PE-bound
(S1.7 is markdown-only and could be picked up by Board, but S1.8 /
S1.9 / S1.10 require Python work). Realistic timeline: PE finishes
S1.10 → then S2.1 starts. Net effect: critical path = +1w on rev3
estimate (17-18w → 18-19w), pushing into the 18w envelope's tail
margin.

### 3.7 S1.7 — Auditor agent role file (~1-2h)

- `paperclips/roles/auditor.md` (new) + CX mirror
  `paperclips/roles-codex/auditor.md` (per
  `feedback_slim_both_claude_codex.md`).
- Agent: receives project/bundle + fetcher output → returns
  per-domain markdown sub-reports.
- Hard rule: NO inventing findings beyond fetcher data.

### 3.8 S1.8 — `palace.audit.run` synchronous MCP tool (~2-4h)

- `services/palace-mcp/src/palace_mcp/audit/run.py`.
- Register on FastMCP server.
- Validates args (`project` XOR `bundle`, slug regex,
  `depth ∈ {quick, full}`).
- Calls discovery → fetcher → renderer.
- Returns:
  ```json
  {
    "ok": true,
    "report_markdown": "# Audit report — tronkit-swift\n...",
    "fetched_extractors": [...],
    "blind_spots": [...],
    "provenance": {...}
  }
  ```

### 3.9 S1.9 — Async workflow launcher + child-issue dispatch (~3-4h)

- `services/palace-mcp/src/palace_mcp/cli.py` — one-shot CLI
  wrapping streamable-HTTP MCP.
- `paperclips/scripts/audit-workflow-launcher.sh`.
- `docs/runbooks/audit-orchestration.md`.

Workflow: parent issue + 3 child issues
(`audit-arch`, `audit-sec`, `audit-crypto`) with `blockedByIssueIds`.
Domain agents post sub-reports → `issue_children_completed` wakes
Auditor → renders final report.

`<<DEPENDS ON S0.2 — 3 composite tools for agent ad-hoc queries
(rev4 — moved here from S1.5)>>`
`<<DEPENDS ON S0.3 — audit-mode prompts>>` (workflow can be drafted
without; smoke test §3.10 must wait for S0.3 to test agent output
quality).

### 3.10 S1.10 — End-to-end smoke harness (~2-3h)

- `services/palace-mcp/tests/audit/smoke/test_audit_e2e.sh`.
- `services/palace-mcp/tests/audit/fixtures/audit-mini-project/`.

Synthetic fixture creates 7 successful `:IngestRun` records (unified
schema) + output nodes. Asserts:
- Golden-file match for produced markdown.
- Paved-path regression: adding a fixture extractor entry produces
  a new section without orchestrator code changes (Opus-MEDIUM-3
  prevention).

## 4. Files in scope (consolidated)

| Path | Action | Sub-slice |
|---|---|---|
| `services/palace-mcp/src/palace_mcp/audit/__init__.py` | new | S1.3 |
| `services/palace-mcp/src/palace_mcp/audit/renderer.py` | new | S1.3 |
| `services/palace-mcp/src/palace_mcp/audit/report_template.md` | new | S1.3 |
| `services/palace-mcp/src/palace_mcp/audit/discovery.py` | new | S1.4 |
| `services/palace-mcp/src/palace_mcp/audit/fetcher.py` | new | S1.5 |
| `services/palace-mcp/src/palace_mcp/audit/run.py` | new | S1.8 |
| `services/palace-mcp/src/palace_mcp/audit/templates/<7 names>.md` | new | S1.2 |
| `services/palace-mcp/src/palace_mcp/extractors/base.py` | extend | S1.3 |
| `services/palace-mcp/src/palace_mcp/extractors/<7 names>.py` | extend (`audit_contract()`) | S1.6 |
| `services/palace-mcp/src/palace_mcp/cli.py` | new | S1.9 |
| `services/palace-mcp/src/palace_mcp/mcp_server.py` | register tool | S1.8 |
| `paperclips/roles/auditor.md` | new | S1.7 |
| `paperclips/roles-codex/auditor.md` | new (mirror) | S1.7 |
| `paperclips/scripts/audit-workflow-launcher.sh` | new | S1.9 |
| `docs/runbooks/audit-orchestration.md` | new | S1.9 |
| `services/palace-mcp/tests/audit/**/*` | new | S1.{2..10} |

## 5. Decision points

| ID | Question | Default | Impact of non-default |
|----|----------|---------|----------------------|
| S1-D1 | Single PR carrying all 10 sub-slices, or 1 PR per sub-slice (10 PRs)? | single PR (matches rev2 sprint shape) | 10 PRs = max parallelism but huge review burden |
| S1-D2 | `palace.audit.run` returns markdown body inline OR writes to file + returns path? | inline body (operator quoted as primary consumer) | file-based reduces MCP response size for huge audits |
| S1-D3 | `audit-workflow-launcher.sh` = bash script or Python CLI subcommand? | bash script (matches existing `imac-deploy.sh` pattern) | Python = more portable but adds CLI surface |
| S1-D4 | Auditor agent operates on JSON or pre-rendered markdown? | JSON (lets renderer truncate; agent doesn't re-format) | markdown = simpler agent prompt, harder size control |
| S1-D5 | Smoke fixture in repo or tests/extractors/fixtures/? | `tests/audit/fixtures/audit-mini-project/` (separate from extractor fixtures) | sharing extractor fixtures couples test data |

## 6. Test plan summary

- **Unit (S1.3 renderer)**: golden-file match against hand-crafted
  extractor output dicts. 1 test per extractor's empty case + 1
  test per non-empty case.
- **Unit (S1.4 discovery)**: synthetic graph + assertion on returned
  extractor list.
- **Integration (S1.5 fetcher)**: synthetic graph + audit_contract()
  on 7 extractors → assert response models valid.
- **E2E (S1.10)**: smoke fixture → `palace.audit.run()` → golden-file
  markdown match. Paved-path regression test: drop a new fixture
  extractor entry → new section appears without code changes.

## 7. Risks (carried from sprint file §"Risks rev2")

- **R1**: `audit_contract()` queries drift from extractor output —
  mitigate by S1.10 smoke + CI gate.
- **R2**: Auditor agent invents findings — mitigate by role prompt
  hard rule + integration test tracing claims to fetcher rows.
- **R3**: Report bloat (>500 words executive summary) — mitigate by
  per-section budget enforced in renderer.
- **R4**: Paved-path regression — mitigate by S1.10 paved-path gate.
- **R5**: Child-issue workflow complexity — mitigate by S1.9
  runbook + S1.10 happy-path coverage.

## 8. Out of scope (deferred to S6+)

- Cron / on-merge audit trigger.
- JSON / Cypher snapshot export of report.
- LLM-bearing agent roles inside the audit pipeline (current 3
  reused agents don't ingest training data — strictly fetcher
  data).
- Per-domain split into Quality / Dependency / Historical agents.
- AuditSynthesizer agent (removed in rev2 — Python renderer
  is sufficient).

## 9. Cross-references

- Sprint file: `docs/superpowers/sprints/D-audit-orchestration.md` §S1
- Audit-V1 overview: `docs/superpowers/sprints/audit-v1-overview.md`
- Roadmap row: `docs/roadmap.md` §"Audit-V1" S1 row
- Predecessor: S0 (`2026-05-07-audit-v1-s0-foundation-prereqs_spec.md`)
- Successors: S2.1 (`B-audit-extractors.md` §S2.1), S2.2/S2.3 (rev3)
- Companion: `2026-05-07-audit-v1-s1-orchestration_plan.md`
