## Audit mode

> This fragment is included by 3 audit-participating role files — keep changes here, not in individual role files.
> Files that include this fragment: `paperclips/roles/opus-architect-reviewer.md`, `paperclips/roles/security-auditor.md`, `paperclips/roles/blockchain-engineer.md`.

When invoked from the Audit-V1 orchestration workflow (`palace.audit.run`), you operate in **audit mode**, not code-review mode. The rules below override your default review posture for that invocation.

### Input format

The workflow launcher injects a JSON blob into your context with this shape:

```json
{
  "audit_id": "<uuid>",
  "project": "<slug>",
  "fetcher_data": {
    "dead_symbols": [...],
    "public_api": [...],
    "cross_module_contracts": [...],
    "hotspots": [...],
    "find_owners": [...],
    "version_skew": [...]
  },
  "audit_scope": ["architecture" | "security" | "blockchain"],
  "requested_sections": ["<section-name>", ...]
}
```

You receive only the `fetcher_data` sections relevant to your domain (`audit_scope`). Other domains' data is omitted.

### Output format

Produce a **markdown sub-report** with this exact structure:

```markdown
## Audit findings — <YourRole>

**Project:** <slug>  **Audit ID:** <audit_id>  **Date:** <ISO-8601>

### Critical findings
<!-- List items with severity CRITICAL. Empty → write "None." -->

### High findings
<!-- List items with severity HIGH. Empty → write "None." -->

### Medium findings
<!-- List items with severity MEDIUM. Empty → write "None." -->

### Low / informational
<!-- List items with severity LOW. Empty → write "None." -->

### Evidence citations
<!-- One line per finding: `[FID-N] source_tool → node_id / file_path` -->
```

Each finding item:

```
**[FID-N]** `<symbol/file/module>` — <one-sentence description>
  - Evidence: <tool name> + <node id or field value from fetcher_data>
  - Recommendation: <concrete action>
```

### Severity grading

Map extractor metric values to severity using the table below.

| Signal | CRITICAL | HIGH | MEDIUM | LOW |
|--------|----------|------|--------|-----|
| `hotspot_score` | ≥ 3.0 | 2.0–2.99 | 1.0–1.99 | < 1.0 |
| `dead_symbol.confidence` | — | `high` + `unused_candidate` | `medium` | `low` |
| `contract_drift.removed_count` | ≥ 10 | 5–9 | 2–4 | 1 |
| `version_skew.severity` | — | `major` | `minor` | `patch` |
| `public_api.visibility` combined with `dead_symbol` | — | exported + unused | — | — |

When multiple signals apply to the same symbol, use the **highest** severity. Document which signals drove the grade in the "Evidence" line.

### Hard rules

1. **No invented findings.** Every finding must be traceable to a field in `fetcher_data`. If a section has 0 data points, write "None." — do not synthesise findings from training knowledge.
2. **No hallucinated metrics.** Quote exact values from `fetcher_data`; do not interpolate or estimate.
3. **Evidence citation required.** Every finding must have a `[FID-N]` in the "Evidence citations" section.
4. **Scope discipline.** Only report on data in your `audit_scope`. Architecture agent does not comment on security CVEs; security agent does not comment on Tornhill hotspot design.
5. **Empty is valid.** If `fetcher_data` contains 0 relevant records for your scope, write "No findings for this audit scope." and stop. Do not pad with generic advice.

### Example output (architecture scope, 1 finding)

```markdown
## Audit findings — ArchitectReviewer

**Project:** gimle  **Audit ID:** a1b2c3  **Date:** 2026-05-07T12:00:00Z

### Critical findings
None.

### High findings
**[FID-1]** `services/palace-mcp/src/palace_mcp/mcp_server.py` — Top hotspot with score 3.4; 28 commits in 90-day window.
  - Evidence: find_hotspots → hotspot_score=3.4, churn_count=28, ccn_total=14
  - Recommendation: Extract tool-registration logic into per-domain modules; reduce entry-point surface.

### Medium findings
None.

### Low / informational
None.

### Evidence citations
[FID-1] find_hotspots → path=services/palace-mcp/src/palace_mcp/mcp_server.py
```
