# ADD Skill Memory Contract Fix

## Branch State

- Branch: `fix/add-skill-memory-contract-spec`
- Base: `origin/develop`
- Base commit: `a52ec7ea311befd04d138ae510b80b89b15ae9fb`
- Date: 2026-06-13

## Problem

The analog-driven-development (ADD) workflow depends on Palace memory for cross-session continuity:

- hydrate prior `Decision` records before design
- read `analog-blacklist`
- write design, active-context, progress, pattern, and smell-instance records after work

Live MacBook-native checks showed that the code discovery side is usable for `uw-ios-app`, but the memory write/read contract is currently incompatible with the ADD skill:

1. `palace.memory.get_project_overview(slug="uw-ios-app")` succeeds, but `palace.memory.lookup(project="uw-ios-app")` returns `unknown_project`.
2. `palace.memory.lookup(project="unstoppable-wallet-ios")` succeeds, which indicates memory project resolution is using project `name` as the accepted value in at least one path.
3. `palace.memory.decide` rejects ADD write-back payloads because `DecideRequest` only allows a narrow Paperclip role set and narrow `slice_ref` formats.

The immediate consequence is that agents can discover code but cannot reliably preserve decisions or blacklists for future sessions.

## Evidence

Live native MCP calls:

```text
palace.memory.get_project_overview {"slug":"uw-ios-app"} -> ok, slug="uw-ios-app", name="unstoppable-wallet-ios"
palace.memory.lookup {"entity_type":"Decision","project":"uw-ios-app"} -> ok:false, error="unknown_project"
palace.memory.lookup {"entity_type":"Decision","project":"unstoppable-wallet-ios"} -> items:[], total_matched:0
```

Source inspection:

- `services/palace-mcp/src/palace_mcp/memory/cypher.py` defines `LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.name AS slug ORDER BY slug"`, which makes resolver callers compare against names rather than slugs.
- `services/palace-mcp/src/palace_mcp/memory/projects.py` uses `LIST_PROJECT_SLUGS` inside `resolve_group_ids`.
- `services/palace-mcp/src/palace_mcp/memory/decide_models.py` allows `decision_maker_claimed` only in `{board, cto, codereviewer, pythonengineer, qaengineer, opusarchitectreviewer, operator}`.
- `SLICE_REF_PATTERN` only accepts `GIM-<n>`, `N+...`, and `operator-decision-YYYYMMDD`.

Validation smoke:

```text
decision_maker_claimed="analog-driven-development:GIM-smoke" -> validation_error
decision_maker_claimed="swiftengineer" -> validation_error
slice_ref="/tmp/spec.md" -> validation_error
slice_ref="https://github.com/.../pull/1" -> validation_error
```

## Assumptions

- `uw-ios-app` is the canonical Palace code project slug for Unstoppable Wallet iOS.
- `unstoppable-wallet-ios` is the mounted git repo slug and human project name.
- Memory APIs should accept the canonical project slug for all Palace memory operations.
- Existing Paperclip validators must remain backward compatible.
- ADD skill write-back should not require mapping itself to a misleading human role such as `operator`.

## Scope

### In Scope

1. Fix memory project resolution so `palace.memory.lookup(project="uw-ios-app")` and `palace.memory.decide(project="uw-ios-app", ...)` resolve to `project/uw-ios-app`.
2. Preserve compatibility with currently accepted project names where practical, so existing callers using `unstoppable-wallet-ios` do not immediately break.
3. Expand `DecideRequest.decision_maker_claimed` to include ADD and relevant Unstoppable/Swift agent identities.
4. Expand `slice_ref` validation to support local spec paths and GitHub PR URLs used by ADD write-back.
5. Add unit/integration tests for the new contracts.
6. Update local skill docs only if implementation behavior differs from the already-corrected ADD skill notes.

### Out Of Scope

- Increasing semantic embedding coverage from 10,000 symbols to full `uw-ios-app`.
- Changing `semantic_search` ranking or liveness scoring.
- Fixing `search_code` CM-sidecar namespace gaps.
- Re-ingesting projects or writing actual ADD memory records beyond test fixtures.

## Proposed Design

### 1. Project Resolution

Change `LIST_PROJECT_SLUGS` to return real slugs:

```cypher
MATCH (p:Project)
RETURN p.slug AS slug
ORDER BY slug
```

Then update or add tests proving:

- `resolve_group_ids(tx, "uw-ios-app") -> ["project/uw-ios-app"]`
- `resolve_group_ids(tx, "unstoppable-wallet-ios")` remains supported if a compatibility alias is intentionally preserved.

Compatibility options:

