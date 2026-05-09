# Sprint S2 — Audit-critical extractors for v1

> **Rev3** (2026-05-07): AV1-D7 flipped → #1 Architecture Layer (S2.2) and
> #7 Error Handling Policy (S2.3) added; sprint split into S2.1 / S2.2 / S2.3.
> Wall-time ~2w → ~8w sequential (or ~3w if #1‖#7 parallelised across two
> Claude engineers). Operator decision GIM-219 2026-05-07.
>
> **Rev2** (2026-05-06): adds mandatory semgrep-Swift spike as prerequisite
> (CTO-HIGH-4, CR-HIGH-2, OPUS-HIGH-3). Removes "already pinned" claim.
> Adds fallback options. Adjusts timing: starts after S1.6 frees PE.

**Goal** (rev3): ship the audit-critical extractor set so audit agents
produce a credible blockchain/security report on a crypto-Kit. For v1
this is **three extractors**: #40 Crypto Domain Model, #1 Architecture
Layer, #7 Error Handling Policy.

**Wall-time** (rev3): ~8 weeks sequential (S2.1 ~2w + S2.2 ~3w + S2.3
~3w on single Claude PE) or ~5 weeks if S2.2 ‖ S2.3 (different files,
two Claude engineers). Spike ~2 days, spec+plan ~2 days each, paperclip
team chain ~1w (S2.1) / ~2w (S2.2 / S2.3 — bigger surfaces).

**Driver**: without these three, the audit report has too many §9 blind
spots to credibly serve as a blockchain auditor's deliverable:
- **#40 (S2.1)** — crypto invariants (address checksum, decimal handling,
  signed-vs-unsigned arithmetic). Without it the Security/BlockchainEngineer
  agents have no Kit-specific signal beyond generic dead-code/hotspot.
- **#1 (S2.2, rev3)** — module/layer violations (`wallet-core` must not
  import UI; `Kit X` must not depend on `Kit Y`). Foundational for an
  architecture review section.
- **#7 (S2.3, rev3)** — swallowed catch / inconsistent error handling.
  In a Wallet Kit, swallowed crypto errors → potential lost funds; this
  is non-negotiable for a security review section.

**Timing**: S2.1 starts after S1.6 frees PythonEngineer (~week 3-4),
not ‖ S1 as rev1 claimed (CTO-MEDIUM-1). S2.2 starts after S2.1 ships
on the same PE; S2.3 after S2.2 (or ‖ S2.2 if a second Claude engineer
is available — different file trees, no overlap).

**Definition of Done** (rev3 — three extractors, each with same contract):

For each of `crypto_domain_model` (S2.1), `arch_layer` (S2.2),
`error_handling_policy` (S2.3):
1. New extractor registered in `EXTRACTORS`.
2. Implements `audit_contract()` (rev2) returning query, response model,
   and template path — report section auto-discovered.
3. Writes domain-specific finding nodes with severity-graded findings.
4. `audit/templates/<extractor_name>.md` shipped.
5. Operator runbook: `docs/runbooks/<extractor_name>.md`.
6. Smoke runs on `tronkit-swift` and produces ≥1 finding on a
   known-good test case (or explicit "clean — 0 findings" with rationale).

**Explicitly NOT in this sprint** (rev3):
- #2 Symbol Duplication Detector — needs embeddings infra; S6+.
- #34 Code Smell Structural — partial overlap with Hotspot; S6+ if smoke
  shows density gap.
- LLM-blocked: #11, #26, #35, #43 — wait for Ollama infra slice.

**Moved INTO this sprint** (rev3, was previously deferred):
- #1 Architecture Layer (now S2.2) — operator AV1-D7 flip.
- #7 Error Handling Policy (now S2.3) — operator AV1-D7 flip.

---

## Prerequisites (rev2 addition)

### S2-prereq: semgrep-on-Swift verification spike

**Problem**: S2.1 originally claimed "semgrep Python package (already pinned
in palace-mcp)" — this is **false**: semgrep is NOT in `pyproject.toml`.
Additionally, semgrep's Swift support maturity is unverified (OPUS-HIGH-3).

**Spike scope** (`docs/research/semgrep-swift-spike/`):
1. Install semgrep in palace-mcp Docker container; measure image size impact.
2. Write 1 real semgrep rule against `tronkit-swift` Swift source
   (e.g., `address_no_checksum_validation`).
