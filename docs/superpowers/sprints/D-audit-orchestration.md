# Sprint S1 (D) — Audit Orchestration

> **Rev2** (2026-05-06): addresses CTO-CRITICAL-1/2, OPUS-CRITICAL-1/2,
> OPUS-HIGH-1/2, CR-CRITICAL-3, CTO-HIGH-3/6, CTO-LOW-1, CR-MED-2.
> See `audit-v1-overview.md` rev2 changelog for full list.

**Goal**: ship the audit pipeline framework — workflow, agent roles,
report format, composite MCP tool — into which any extractor's data
plugs in without code changes to the orchestration layer.

**Wall-time**: ~4-5 weeks calendar (S0 prerequisite: ~1 week; S1 main:
~3-4 weeks at 2-3 slices/day with phase chains).

**Driver**: `palace.audit.run(project="tronkit-swift")` returns a
structured markdown audit report.

**Definition of Done**:
1. New role file for `Auditor` agent deployed.
2. Audit-mode prompt sections appended to `OpusArchitectReviewer`,
   `SecurityAuditor`, `BlockchainEngineer` role files.
3. New MCP composite tool `palace.audit.run` (synchronous data+render) registered.
4. Async workflow launcher `audit-workflow-launcher.sh` with child-issue dispatch.
5. Markdown report template at `services/palace-mcp/src/palace_mcp/audit/report_template.md`.
6. Per-extractor section templates at `services/palace-mcp/src/palace_mcp/audit/templates/<name>.md`
   for: `hotspot`, `dead_symbol_binary_surface`, `dependency_surface`,
   `code_ownership` (post-GIM-216), `cross_repo_version_skew`
   (post-GIM-218 or blind-spot stub), `public_api_surface`, `cross_module_contract`.
7. End-to-end synthetic test: seed graph with known fixture data,
   run tool, assert report contains expected per-extractor sections
   in correct order with severity-graded findings.
8. Workflow doc: `docs/runbooks/audit-orchestration.md`.

**NOT in this sprint** (deferred to S6+):
- Cron / on-merge trigger.
- JSON / Cypher snapshot export.
- LLM-bearing agent roles.
- Per-domain split into Quality / Dependency / Historical agents.
- AuditSynthesizer agent (removed in rev2 — Python renderer is sufficient).

---

## S0 — Foundation prerequisites (rev2 addition)

Three prerequisite slices that must land before S1 work starts.
These address the structural gaps identified by all 3 reviewers.

### S0.1 — Unify IngestRun schema (OPUS-CRITICAL-1)

**Problem**: Two competing `:IngestRun` creation paths with incompatible schemas:
- Path A (runner.py/cypher.py): `{id, source, group_id, ...}` — used by hotspot, dead_symbol, dependency_surface, etc.
- Path B (foundation/checkpoint.py): `{run_id, project, extractor_name, ...}` — used by symbol_index_*.

S1.4 discovery Cypher uses Path B fields (`extractor_name`, `project`) and would
miss all Path A IngestRun records.

**Scope**: Add `extractor_name` and `project` as canonical fields to Path A
IngestRun creation. Specifically:
- `extractors/cypher.py` — add `extractor_name = $extractor_name, project = $project` to CREATE.
- `extractors/runner.py` — pass `extractor_name` (derived from `source` field minus `extractor.` prefix) and `project` (derived from `group_id` minus `project/` prefix).
- Migration query for existing IngestRun nodes: `MATCH (r:IngestRun) WHERE r.extractor_name IS NULL SET r.extractor_name = ...`.
- Test: verify both paths produce `:IngestRun` nodes queryable by `extractor_name + project`.

**Size**: 2-4 hours (schema migration + tests).
**Branch**: `feature/GIM-NN-unify-ingest-run-schema`

### S0.2 — Create missing composite MCP tools (CR-CRITICAL-3)

**Problem**: S1 fetchers need `palace.code.find_*` composite tools.
Currently exist: `find_references`, `test_impact`, `find_hotspots` (3 of 8 needed).
Missing: `find_owners`, `find_version_skew`, `find_dead_symbols`,
`find_public_api`, `find_cross_module_contracts`.

**Scope**: Create 5 composite tools in `code_composite.py`, each wrapping
existing Cypher queries with Pydantic response models. Each tool is a
thin wrapper — the underlying extractors and graph data already exist.

**Size**: 4-6 hours (5 tools × ~1 hour each including tests).
**Branch**: `feature/GIM-NN-audit-composite-tools`
**Parallelisable**: can run alongside S0.1 (different files).

### S0.3 — Audit-mode prompt sections for 3 reused agents (OPUS-MEDIUM-2)

