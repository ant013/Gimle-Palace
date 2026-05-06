# Sprint S2 (B-min) — Audit-critical extractors for v1

**Goal**: ship the minimum-viable additional extractor set that audit
agents need to produce a credible report on a crypto-Kit. For v1, this
is a single extractor: **#40 Crypto Domain Model**.

**Wall-time**: ~1.5 weeks calendar (one Board+Claude session for
spec+plan + one paperclip team chain for impl).

**Driver**: without #40, the Security and BlockchainEngineer agents
have no Kit-specific signal beyond generic dead-code/hotspot. For
`tronkit-swift` / `bitcoinkit-swift` the operator's stated value is
"check that crypto invariants are right" — that's #40's exact remit.

**Definition of Done**:
1. New extractor `crypto_domain_model` registered in `EXTRACTORS`
   (`services/palace-mcp/src/palace_mcp/extractors/registry.py`).
2. Writes `:CryptoFinding` nodes (or `:IngestRun` extras +
   `:Project` properties — TBD in spec) with severity-graded
   address / decimal / checksum issues.
3. `audit_section_template.md` shipped with the extractor.
4. Operator runbook: `docs/runbooks/crypto-domain-model.md`.
5. Smoke runs on `tronkit-swift` (or `gimle` mini-fixture if real
   crypto-Kit not yet ingested) and produces ≥1 finding on a
   known-good test case.

**Explicitly NOT in this sprint**:
- #1 Architecture Layer Extractor — high-value but bigger
  surface; deferred to S6+ unless S4 smoke surfaces an
  architecture-specific gap.
- #2 Symbol Duplication Detector — needs embeddings infra; bigger
  slice; S6+ candidate.
- #34 Code Smell Structural — partially overlaps with #44 Hotspot
  (already merged); v1 audit can lean on Hotspot's per-function
  CCN. S6+ if smoke shows the gap.
- #7 Error Handling Policy — high-value for security; deferred to
  S6+. v1 audit Security section explicitly notes this as a blind
  spot.
- LLM-blocked: #11, #26, #35, #43 — wait for Ollama infra slice.

---

## Slices

### S2.1 — `#40 Crypto Domain Model` extractor

**Spec file**: `docs/superpowers/specs/<date>-GIM-NN-crypto-domain-model.md`
**Plan file**: `docs/superpowers/plans/<date>-GIM-NN-crypto-domain-model.md`
**Branch**: `feature/GIM-NN-crypto-domain-model`

**Scope** (rev1 — to be refined in brainstorm):

Reads from existing graph:
- `:File` (project_id, path) — from any symbol_index_*
- `:Symbol` (qualified_name, kind, file, start_line, end_line) —
  from symbol_index_swift / clang
- `:ExternalDependency.purl` — from dependency_surface
  (filter purl prefixes that match crypto libraries:
  `pkg:github/horizontalsystems/*`, `pkg:swift/*bigint*`,
  `pkg:swift/*crypto*`, etc.)

Writes:
- `:CryptoFinding {project_id, kind, severity, file, start_line, end_line, message, run_id}`
  - `kind ∈ {address_validation_missing, decimal_unit_confusion,
    checksum_invariant_violation, key_storage_pattern,
    arithmetic_overflow_risk, ...}`
  - `severity ∈ {critical, high, medium, low}`

Detection strategy: **semgrep custom rules over Swift source**.
Per-rule severity + message in YAML. Parser runs `semgrep --config
<rule-bundle> --json <repo>` and ingests findings.

**Tool stack** (per roadmap):
- `semgrep` Python package (already pinned in palace-mcp)
- Custom rule bundle at
  `services/palace-mcp/src/palace_mcp/extractors/crypto_domain_model/rules/`

**Why semgrep, not LLM**: deterministic, fast, no Ollama dep,
auditable rules (operator can read `address_validation.yml` and
understand why a finding fired). LLM-bearing version is a
separate followup if rules prove too coarse.

**Initial rule set (≤10 rules for v1)** — to be specified in
brainstorm; candidate list:
1. `address_no_checksum_validation` — Swift `String → Address`
   construction without `try` + checksum verifier.
2. `decimal_raw_uint_arithmetic` — `BigInt * 10^18` literals
   without a `Decimals` wrapper.
3. `wei_eth_unit_mix` — heuristic for variables named `wei` and
   `eth` in same expression.
4. `private_key_string_storage` — `String` typed property named
   `*Key*` or `*PrivateKey*`.