- Preferred: introduce a resolver that accepts `p.slug`, `p.name`, and possibly `p.cm_project_name` as aliases, but always returns `project/<p.slug>`.
- Minimal: fix `LIST_PROJECT_SLUGS` to `p.slug` and update ADD to use only `uw-ios-app`.

Preferred is safer because this session found existing live callers can currently pass `unstoppable-wallet-ios`.

### 2. Decide Identity Validation

Extend `VALID_DECISION_MAKERS` or replace it with a structured pattern that accepts:

- existing Paperclip roles unchanged
- `analog-driven-development:<task-id>`
- likely ADD subagent identities if used directly, such as `analog-discoverer:<task-id>` and `choice-adversary:<task-id>`
- Swift/Unstoppable roles that may be used by operator workflows, for example `swiftengineer`, `swiftuiengineer`, `swiftconcurrencyengineer`, `uwswiftengineer`, or equivalent local naming if already present in role files

The key requirement is that identity remains bounded and auditable; do not accept arbitrary free-form strings unless a clear audit prefix rule is added.

### 3. Slice Reference Validation

Expand `SLICE_REF_PATTERN` to accept:

- existing `GIM-<n>`, `N+...`, `operator-decision-YYYYMMDD`
- repo-relative spec paths under established spec locations:
  - `docs/superpowers/specs/*.md`
  - `docs/superpowers/plans/*.md`
  - `docs/specs/*.md` if retained for local ADD notes
- GitHub PR URLs:
  - `https://github.com/<org>/<repo>/pull/<number>`
- optional `bootstrap:<task-id>` used by the ADD persistent-memory reference

Do not allow arbitrary absolute paths as final implementation unless a strong reason appears; they are harder to audit and move across machines.

### 4. Tests

Add or update tests in:

- `services/palace-mcp/tests/memory/test_decide_models.py`
- project-resolution tests covering `resolve_group_ids`
- integration or wire tests for:
  - `palace.memory.lookup(project="uw-ios-app")` on a seeded `:Project`
  - `palace.memory.decide(project="uw-ios-app", decision_maker_claimed="analog-driven-development:GIM-123", slice_ref="docs/superpowers/specs/example.md")`
  - lookup can read back the written Decision under `project="uw-ios-app"`

## Affected Files

Expected implementation files:

- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/memory/projects.py`
- `services/palace-mcp/src/palace_mcp/memory/decide_models.py`
- `services/palace-mcp/tests/memory/test_decide_models.py`
- relevant memory/project resolution tests under `services/palace-mcp/tests/`
- optional ADD skill docs under `/Users/ant013/Data/AI/gimle-skills/analog-driven-development/` if the accepted contract changes

## Acceptance Criteria

- `palace.memory.lookup(entity_type="Decision", project="uw-ios-app", limit=1)` no longer returns `unknown_project`.
- `palace.memory.decide` accepts:
  - `project="uw-ios-app"`
  - `decision_maker_claimed="analog-driven-development:GIM-123"`
  - `slice_ref="docs/superpowers/specs/2026-06-13-example.md"`
- A decide/lookup roundtrip works for `project="uw-ios-app"`.
- Existing valid decide payloads still pass.
- Existing invalid identities and unsafe slice refs still fail.
- No change to `semantic_search` behavior in this slice.

## Verification Plan

Run in `services/palace-mcp`:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest tests/memory/test_decide_models.py
uv run pytest tests/integration/test_decide_lookup_roundtrip.py
```

Then run a live MacBook-native smoke after restart:

```bash
python3 /Users/ant013/Android/Gimle-Palace-native/scripts/native-mcp-call.py \
  palace.memory.lookup \
  '{"entity_type":"Decision","project":"uw-ios-app","limit":1}' \
  60
```

If writing a live Decision is acceptable during implementation, use a clearly tagged test record and verify lookup. Otherwise, rely on integration test fixtures and use live lookup only.

## Open Questions

1. Should memory APIs continue accepting `project="unstoppable-wallet-ios"` as an alias, or should callers be forced to use `uw-ios-app` everywhere except `palace.git.*`?
2. Which exact Swift/Unstoppable role names should be allowlisted beyond `analog-driven-development:<task-id>`?
3. Should `slice_ref` accept only repo-relative spec/plan paths, or also absolute local paths used by older ADD skill notes?
4. Should we add a dedicated `agent:<name>:<task-id>` identity pattern instead of enumerating many agent names?

## Non-Goals For This Spec

The report also identified semantic coverage and dead-code ranking issues. Those are valid, but they should be handled in a separate slice after memory continuity is restored.