3. Run against 100+ Swift files; measure: hit count, false-positive rate, runtime.
4. Document Swift tree-sitter grammar coverage for the patterns we need.
5. **Decision**: if false-positive rate > 30% or Swift grammar gaps block
   ≥2 of the 5 candidate rules → switch to fallback.

**Fallback options** (ordered by preference):
- `ast-grep` — Rust-based, lighter (~10MB vs ~500MB semgrep), good Swift support.
- Regex heuristics over Swift source — simplest, least accurate, no external dep.
- `tree-sitter-swift` + custom Python walker — medium complexity, good accuracy.

**Size**: ~1-2 days (spike only, not impl).
**Must complete before S2.1 spec brainstorm.**

---

## Slices

### S2.1 — `#40 Crypto Domain Model` extractor

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-crypto-domain-model.md`
**Plan file**: `docs/superpowers/plans/<date>-GIM-NN-crypto-domain-model.md`
**Branch**: `feature/GIM-NN-crypto-domain-model`

**Scope** (rev3 + GIM-243 formalisation):

Reads from existing graph:
- `:File` (project_id, path) — from any symbol_index_*
- `:Symbol` (qualified_name, kind, file, start_line, end_line) —
  from symbol_index_swift / clang
- `:ExternalDependency.purl` — from dependency_surface

Writes:
- `:CryptoFinding {project_id, kind, severity, file, start_line, end_line, message, run_id}`

Implements `audit_contract()` (rev2):
```python
def audit_contract(self) -> AuditContract:
    return AuditContract(
        query="MATCH (f:CryptoFinding {project: $project}) RETURN f ...",
        response_model=CryptoFindingList,
        template_path=Path("audit/templates/crypto_domain_model.md"),
        severity_mapper=crypto_severity,
    )
```

**Detection strategy**: Determined by spike outcome (see S2-prereq above).
Default: semgrep custom rules. Fallback: ast-grep or regex.

**Initial rule set (≤10 rules for v1)** — concrete YAML produced by spike:
1. `address_no_checksum_validation`
2. `decimal_raw_uint_arithmetic`
3. `wei_eth_unit_mix`
4. `private_key_string_storage`
5. `bignum_overflow_unguarded`

(Operator confirms set in brainstorm. CR-LOW-1: spike must produce
≥3 concrete rule files before TDD plan starts.)

**Audit section template** (`audit/templates/crypto_domain_model.md`):

```markdown
## Crypto domain findings ({{ kit_name }})

{% if findings %}
### Critical / high
{% for f in critical_high %}
- **{{ f.severity }}** [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}

### Medium / low
{% for f in medium_low %}
- {{ f.severity }} [{{ f.kind }}] `{{ f.file }}:{{ f.start_line }}` — {{ f.message }}
{% endfor %}

**Provenance**: run_id `{{ run_id }}` completed {{ completed_at }}.

{% else %}
No findings — extractor `crypto_domain_model` ran at `{{ run_id }}`,
scanned `{{ files_scanned }}` files against `{{ rules_active }}` rules,
found 0 issues.
{% endif %}
```

**Test plan**:
- Unit: per-rule fixture (good case + bad case).
- Integration: synthetic fixture → expected `:CryptoFinding` count.
- Smoke: tronkit-swift real source → manually inspect findings.

**Decision points**:
- D1: 5-rule v1 vs broader (10+)?
- D2: severity scheme — 4 levels vs 5 (add `informational`)?
- D3: Swift only for v1? (Default yes.)
- D4: rule versioning — single bundle by git SHA.
- D5: duplicate rule firing — coalesce, take highest severity.

---

### S2.2 — `#1 Architecture Layer` extractor (rev3)