**Problem**: OpusArchitectReviewer, SecurityAuditor, BlockchainEngineer have
role prompts optimized for code review, not audit report generation. They
need to know: how to consume fetcher output, what constitutes a "finding",
how to grade severity from extractor metrics, sub-report output format.

**Scope**: Append `## Audit mode` section to each of the 3 role files:
- Input format: JSON blob from `palace.audit.run` fetcher output.
- Output format: markdown sub-report with severity-graded findings.
- Severity grading rules: map extractor scores → critical/high/medium/low.
- Hard rule: NO inventing findings beyond what fetcher data shows.

**Size**: 1-2 hours (3 role file additions + review).
**Branch**: `feature/GIM-NN-audit-mode-prompts`
**Parallelisable**: independent of S0.1 and S0.2.

---

## S1 Slices (honest sizing per rev2)

### S1.1 — Audit deliverable spec

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-audit-deliverable-format.md`
**Plan file**: `docs/superpowers/plans/<date>-GIM-NN-audit-deliverable-format.md`

**Scope**: define the markdown structure of the audit report.

What the spec answers:
- Section list (overview from `audit-v1-overview.md` §1).
- Severity rank: `critical | high | medium | low | informational`.
  Per-extractor mapping documented (e.g., `hotspot.score >= 0.8` =
  high; `cross_repo_version_skew.severity = 'major'` = high).
- Per-section length budget (Executive ≤500 words; per-domain ≤2000 words).
- Token budget per agent (AV1-D6): target 50K input / 10K output
  per domain agent; measured after S4 dry run.
- Empty-section behaviour: when an extractor has no findings,
  section reads "No findings — extractor X ran at <run_id> on
  <head_sha>, scanned N files, found 0 issues."
- Blind-spot disclosure: explicit list of extractors NOT yet merged.
- Provenance trailer format.
- `BaseExtractor.audit_contract()` schema definition (rev2).
- IngestRun schema contract: all extractors MUST write `:IngestRun`
  with `{run_id, extractor_name, project, success, completed_at}`.

**Size**: ~1 hour.
**Why first**: every subsequent slice references this spec.

---

### S1.2 — Per-extractor section template files (rev2: in `audit/templates/`)

**Files** (one per extractor, in `audit/templates/` — NOT inside extractor dirs):
- `services/palace-mcp/src/palace_mcp/audit/templates/hotspot.md`
- `.../templates/dead_symbol_binary_surface.md`
- `.../templates/dependency_surface.md`
- `.../templates/code_ownership.md`
- `.../templates/cross_repo_version_skew.md`
- `.../templates/public_api_surface.md`
- `.../templates/cross_module_contract.md`

**Rev2 change**: Templates live in `audit/templates/<name>.md`, not
`extractors/<name>/audit_section_template.md`. This avoids the flat-to-directory
extractor refactor (CTO-LOW-1, CR-MED-2). The `audit_contract()` method on each
extractor returns a `template_path` pointing here.

**Format**: Jinja2 template with standardized variable contract defined in S1.1.
Each template receives: `findings` (list), `summary_stats` (dict),
`provenance_run_id`, `provenance_completed_at`.

**Size**: ~2-3 hours (7 templates + template contract spec).

---

### S1.3 — Markdown rendering engine + `audit_contract()` base class

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/__init__.py`
- `services/palace-mcp/src/palace_mcp/audit/renderer.py`
- `services/palace-mcp/src/palace_mcp/audit/report_template.md`
- `services/palace-mcp/src/palace_mcp/extractors/base.py` — add `audit_contract()` method
- `tests/audit/unit/test_audit_renderer.py`

**Scope**: pure-function renderer + base class contract.

- `BaseExtractor.audit_contract() → AuditContract | None` (rev2).
- Renderer reads top-level template (`report_template.md`).
- For each extractor with non-None `audit_contract()`, loads
  `audit_contract().template_path`, renders with fetched data.
- Severity sort: in-section findings sorted critical → low; sections
  ordered by max severity first.

**Test fixtures**: hand-crafted extractor output dicts; assert markdown
matches golden file.

**Size**: ~3-4 hours (renderer + base class + tests).

---

### S1.4 — Extractor discovery via `:IngestRun` (rev2: unified schema)

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/discovery.py`
- `tests/audit/integration/test_audit_discovery.py`

**Scope**: query `:IngestRun` for the latest successful run per
`extractor_name` for a given `project`/`bundle`.

**Rev2 change**: After S0.1 unifies the schema, ALL IngestRun records have
`extractor_name` and `project` fields. Discovery Cypher:

```cypher
MATCH (r:IngestRun {project: $project, success: true})
WHERE r.extractor_name IS NOT NULL
WITH r.extractor_name AS name, r
ORDER BY r.completed_at DESC
WITH name, head(collect(r)) AS latest
RETURN name, latest.run_id AS run_id,
       latest.completed_at AS completed_at,
       latest
