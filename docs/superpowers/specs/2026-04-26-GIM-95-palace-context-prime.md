---
slug: GIM-95-palace-context-prime
status: draft (operator review pending)
branch: feature/GIM-95-palace-context-prime
paperclip_issue: TBD (will be assigned by paperclip on issue create)
predecessor: 9c87fb9 (develop tip after GIM-94 merge)
date: 2026-04-26
parent_initiative: N+2 Category 1 (USE-BUILT) — extract value from N+1a infrastructure
sequence_position: 2 of 4 (after palace.memory.decide, before test_impact and semantic_search)
---

# GIM-95 — palace.context.prime — per-role agent priming via /prime slash command

## Goal

Eliminate the **cold-start blind spot** for agents working in the gimle-palace repo. At session start, an operator (or any caller) invokes `palace.context.prime(role, slice_id?, budget?)` via the `/prime` slash command and receives a **per-role-tailored context snapshot** (≤ 2000 tokens) covering:

- Current slice context (branch, slice id, recent commits)
- Last 3-5 `:Decision` filtered by `slice_ref`
- Health summary (graphiti reachable, code_graph reachable, last bridge run)
- **Role-specific extras** (per role: CTO/CR/PE/Opus/QA/Operator) including 5-10 tool-usage hints with concrete invocation examples ("when investigating X, call `palace.code.search_graph(name_pattern=...)`")

This closes the gap between "agent has MCP tools available (lazy)" and "agent has no idea what to query" — the priming proactively shows what's relevant **for this role at this moment**.

## Sequence and dependencies

This is **Slice 2 of 4** in N+2 Category 1 (USE-BUILT). Per operator decision (2026-04-26):

1. `palace.memory.decide` — write-side `:Decision` tool (separate slice GIM-NN)
2. **`palace.context.prime` — this slice**
3. `palace.code.test_impact(qn)` — composite tool
4. `palace.code.semantic_search` — hybrid retrieval

**Implementation order vs design order:** This spec can be built before `palace.memory.decide` lands — priming will return empty `:Decision` lists initially and start returning real decisions once decide tool is shipped and used. **Not a blocking dependency.**

**Hard dependencies:**
- N+1a foundation (Graphiti + CM + bridge) — ✅ landed (GIM-75/76/77)
- `palace.memory.lookup` — ✅ existing
- `palace.code.*` tools — ✅ landed (GIM-89 fix verified)
- `palace.memory.health` — ✅ existing

## Non-goals

- Auto-refresh of priming during session (operator decided Q5: lazy refresh — agent re-queries when in doubt)
- Paperclip-side hook integration (operator decided Q3: a — operator-only `/prime` slash command for v1; paperclip integration is **out of scope**, separate slice if pursued later)
- `palace.memory.decide` write-side tool (separate slice in queue position 1)
- Static CLAUDE.md priming (would be one-size-fits-all and stale; not what operator wants)

## Architecture

### High-level flow

```
operator types `/prime`
    ↓
Claude Code slash-command routes to MCP tool palace.context.prime
    ↓ (via SSH tunnel localhost:8080/mcp)
palace-mcp container receives tool call
    ↓
palace.context.prime resolves: role (from arg or env)
                                slice_id (from git branch / arg)
                                budget (default moderate ≤2000)
    ↓
Universal core builder (always):
  - Slice header
  - palace.memory.health snapshot (1-line)
  - palace.memory.lookup :Decision filtered by slice_ref
    ↓
Role-specific extras dispatcher (one of CTO/CR/PE/Opus/QA/Operator)
    ↓
Format as Markdown ≤ budget
    ↓
Return text content via MCP
    ↓
Slash command displays in Claude Code
```

### Per-role priming content

Per operator decision (2026-04-26 Q3: per-role splitting). Each role gets:

#### Universal core (≤ 600 tokens, always included)

```
You are <ROLE> working on slice <SLICE_ID> (branch <BRANCH_NAME>).

Recent decisions (filtered by slice_ref=<SLICE_ID>, last 3, newest first):
  - <ts> — <title> (provenance: <p>, decision_maker: <m>)
  - ...

Health: graphiti=<ok|degraded>  code_graph=<ok|degraded>  bridge_last_run=<ts ago>
```

If `:Decision` filter returns empty: substitute "No decisions recorded for this slice yet (palace.memory.decide tool ships in separate slice)."

#### Operator extras (≤ 1400 tokens)