**Spec file**: `docs/superpowers/specs/2026-05-08-GIM-243-arch-layer-extractor_spec.md`
**Plan file**: `docs/superpowers/plans/2026-05-08-GIM-243-arch-layer-extractor.md`
**Branch**: `feature/GIM-243-arch-layer-extractor`
**Team**: Claude (per `roadmap.md` §2.1 #1; deterministic, Python orchestration).

**CTO formalisation (GIM-243, 2026-05-08)**:
- `AuditContract` example below is superseded by the current S1/GIM-239 shape:
  `extractor_name`, `template_name`, `query`, `severity_column`,
  `max_findings`, `severity_mapper`.
- Module-level dependencies MUST use a new `:MODULE_DEPENDS_ON` edge. Existing
  `:DEPENDS_ON` remains owned by `dependency_surface` as
  `(:Project)-[:DEPENDS_ON]->(:ExternalDependency)`.
- `modules-graph-assert`, ArchUnit-compatible syntax and tree-sitter are not
  part of v1 unless a fresh `docs/research/*arch-layer*spike/` artifact is
  produced first. Default implementation path is conservative Python parsing.

**Scope** (rev1 — to be refined in brainstorm):

Reads from existing graph + repo:
- `:File` (project_id, path) — from any symbol_index_*
- `:Symbol` — from symbol_index_swift (and clang for native deps)
- Per-module manifests: `Package.swift` (SwiftPM), `build.gradle.kts` (Gradle)
- Existing `dependency_surface` graph may be used as optional context, but
  `arch_layer` must not require it and must not change its relationship shape.

Writes:
- `:Module {project_id, slug, kind: "swiftpm"|"gradle", manifest_path}`
- `:Layer {project_id, name, rule_source}` — declared via convention or
  manifest (e.g., SwiftPM target type, Gradle plugin tag).
- `(:Module)-[:MODULE_DEPENDS_ON {scope, declared_in, evidence_kind, run_id}]->(:Module)`
  — intra-project edges.
- `(:Module)-[:IN_LAYER]->(:Layer)`.
- `:ArchViolation {project_id, kind, severity, src_module, dst_module, rule, message, run_id}`
  — when an actual edge violates a declared layer rule.

Implements `audit_contract()`:
```python
def audit_contract(self) -> AuditContract:
    return AuditContract(
        extractor_name="arch_layer",
        template_name="arch_layer.md",
        query="MATCH (v:ArchViolation {project_id: $project_id}) ... RETURN v ...",
        severity_column="severity",
        severity_mapper=arch_severity,
    )
```

**Detection strategy**:
- **Swift**: parse `Package.swift` (Swift Package Manager) for targets +
  declared `dependencies`; build module graph; apply layer rules from
  `.palace/architecture-rules.yaml` or `docs/architecture-rules.yaml`.
- **Kotlin/Gradle**: parse `settings.gradle.kts` includes and direct
  `project(":module")` dependencies from module `build.gradle.kts` files.
- **Import evidence**: conservative text scanner for Swift/Kotlin/Java imports.
  No new external tooling dependency in v1 unless a fresh spike is reviewed.

**Initial rule set (≤6 rules for v1)** — concrete YAML produced by spike:
1. `wallet_core_no_ui_import` — `*-core` modules MUST NOT import `*-ui`
2. `kit_no_kit_import` — `*-kit` modules MUST NOT depend on other `*-kit`
   except via declared cross-Kit interface
3. `domain_no_infra` — `domain/*` MUST NOT import `infra/*`
4. `no_circular_module_deps` — strongly-connected-components check
5. `manifest_dep_actually_used` — declared dep with no AST import = warn
6. `ast_dep_not_declared` — AST import without manifest declaration = error

**Audit section template** (`audit/templates/arch_layer.md`): module DAG
summary + violation list (severity-grouped) + provenance.

**Test plan**:
- Unit: per-rule fixture (good case + bad case) on synthetic SwiftPM/Gradle.
- Integration: real `tronkit-swift` `Package.swift` → expected `:Module` count.
- Smoke: tronkit-swift real source → ≥0 violations (clean target is OK if
  declared explicitly).

**Decision points**:
- AL-D1: Where do layer rules live? (Default: `docs/architecture-rules.yaml`
  per project; shipped from convention scaffold.)
- AL-D2: Default behaviour when project has NO rule file? (Default: emit
  module DAG only, no violations; report says "no rules declared".)
- AL-D3: Cross-Kit rules at bundle level? (v1 default: per-project only;
  bundle-level deferred to S5 retrospective.)

**Wall-time**: ~3 weeks (spec+plan ~3 days; paperclip team chain ~2w —
larger surface than #40 because of two-language manifest parsing).

---

### S2.3 — `#7 Error Handling Policy` extractor (rev3)

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-error-handling-policy.md`
**Plan file**: `docs/superpowers/plans/<date>-GIM-NN-error-handling-policy.md`
**Branch**: `feature/GIM-NN-error-handling-policy`
**Team**: Claude (per `roadmap.md` §2.2 #7; heuristic, semgrep + ast-grep
+ detekt — Python orchestration).

**Scope** (rev1 — to be refined in brainstorm):

Reads:
- `:File` + `:Symbol` from symbol_index_swift (Swift) and symbol_index_java
  (Kotlin/Java).
- AST via SwiftSyntax (Swift) + tree-sitter / detekt (Kotlin) per file batch.

Writes:
- `:CatchSite {project_id, file, start_line, end_line, swallowed: bool, kind, rethrows: bool}`
  — every catch/do-catch block with classification.
- `:ErrorPolicy {project_id, module, style: "result"|"throws"|"nullable"|"mixed", confidence}`
  — per-module aggregate.
- `:ErrorFinding {project_id, kind, severity, file, start_line, message, run_id}`
  — surfaced violations (e.g., empty-catch in signing path).

Implements `audit_contract()` returning standard fields → renders
`audit/templates/error_handling_policy.md`.

**Detection strategy**: pattern set decided in spike:
- **Swift**: SwiftSyntax visitor walking `do { try } catch` AST nodes.
  Empty catch detection, `catch { }` discarding error, `try?` swallow
  in critical paths (heuristic: file paths matching `*Sign*`, `*Crypto*`,
  `*Balance*`, `*Wallet*`).
- **Kotlin**: detekt rules `EmptyCatchBlock`, `TooGenericExceptionCaught`,
  `SwallowedException`; semgrep custom rules on top for Kit-specific
  patterns.
- **Cross-language**: ast-grep rules for inconsistency between modules
  (e.g., one Kit returns `Result<T, E>`, neighbour returns `T?`).

**Initial rule set (≤8 rules for v1)** — produced by spike:
1. `empty_catch_in_crypto_path`
2. `try_optional_swallow_in_signing`
3. `result_throws_mix_within_module`
4. `generic_exception_caught_at_kit_boundary`
5. `rethrow_loses_original_context`
6. `catch_to_log_silent_failure`
7. `error_returned_as_string_not_typed`
8. `nil_coalesce_swallows_decode_error`

**Audit section template** (`audit/templates/error_handling_policy.md`):
per-module policy summary + finding list (severity-grouped) + provenance.

**Test plan**:
- Unit: per-rule fixture (good + bad) on Swift + Kotlin samples.
- Integration: synthetic Swift Kit → expected `:CatchSite` count + policies.
- Smoke: tronkit-swift → operator + BlockchainEngineer review top-5 findings
  for false-positive rate (target ≤2/5).

**Decision points**:
- EHP-D1: Which file-path heuristic identifies "critical paths"? (Default:
  regex over file path; refine post-smoke.)
- EHP-D2: Severity mapping for swallowed catch? (Default: `high` in critical
  paths, `medium` elsewhere, `low` if `// MARK: deliberate` comment present.)
- EHP-D3: Cross-module policy mismatch — error or warn? (Default: warn at
  v1; promote to error if smoke evidence supports.)

**Wall-time**: ~3 weeks (spec+plan ~3 days; paperclip team chain ~2w).

---

### S2.4 (deferred — listed for transparency, NOT in v1)

| # | Name | Rationale for deferral | Trigger to start |
|---|------|------------------------|------------------|
| 2 | Symbol Duplication | Needs embedding infra | After embedding infra lands |
| 34 | Code Smell Structural | Overlaps with hotspot CCN | After v1 shows density gap |

---

## Why this scope (rev3)

1. **#40 (S2.1)** — operator's target is crypto Kits; rule output is
   highest ROI per week.
2. **#1 (S2.2)** — module/layer violations are foundational for any
   architecture review; without them §1 of report is hollow.
3. **#7 (S2.3)** — swallowed errors in crypto code paths are the kind of
   issue that loses user funds; cannot be a §9 disclaimer in a Wallet
   audit.
4. **All three** follow the proven extractor pattern + `audit_contract()`
   paved path — they don't require orchestrator changes.
5. Post-v1 paved path (rev2: `audit_contract()`) absorbs #2 / #34 / LLM-
   blocked extractors as iterative S6+ slices.

## Cross-references

- Overview: `audit-v1-overview.md`
- Workflow / agent definitions: `D-audit-orchestration.md`
- Renderer / templates: `D-audit-orchestration.md` §S1.2, S1.3
- Post-v1 intake: `docs/roadmap.md` §"Post-v1 slice intake protocol"
- Semgrep spike precedent: `docs/research/` directory
