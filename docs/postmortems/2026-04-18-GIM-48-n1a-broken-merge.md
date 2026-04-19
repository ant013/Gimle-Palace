# Postmortem — GIM-48 N+1a broken merge + same-day revert

**Incident date:** 2026-04-18
**Duration:** ~24 h from broken merge (`9d87fa0`) to revert (`a4abd28`)
**Severity:** high — develop held unrunnable code; iMac deploy crashed
on startup; false-positive `/healthz` masked the state
**Author:** Board
**Status:** closed, replacement slice opened as GIM-52

## What happened

1. N+1a Graphiti substrate swap was implemented (GIM-48) on the
   feature branch, passed unit tests (all mocked), passed
   CodeReviewer Phases 1.2 and 3.1, and was **squash-merged to
   develop** as `9d87fa0`.
2. Manual iMac deploy pulled develop and rebuilt the container.
   Container entered crash-loop on startup.
3. Three layered runtime blockers were found and fixed in hotfix PR
   #17 (merged as `93cb2da`):
   - `OpenAIGenericClient` → `OpenAIClient` import-path rename in
     graphiti-core.
   - `LLMClient.__init__` unconditionally creates `Cache("./llm_cache")`
     via `diskcache` — `appuser` cannot write to WORKDIR.
   - `Graphiti(...)` default `cross_encoder` reads `OPENAI_API_KEY`
     from env, which we do not ship.
4. After hotfix landed, container went healthy on `/healthz`. But
   verification against the real `graphiti-core` 0.4.3 library
   revealed that the entire N+1a implementation targets API surfaces
   that do not exist: `Graphiti.nodes.*`, `Graphiti.edges.*`,
   `EntityNode.attributes`. Every real MCP tool call crashes
   `AttributeError` — `/healthz` only calls
   `driver.verify_connectivity()` so it stayed green.
5. Revert PR #18 reverted both `93cb2da` and `9d87fa0` in one commit
   (`a4abd28`), returning develop to the N+0 state that had been
   running in production for 16 h.

## Why this slipped through — three independent gates all failed

### Gate 1 — CI was already red at merge

At the moment CR approved and CTO merged `9d87fa0`, the feature
branch had **6 ruff errors, 40 mypy `attr-defined` errors, and 1 test
collection error**. The mypy errors pointed at exactly the
nonexistent `graphiti.nodes`, `graphiti.edges`, and
`EntityNode.attributes` accesses that later caused the production
`AttributeError`. CR and CTO merged without reading CI output. GitHub
branch protection did not enforce status checks on merge.

### Gate 2 — QA Phase 4.1 was skipped

CodeReviewer released status `in progress → todo` instead of
reassigning QAEngineer. CTO picked up the `todo` and set it directly
to `done` without Phase 4.1 evidence. No QA run, no live smoke, no
ingest-CLI check. See `feedback_qa_skipped_gim48.md` for timeline.

### Gate 3 — unit tests mocked the broken APIs

The entire unit test suite used `MagicMock(spec=Graphiti)` and
`MagicMock(spec=EntityNode)`. `MagicMock` responds to **any**
attribute access, so `node.attributes["status"]` and
`graphiti.nodes.entity.get_by_group_ids(...)` looked clean. The real
library raises `AttributeError` on first access.

### Bonus — verification doc itself was wrong

`docs/research/graphiti-core-verification.md` captured claims from a
stale graphiti-core version via context7. The mini-gap spike that was
meant to verify `EntityNode.attributes` round-trip against the live
library (spec §10, Gap #2) was deferred, not executed.

## What this tells us about our process

- **Review discipline alone is not enough.** The CR prompt correctly
  demanded evidence against rubber-stamping, but the existing process
  does not force CR to run CI locally or paste its output. Without an
  evidence-gate, review can still approve red code.
- **Phase handoff is under-specified.** Plan-files listed who runs
  Phase 4.1, but not **who reassigns the QA agent after CR APPROVE**.
  In practice CR released ownership to `todo`, CTO saw `todo` and
  closed. The transition from Phase 3 → 4 had no explicit owner.
- **Mock-heavy testing lets us pretend.** `MagicMock(spec=X)` passes
  attribute checks at the class level but not at the instance level.
  A real-library integration test would have caught this in minutes.
- **Library verification needs live proof, not documentation.**
  Pulling snippets from context7 is good for a starting hypothesis;
  it is not a substitute for `inspect.signature(Cls.__init__)` and
  `dir(cls)` against the installed library.
- **Successful `/healthz` is not a signal.** It only told us Neo4j
  was reachable. The real product surface (`palace.memory.health` MCP
  tool returning counts) was broken, but there was no automated
  check verifying it.

## Changes made in response

### Immediate (same session)

- Hotfix PR #17 + revert PR #18. Develop back to N+0 (working).
- Admin-merge was required for both because CI was red from N+1a
  inheritance. Revert admin-merge restored green.
- CI hotfix PR #19 (non-admin merge — first green merge since N+1a):
  two pre-existing `TestFireAndForgetConstraints` failures fixed by
  stubbing `NEO4J_PASSWORD` env in a test fixture.

### Process (shipped as part of GIM-52 spec)

- GIM-52 acceptance criteria make CI-green **non-negotiable** for
  merge. CR APPROVE must paste literal `ruff/mypy/pytest` output.
- GIM-52 plan-file Phase 4.1 specifies the exact QA evidence format:
  commit SHA, `docker compose ps`, `/healthz`, `palace.memory.health()`
  via MCP, `palace.memory.lookup` response sample, ingest CLI output,
  direct Cypher invariant check, and an iMac checkout cleanup
  (`feedback_imac_checkout_discipline.md`).
- GIM-52 plan Task 11 introduces a `live_driver` pytest fixture and
  `@pytest.mark.integration` tests that must run against a real Neo4j,
  not a mock. This closes Gate 3.

### Process (planned — not in GIM-52 scope)

- Add `phase-handoff.md` fragment to `ant013/paperclip-shared-fragments`:
  explicit reassignment rules after CR APPROVE and before CTO close.
  Deferred from this session to avoid re-deploying all 11 agents
  without supervision.
- Evaluate branch protection tightening on GitHub: require
  `lint/typecheck/test/docker-build` as **required** checks with
  admin override logged and justified.

## Decision: pivot instead of rebuild

Instead of redesigning N+1a against the verified graphiti-core API,
we accepted that the installed 0.4.3 library cannot hold our domain
attributes natively. A hybrid approach (graphiti-core for edges +
raw Cypher for properties) would return ~20% of the swap value for
2–3 days of work. The concrete unlock we actually needed from N+1a —
multi-project namespacing for N+1b — costs a single schema column
plus an index. See GIM-52 spec.

graphiti-core remains on the roadmap, but gated on a driving product
need (search, probably at N+1c) and on a proper live-library spike
before any implementation commits.

## References

- GIM-48 paperclip issue — original N+1a scope
- PR #17 (`93cb2da`) — startup hotfix, superseded by revert
- PR #18 (`a4abd28`) — revert to N+0
- PR #19 (`126eb49`) — pre-existing test failures fixed (GIM-45/46)
- GIM-52 paperclip issue — group_id micro-slice replacement
- `feedback_qa_skipped_gim48.md` — QA gate failure detail
- `reference_graphiti_core_api_truth.md` — verified real API surface
- `feedback_imac_checkout_discipline.md` — production checkout hygiene
- `docs/research/graphiti-core-verification.md` — marked with caution
  banner, historical only