5. `bignum_overflow_unguarded` — `BigUInt` arithmetic in `try?`-
   wrapped block.

(Operator confirms set in brainstorm.)

**Audit section template** (`extractors/crypto_domain_model/audit_section_template.md`):

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

**Provenance**: run_id `{{ run_id }}` completed {{ completed_at }}; rule bundle version `{{ rule_bundle_version }}`.

{% else %}
No findings — extractor `crypto_domain_model` ran at `{{ run_id }}`,
scanned `{{ files_scanned }}` files against `{{ rules_active }}` rules,
found 0 issues.
{% endif %}
```

**Test plan** (per spec):
- Unit: per-rule fixture (good case + bad case) → semgrep returns
  expected match count.
- Integration: synthetic fixture with known good + bad files →
  extractor writes expected `:CryptoFinding` count.
- Smoke (manual): run on `tronkit-swift` real source via Track A
  fixture → manually inspect findings for plausibility.

**Decision points (operator confirms in brainstorm)**:
- D1: 5-rule v1 vs broader (10+ rules) v1?
- D2: severity rank scheme — 4 levels (`critical/high/medium/low`)
  vs 5 (add `informational`)?
- D3: extractor scope — Swift only for v1, or also Solidity / Kotlin?
  Default Swift only (matches operator product target = tronKit
  + bitcoinKit).
- D4: rule pack versioning — single `v1.yml` baseline vs
  `rules-2026-05-06/`-style snapshots? Default single bundle
  versioned by git SHA.
- D5: duplicate rule firing on same line — coalesce vs preserve?
  Default coalesce, take highest severity.

---

### S2.2 (deferred — listed for transparency, NOT in v1)

These are NOT v1 sprint slices. They're documented here so the
operator can pick them up post-v1 as S6+ slices via the standard
intake protocol (`docs/roadmap.md` §"Post-v1 slice intake").

| # | Name | Rationale for deferral | Trigger to start |
|---|------|------------------------|------------------|
| 1 | Architecture Layer | Big surface; needs cross-language schema decisions; v1 audit Architecture section uses public_api_surface + cross_module_contract data which is sufficient for first pass | After 2-3 audit reports surface "architectural drift" gaps |
| 2 | Symbol Duplication | Needs embedding infra (sentence-transformers / UniXcoder) deploy; that's a separate infra slice | After embedding infra lands |
| 7 | Error Handling Policy | High-value for security but semgrep rule set design is itself a small spec; can run after #40's rule-design pattern is proven | After #40 is in production for ≥1 week |
| 34 | Code Smell Structural | Partial overlap with `hotspot` (already merged) — function-level CCN is in `palace.code.list_functions`; the gap is per-line smell counters which is incremental | After v1 audit shows "we want per-line smell density" |

When operator triggers any of these, follow the same Board+Claude
+ paperclip pattern: brainstorm Q-round → spec rev1 → 4-agent
audit → spec rev2 → TDD plan → push branch → create paperclip
issue. Same pattern as GIM-216 / GIM-218.

---

## Why ONLY #40 in v1 (justification)

1. **Operator's product target is `tronkit-swift` + `bitcoinkit-swift`** —
   crypto Kits where #40's rule output is the highest single signal
   per dollar of effort.
2. **The other 4 from Phase B don't kill v1**:
   - #1 Architecture Layer — first audit can use `public_api_surface`
     + `cross_module_contract` (already merged) for layer/contract
     view. Gap is acceptable for v1; explicitly disclosed in
     report's blind-spots section.
   - #2 Symbol Duplication — operator will see duplication via
     manual review of 41-Kit reports; auto-detection is nice-to-
     have, not v1-blocking.
   - #34 Code Smell — `hotspot` ships per-function CCN already.
   - #7 Error Handling — security-relevant but operator-time-on-
     rules is high; defer until after #40 proves the semgrep
     pattern.
3. **Adding #40 to existing infra is small** — one extractor slice
   following the same pattern as `dead_symbol_binary_surface`
   (GIM-193): semgrep-style detection + write findings to graph.
4. **Post-v1 paved path absorbs the others** — once v1 ships,
   #1/#2/#7/#34 each plug in as S6+ slices without re-touching
   audit workflow.

## Cross-references

- Overview: `audit-v1-overview.md`
- Workflow / agent definitions: `D-audit-orchestration.md`
- Renderer / templates: `D-audit-orchestration.md` §S1.2, S1.3
- Post-v1 intake: `docs/roadmap.md` §"Post-v1 slice intake protocol"