```

**IngestRun schema contract** (rev2, CR-MED-3): documented in S1.1 spec.

**Size**: ~1-2 hours.
**Can run parallel with S1.3.**

---

### S1.5 — Generic audit data fetcher via `audit_contract()` (rev2)

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/fetcher.py`
- `tests/audit/integration/test_audit_fetcher.py`

**Rev2 rewrite (CTO-CRITICAL-1, OPUS-CRITICAL-2)**: Single generic fetcher
instead of 7 hardcoded `fetch_X()` functions:

```python
async def fetch_audit_data(
    driver: AsyncDriver,
    discovery_result: dict[str, IngestRunInfo],
    extractor_registry: dict[str, BaseExtractor],
) -> dict[str, AuditSectionData]:
    results = {}
    for name, run_info in discovery_result.items():
        extractor = extractor_registry.get(name)
        if not extractor or not extractor.audit_contract():
            continue
        contract = extractor.audit_contract()
        raw = await driver.execute_query(contract.query, project=run_info.project)
        parsed = contract.response_model.model_validate(raw)
        results[name] = AuditSectionData(
            extractor_name=name, data=parsed,
            template_path=contract.template_path, provenance=run_info,
        )
    return results
```

**Prerequisite**: S0.1 + S0.2 + S1.3 (base class) + S1.4 (discovery).
**Size**: ~2-3 hours.

---

### S1.6 — Implement `audit_contract()` on 7 existing extractors

**Files**: 7 extractor `.py` files + 7 template files from S1.2.

**Scope**: For each of the 7 extractor classes that produce audit data, implement
`audit_contract()` returning query, response model, and template path.

| Extractor | Query source |
|-----------|-------------|
| `hotspot` | `palace.code.find_hotspots` Cypher (from S0.2) |
| `dead_symbol_binary_surface` | `find_dead_symbols` Cypher (from S0.2) |
| `dependency_surface` | existing Cypher in extractor |
| `public_api_surface` | `find_public_api` Cypher (from S0.2) |
| `cross_module_contract` | `find_cross_module_contracts` Cypher (from S0.2) |
| `code_ownership` | `find_owners` Cypher (from S0.2) — post-GIM-216 |
| `cross_repo_version_skew` | `find_version_skew` Cypher (from S0.2) — post-GIM-218 or stub |

**Size**: ~4-6 hours (7 implementations × ~45 min each with tests).

---

### S1.7 — Auditor agent role file (rev2: single new role, no Synthesizer)

**Files**:
- `paperclips/roles/auditor.md`
- `paperclips/roles-codex/auditor.md` (CX-side parity)
- `paperclips/dist/codex/auditor.md` (compiled)
- `paperclips/scripts/deploy-agents.sh` — add `auditor` to AGENT_NAMES

**Scope**: role prompt for a multi-domain auditor. The agent:
- Receives a project/bundle + `palace.audit.run` output.
- Returns per-domain markdown sub-reports (Quality / Dependencies / Ownership).
- Does NOT make subjective judgment beyond what extractors already say.
- Hard rule: NO inventing findings — only re-narrate fetcher data.

**Rev2**: No AuditSynthesizer role. Synthesis = Python function call.
**UUID**: assigned at deploy.
**Size**: ~1-2 hours.

---

### S1.8 — `palace.audit.run` synchronous MCP tool (rev2: no agent_subreports)

**Files**:
- `services/palace-mcp/src/palace_mcp/audit/run.py`
- `services/palace-mcp/src/palace_mcp/server.py` — register tool
- `tests/audit/integration/test_audit_run_e2e.py`

**Rev2 rewrite (CTO-CRITICAL-2)**: Synchronous data+render only.

1. Validates args (`project` XOR `bundle`, regex on slugs, `depth` ∈ {`quick`, `full`}).
2. Calls `audit/discovery.py` for available extractors.
3. Calls `audit/fetcher.py` generic fetcher for each.
4. Calls `audit/renderer.py` to produce markdown.
5. Returns report.

**Returns**:
```json
{
  "ok": true,
  "report_markdown": "# Audit report — tronkit-swift\n...",
  "fetched_extractors": ["hotspot", "dead_symbol_binary_surface", ...],
  "blind_spots": ["crypto_domain_model: NOT MERGED", "code_smell: BLIND"],
  "provenance": {...}
}
```

