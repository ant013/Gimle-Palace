# Sprint S2 (B-min) — Audit-critical extractors for v1

> **Rev2** (2026-05-06): adds mandatory semgrep-Swift spike as prerequisite
> (CTO-HIGH-4, CR-HIGH-2, OPUS-HIGH-3). Removes "already pinned" claim.
> Adds fallback options. Adjusts timing: starts after S1.6 frees PE.

**Goal**: ship the minimum-viable additional extractor set that audit
agents need to produce a credible report on a crypto-Kit. For v1, this
is a single extractor: **#40 Crypto Domain Model**.

**Wall-time**: ~2 weeks calendar (spike: ~2 days; spec+plan: ~2 days;
one paperclip team chain for impl: ~1 week).

**Driver**: without #40, the Security and BlockchainEngineer agents
have no Kit-specific signal beyond generic dead-code/hotspot. For
`tronkit-swift` / `bitcoinkit-swift` the operator's stated value is
"check that crypto invariants are right" — that's #40's exact remit.

**Timing (rev2)**: S2 starts after S1.6 frees PythonEngineer (~week 3),
not in parallel with S1 as rev1 claimed (CTO-MEDIUM-1 — same PE
needed for both).

**Definition of Done**:
1. New extractor `crypto_domain_model` registered in `EXTRACTORS`.
2. Implements `audit_contract()` (rev2) returning query, response model,
   and template path — report section auto-discovered.
3. Writes `:CryptoFinding` nodes with severity-graded findings.
4. `audit/templates/crypto_domain_model.md` shipped with the extractor.
5. Operator runbook: `docs/runbooks/crypto-domain-model.md`.
6. Smoke runs on `tronkit-swift` and produces ≥1 finding on a
   known-good test case.

**Explicitly NOT in this sprint**:
- #1 Architecture Layer Extractor — deferred to S6+.
- #2 Symbol Duplication Detector — needs embeddings infra; S6+.
- #34 Code Smell Structural — partial overlap with Hotspot; S6+.
- #7 Error Handling Policy — deferred to S6+ (per AV1-D7, operator
  explicitly confirms this blind spot is acceptable for v1).
- LLM-blocked: #11, #26, #35, #43 — wait for Ollama infra slice.

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

**Scope** (rev1 — to be refined in brainstorm):

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

### S2.2 (deferred — listed for transparency, NOT in v1)

| # | Name | Rationale for deferral | Trigger to start |
|---|------|------------------------|------------------|
| 1 | Architecture Layer | Big surface; v1 uses public_api + cross_module | After 2-3 audit reports surface gaps |
| 2 | Symbol Duplication | Needs embedding infra | After embedding infra lands |
| 7 | Error Handling Policy | High-value but deferred per AV1-D7 | After #40 pattern proven ≥1 week |
| 34 | Code Smell Structural | Overlaps with hotspot CCN | After v1 shows density gap |

---

## Why ONLY #40 in v1

1. Operator's target is crypto Kits — #40's rule output is highest ROI.
2. Other 4 don't kill v1 — disclosed as blind spots.
3. Adding #40 follows proven extractor pattern.
4. Post-v1 paved path (rev2: `audit_contract()`) absorbs the rest.

## Cross-references

- Overview: `audit-v1-overview.md`
- Workflow / agent definitions: `D-audit-orchestration.md`
- Renderer / templates: `D-audit-orchestration.md` §S1.2, S1.3
- Post-v1 intake: `docs/roadmap.md` §"Post-v1 slice intake protocol"
- Semgrep spike precedent: `docs/research/` directory
