# Audit report — tron-kit after GIM-283-2 (Slice 1)

**Date:** 2026-05-13
**Slice:** GIM-283-2 — Coverage (testability_di + reactive + DEFAULT_EXTRACTORS)
**Branch:** `feature/GIM-283-2-audit-coverage-gaps`
**Status:** PENDING — requires iMac live smoke (QAEngineer Phase 4.1)

## Verification scope

Per plan Task 1.6, the QAEngineer must run the following on iMac and paste
real MCP output in place of the expected-output stubs below.

```bash
bash paperclips/scripts/ingest_swift_kit.sh tron-kit --bundle=uw-ios
palace.audit.run(project="tron-kit")
```

## Expected outcomes

| Extractor | Expected status | Notes |
|-----------|----------------|-------|
| `testability_di` | `OK` or `RUN_FAILED` with reason | GIM-242 merged via PR #161; should appear as audit section |
| `reactive_dependency_tracer` | `RUN_FAILED` + `swift_helper_unavailable` | Expected — no `reactive_facts.json` in tron-kit; diagnostic maps to INFORMATIONAL |
| `coding_convention` | `OK` or `RUN_FAILED` with reason | Added to DEFAULT_EXTRACTORS in this slice |
| `localization_accessibility` | `OK` or `RUN_FAILED` with reason | Added to DEFAULT_EXTRACTORS in this slice |
| `arch_layer` | `OK` or `NOT_ATTEMPTED` | Added to DEFAULT_EXTRACTORS |
| `error_handling_policy` | `OK` or `NOT_ATTEMPTED` | Added to DEFAULT_EXTRACTORS |
| `hot_path_profiler` | `OK` or `NOT_ATTEMPTED` | Added to DEFAULT_EXTRACTORS |

## Acceptance criteria

- [ ] `testability_di` appears as a section in the audit report (not `NOT_APPLICABLE`)
- [ ] `reactive_dependency_tracer` appears with `swift_helper_unavailable` diagnostic
      and severity `INFORMATIONAL` (not an error or blocker)
- [ ] `coding_convention` and `localization_accessibility` are present in the report
      (any status except `NOT_APPLICABLE`)
- [ ] No regression in extractors that passed before this slice

## QA evidence placeholder

*To be filled by QAEngineer during Phase 4.1 smoke on iMac.*

```
# paste palace.audit.run(project="tron-kit") output here
```
