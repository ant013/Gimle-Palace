# ADD Skill Memory Contract Fix

## Branch State

- Branch: `fix/add-skill-memory-contract-spec`
- Base: `origin/develop`
- Base commit: `a52ec7ea311befd04d138ae510b80b89b15ae9fb`
- Spec revision: rev2 after audit
- Date: 2026-06-13

## Problem

The analog-driven-development (ADD) workflow depends on Palace memory for cross-session continuity:

- hydrate prior `Decision` records before design
- read `analog-blacklist`
- write design, active-context, progress, pattern, and smell-instance records after work

Live MacBook-native checks showed that the code discovery side is usable for `uw-ios-app`, but the memory write/read contract is currently incompatible with the ADD skill.

The root bug is not just that `LIST_PROJECT_SLUGS` returns `p.name`. The deeper defect is that memory project resolution accepts aliases during its gate, then echoes the caller input back into `project/<input>` instead of resolving aliases to the canonical `Project.slug`.

That produces two bad states:

1. Canonical slug path fails loudly:
   - `palace.memory.get_project_overview(slug="uw-ios-app")` succeeds.
   - `palace.memory.lookup(project="uw-ios-app")` returns `unknown_project`.
2. Human-name alias path fails silently:
   - `palace.memory.lookup(project="unstoppable-wallet-ios")` returns `ok` with zero rows.
   - This scopes to `project/unstoppable-wallet-ios`, while actual project data is under `project/uw-ios-app`.
   - An agent will infer "no Decisions exist" even if Decisions exist under the canonical slug.

Separately, `palace.memory.decide` rejects ADD write-back payloads because `DecideRequest` only allows a narrow Paperclip role set and narrow `slice_ref` formats.

## Evidence

Live native MCP calls:

```text
palace.memory.get_project_overview {"slug":"uw-ios-app"}
  -> ok, slug="uw-ios-app", name="unstoppable-wallet-ios"

palace.memory.lookup {"entity_type":"Decision","project":"uw-ios-app"}
  -> ok:false, error="unknown_project"

palace.memory.lookup {"entity_type":"Decision","project":"unstoppable-wallet-ios"}
  -> items:[], total_matched:0
```

Source inspection:

- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
  - `LIST_PROJECT_SLUGS = "MATCH (p:Project) RETURN p.name AS slug ORDER BY slug"`
  - `ENTITY_COUNTS_BY_PROJECT` also returns `p.name AS slug`.
  - `CHECK_PROJECT_NAMESPACE_CONFLICT` already encodes useful slug/name/cm namespace logic and should inform the resolver design.
- `services/palace-mcp/src/palace_mcp/memory/projects.py`
  - `resolve_group_ids` gates against known values then returns `f"project/{project}"`.
  - This verbatim echo is what turns an accepted alias into a wrong `group_id`.
- `services/palace-mcp/src/palace_mcp/memory/health.py`
  - `projects` comes from `LIST_PROJECT_SLUGS`.
  - `entity_counts_per_project` comes from `ENTITY_COUNTS_BY_PROJECT`.
  - `git_repos_unregistered = set(git_available) - set(slugs)` currently works by accident when `slugs` are names matching directories.
- `services/palace-mcp/src/palace_mcp/memory/decide_models.py`
  - `decision_maker_claimed` allows only `{board, cto, codereviewer, pythonengineer, qaengineer, opusarchitectreviewer, operator}`.
  - `SLICE_REF_PATTERN` only accepts `GIM-<n>`, `N+...`, and `operator-decision-YYYYMMDD`.

Validation smoke:

```text
decision_maker_claimed="analog-driven-development:GIM-smoke" -> validation_error
decision_maker_claimed="swiftengineer" -> validation_error
slice_ref="docs/superpowers/specs/example.md" -> currently invalid
slice_ref="https://github.com/ant013/Gimle-Palace/pull/1" -> currently invalid
slice_ref="/tmp/spec.md" -> currently invalid; should remain invalid
```

## Assumptions

