# GIM-335 — Hotspot audit template "scanned 0 files" fix — Implementation Plan

**Issue:** GIM-335
**Spec:** `docs/superpowers/specs/2026-05-17-GIM-335-hotspot-audit-supplement_spec.md`
**Branch:** `feature/GIM-335-hotspot-audit-supplement`
**Target:** `develop`
**Predecessor:** GIM-283 merged to `develop` at `d072dcb`
**Formal handoff targets:** `[@CodeReviewer](agent://bd2d7e20-a780-4a4a-a3e8-d48a7e0a08b7?i=eye)` (Phase 1.2),
`[@MCPEngineer](agent://274a0b0c-ebe8-4613-ad0e-3e745c817a97?i=wrench)` (Phase 2),
`[@CodeReviewer](agent://bd2d7e20-a780-4a4a-a3e8-d48a7e0a08b7?i=eye)` (Phase 3.1),
`[@OpusArchitectReviewer](agent://8d6649e2-de08-4413-93ea-8e964d03413b?i=eye)` (Phase 3.2),
`[@QAEngineer](agent://58b68640-e8f7-4744-90f2-0ad35b18e698?i=bug)` (Phase 4.1).

---

## File Structure

Phase 3.1 must compare implementation scope mechanically:

```bash
git diff --name-only origin/develop..HEAD | sort
```

Expected Phase 2 implementation scope is **3 files** (**0 NEW + 3 MOD**).
Full branch diff at Phase 3.1 should show **5 files total** (**3 impl + 2 docs**):

| Status | Path |
|--------|------|
| NEW | `docs/superpowers/specs/2026-05-17-GIM-335-hotspot-audit-supplement_spec.md` |
| NEW | `docs/superpowers/plans/2026-05-17-GIM-335-hotspot-audit-supplement.md` |
| MOD | `services/palace-mcp/src/palace_mcp/audit/fetcher.py` |
| MOD | `services/palace-mcp/src/palace_mcp/audit/templates/hotspot.md` |
| MOD | `services/palace-mcp/tests/audit/integration/test_audit_fetcher.py` |

---

## Tasks

### Task 1 — Add `_HOTSPOT_SUPPLEMENT` and helper (fetcher.py)

**Test first:** Write the integration test (Task 3) skeleton before touching production code.

**Impl:**

1. Add `_HOTSPOT_SUPPLEMENT` Cypher constant after `_ARCH_LAYER_SUPPLEMENT` (line 35):

```python
_HOTSPOT_SUPPLEMENT = """
MATCH (f:File {project_id: $project_id})
WHERE coalesce(f.complexity_status, 'stale') = 'fresh'
RETURN count(f) AS total_scanned_files
""".strip()
```

2. Add `_fetch_hotspot_supplement` helper (parallel to `_fetch_arch_layer_supplement`):

```python
async def _fetch_hotspot_supplement(
    driver: Any, run_info: RunInfo
) -> dict[str, Any]:
    async with driver.session() as session:
        result = await session.run(
            _HOTSPOT_SUPPLEMENT,
            project_id=f"project/{run_info.project}",
        )
        record = await result.single()
    return {"total_scanned_files": record["total_scanned_files"] if record else 0}
```

3. Add supplement call block in `fetch_audit_data` after the arch_layer block (after line 95):

```python
if extractor_name == "hotspot":
    try:
        supplement = await _fetch_hotspot_supplement(driver, run_info)
        summary_stats.update(supplement)
    except Exception:
        log.warning(
            "hotspot supplemental query failed for project %r",
            run_info.project,
            exc_info=True,
        )
```

**Commit:** `fix(audit): add hotspot supplemental query for real scanned-file count (GIM-335)`

### Task 2 — Update template (hotspot.md)

Update **no-findings path** (line 16-17) from:
```
scanned {{ summary_stats.get('file_count', 0) }} files, found 0 issues.
```
to:
```
scanned {{ summary_stats.get('total_scanned_files', summary_stats.get('file_count', 0)) }} files, found 0 with non-zero hotspot scores.
```

Update **findings path summary** (line 12) from:
```
{{ summary_stats.file_count }} file{{ 's' if ...
```
to:
```
{{ summary_stats.get('total_scanned_files', summary_stats.file_count) }} file{{ 's' if ...
```

**Commit:** squash with Task 1 or separate `fix(audit): update hotspot template to show real file count (GIM-335)`

### Task 3 — Integration test (test_audit_fetcher.py)

Add `TestHotspotSupplement` class:

1. Seed 3 File nodes with `project_id='project/test-proj'`, `complexity_status='fresh'`, `hotspot_score=0.0`
2. Run `fetch_audit_data` with real `HotspotExtractor`
3. Assert `section.summary_stats['total_scanned_files'] == 3`
4. Assert `section.findings == []` (no files pass score > 0)
5. Render via `render_section` and assert "scanned 3 files" appears in output
6. Assert "scanned 0 files" does NOT appear

**Commit:** `test(audit): integration test for hotspot supplemental file count (GIM-335)`

---

## Acceptance criteria

1. When hotspot finds 0 files with `hotspot_score > 0`, template reports the actual count of processed files
2. When hotspot finds N > 0 files, summary shows `total_scanned_files` as denominator
3. `uv run ruff check` clean
4. `uv run mypy src/` clean
5. `uv run pytest tests/audit/` green

## Phase handoff

- Phase 1.2: CodeReviewer validates plan completeness
- Phase 2: MCPEngineer implements on `feature/GIM-335-hotspot-audit-supplement`
- Phase 3.1+: standard review chain
