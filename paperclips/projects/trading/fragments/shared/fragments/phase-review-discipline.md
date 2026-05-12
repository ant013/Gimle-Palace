<!-- derived-from: paperclips/fragments/targets/codex/shared/fragments/phase-review-discipline.md @ shared-submodule 285bf36 -->
<!-- on shared advance, manually diff and re-derive -->
<!-- Trading has no Opus/Architect role — Phase 3.2 section from shared dropped entirely -->

# Phase review discipline

## Phase 5 — Plan vs Implementation file-structure check

CR must paste `git diff --name-only <base>..<head>` and compare file count against plan's "File Structure" table before APPROVE.

Why: {{evidence.review_scope_drift_issue}} — PE silently reduced 6→2 files; tooling checks don't catch scope drift.

```bash
git diff --name-only <base>..<head> | sort
# Compare against plan's "File Structure" table. Count must match.
```

PE scope reduction without comment = REQUEST CHANGES.