```
Recent develop activity:
  - <last 5 commits with hashes + dates + titles>

In-flight slices (status=in_progress):
  - <list from paperclip API>

Backlog candidates (priority>=high, status=backlog, top 5):
  - <list>

Recent memory updates (operator memory):
  - <list of files modified in last 7 days>

Useful tools for exploration (ranked):
  - palace.code.get_architecture(project="repos-gimle") — broad project structure
  - palace.code.search_graph(name_pattern="...", project="repos-gimle") — find function/class by name
  - palace.code.trace_call_path(function_name="...", project="repos-gimle", mode="callers"|"callees") — call chains
  - palace.code.get_code_snippet(qualified_name="<repos-gimle.path.dotted>", project="repos-gimle") — read source
  - palace.memory.lookup(entity_type="Decision", filters={...}, limit=5) — past decisions
  - palace.memory.health() — verify graph freshness
  - palace.code.query_graph(query="MATCH (n:Function) ... RETURN ...", project="repos-gimle") — Cypher

Example workflow: "where is this function defined → who calls it → recent decisions touching its module" — search_graph → trace_call_path callers → lookup Decision filtered by file_path.
```

#### CTO extras (≤ 1400 tokens)

Phase 1.1 (Formalize) and 4.2 (Merge) context:

```
Phase context: <auto-detected from issue status — 1.1 if newly assigned, 4.2 if status=in_review>

For Phase 1.1:
  - Spec path candidates: docs/superpowers/specs/<date>-<slice>-design.md
  - Plan path: docs/superpowers/plans/<date>-<slice>.md
  - Verify dependencies in spec frontmatter `depends_on:` are merged on develop
  - Branch hygiene: cut FB from current develop tip; verify `git log HEAD ^origin/develop` is empty

For Phase 4.2:
  - Verify CI green: `gh pr view <PR> --json statusCheckRollup`
  - Verify QA Phase 4.1 evidence comment present
  - Verify Phase 3.2 Opus APPROVE comment present
  - Squash-merge command: `gh pr merge <N> --squash --delete-branch`
  - **CTO-only** action (per fragment compliance-enforcement.md, GIM-94 D1)

Useful tools:
  - palace.memory.lookup(entity_type="Decision", filters={agent_role: "CTO"}, limit=5)
  - palace.memory.health() — verify before merge
```

#### CodeReviewer extras (≤ 1400 tokens)

Phases 1.2 (plan-first), 3.1 (mechanical), 3.2 (adversarial — when CR substitutes for Opus). Phase auto-detected from issue + recent comments.

```
Phase context: <1.2 | 3.1 | 3.2 — auto-detected>

For Phase 1.2 (plan-first review):
  - Read docs/superpowers/plans/<slice>.md
  - Verify each task has: test+impl+commit pattern, concrete acceptance, dependency closure
  - Reject if vague or missing CR/PE/Opus/QA assignments

For Phase 3.1 (mechanical):
  - Run: cd services/palace-mcp && uv run ruff check && uv run ruff format --check && uv run mypy src/ && uv run pytest
  - Paste full output in APPROVE comment (anti-rubber-stamp rule)
  - Scope audit: git log origin/develop..HEAD --name-only | sort -u — every file in slice's declared scope

For Phase 3.2 (adversarial substitution rare):
  - Same as Opus 3.2 below

Useful tools:
  - palace.code.search_graph(qn_pattern="<file path pattern>", project="repos-gimle") — what's in scope
  - palace.memory.lookup(entity_type="Decision", filters={agent_role: "CodeReviewer"}, limit=5) — prior reviews
  - palace.code.query_graph(query="MATCH (s:Symbol) WHERE s.qualified_name CONTAINS '<scope>' RETURN count(s)", project="repos-gimle") — scope sizing
```

#### PythonEngineer extras (≤ 1400 tokens)

```
Phase 2 implementation context:

Plan tasks (from current FB plan doc, parsed):
  - <list with status: not started | in progress | done>
  - <which task is current?>

Acceptance criteria (per task):
  - <extracted from plan>

Hard discipline (from compliance-enforcement.md):
  - Phase 4.2 squash-merge — CTO-only. PE pushes final fix and stops; never call gh pr merge.
  - MCP wire-contract test rule: any new @mcp.tool needs integration test via streamablehttp_client.
  - Use gh pr create --body-file (not inline --body).

Useful tools:
  - palace.code.get_code_snippet(qualified_name="...", project="repos-gimle") — read existing code before editing
  - palace.code.search_graph(name_pattern="...", project="repos-gimle") — find similar implementations
  - palace.code.trace_call_path(function_name="...", project="repos-gimle", mode="callees") — what would my edit affect
  - palace.memory.lookup(entity_type="Decision", filters={agent_role: "PythonEngineer"}, limit=3) — past similar work
```

