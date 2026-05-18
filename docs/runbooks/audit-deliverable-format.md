# Audit Deliverable Format — Contract Reference

**Document date:** 2026-05-07
**Slice:** S1.1 of Audit-V1
**Status:** Canonical (S1 implementation reference)

---

## 1. Report structure — 10 sections

Every audit report is a markdown document with exactly these 10 top-level sections, in this default order (may be reordered by max-severity; see §6):

| # | Section heading | Extractor |
|---|----------------|-----------|
| 1 | Executive Summary | (synthesised by renderer) |
| 2 | Code Hotspots | `hotspot` |
| 3 | Dead Symbols & Binary Surface | `dead_symbol_binary_surface` |
| 4 | Dependency Surface | `dependency_surface` |
| 5 | Code Ownership | `code_ownership` |
| 6 | Cross-Repo Version Skew | `cross_repo_version_skew` |
| 7 | Public API Surface | `public_api_surface` |
| 8 | Cross-Module Contract Drift | `cross_module_contract` |
| 9 | Blind Spots | (synthesised by renderer) |
| 10 | Provenance | (synthesised by renderer) |

Sections 2–8 are extractor-driven (data-in → template-out). Sections 1, 9, 10 are
renderer-synthesised from aggregated section data.

---

## 2. Severity rank ladder

```
critical > high > medium > low > informational
```

Integer rank (lower = more severe):

| Severity | Rank |
|----------|------|
| critical | 0 |
| high | 1 |
| medium | 2 |
| low | 3 |
| informational | 4 |

---

## 3. Per-extractor default severity mapping

Extractors declare a `severity_column` in their `AuditContract`. The renderer maps
domain-specific values to the canonical ladder. Default mappings:

| Extractor | Severity trigger | Canonical severity |
|-----------|-----------------|-------------------|
| `hotspot` | `hotspot_score >= 4.0` | critical |
| `hotspot` | `hotspot_score >= 2.0` | high |
| `hotspot` | `hotspot_score >= 1.0` | medium |
| `hotspot` | `hotspot_score >= 0.0` | low |
| `dead_symbol_binary_surface` | `candidate_state = CONFIRMED_DEAD` | high |
| `dead_symbol_binary_surface` | `candidate_state = UNUSED_CANDIDATE` | medium |
| `dead_symbol_binary_surface` | `candidate_state = SKIPPED` | informational |
| `dependency_surface` | (all listed deps) | informational |
| `code_ownership` | `weight < 0.2` (diffuse ownership) | medium |
| `code_ownership` | (normal ownership) | low |
| `cross_repo_version_skew` | `severity = major` | high |
| `cross_repo_version_skew` | `severity = minor` | medium |
| `cross_repo_version_skew` | `severity = patch` | low |
| `public_api_surface` | (all listed symbols) | informational |
| `cross_module_contract` | `removed_count > 0` | high |
| `cross_module_contract` | `signature_changed_count > 0` | medium |
| `cross_module_contract` | `added_count > 0` | low |

---

## 4. Per-section length budget

| Section | Max words |
|---------|-----------|
| Executive Summary | 200 |
| Each extractor section (2–8) | 500 per section |
| Blind Spots | 200 |
| Provenance | 100 |

Total report budget: ~4 000 words. Renderer truncates findings lists to
`AuditContract.max_findings` (default 100) before rendering.

---

## 5. Token budget per agent (AV1-D6)

During async workflow (S1.9), domain agents receive fetcher output JSON:

- **Input context:** ≤ 50 000 tokens (fetcher data + role prompt)
- **Output:** ≤ 10 000 tokens (per-domain sub-report markdown)

The launcher shell script enforces these limits by slicing fetcher JSON
before injecting into agent issues.

---

## 6. Section ordering rule

Sections 2–8 are ordered by their **max severity** across all findings.
`critical` sections appear first, `informational` last. Ties preserve the
default order from §1. Executive Summary, Blind Spots, and Provenance always
occupy positions 1, 9, 10 respectively regardless of severity.

---

## 7. Empty-section format

When an extractor has a successful `:IngestRun` but returned zero findings:

```
No findings — extractor `<name>` ran at `<run_id>` on `<head_sha>`,
scanned N items, found 0 issues.
```

When an extractor has no `:IngestRun` at all (blind spot):

```
⚠ Extractor `<name>` has not run for project `<slug>`. Data unavailable.
Run `palace.ingest.run_extractor(name="<name>", project="<slug>")` to populate.
```

---

## 8. Blind-spot disclosure rules

The renderer MUST include a Blind Spots section (§9) that lists every extractor
present in the registry with `audit_contract() != None` but absent from
`discovery.find_latest_runs()`. This makes coverage gaps explicit and
machine-readable.

---

## 9. Provenance trailer format

Every report ends with a Provenance section containing:

```markdown
## Provenance

| Field | Value |
|-------|-------|
| Project | `<slug>` |
| Generated at | `<ISO-8601 UTC>` |
| Fetched extractors | `<comma-separated names>` |
| Blind spots | `<comma-separated names or "none">` |
| Fetched run IDs | `<run_id per extractor>` |
```

---

## 10. `BaseExtractor.audit_contract()` type signature

```python
from palace_mcp.audit.contracts import AuditContract

class BaseExtractor(ABC):
    def audit_contract(self) -> AuditContract | None:
        """Return audit contract for this extractor, or None to opt out.

        Default: None (extractor produces no audit section).
        Override in extractors that participate in palace.audit.run.
        """
        return None
```

The `AuditContract` dataclass (defined in `palace_mcp/audit/contracts.py`):

```python
@dataclass(frozen=True)
class AuditContract:
    extractor_name: str    # matches extractor registry key
    template_name: str     # filename under audit/templates/ (e.g. "hotspot.md")
    query: str             # Cypher query; receives $project param
    severity_column: str   # key in each finding dict used for severity mapping
    max_findings: int = 100
```

---

## 11. `:IngestRun` schema contract (S0.1 unified)

After S0.1, every `:IngestRun` node — regardless of creation path — has:

| Property | Type | Notes |
|----------|------|-------|
| `run_id` | string | UUID |
| `extractor_name` | string | registry key, e.g. `"hotspot"` |
| `project` | string | project slug, e.g. `"gimle"` |
| `success` | boolean | `true` on clean finish |
| `started_at` | datetime | neo4j DateTime |
| `completed_at` | datetime | null until finalised |
| `nodes_written` | int | |
| `edges_written` | int | |
| `error_code` | string | null on success |

The discovery query uses `(extractor_name, project, success)` — all three fields
are indexed (`ingest_run_lookup` in `foundation/schema.py`).
