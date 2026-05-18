# Testability / DI Pattern Extractor (#8) — Specification

**Document date:** 2026-05-07
**Status:** Draft · awaiting CX-CTO formalisation (post-E6 close)
**Author:** Board+Claude session (operator + Claude Opus 4.7)
**Team:** Codex (CX-native: Konsist + Harmonize + detekt + MockK/Mockito patterns + SwiftSyntax)
**Slice ID:** Phase 2 §2.2 #8 Testability/DI Pattern Extractor
**Companion plan:** `2026-05-07-testability-di-pattern-extractor_plan.md`
**Branch:** `feature/GIM-NN-testability-di-extractor`
**Blockers (rev4):**
- **E6 closure** (CX hire).
- **S0.1 IngestRun schema unification** (rev4 — CTO-XF-H1) — uses unified schema; wait for S0 if it lands later than E6.

---

## 1. Goal

Extract dependency-injection style + test-double patterns + testability
markers from Swift + Kotlin source so audit agents can answer:

- "Is this code unit-testable, or does it bake in concrete
  collaborators?"
- "What DI style does this project use — manual init injection,
  framework-bound (Hilt/Koin/Resolver/Swinject), property-based?"
- "Are mocks / stubs / fakes used consistently, or is there a mix
  of MockK + Mockito + hand-rolled fakes that drift over time?"

Addresses target problem **#11 (testability / DI pattern coverage)**
in the original 45-extractor research inventory.

**Definition of Done:**

1. New extractor `testability_di` registered in `EXTRACTORS`.
2. `audit_contract()` returns per-module DI style + per-collaborator
   pattern as a Pydantic response model.
3. Writes `:DiPattern` + `:TestDouble` + `:UntestableSite` nodes.
4. `audit/templates/testability_di.md` ships.
5. Operator runbook `docs/runbooks/testability-di.md`.
6. Smoke on `tronkit-swift` + `unstoppable-wallet-android` produces
   ≥1 detected DI style + ≥0 untestable sites with severity grading.

## 2. Scope

### In scope
- **DI style classification per module**:
  - manual init-injection
  - property-injection
  - factory-method DI
  - framework-bound (Hilt, Koin, Resolver, Swinject)
  - service-locator (anti-pattern flagged)
- **Test-double pattern detection**:
  - MockK / Mockito (Kotlin) usage rate per test target
  - hand-rolled fake / stub class detection
  - Cuckoo / Mockito.swift / hand-rolled (Swift)
- **Untestable-site detection**:
  - hard-coded singleton access (`SharedPrefs.getInstance()` /
    `UserDefaults.standard` directly inside business logic)
  - direct `URLSession.shared` use without abstraction
  - `Date()` / `Calendar.current` access without injectable clock
  - file-system / network call without protocol seam