- `uw-ios-app` is the canonical Palace code/memory project slug for Unstoppable Wallet iOS.
- `unstoppable-wallet-ios` is a human project name and mounted git repo slug.
- Memory APIs should accept the canonical slug and may accept aliases, but they must always resolve to the canonical `group_id = project/<slug>`.
- Existing Paperclip validators must remain backward compatible.
- ADD skill write-back should not require mapping itself to a misleading human role such as `operator`.
- `slice_ref`, `evidence_ref`, and `decision_maker_claimed` are stored as opaque audit attributes; they are not dereferenced by the decide path.

## Scope

### In Scope

1. Replace gate-then-echo memory project resolution with canonical resolution:
   - input may be slug, name, or `cm_project_name`
   - output is always `project/<resolved_slug>`
2. Fix slug/name projections used by health:
   - `LIST_PROJECT_SLUGS`
   - `ENTITY_COUNTS_BY_PROJECT`
   - `git_repos_unregistered` calculation
3. Preserve read compatibility for `project="unstoppable-wallet-ios"` as an alias, while canonical write/read key remains `uw-ios-app`.
4. Expand `DecideRequest.decision_maker_claimed` for bounded ADD/agent identities.
5. Expand `slice_ref` validation for repo-relative spec/plan paths, GitHub PR URLs, and ADD bootstrap refs.
6. Harden validators against audit-integrity issues.
7. Add unit/integration/wire tests that use fixtures where `slug != name`.
8. Update local ADD skill docs only if implementation behavior differs from the already-corrected ADD skill notes.

### Out Of Scope

- Increasing semantic embedding coverage from 10,000 symbols to full `uw-ios-app`.
- Changing `semantic_search` ranking or liveness scoring.
- Fixing `search_code` CM-sidecar namespace gaps.
- Re-ingesting projects or writing actual production ADD memory records beyond test fixtures.

## Proposed Design

### 1. Canonical Project Resolver

Introduce a single DB-backed resolver for memory scoping, for example:

```python
async def resolve_project_slugs(tx, project) -> list[str]:
    ...
```

Behavior:

- `None` returns the default group id unchanged.
- `"*"` returns all canonical project slugs.
- `str` input resolves by:
  - `p.slug = $value`
  - or `p.name = $value`
  - or `p.cm_project_name = $value`
- `list[str]` resolves each input independently.
- unknown values raise `UnknownProjectError`.
- returned group ids are always `project/<p.slug>`.
- never construct `project/<caller_input>` after accepting an alias.

This should reuse the existing namespace semantics already present near `CHECK_PROJECT_NAMESPACE_CONFLICT` instead of adding a new incompatible interpretation of slug/name/cm identity.

`LIST_PROJECT_SLUGS` should still be corrected to return canonical slugs:

```cypher
MATCH (p:Project)
RETURN p.slug AS slug
ORDER BY slug
```

`ENTITY_COUNTS_BY_PROJECT` should also return canonical slug keys:

```cypher
RETURN p.slug AS slug, type, cnt
```

### 2. Health Output Compatibility

After canonical slug fixes, `health.projects` and `health.entity_counts_per_project` must use the same canonical keys.

`git_repos_unregistered` must not compare mounted directory names directly to project slugs. It should account for `Project.relative_path` and/or `Project.name` when deciding whether a mounted repo is represented by a registered project.

Acceptance examples:

- `projects` includes `uw-ios-app`.
- `entity_counts_per_project` uses key `uw-ios-app`.
- mounted repo directory `unstoppable-wallet-ios` is not reported as unregistered if `Project{slug:"uw-ios-app", relative_path:"unstoppable-wallet-ios"}` exists.

### 3. Decide Identity Validation

Keep `VALID_DECISION_MAKERS` closed for privileged Paperclip roles and add a bounded agent identity path.

Allowed:

- existing Paperclip roles unchanged
- `analog-driven-development:<task-id>`
- `analog-discoverer:<task-id>`
- `choice-adversary:<task-id>`
- explicitly chosen Swift/Unstoppable roles only if already used by local workflows

Preferred identity rule:

```text
<agent-role>:<task-id>
```

where:

- `<agent-role>` is from a closed allowlist, not arbitrary
- `<task-id>` is 1-80 chars
- charset excludes whitespace and `:`
- privileged names such as `operator`, `board`, and `cto` cannot be used as `<agent-role>` prefixes

