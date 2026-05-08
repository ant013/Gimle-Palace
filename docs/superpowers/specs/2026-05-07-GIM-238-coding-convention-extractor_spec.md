# Coding Convention Extractor (#6) — Specification

**Document date:** 2026-05-07
**Status:** Formalised for GIM-238 · awaiting CXCodeReviewer plan-first review
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Codex (CX-native: SwiftSyntax + Konsist + detekt + semgrep)
**Slice ID:** Phase 2 §2.2 #6 (Coding Convention Extractor)
**Companion plan:** `2026-05-07-GIM-238-coding-convention-extractor.md`
**Branch:** `feature/GIM-238-coding-convention-extractor`
**Blockers (rev6 formalisation):** none.

**Resolved prerequisites (rev6 formalisation):**
- E6 closed via GIM-229 / PR #116 squash merge `e2f9a09` on
  2026-05-08.
- S0.1 IngestRun schema unification is present on `origin/develop`:
  `services/palace-mcp/src/palace_mcp/extractors/cypher.py`
  writes `extractor_name + project` on `:IngestRun`.

---

## 1. Goal

Extract project-specific coding conventions (naming patterns, structural
patterns, idiomatic style choices) from Swift + Kotlin source so audit
agents can answer:

- "Is this PR consistent with project naming conventions?"
- "Does module X follow the same coding patterns as the rest of the
  codebase?"
- "What are the dominant style idioms here — Result vs throws,
  property-wrappers vs computed-property, sealed-class vs enum-class?"

This addresses target problem **#3 (project-specific code idioms)** in
the original 45-extractor research inventory.

**Definition of Done:**