#### OpusArchitectReviewer extras (≤ 1400 tokens)

Phase 3.2 adversarial review:

```
Phase 3.2 adversarial review context:

PR diff stats: <gh pr view <N> --json additions,deletions,files>

Adversarial categories to check (per memory feedback_anti_rubber_stamp):
  - Security: input validation, secrets handling, SSH key safety
  - Error handling: silent failures, fallback paths, retry semantics
  - API stability: external library version pin, deprecated methods
  - Test coverage: real MCP integration test (GIM-91 rule), no mock-substrate happy-path
  - Spec drift: any task in plan not in commits → red flag

Useful tools:
  - palace.code.query_graph(query="MATCH (n:Function) WHERE n.qualified_name CONTAINS '<changed file>' RETURN n.name, n.in_degree, n.out_degree", project="repos-gimle") — high-coupling = high risk
  - palace.code.search_code(pattern="except:|except Exception", project="repos-gimle") — bare except hunt
  - palace.memory.lookup(entity_type="Decision", filters={agent_role: "OpusArchitectReviewer"}, limit=5) — past adversarial findings
```

#### QAEngineer extras (≤ 1400 tokens)

Phase 4.1 live smoke:

```
Phase 4.1 live smoke context:

Spec acceptance section: <extracted from spec § Acceptance or § QA>
Smoke commands: <extracted from spec, default fallback to deploy-checklist runbook>
Pre-flight requirements: docker compose --profile review up -d --build --wait must reach healthy

Discipline (post-Phase 4.1):
  - Restore production checkout to develop:
      cd /Users/Shared/Ios/Gimle-Palace && git checkout develop && git pull --ff-only
  - Verify: git branch --show-current outputs "develop"
  - Per worktree-discipline.md (GIM-90)

Useful tools:
  - palace.memory.health() — pre-smoke + post-smoke comparison
  - palace.code.search_graph(label="Function", name_pattern="<smoke target>", project="repos-gimle") — verify symbol exists in CM after rebuild
  - palace.memory.lookup(entity_type="Symbol", filters={qualified_name_contains: "<target>"}, limit=2) — verify bridge wrote target
  - paperclip API: GET /api/issues/<id>/comments?order=desc&limit=1 — see prior QA evidence for pattern
```

### Token budget enforcement

The tool MUST measure output bytes and truncate gracefully if over budget:

```python
def render_priming(role: str, slice_id: str, budget: int = 2000) -> str:
    universal = render_universal_core(slice_id)         # ~500 tokens hard cap
    extras = render_role_extras(role, slice_id)         # variable
    full = universal + "\n\n" + extras
    tokens_estimate = len(full) // 4  # ~4 chars per token rough avg
    if tokens_estimate > budget:
        # Truncate role extras section first (universal stays intact)
        truncated = truncate_to_budget(full, budget)
        return truncated + "\n\n[priming truncated to budget]"
    return full
```

Token estimation: 1 token ≈ 4 chars (English/code ASCII). For a more accurate count, optionally use `tiktoken` cl100k_base if available; fall back to char/4 approximation.

### MCP tool signature

```python
@_tool(
    name="palace.context.prime",
    description=(
        "Per-role agent priming. Returns a context snapshot tailored to the given role "
        "(operator/cto/codereviewer/pythonengineer/opusarchitectreviewer/qaengineer) for "
        "the given slice (auto-detected from git branch if omitted) within the token budget."
    ),
)
async def palace_context_prime(
    role: str,
    slice_id: str | None = None,
    budget: int = 2000,
) -> dict[str, Any]:
    """..."""
```