Do not use a generic unrestricted `agent:<name>:<task-id>` unless `<name>` is also allowlisted. Otherwise audit entries could impersonate privileged roles.

### 4. Slice Reference Validation

Replace the single broad regex with small anchored validators. Use `.fullmatch()` or `\Z`, not `.match()`.

Allowed:

- existing `GIM-<n>`, `N+...`, `operator-decision-YYYYMMDD`
- `bootstrap:<task-id>`
- repo-relative docs paths:
  - `docs/superpowers/specs/<file>.md`
  - `docs/superpowers/plans/<file>.md`
  - `docs/specs/<file>.md`
- GitHub PR URLs:
  - `https://github.com/<org>/<repo>/pull/<number>`

Hardening requirements:

- cap `slice_ref` length at 256
- reuse `validate_relative_path` for repo-relative paths before prefix checks
- reject absolute paths
- reject `..`
- reject `%2e` / `%2E`
- reject NUL
- reject backslash
- reject prefix escapes such as `docs/superpowers/specs-evil/file.md`
- anchor GitHub URL as `https://github\.com/<org>/<repo>/pull/\d+\Z`
- reject `github.com.evil.com`, userinfo spoofing, and non-HTTPS URLs
- avoid one large regex with nested `(.+/)*` style constructs

Absolute local paths should remain invalid in this slice. If ADD needs portable local spec refs, use repo-relative paths.

## Affected Files

Expected implementation files:

