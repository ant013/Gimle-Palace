# Audit-V1 S0 — Foundation Prerequisites — Specification

**Document date:** 2026-05-07
**Status:** Formalised (GIM-228)
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Claude
**Slice ID:** S0 (Audit-V1 sprint sequence, rev3)
**Companion plan:** `2026-05-07-audit-v1-s0-foundation-prereqs_plan.md`
**Source sprint file:** `docs/superpowers/sprints/D-audit-orchestration.md` §S0 (rev2)
**Roadmap row:** `docs/roadmap.md` §"Audit-V1" sprint table — S0
**Branch:** `feature/GIM-228-audit-v1-s0-foundation-prereqs`.

---

## 1. Goal

Land three independent prerequisite slices that unblock Audit-V1 S1 (Audit
Orchestration). Without S0, S1.4 discovery misses half the extractors,
S1.5 fetcher has no composite MCP tools to call, and the 3 reused agents
(Opus / Security / Blockchain) have no audit-mode prompt section.

**Definition of Done for the S0 sprint as a whole:**

1. **S0.1 IngestRun schema unified** — both creation paths (`runner.py`
   via `cypher.py` AND `foundation/checkpoint.py`) write the same
   canonical fields (`extractor_name`, `project`) on every `:IngestRun`
   node.
2. **S0.2 Three NEW composite MCP tools exist** (`find_dead_symbols`,
   `find_public_api`, `find_cross_module_contracts`). Each is a thin
   wrapper around an existing extractor's Cypher query, returns a
   Pydantic response model. **(rev4 correction)**: `find_owners`
   already registered at `mcp_server.py:850` (GIM-216, merged
   `2d6e6c1`); `find_version_skew` registered via
   `register_version_skew_tools()` at `mcp_server.py:790` (GIM-218,
   merged `603c840`). S0.2 scope reduced from 5 → 3.
3. **S0.3 Audit-mode prompt fragment** authored at
   `paperclips/fragments/local/audit-mode.md` (NOT in role files
   directly), included via `<!-- @include fragments/local/audit-mode.md -->`
   marker in 3 Claude role files (kebab-case, per `paperclips/build.sh`):
   `paperclips/roles/opus-architect-reviewer.md`,
   `paperclips/roles/security-auditor.md`,
   `paperclips/roles/blockchain-engineer.md`. CX-side mirror is
   **deferred to E6** because CX-side `cx-blockchain-engineer.md` /
   `cx-security-auditor.md` files **don't exist on develop yet**
   (only `cx-code-reviewer.md`, `cx-cto.md`, etc. + `codex-architect-reviewer.md`).
   E6 hires create the CX security/blockchain role files **with**
   the audit-mode fragment-include already in place.
4. **Removed** — `palace.audit.run` is S1.6 scope (see §8), not S0.

## 2. Why now / why this scope

S1 (Audit Orchestration) is the biggest sprint in the rev3 critical path
(3-4 weeks, single Claude PE). Three reviewers on rev1 (CTO, CR, Opus)
flagged that the original "S1‖S2 parallel" plan was unsafe because:

- **OPUS-CRITICAL-1**: dual `:IngestRun` schema means the discovery
  Cypher in S1.4 silently drops half the extractors.
- **CR-CRITICAL-3**: 5 of the 8 composite tools the S1.5 fetcher relies
  on don't exist yet — fetcher would `attribute-not-found` at runtime.
- **OPUS-MEDIUM-2**: reusing 3 existing agents without audit-mode
  prompts means each domain agent ad-libs the report format.

Rev2 introduced S0 as a 1-week prerequisite that fixes all three before
S1 starts. Each S0 sub-slice (S0.1 / S0.2 / S0.3) is parallelisable
(different file trees) and small (2-6 hours each).

## 3. Scope — three sub-slices

### 3.1 S0.1 — Unify IngestRun schema (OPUS-CRITICAL-1)

**Problem state**: two `:IngestRun` creation paths produce nodes with
incompatible schemas; the audit discovery Cypher uses Path B's field
names (`extractor_name`, `project`) and silently misses every Path A
node. Affected extractors at risk of being invisible to the audit:
`hotspot`, `dead_symbol_binary_surface`, `dependency_surface`,
`code_ownership` (after GIM-216 merges), `cross_module_contract`,
`public_api_surface`, and any future Path A extractor.

**Target end state**: `:IngestRun` nodes from both paths queryable
uniformly by `(extractor_name, project)` keys. Existing nodes
back-filled by a one-shot migration query.

**Files in scope**:
- `services/palace-mcp/src/palace_mcp/extractors/cypher.py` — extend
  the CREATE statement so Path A IngestRuns carry `extractor_name`
  + `project`.
- `services/palace-mcp/src/palace_mcp/extractors/runner.py` — derive
  both fields and pass them through.