1. New extractor `coding_convention` registered in `EXTRACTORS`
   (CX team's parallel registry).
2. Implements `audit_contract()` returning per-module convention
   summary as a Pydantic response model.
3. Writes `:Convention` + `:ConventionViolation` nodes (schema in §4).
4. `audit/templates/coding_convention.md` ships with the extractor.
5. Operator runbook `docs/runbooks/coding-convention.md`.
6. Smoke runs on `tronkit-swift` and `unstoppable-wallet-android`
   producing ≥3 detected conventions per project + ≥0 violations
   (or explicit "clean" with rationale).

## 2. Why now / why this scope

**Now**: post-E6 close, CX team has parity. #6 is one of the
high-ROI CX-native independent extractors that don't depend on any
chain (after E6). Operator's 35/65 swap places it in the early
batch of Codex queue.

**Scope choice — what counts as a "convention"**:
- **Naming**: file naming, type naming (UpperCamel vs UPPER_SNAKE),
  test naming pattern (e.g., `Test`-suffix vs `*Tests` class).
- **Structural**: typealias usage rate, extension-vs-protocol
  preference, sealed-class vs enum-class for ADTs.
- **Idiomatic**: error style (throws / Result / nullable), DI style
  (init-injection / property / framework-bound),
  property-wrapper-vs-computed for derived values.

**Out of scope (deferred or covered elsewhere)**:
- Test smell / flaky tests → #38.
- **DI patterns** → **#8 is authoritative** (rev4 — CTO-#8-M1 finding).
  Drop `structural.di_style` from §6 rule set (down to 7 rules).
  Audit template cross-references #8's `:DiPattern` rows.
- Error handling smells → #7 (S2.3 in audit-v1).
- Dead code → #33 (already merged GIM-193).
- Complexity hotspots → #44 (already merged GIM-195).

## 3. Detection strategy

### 3.1 Swift surface
- **Tool**: SwiftSyntax (semantic AST, not regex).
- **Library aids**: Harmonize (rule-based linter), SwiftSyntax cookbooks
  for visitor patterns.
- **Approach**: AST visitor walks declarations; per-rule classifier
  emits `:Convention` records keyed on `kind + module + sample_paths`.

### 3.2 Kotlin surface
- **Tool**: Konsist (production library for AST queries) +
  detekt rules (some can be reused).
- **Approach**: Konsist DSL queries enumerate constructs; per-rule
  classifier emits `:Convention` records.

### 3.3 Cross-language alignment
- **Tool**: semgrep custom rule pack as a portable layer for
  patterns expressible in plain pattern matching (e.g.,
  cross-language naming or structural outlier shapes).
- **Why semgrep**: shared rule format across Swift and Kotlin avoids
  reimplementing each rule twice.

### 3.4 Confidence vs heuristic
Per the original research inventory, confidence is `heuristic`. The
extractor reports a `confidence` field (`certain` for AST-derived,
`heuristic` for semgrep-derived) on each finding so the audit
renderer can grade severity accordingly.

## 4. Schema impact

```cypher
// Per-module convention summary (one node per detected convention)
(:Convention {
  project_id: string,         // "gimle" / "tronkit-swift" / "uw-ios" etc
  module: string,             // module path (Swift target, Gradle module)
  kind: string,               // e.g., "naming.test_class", "error.style"
  dominant_choice: string,    // e.g., "*Tests", "Result"
  confidence: string,         // "certain" | "heuristic"
  sample_count: int,          // how many sites support this
  outliers: int,              // sites that violate
  run_id: string              // back-ref to :IngestRun
})

// Per-site outlier (violations of a detected convention)
(:ConventionViolation {
  project_id, module, kind,
  file: string, start_line: int, end_line: int,
  message: string,            // e.g., "Test class named XKitTest, but module uses *Tests pattern"
  severity: string,           // "low" | "medium" | "high"
  run_id: string
})
```

Indices:
- `INDEX :Convention(project_id, module, kind)` — primary lookup.
- `INDEX :ConventionViolation(project_id, severity)` — severity filter.

## 5. `audit_contract()`

```python
def audit_contract(self) -> AuditContract:
    from palace_mcp.audit.contracts import AuditContract, Severity

    def severity_from_outlier_ratio(ratio: float) -> Severity:
        if ratio >= 0.1:
            return Severity.HIGH
        if ratio > 0:
            return Severity.MEDIUM
        return Severity.LOW

    return AuditContract(
        extractor_name="coding_convention",
        template_name="coding_convention.md",
        query="""
            MATCH (c:Convention {project_id: $project})
            OPTIONAL MATCH (v:ConventionViolation {project_id: $project, kind: c.kind})
            WITH c, collect(v) AS violations,
                 CASE
                   WHEN c.sample_count = 0 THEN 0.0
                   ELSE toFloat(c.outliers) / toFloat(c.sample_count)
                 END AS outlier_ratio
            RETURN c.module AS module,
                   c.kind AS kind,
                   c.dominant_choice AS dominant_choice,
                   c.confidence AS confidence,
                   c.sample_count AS sample_count,
                   c.outliers AS outliers,
                   violations AS violations,
                   outlier_ratio AS outlier_ratio
        """.strip(),
        severity_column="outlier_ratio",
        severity_mapper=severity_from_outlier_ratio,
    )
```

Audit report renders per-module convention summary + outlier list +
per-violation severity-graded lines.

## 6. Initial rule set (≤7 rules for v1, rev4 — was 8)

Concrete rule list, refined in CX-CTO formalisation. **Rev4 dropped
`structural.di_style`** — DI is #8's authoritative remit
(CTO-#8-M1 cross-coordination).

1. **`naming.type_class`** — UpperCamel vs UPPER_SNAKE on `class` /
   `struct` declarations.
2. **`naming.test_class`** — `*Tests` suffix vs `Test*` prefix vs
   `*Spec` for test classes.
3. **`naming.module_protocol`** — `*Protocol`, `*able`, `*ing` for
   protocols / interfaces.
4. **`structural.adt_pattern`** — sealed class (Kotlin) /
   enum-with-associated-values (Swift) vs class hierarchy.
5. **`structural.error_modeling`** — Result / throws / nullable /
   sentinel-string for error returns.
6. **`idiom.collection_init`** — `[]` vs `Array()` vs `listOf()` /
   typealias usage rates.
7. **`idiom.computed_vs_property`** — computed properties for derived
   values vs cached `@Lazy` / `lazy var`.

(Rule 6 `structural.di_style` from rev3 dropped — see Out-of-scope §2.)

## 7. Decision points

| ID | Question | Default | Impact of non-default |
|----|----------|---------|----------------------|
| **CC-D1** | Run on Swift only, Kotlin only, or both for v1? | both (CX team parity) | Swift-only = halves smoke time but breaks UW-Android ROI |
| **CC-D2** | Use Harmonize library or hand-roll SwiftSyntax visitors? | Harmonize for Swift (proven library) | hand-roll = +5d but no external dep |
| **CC-D3** | Use Konsist DSL or detekt rules for Kotlin? | Konsist (production AST DSL) | detekt = simpler but rule set is mostly check-mode, not classify-mode |
| **CC-D4** | semgrep adds value, or AST is sufficient? | semgrep adds value for cross-lang rules | drop semgrep = pure-AST, simpler but more code duplication across langs |
| **CC-D5** | Threshold for "outlier" status: percent vs absolute count? | 10% threshold + `min_sample_count=5` | absolute = simpler but breaks on small modules |

## 8. Test plan summary

- **Unit per rule**: synthetic Swift / Kotlin fixtures (good case +
  bad case + outlier case) → assert classifier returns correct
  `:Convention` + `:ConventionViolation` rows.
- **Integration**: real `tronkit-swift` ingest → assert ≥3
  `:Convention` rows + ≥0 violations.
- **Smoke**: `unstoppable-wallet-android` → manually inspect top-10
  conventions for plausibility.
- **Acceptance for audit-v1 §1 Architecture section** — convention
  data feeds the report; per `E-smoke.md` rev3 acceptance criteria.

## 9. Risks

- **R1 — false positives**: heuristic rules will surface non-issues.
  Mitigation: ship `confidence` field; renderer down-grades severity
  on heuristic-derived findings.
- **R2 — Swift / Kotlin tooling drift**: SwiftSyntax / Konsist
  versions move. Mitigation: pin in `pyproject.toml`; integration
  tests run on CI weekly to catch breakage.
- **R3 — module / target detection**: SwiftPM target boundary is
  clearer than Gradle module hierarchy. Mitigation: use existing
  `:Module` / `:Target` from Phase 1 symbol-index; do NOT
  re-discover.
- **R4 — performance**: walking large repos AST'ly is slow. Mitigation:
  per-batch processing (50 files × parallel workers); cache by file
  SHA (skip re-walk if file unchanged since last run).

## 10. Out of scope

- LLM-driven convention naming.
- Cross-project convention comparison (post-v1 if useful).
- Suggestions / auto-fixes (audit is read-only).
- Test-smell rules — covered by #38.

## 11. Cross-references

- Original research: `docs/research/extractor-library/report.md`
  §2.2 Conventional row #6 + `Coding_Convention_Extractor.json`.
- Roadmap row: `docs/roadmap-archive.md` §2.2 #6.
- Audit-V1 integration: feeds §2 Architecture and §3 Quality
  sections of audit report (after extractor merges).
- E6 prereq: `2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`.
- Companion: `2026-05-07-GIM-238-coding-convention-extractor.md`.