- `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- `services/palace-mcp/src/palace_mcp/memory/projects.py`
- `services/palace-mcp/src/palace_mcp/memory/health.py`
- `services/palace-mcp/src/palace_mcp/memory/decide_models.py`
- `services/palace-mcp/tests/memory/test_projects.py`
- `services/palace-mcp/tests/memory/test_decide_models.py`
- health tests, existing or new, covering slug/name divergence
- `services/palace-mcp/tests/integration/test_decide_lookup_roundtrip.py`
- `services/palace-mcp/tests/integration/test_palace_memory_decide_wire.py`
- optional ADD skill docs under `/Users/ant013/Data/AI/gimle-skills/analog-driven-development/` if the accepted contract changes

## Test Plan

### Project Resolution Tests

Use fixtures where `slug != name`:

```text
slug = "uw-ios-app"
name = "unstoppable-wallet-ios"
cm_project_name = "repos-hs-unstoppable-wallet-ios"
relative_path = "unstoppable-wallet-ios"
```

Required cases:

- `resolve_group_ids(tx, "uw-ios-app") -> ["project/uw-ios-app"]`
- `resolve_group_ids(tx, "unstoppable-wallet-ios") -> ["project/uw-ios-app"]`
- `resolve_group_ids(tx, "repos-hs-unstoppable-wallet-ios") -> ["project/uw-ios-app"]`
- `resolve_group_ids(tx, ["uw-ios-app", "unstoppable-wallet-ios"])` resolves both to canonical group ids; duplicates should be handled deliberately.
- `resolve_group_ids(tx, "*")` returns canonical slug group ids only.
- unknown values raise `UnknownProjectError`.
- no path returns `project/unstoppable-wallet-ios` for this fixture.

### Health Tests

Required cases:

- `health.projects` keys use canonical slugs.
- `health.entity_counts_per_project` keys use the same canonical slugs.
- `git_repos_unregistered` does not report `unstoppable-wallet-ios` when a project exists with `relative_path="unstoppable-wallet-ios"`.

### Decide Model Tests

Positive:

- existing `GIM-*`, `N+*`, and `operator-decision-*`
- `decision_maker_claimed="analog-driven-development:GIM-123"`
- `decision_maker_claimed="choice-adversary:GIM-123"`
- `slice_ref="docs/superpowers/specs/2026-06-13-example.md"`
- `slice_ref="docs/superpowers/plans/2026-06-13-GIM-123-example.md"`
- `slice_ref="docs/specs/add-design.md"`
- `slice_ref="https://github.com/ant013/Gimle-Palace/pull/453"`
- `slice_ref="bootstrap:GIM-123"`

Negative:

- `slice_ref="/tmp/spec.md"`
- `slice_ref="../docs/superpowers/specs/x.md"`
- `slice_ref="docs/superpowers/specs/../x.md"`
- `slice_ref="docs\\superpowers\\specs\\x.md"`
- `slice_ref="docs/superpowers/specs-evil/x.md"`
- `slice_ref="docs/superpowers/specs/%2e%2e/x.md"`
- `slice_ref="https://github.com.evil.com/org/repo/pull/1"`
- `slice_ref="https://user@github.com/org/repo/pull/1"`
- `slice_ref="http://github.com/org/repo/pull/1"`
- any `slice_ref` with trailing newline
- bare `decision_maker_claimed="analog-driven-development"`
- free-form `decision_maker_claimed="hacker:GIM-123"`
- privileged prefix spoofing if a prefix form is added, e.g. `operator:GIM-123`
- identity with whitespace or extra colon

### Integration / Wire Tests

Required cases:

- Seed `:Project{slug:"uw-ios-app", name:"unstoppable-wallet-ios"}`.
- `palace.memory.decide(project="uw-ios-app", decision_maker_claimed="analog-driven-development:GIM-123", slice_ref="docs/superpowers/specs/example.md", ...)` writes a `Decision`.
- `palace.memory.lookup(project="uw-ios-app")` reads it back.
- `palace.memory.lookup(project="unstoppable-wallet-ios")` also resolves to the same canonical group and can read it back, if alias compatibility is retained.
- No test fixture may use only `slug == name` for project-resolution coverage.

## Acceptance Criteria

- `palace.memory.lookup(entity_type="Decision", project="uw-ios-app", limit=1)` no longer returns `unknown_project`.
- Alias inputs such as `project="unstoppable-wallet-ios"` resolve to `project/uw-ios-app`, not `project/unstoppable-wallet-ios`.
- A decide/lookup roundtrip works for `project="uw-ios-app"`.
- `palace.memory.decide` accepts:
  - `project="uw-ios-app"`
  - `decision_maker_claimed="analog-driven-development:GIM-123"`
  - `slice_ref="docs/superpowers/specs/2026-06-13-example.md"`
- Existing valid decide payloads still pass.
- Existing invalid identities and unsafe slice refs still fail.
- `health.projects` and `health.entity_counts_per_project` use matching canonical keys.
- `git_repos_unregistered` does not regress for mounted repos whose directory name equals project `name` / `relative_path`.
- No change to `semantic_search` behavior in this slice.

## Verification Plan

Run in `services/palace-mcp`:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src/
uv run pytest tests/memory/test_projects.py
uv run pytest tests/memory/test_decide_models.py
uv run pytest tests/memory/test_health.py
uv run pytest tests/integration/test_decide_lookup_roundtrip.py
uv run pytest tests/integration/test_palace_memory_decide_wire.py
```

If there is no existing `test_health.py`, add the nearest equivalent focused health unit test and include it in this gate.

Then run live MacBook-native smoke after restart:

```bash
python3 /Users/ant013/Android/Gimle-Palace-native/scripts/native-mcp-call.py \
  palace.memory.lookup \
  '{"entity_type":"Decision","project":"uw-ios-app","limit":1}' \
  60
```

If writing a live Decision is acceptable during implementation, use a clearly tagged test record and verify lookup under both canonical slug and alias. Otherwise, rely on integration fixtures and use live lookup only.

## Resolved Design Questions

1. Memory APIs should continue accepting `project="unstoppable-wallet-ios"` as a read/write alias, but the canonical stored group id is always `project/uw-ios-app`.
2. Do not allow unrestricted `agent:<name>:<task-id>`. Use a closed agent-role allowlist plus bounded `:<task-id>` suffix.
3. Do not accept absolute local paths in `slice_ref` in this slice. Use repo-relative spec/plan paths.
4. Reuse `validate_relative_path` for path validation and add path/URL-specific hardening rather than one large regex.

## Non-Goals For This Spec

The report also identified semantic coverage and dead-code ranking issues. Those are valid, but they should be handled in a separate slice after memory continuity is restored.
