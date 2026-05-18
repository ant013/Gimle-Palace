# GIM-335 — Hotspot audit template "scanned 0 files" fix — Specification

**Date:** 2026-05-17
**Status:** Draft for plan-first review
**Issue:** GIM-335
**Branch:** `feature/GIM-335-hotspot-audit-supplement`
**Parent:** GIM-333 (suspicious-zero diagnostic, merged via PR #208)
**Predecessor:** GIM-283 audit-v1-pipeline-fixes, merged to `develop` at `d072dcb`

---

## 1. Problem

The hotspot audit template (`audit/templates/hotspot.md`) shows "scanned 0
files, found 0 issues" when `findings=[]`. This happens when all
`hotspot_score = 0.0` — e.g. TronKit where 86 files were processed but all
scores were 0 due to exhausted churn window (no commits within the 90-day
window).

The output is misleading: the extractor ran and analysed files, but the
audit report suggests nothing was scanned.

## 2. Root cause

Two-part chain:

1. **Audit contract query** (`hotspot/extractor.py:191`) filters
   `WHERE coalesce(f.hotspot_score, 0.0) > 0`, so only files with non-zero
   scores appear in findings.

2. **`_build_summary_stats`** (`audit/fetcher.py:117`) sets
   `file_count = len(findings)`. When findings is empty, `file_count = 0`.

3. **Template** (`hotspot.md:17`) renders
   `scanned {{ summary_stats.get('file_count', 0) }} files` — which shows 0.

The audit contract query filtering is correct (we don't want to list 86
zero-score files). The problem is that `_build_summary_stats` has no way to
know how many files were actually processed.

## 3. Fix approach

Follow the established `arch_layer` supplemental query pattern
(`fetcher.py:28-35, 86-95`). The `arch_layer` extractor already solves
the identical problem: when `findings=[]`, it runs a supplemental Cypher
query to fetch module/rule counts directly from Neo4j.

### 3.1 Supplemental Cypher query

```cypher
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN count(f) AS total_scanned_files
```

This counts all files the hotspot extractor wrote to Neo4j with
`complexity_status='fresh'` — the real count of analysed files.

### 3.2 Template update

The no-findings path should show:
- Real scanned count from the supplement
- Explicit "0 with non-zero hotspot scores" instead of ambiguous "found 0 issues"

The findings path summary should also show `total_scanned_files` as denominator.

## 4. Scope

| File | Change |
|------|--------|
| `services/palace-mcp/src/palace_mcp/audit/fetcher.py` | Add `_HOTSPOT_SUPPLEMENT` constant, `_fetch_hotspot_supplement` helper, supplement call in `fetch_audit_data` |
| `services/palace-mcp/src/palace_mcp/audit/templates/hotspot.md` | Use `total_scanned_files` in both paths |
| `services/palace-mcp/tests/audit/integration/test_audit_fetcher.py` | Integration test: seed File nodes with score=0, verify supplement populates real count |

Estimated: ~30 LOC production, ~40 LOC test.

## 5. Out of scope

- Changing the audit contract query to include zero-score files.
- Generalising the supplemental query pattern (each extractor's supplement
  is specific to its domain).
- IB-2/IB-3/IB-4 infra blockers from PR #205 (flagged to operator separately).