- `services/palace-mcp/src/palace_mcp/migrations/2026_05_xx_unify_ingest_run.py`
  — back-fill query. Idempotent.
- Tests under `services/palace-mcp/tests/extractors/unit/test_ingest_run_schema.py`
  + `tests/integration/test_ingest_run_unification.py`.

**Out of scope**: changing the Path B schema. Path B already has the
canonical fields; Path A is the loser of this convergence.

### 3.2 S0.2 — Three NEW composite MCP tools (rev4 — was 5, scope corrected)

**Problem state (rev4)**: The S1.9 async workflow needs domain agents
to query per-extractor data via MCP composites. Currently registered
on develop (verified against `mcp_server.py` HEAD): `find_references`,
`test_impact`, `find_hotspots`, `list_functions`, `find_owners`
(GIM-216), `find_version_skew` (GIM-218). Three are still missing:
`find_dead_symbols`, `find_public_api`, `find_cross_module_contracts`.

**Note for S1.5 fetcher**: the fetcher uses **direct Cypher** via
`audit_contract().query`, NOT MCP composite tools (per OPUS-H1
correction in rev4 review). Composite tools are an **agent-facing**
surface for ad-hoc queries during S1.9 workflows, not consumed by
the in-process fetcher. S0.2 dependency therefore moves from S1.5 to
S1.9.

**Target end state**: 3 new composite MCP tools registered as per-tool
modules under `services/palace-mcp/src/palace_mcp/code/` (Pattern B —
matching existing `find_hotspots.py` / `find_owners.py` / `list_functions.py`):