No `agent_subreports` — async workflow is separate (S1.9).
**Size**: ~2-4 hours.

---

### S1.9 — Async workflow launcher + child-issue dispatch (rev2: redesigned)

**Files**:
- `services/palace-mcp/src/palace_mcp/cli.py` — one-shot MCP CLI wrapper
- `paperclips/scripts/audit-workflow-launcher.sh`
- `docs/runbooks/audit-orchestration.md`

**Rev2 rewrite (OPUS-HIGH-1)**: Uses Paperclip child issues for parallel dispatch.

**Workflow**:
1. Operator: `bash audit-workflow-launcher.sh tronkit-swift`.
2. Script calls `python3 -m palace_mcp.cli audit.run --project=<slug>` to verify data exists.
3. Creates parent issue: `audit: <slug>`, assigned to `Auditor`.
4. Creates 3 child issues with `blockedByIssueIds`:
   - `audit-arch: <slug>` → `OpusArchitectReviewer`
   - `audit-sec: <slug>` → `SecurityAuditor`
   - `audit-crypto: <slug>` → `BlockchainEngineer`
5. Parent status `blocked`, `blockedByIssueIds` = [3 child IDs].
6. Each domain agent wakes, queries palace tools, posts sub-report, marks `done`.
7. `issue_children_completed` → Auditor wakes → collects sub-reports → renders final report.

**MCP invocation from bash** (CTO-HIGH-6, CR-HIGH-4): `palace_mcp.cli` module —
thin one-shot wrapper connecting to palace-mcp's streamable HTTP endpoint.

**Size**: ~3-4 hours (CLI wrapper ~2h + launcher script ~1h + runbook ~1h).

---

### S1.10 — End-to-end smoke harness

**Files**:
- `services/palace-mcp/tests/audit/smoke/test_audit_e2e.sh`
- `services/palace-mcp/tests/audit/fixtures/audit-mini-project/`

**Scope**: verify full pipeline against synthetic fixture.
Creates 7 successful `:IngestRun` records (unified schema) + output nodes.
Runs `palace.audit.run`, asserts golden-file match.

Also verifies paved-path regression: adding a fixture extractor entry
produces a new section without orchestrator changes.

**Size**: ~2-3 hours.

---

## Slice ordering (rev2)

| Slice | Size | Position rationale |
|-------|------|-------------------|
| S0.1 IngestRun unify | 2-4h | Prerequisite for all discovery |
| S0.2 Composite tools | 4-6h | Prerequisite for fetcher queries; ‖ S0.1 |
| S0.3 Audit-mode prompts | 1-2h | Independent; ‖ S0.1+S0.2 |
| S1.1 deliverable spec | ~1h | Defines contracts |
| S1.2 templates | 2-3h | Before renderer |
| S1.3 renderer + base | 3-4h | Pure function, testable alone |
| S1.4 discovery | 1-2h | Low-risk Cypher; ‖ S1.3 |
| S1.5 generic fetcher | 2-3h | Needs S1.3 + S1.4 |
| S1.6 audit_contract() × 7 | 4-6h | Needs S1.5 + S0.2 + S1.2 |
| S1.7 Auditor role | 1-2h | Independent of Python |
| S1.8 composite tool | 2-4h | Needs S1.5 + S1.6 |
| S1.9 workflow | 3-4h | Needs S1.7 + S1.8 |
| S1.10 smoke | 2-3h | End-to-end verification |

**Total impl**: ~30-42 hours. **Calendar**: ~4-5 weeks (including S0).

**Team allocation** (rev2, CTO-MEDIUM-1): PythonEngineer needed for S0+S1.
S2 also needs PE. Since one PE can't run S1 and S2 in parallel, **S2
starts after S1.6 frees PE** (~week 3). S3 (InfraEngineer) is truly
parallel with S1.

## Risks (rev2)

| Risk | Mitigation |
|------|------------|
| `audit_contract()` queries drift from extractor output | S1.10 smoke with synthetic fixture; CI fails on drift |
| Auditor invents findings | Role prompt hard rule + integration test tracing claims to fetcher rows |
| Report bloat | 500-word cap + per-section budget; renderer truncates with trailer |
| Paved-path regression | S1.10 gate: add fixture entry → new section without code changes |
| Child-issue workflow complexity | S1.9 runbook + S1.10 happy-path coverage |

## Cross-references

- Overview: `audit-v1-overview.md`
- Roadmap: `docs/roadmap.md` §"Audit-V1"
- B-min slice (after S1.6): `B-audit-extractors.md`
- C ingestion (parallel with S1): `C-ingestion-automation.md`
- Smoke (after S0+S1+S2+S3): `E-smoke.md`
