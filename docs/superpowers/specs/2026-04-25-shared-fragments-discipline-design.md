---
slug: shared-fragments-discipline
status: proposed
branch: feature/GIM-82-shared-fragments-discipline (cut from develop after umbrella lands)
paperclip_issue: 82
parent_umbrella: 79
predecessor: develop tip after umbrella merge
date: 2026-04-25
---

# GIM-81 — Shared-fragments discipline updates (branch hygiene + evidence rigor + spec quality)

## 1. Context

Three repeated process failures in the N+1 sessions (GIM-74/75/76):

1. **Cross-branch contamination** — PE on `feature/GIM-76-codebase-memory-sidecar` carried a `chore(gim75): ingest→extractor refactor` commit (`e7ff6d5`) so local tests would pass while GIM-75 was unmerged. Later cleanup of that commit accidentally regressed `register_code_tools(_tool)` deletion → entire GIM-76 deliverable was dead code (caught by CR Phase 3.1 re-review).
2. **False evidence claims** — PE wrote "no new mypy --strict errors, all 8 are pre-existing" on GIM-76 Phase 2; CR found 4 new ones in `code_router.py`. Saved time wasted in re-review cycle.
3. **Spec changing existing-field semantics without grep audit** — N+1a.1 §3.10 declared "`:Project` stores slug in `EntityNode.name`" without `grep -r 'p\.name' src/` audit. `cypher.py:UPSERT_PROJECT` already used `name` for display string. OpusArchitectReviewer caught the latent production bug at Phase 3.2.

These are discipline gaps, not technical bugs. Each can be plugged with a one-page checklist in the existing paperclip-shared-fragments submodule, where every Gimle agent already pulls per-phase rules.

## 2. Problem

The shared-fragments repo (`ant013/paperclip-shared-fragments`, submoduled at `paperclips/fragments/shared`) has fragments for `phase-1.1-formalize.md`, `phase-3.1-implementation-evidence.md`, etc. They cover most workflows but lack:

- A **branch-hygiene** fragment forbidding stash/cherry-pick between parallel slice branches.
- A rule in `phase-3.1-implementation-evidence.md` requiring **paste of exact tool output** when implementer claims "no new errors" — and requiring CR to audit `git log origin/develop..HEAD --name-only` for out-of-scope files.
- A rule in `phase-1.1-formalize.md` requiring spec writers to (a) live-verify any external library API reference, (b) `grep` audit existing usages of any field/property whose semantics the spec changes.

## 3. Solution — three fragment changes in submodule, then submodule SHA bump

All work lives in `ant013/paperclip-shared-fragments` (separate repo, submoduled). One PR there, then a submodule-bump PR in this repo. Both PRs together = this slice.

### 3.1 NEW fragment: `branch-hygiene.md`

```markdown
# branch-hygiene

## Rule

Never carry changes between parallel slice branches by stash, cherry-pick,
git apply, or copy-paste. If Slice B's local tests fail because they need
Slice A's code, **wait** for Slice A to merge into develop, then
`git rebase origin/develop` on Slice B's branch.

## Why

In GIM-75/76 (2026-04-24), PythonEngineer working on GIM-76 carried a
GIM-75 chore commit so local tests would pass. Subsequent cleanup of
that carry-over commit accidentally deleted unrelated GIM-76 wiring
(`register_code_tools(_tool)`) — entire GIM-76 deliverable was dead
code, caught only at CR Phase 3.1 re-review. Cost: one extra round-trip
through Phase 2/3.1.

## Practical guidance

- If Slice B truly needs Slice A first → mark Slice B as `depends_on: A`
  in the spec frontmatter; CTO Phase 1.1 verifies dependency closure
  before starting Phase 2.
- If Slice B can be implemented in isolation but tests can't run → it's
  fine to write the impl + add `@pytest.mark.skipif(not _has_dep_a())`
  guards. Land it; integration tests come post-merge of A.
- Local development convenience (e.g. `git stash apply` from another
  branch in your own worktree) is fine; **never commit** that stash on
  the slice branch.

## How CR enforces

CR Phase 3.1 runs:

    git log origin/develop..HEAD --name-only --oneline | sort -u

and asserts every changed file is in the slice's declared scope. Any
file outside scope → REQUEST CHANGES citing this fragment.
```

### 3.2 UPDATE: `phase-3.1-implementation-evidence.md`

Add a new section near the top:

```markdown
## Evidence rigor

When implementer comment claims "no new mypy errors / no new ruff errors
/ no new test failures / N pre-existing", paste the **exact tool output**:

    $ uv run mypy --strict src/
    Found 4 errors in 1 file (checked 33 source files)
    src/palace_mcp/code_router.py:44: error: ...
    ...

If the claim is "all errors are pre-existing", show:

    $ git stash; uv run mypy --strict src/ 2>&1 | wc -l
    8
    $ git stash pop; uv run mypy --strict src/ 2>&1 | wc -l
    8

(or equivalent diff against `origin/develop`).

CR Phase 3.1 must independently re-run the same commands and paste its
own output in the review comment. If implementer numbers don't match
CR numbers within ±1 line, REQUEST CHANGES regardless of CRITICAL count.

## Scope audit

Before passing CRITICAL review, CR runs:

    git log origin/develop..HEAD --name-only --oneline | sort -u

Each file in the diff must trace to a task in the spec. Files outside
declared scope → REQUEST CHANGES citing branch-hygiene fragment.
```