| Tool | Backing extractor | Response model |
|---|---|---|
| `palace.code.find_dead_symbols` | `dead_symbol_binary_surface` (#33, GIM-193) | `DeadSymbolList` |
| `palace.code.find_public_api` | `public_api_surface` (#27, GIM-190) | `PublicApiList` |
| `palace.code.find_cross_module_contracts` | `cross_module_contract` (#31, GIM-192) | `ContractDriftList` |

Each tool is a thin wrapper: `await tx.run(<cypher>) → response_model`.
Tests cover happy-path + empty-result + project-not-registered.

**Files in scope** (rev4 — 3 new tools, not 5):
- 3 new per-tool modules under `services/palace-mcp/src/palace_mcp/code/`:
  `find_dead_symbols.py`, `find_public_api.py`, `find_cross_module_contracts.py`
  (Pattern B — matching existing `find_hotspots.py` / `find_owners.py`).
- 3 response Pydantic models (location: alongside tool registration).
- Register each new tool in `mcp_server.py` following the existing
  pattern (lines 797 / 824 / 850).
- Tests under `services/palace-mcp/tests/` for each new tool —
  3 tools × 3 cases (empty / seeded / project-not-registered) = 9 tests.
- 1 integration test seeding graph + calling all 3 tools.

**Out of scope**: the audit fetcher itself (S1.5 uses direct Cypher,
not MCP). Tools must be consumable from outside the audit — they're
general-purpose for agent ad-hoc queries during S1.9 workflows.

### 3.3 S0.3 — Audit-mode prompt fragment (OPUS-MEDIUM-2; rev4-corrected)

**Problem state**: the 3 reused agents
(`OpusArchitectReviewer`, `SecurityAuditor`, `BlockchainEngineer`)
have role prompts tuned for code review, not for audit-report
generation. When called from the workflow launcher, each will
ad-lib the format, severity grading, and what counts as a finding —
output won't be consistent across audit runs.

**Target end state (rev4)**: a new fragment file at
`paperclips/fragments/local/audit-mode.md` is included via
`<!-- @include fragments/local/audit-mode.md -->` marker (correct
syntax per `paperclips/build.sh` HEAD) into 3 Claude role files
(kebab-case naming, verified against `git ls-tree origin/develop`):

- `paperclips/roles/opus-architect-reviewer.md`
- `paperclips/roles/security-auditor.md`
- `paperclips/roles/blockchain-engineer.md`

The fragment defines:

- **Input format**: JSON blob shape from `palace.audit.run` fetcher.
- **Output format**: markdown sub-report — section header, severity-
  graded finding list, evidence-citation rule.
- **Severity grading**: how to map extractor metric values
  (`importance_score`, `churn_count`, `cyclomatic_complexity`,
  finding count, …) → `critical` / `high` / `medium` / `low`.
- **Hard rule**: agent NEVER invents findings beyond what fetcher
  data shows. If fetcher returns 0 findings for a section, sub-
  report says "no findings" — no synthesis from agent's training data.

**Verification step**: run `bash paperclips/build.sh --target claude`
after editing; verify rendered `paperclips/dist/<role>.md` contains
the audit-mode section (build.sh awk script expands the marker).

**CX-side parity (rev4 — DEFERRED to E6)**:
On develop, only `cx-code-reviewer.md`, `cx-cto.md`, `cx-infra-engineer.md`,
`cx-mcp-engineer.md`, `cx-python-engineer.md`, `cx-qa-engineer.md`,
`cx-research-agent.md`, `cx-technical-writer.md`, plus
`codex-architect-reviewer.md` (different prefix) exist.
**There is no `cx-security-auditor.md` or `cx-blockchain-engineer.md`
on develop yet** — those files are E6 deliverables. E6 (CX hire)
spec must include the `<!-- @include fragments/local/audit-mode.md -->`
marker at creation time.

**Files in scope** (Claude side, rev4):
- `paperclips/fragments/local/audit-mode.md` (new)
- `paperclips/roles/opus-architect-reviewer.md` (append marker)
- `paperclips/roles/security-auditor.md` (append marker)
- `paperclips/roles/blockchain-engineer.md` (append marker)
- `paperclips/dist/<role>.md` × 3 (regenerated)

**Out of scope**: the Auditor role file (new role, lands in S1.7);
CX-side audit-mode markers (deferred to E6).

## 4. Schema impact

Only S0.1 touches Neo4j schema:

```cypher
// Before (Path A)
CREATE (r:IngestRun {id: $id, source: $source, group_id: $gid, ...})

// After (Path A)
CREATE (r:IngestRun {
  id: $id, source: $source, group_id: $gid,
  extractor_name: $extractor_name,   // NEW — canonical
  project: $project                  // NEW — canonical
})
```

Migration query (idempotent — safe to re-run):

```cypher
MATCH (r:IngestRun)
WHERE r.extractor_name IS NULL AND r.source STARTS WITH 'extractor.'
SET r.extractor_name = substring(r.source, 10),
    r.project = CASE WHEN r.group_id STARTS WITH 'project/'
                     THEN substring(r.group_id, 8)
                     ELSE r.group_id END
```

`palace_mcp.cli` gets a one-shot subcommand `migrate ingest-run-unify`
that runs this query.

## 5. Decision points

| ID | Question | Default | Impact of non-default |
|----|----------|---------|----------------------|
| S0-D1 | Migrate existing IngestRun rows or only new ones? | migrate all (idempotent) | leaving old rows orphans pre-2026-05-07 audit history from S1 discovery |
| S0-D2 | Composite tools async or sync? | async (same as siblings `find_references`) | sync would break consistency with rest of `palace.code.*` surface |
| S0-D3 | CX-side role files mandatory or optional? | mandatory (per Codex parity rule) | CX team can't run audits if Codex agents lack audit-mode prompts |
| S0-D4 | Composite tools accept `bundle=` parameter? | no, v1 is per-project; bundle composition is S5 | adding bundle now would add ~1 day per tool |

## 6. Test plan summary

- **Unit (S0.1)**: schema migration query is idempotent + back-fills
  correct field values for synthetic Path A rows.
- **Unit (S0.2)**: each composite tool against an empty graph returns
  empty list; against a seeded fixture returns expected response shape.
- **Integration (S0.1+S0.2)**: end-to-end test seeds graph with mixed
  Path A + Path B IngestRuns and 1 record per extractor; calls all 3
  NEW composite tools; asserts row counts.
- **Lint (S0.3)**: role files pass markdown-lint + the audit-mode
  section follows the same heading template across all 3 Claude role
  files (CX-side deferred to E6).

## 7. Risks

- **R1**: migration query overlap with active extractor runs. Mitigation:
  run migration with `CALL { … } IN TRANSACTIONS OF 100 ROWS` and a
  pre-check that no `:IngestRun` is currently in `started` state.
- **R2**: drift between Claude and Codex audit-mode prompts. Mitigation:
  CX-side files are direct mirrors of Claude side with a "this file mirrors
  ..." comment at the top; CR Phase 3.1 must `diff` the audit-mode sections
  between team pairs before APPROVE.
- **R3**: composite tool schema accidentally breaks an external palace.code
  consumer. Mitigation: 3 tools are NEW (no overload), so no break risk;
  registry registration only.

## 8. Out of scope / explicitly NOT in S0

- Audit workflow (S1).
- New extractor implementations.
- LLM-bearing infra (deferred per AV1-D4).
- `palace.audit.run` composite tool (lands in S1.6).
- `audit-workflow-launcher.sh` (lands in S1.9).

## 9. Cross-references

- Sprint file: `docs/superpowers/sprints/D-audit-orchestration.md` §S0
- Audit-V1 overview: `docs/superpowers/sprints/audit-v1-overview.md`
- Roadmap row: `docs/roadmap.md` §"Audit-V1" — S0 row
- Reviewer findings driving S0: OPUS-CRITICAL-1, CR-CRITICAL-3, OPUS-MEDIUM-2
- Companion: `2026-05-07-audit-v1-s0-foundation-prereqs_plan.md`