### Out of scope
- Test smell detection (#38).
- Coverage gap (#28 covers actual coverage measurement).
- Mutation testing.
- Test runner config drift.

### Cross-reference with #6 Coding Convention (rev4 — CTO-#8-M1)

#6 also has a `structural.di_style` rule. To avoid double-counting
DI patterns:

- **#8 (this extractor) is the AUTHORITATIVE source** for DI analysis.
  Audit report §3 Quality cites `:DiPattern` rows.
- **#6's `structural.di_style`** is a coarse convention summary signal
  only; it should NOT contradict #8. If #6 detects "init_injection"
  in a module where #8 finds "framework_bound (Hilt)", #8 wins (more
  detail).
- **Recommended action during #6 implementation**: drop
  `structural.di_style` from #6's rule set entirely (down to 7 rules)
  and add a cross-link in the audit template referencing #8's
  `:DiPattern` for DI questions. This is a #6 spec change, not a #8
  one — flagged here for cross-coordination.

## 3. Detection strategy

| Surface | Tool | Method |
|---|---|---|
| Kotlin DI style | Konsist DSL queries | match init-injection / property-injection / `@Inject` |
| Kotlin frameworks | detekt + AST | detect Hilt / Koin / Dagger declarations |
| Kotlin mocks | semgrep + AST | detect `mockk()` / `mock()` calls per target |
| Swift DI style | SwiftSyntax visitor | match init-injection / property / dependency-resolver |
| Swift frameworks | semgrep | detect Resolver / Swinject / Cleanse imports |
| Swift mocks | SwiftSyntax + naming | match `*Spy`, `*Stub`, `*Fake`, `*Mock` classes |
| Untestable sites | semgrep cross-lang | match `*.shared` / `*.getInstance()` / `Date()` in non-test files |

### Confidence
`heuristic` per research inventory. Per-finding `confidence` field.

## 4. Schema impact

```cypher
(:DiPattern {
  project_id, module,
  style: string,            // "init_injection" | "property_injection" | "factory" | "framework_bound" | "service_locator"
  framework: string|null,   // "hilt" | "koin" | "dagger" | "resolver" | "swinject" | null
  sample_count: int,
  outliers: int,
  confidence: string,       // "certain" | "heuristic"
  run_id: string
})

(:TestDouble {
  project_id, module,
  kind: string,             // "mockk" | "mockito" | "spy" | "stub" | "fake" | "hand_rolled"
  target_symbol: string,    // qualified name of mocked type
  test_file: string,
  run_id: string
})

(:UntestableSite {
  project_id, module,
  file, start_line, end_line,
  category: string,         // "singleton" | "hardcoded_session" | "direct_clock" | "direct_filesystem" | "direct_network"
  symbol_referenced: string,
  severity: string,         // "low" | "medium" | "high"
  message: string,
  run_id: string
})
```

Indices:
- `INDEX :DiPattern(project_id, module)`.
- `INDEX :UntestableSite(project_id, severity)`.

## 5. `audit_contract()`

```python
def audit_contract(self) -> AuditContract:
    return AuditContract(
        query="""
            MATCH (di:DiPattern {project: $project})
            OPTIONAL MATCH (us:UntestableSite {project: $project, module: di.module})
            RETURN di, collect(us) AS untestable
        """,
        response_model=TestabilityDiAuditList,
        template_path=Path("audit/templates/testability_di.md"),
        severity_mapper=lambda di: "high" if di.style == "service_locator" else "medium" if di.outliers > 0 else "low",
    )
```

## 6. Initial rule set (≤7 rules)

1. **`di.init_injection`** — ctor-arg injection of collaborators.
2. **`di.property_injection`** — `@Inject lateinit var` (Kotlin),
   `@Resolver` property (Swift Resolver).
3. **`di.framework_bound`** — Hilt `@HiltAndroidApp` / Koin module /
   Dagger component / Swinject Container.
4. **`di.service_locator`** — `*.shared` / `*.getInstance()` in
   non-DI-config code (anti-pattern).
5. **`mock.style`** — MockK / Mockito / Cuckoo per test class.
6. **`untestable.singleton_access`** — `*.shared` / `*.getInstance()`
   in business-logic file.
7. **`untestable.direct_clock`** — `Date()` / `Calendar.current` /
   `Instant.now()` in non-test code (no injectable clock).

## 7. Decision points

| ID | Question | Default | Impact |
|----|----------|---------|--------|
| **TD-D1** | Run on Swift only / Kotlin only / both | both | Swift-only halves smoke time, breaks UW-Android ROI |
| **TD-D2** | service-locator severity = high or medium? | high (operator-confirmable) | medium = soft signal, harder to action |
| **TD-D3** | Test-double `:TestDouble` kept in graph or just counted? | kept (lets audit say "MockK usage 70% / Mockito 25% / hand-rolled 5%") | counted = lighter graph, less detail |
| **TD-D4** | Untestable-site detection scope — only crypto/wallet paths or whole project? | whole project; severity higher in critical paths | crypto-only = focused but misses general anti-patterns |
| **TD-D5** | semgrep cross-lang rule for `*.shared` — too noisy? | start permissive; tune in smoke | strict = misses real cases |

## 8. Test plan

- **Unit per rule**: Swift + Kotlin fixtures (good / bad / outlier).
- **Integration**: synthetic Swift Kit + Kotlin module → assert
  `:DiPattern` rows + `:UntestableSite` rows match expected.
- **Smoke**: `tronkit-swift` real source → operator + BlockchainEngineer
  review top-5 untestable sites for false-positive rate ≤2/5.

## 9. Risks

- **R1**: framework detection misses custom DI helpers. Mitigation:
  rule set starts conservative; add custom-helper rules per smoke
  evidence.
- **R2**: heuristic mock detection conflates spy/stub/fake. Mitigation:
  `kind` field optional; renderer presents detected categories
  faithfully without re-classifying.
- **R3**: `*.shared` / `getInstance()` is sometimes legitimate
  (system APIs). Mitigation: allowlist for `URLSession.shared`,
  `FileManager.default`, `UserDefaults.standard` in DI-config files
  only; flag in business logic.
- **R4**: performance on large repos. Mitigation: per-batch + cache by
  file SHA.

## 10. Out of scope

- Test runner / CI infrastructure validation.
- Test coverage measurement (#28).
- Mutation testing / hypothesis-test detection.
- Auto-fix / refactor suggestions.

## 11. Cross-references

- Original research: `docs/research/extractor-library/report.md` §2.2
  row #8.
- Roadmap: `docs/roadmap-archive.md` §2.2 #8.
- E6 prereq: `2026-05-07-cx-team-hire-blockchain-security-pyorch_*.md`.
- Audit-V1 integration: feeds §3 Quality + §4 Security
  (untestable-site signals).
- Companion: `2026-05-07-testability-di-pattern-extractor_plan.md`.