### 3.3 UPDATE: `phase-1.1-formalize.md`

Add two new sections:

```markdown
## External library reference rule

Any spec line that references an external library API (constructor,
method, return-type) MUST be backed by a live-verified spike committed
to the repo under `docs/research/<library-version>-spike/` or a
`reference_<lib>_api_truth.md` memory file dated within the last 30
days.

Memory references are not enough by themselves — memory drifts; cite
both the memory file AND the underlying repo spike.

CTO Phase 1.1 runs:

    grep -E 'from <lib> import|<lib>\.<method>' <spec-file> | wc -l

For every match, verify a corresponding spike file exists or REQUEST
CHANGES citing this rule.

**Why:** N+1a (2026-04-18) was reverted because the spec referenced
`graphiti-core 0.4.3` API that didn't exist in the installed version;
N+1a.1 rev1 (2026-04-24) hardcoded `LLM: None` against the same
unverified guess. Both could have been caught by a 30-minute spike.

## Existing-field semantic-change rule

If the spec changes the semantics of a field/property/column that
already exists in code (e.g. "`:Project` stores slug in
`EntityNode.name`"), the spec writer MUST include in the spec:

1. Output of `grep -r '<field-name>' src/` showing every existing
   call-site.
2. An explicit list of which call-sites change and which don't.

CTO Phase 1.1 verifies the grep output is current (re-runs against
HEAD); REQUEST CHANGES if the spec is missing the audit or if grep
output reveals call-sites the spec doesn't acknowledge.

**Why:** N+1a.1 §3.10 changed `:Project.name` semantics without grep'ing
`UPSERT_PROJECT` which already used `name` for a display string.
OpusArchitectReviewer caught the latent production bug at Phase 3.2 —
should have been caught at Phase 1.1 with a 1-minute grep.
```

## 4. Tasks

1. Open PR in `ant013/paperclip-shared-fragments`:
   - Add new file `fragments/branch-hygiene.md`.
   - Update `fragments/phase-3.1-implementation-evidence.md` per §3.2.
   - Update `fragments/phase-1.1-formalize.md` per §3.3.
   - Run `./build.sh` to regenerate `dist/*.md` bundles.
2. Merge that PR; record the new submodule SHA.
3. In this repo:
   - Bump submodule pointer to the new SHA.
   - Run `paperclips/deploy-agents.sh --local` to push fresh bundles to all 11 Gimle agents.
4. Operator verification: pick a recent agent's `AGENTS.md` bundle on iMac, grep for `branch-hygiene` and the two new sections.

No CI / app changes; pure fragments. Acceptance is text-presence in deployed bundles.

## 5. Tests

### 5.1 Submodule-side (in paperclip-shared-fragments)

- Existing `build.sh` smoke (regenerates dist).
- `lint-fragments.sh` (existing) catches markdown errors.

### 5.2 In this repo

- Operator runs `git submodule update --init --recursive`; verifies new SHA.
- Operator runs `paperclips/deploy-agents.sh --local`; verifies success.
- Operator verifies fragment text in one agent's bundle.

### 5.3 Live verification (next slice that triggers each rule)

Hard to test in this slice — these are process rules, validated in the wild. Add a "fragment activation log" entry in `docs/postmortems/` when CR cites one of the new rules in a future REQUEST CHANGES — that's the rules earning their keep.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Fragments add friction without preventing actual mistakes | First fragment activation in the wild is the validation. If after 3 slices no activations, retire the rule. |
| Branch-hygiene rule blocks legitimate cross-slice dependencies | Rule explicitly carves out the `depends_on:` frontmatter pattern. CTO can grant exceptions when documented. |
| Implementer-vs-CR mypy/ruff number-matching too strict (±1 line) | Tune in followup if false-positive rate >5%. |

## 7. References

- `paperclip-shared-fragments` submodule path: `paperclips/fragments/shared/`.
- Existing fragment style: `paperclips/fragments/shared/fragments/phase-handoff.md`.
- Local Gimle overlay: `paperclips/fragments/local/test-design-gimle.md` (precedent for project-scoped overrides).
- Predecessor incidents:
  - GIM-75/76 cross-branch contamination — 2026-04-24 PE carry-over of `e7ff6d5`.
  - GIM-76 false mypy claim — 2026-04-24 CR found 4 errors PE missed.
  - N+1a.1 latent bug — 2026-04-25 OpusArchitectReviewer Phase 3.2 found `:Project.name` semantic clash.