Returns:
```json
{
  "role": "PythonEngineer",
  "slice_id": "GIM-95",
  "branch": "feature/GIM-95-palace-context-prime",
  "budget_tokens": 2000,
  "estimated_tokens": 1850,
  "content": "<formatted markdown context>",
  "truncated": false
}
```

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | New module `services/palace-mcp/src/palace_mcp/context/__init__.py` + `prime.py` (core orchestration) | PE | — |
| 2 | Universal core renderer — slice detection from branch, decisions filter, health snapshot | PE | T1 |
| 3 | Role extras renderers — 6 functions (one per role: operator, cto, cr, pe, opus, qa) | PE | T1 |
| 4 | Token budget measurement + graceful truncation | PE | T2, T3 |
| 5 | MCP tool registration `palace.context.prime` in `mcp_server.py` (Pattern #21 dedup) | PE | T1-T4 |
| 6 | Slash command `/prime` integration — Claude Code config snippet in `docs/runbooks/operator-claude-code-setup.md` | PE | T5 |
| 7 | Unit tests — mock graphiti + paperclip API; per-role rendering | PE | T1-T5 |
| 8 | Integration test through real MCP HTTP+SSE (per GIM-91 rule) — `tests/integration/test_palace_context_prime_wire.py` | PE | T5 |
| 9 | Live smoke evidence (QA Phase 4.1) — operator runs `/prime` for each role, verifies budget + content | QA | T5-T8 |

### Task 1 — module scaffold

```
services/palace-mcp/src/palace_mcp/context/
    __init__.py     (empty re-export marker)
    prime.py        (PrimingRequest, PrimingResponse Pydantic models + render functions)
    universal.py    (universal core renderer)
    roles/
        __init__.py
        operator.py
        cto.py
        codereviewer.py
        pythonengineer.py
        opusarchitectreviewer.py
        qaengineer.py
```

### Task 2 — universal core

Inputs: `slice_id` (optional, auto-detect from git branch via `subprocess.run(["git","branch","--show-current"])` if omitted).

Outputs:
- Slice header line
- `palace.memory.lookup(entity_type="Decision", filters={slice_ref: slice_id}, limit=3, order_by="created_at desc")` — call existing internal helper, NOT through MCP self-loop
- `palace.memory.health()` — call internal helper, format 1-line summary

If `palace.memory.lookup` returns empty for slice_ref filter, fallback message: "No `:Decision` recorded yet for `<slice_id>`. Decisions write tool ships in separate slice."

### Task 3 — role extras renderers

One async function per role, signature:

```python
async def render_role_extras(role: str, slice_id: str, *, deps: PrimingDeps) -> str:
    """deps wraps existing helpers: graphiti, paperclip_client, gh_client."""
```

Per spec § Per-role priming content above. Each renderer respects ≤ 1400 token soft cap (universal core takes ≤ 600).

For Operator: queries paperclip API for in_progress slices + backlog top-5; queries memory dir for recent file mtimes; queries git for last 5 develop commits.

For CTO/CR/PE/Opus/QA: more focused — phase auto-detection (from paperclip issue's recent comments OR from operator-passed `phase=` arg in future revision); plan/spec doc parsing for tasks/acceptance; tool hints with example invocations.

### Task 4 — token budget

Use `len(content_str) // 4` for char/4 approximation. If tiktoken cl100k_base available (optional dep), use it for accuracy.

Truncation strategy:
1. Universal core stays intact (≤ 600 tokens by design)
2. Role extras section is truncated tail-first (drop last bullet items)
3. Append "[priming truncated to budget X tokens]" footer
4. Set `truncated: true` in response

### Task 5 — MCP tool registration

In `services/palace-mcp/src/palace_mcp/mcp_server.py`, register `palace.context.prime` via `_tool()` wrapper (Pattern #21 dedup). Schema declared explicitly per GIM-89 lessons — flat args (`role`, `slice_id`, `budget`).

### Task 6 — Operator slash-command setup

Create `docs/runbooks/operator-claude-code-setup.md` (new file) with:

```
# Operator Claude Code setup

## Prerequisite: SSH tunnel to palace-mcp

Open a terminal:
    ssh -L 8080:localhost:8080 imac-ssh.ant013.work

(Keep open for the session; closes the tunnel when terminal exits.)

## Register palace-mcp MCP server

Edit `~/.claude.json` (project-level):
    {
      "mcpServers": {
        "palace-mcp": {
          "type": "http",
          "url": "http://localhost:8080/mcp"
        }
      }
    }

## /prime slash command

In Claude Code, type `/prime` at session start. It calls `palace.context.prime` with default args (role=operator, slice auto-detected from git branch). Output is the priming snapshot.

To prime as a different role for testing:
    /prime --role=PythonEngineer --slice=GIM-95
```

### Task 7 — Unit tests

Per role × per scenario (decisions present / decisions empty / health degraded / branch detection failure):
- Mock graphiti's `search` / `lookup` returns
- Mock paperclip_client's responses
- Assert content contains expected sections
- Assert token estimate ≤ budget
- Assert role-specific bullet present (e.g. "Phase 4.2 squash-merge — CTO-only" in PE priming output)

Target ≥ 90% coverage on `services/palace-mcp/src/palace_mcp/context/`.

### Task 8 — Integration test via real MCP

Per `paperclip-shared-fragments/fragments/compliance-enforcement.md` MCP wire-contract rule (GIM-91):

```python
# tests/integration/test_palace_context_prime_wire.py
async def test_prime_via_streamablehttp_returns_role_extras():
    async with streamablehttp_client("http://localhost:8080/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.context.prime", arguments={"role": "PythonEngineer"})
            content = result.content[0].text
            assert "PythonEngineer" in content
            assert "Phase 4.2 squash-merge — CTO-only" in content
            assert len(content) // 4 <= 2000
```

### Task 9 — QA Phase 4.1 live smoke

Operator-driven on iMac (after PE pushes final commit):

1. `docker compose --profile review up -d --build --wait` (per deploy-checklist GIM-94 T4)
2. From operator's MacBook with SSH tunnel: invoke `/prime` for each role:
   ```
   /prime
   /prime --role=cto
   /prime --role=codereviewer
   /prime --role=pythonengineer
   /prime --role=opusarchitectreviewer
   /prime --role=qaengineer
   ```
3. For each: verify role-specific section appears, token count ≤ 2000, no errors.
4. Take screenshots / paste outputs as QA evidence in PR body.

## Acceptance

1. Each of 6 roles (Operator + 5 paperclip roles) returns a unique role-specific extras section
2. Universal core appears identically for every role (slice header, decisions, health)
3. Tool returns `estimated_tokens ≤ budget` for all role-extras combinations on a standard test slice
4. Integration test (Task 8) passes through real MCP HTTP+SSE (NOT via mocked `_cm_session.call_tool`)
5. Slash command setup runbook (Task 6) followable end-to-end by a fresh operator
6. Empty decisions filter returns the fallback message; doesn't crash
7. Branch auto-detection works on standard `feature/GIM-N-...` branches; falls back gracefully on detached HEAD or non-standard branches
8. Token-budget truncation triggers when role extras would push over 2000; `truncated: true` flag set

## Out of scope (defer to future slices)

- Paperclip-side hook integration (auto-prime at agent run start) — operator declined for v1, separate slice
- Auto-refresh during session — operator chose lazy refresh (Q5 i)
- Phase auto-detection beyond branch parsing — first version uses simple heuristic
- Caching priming output — per-call computation is fine at ≤ 100ms
- Custom budget profiles per role — fixed `≤ 2000 moderate` for all initially

## Open questions for operator review

1. **MCP tool name placement:** under `palace.context.*` namespace as proposed, or fold into `palace.memory.*` (since it queries memory)? `palace.context` keeps it discoverable as a separate concern.

2. **Slash command implementation path:** Is a `/prime` slash command in Claude Code feasible via project config OR does it need to be a manual user-invoked tool call? If the latter, operator types `palace.context.prime(role="operator")` directly — less ergonomic but simpler.

3. **Paperclip role detection:** for paperclip agents (out of scope for v1 but worth thinking ahead), would they pass `role` explicitly, or would the tool look at env var `PAPERCLIP_ROLE` if present? Decide now to keep extension path clean.

4. **`PrimingDeps` injection pattern:** wire via FastAPI lifespan (matches existing `set_driver`/`set_graphiti` pattern in `mcp_server.py`) or via Context-managed dependency? Existing palace-mcp pattern is module-global setters; consistent for now.

## References

- `docs/superpowers/specs/2026-04-25-palace-ops-unstick-issue-design.md` — sibling palace.ops.* tool, follows same MCP registration pattern
- `services/palace-mcp/src/palace_mcp/mcp_server.py:139-` — `_tool()` decorator (Pattern #21)
- `services/palace-mcp/src/palace_mcp/code_router.py` — palace.code.* registration pattern (post-GIM-89 fix, flat args)
- `paperclip-shared-fragments/fragments/compliance-enforcement.md` — MCP wire-contract test rule (GIM-91)
- Memory `feedback_single_token_review_gate` — reminder that we have one shared GH token
- Memory `reference_paperclip_pr_body_literal_newlines` — gh pr create --body-file pattern
