# GIM-91 Plan: MCP integration test rule + reference pattern

**Issue:** GIM-91 — Test-pyramid gap: MCP tools must have integration test through real HTTP+SSE call
**Branch:** `feature/GIM-91-mcp-integration-test-rule`
**Grounded on:** develop at `1ff5ff2` (GIM-89 merge)
**Spec:** Issue description (self-contained)

---

## Context

GIM-89 exposed a systemic gap: all existing tests mocked below the FastMCP
signature-binding layer, so a broken `inputSchema` passed every gate. This
slice closes the gap with two deliverables:

1. A compliance-enforcement rule requiring real MCP HTTP+SSE integration tests
   for any `@mcp.tool`-registered tool.
2. A reference integration test demonstrating the pattern on
   `palace.memory.health`.

## Tasks

### Task 1 — Extend `compliance-enforcement.md` fragment

**Owner:** PythonEngineer (doc change in shared fragments)
**Files:**
- `paperclips/fragments/shared/fragments/compliance-enforcement.md`

**What to do:**
Append a new section at the end of the file:

```markdown
## MCP wire-contract test (integration test rule)

Any tool registered via `@mcp.tool` / `register_X_tools` that crosses the
MCP wire boundary (callable from external MCP clients like Claude Code)
MUST have at least one test that:

1. Spawns a test FastMCP instance bound to a localhost port (or the
   palace-mcp container)
2. Connects via `streamablehttp_client` / SSE / actual MCP HTTP client
3. Calls `tools/list` — asserts the tool appears with correct `inputSchema`
4. Calls `tools/call` with FLAT arguments (not nested
   `{arguments: {...}}`) — asserts non-empty result on a known-good case
5. Calls `tools/call` with WRONG argument shape — asserts proper error

Mocks at the FastMCP signature-binding level (e.g. mocking `call_tool`
directly, calling `_forward()` programmatically) DO NOT count as MCP
integration tests. They test the implementation, not the contract.

### CR enforcement (Phase 3.1)

If a PR adds or modifies an `@mcp.tool` or passthrough decorator, CR MUST
verify there is an integration test file with `streamablehttp_client` or
equivalent real MCP HTTP client. If absent, REQUEST CHANGES.
```

**Acceptance criteria:**
- [ ] New section appended to `compliance-enforcement.md`
- [ ] Section text matches the spec in issue description

**Dependencies:** None

---

### Task 2 — Rebuild `paperclips/dist/` with the new fragment

**Owner:** PythonEngineer
**Files:**
- `paperclips/dist/code-reviewer.md` (output of build)

**What to do:**
Run `bash paperclips/build.sh` and commit the resulting `dist/` changes.

**Acceptance criteria:**
- [ ] `paperclips/build.sh` exits 0
- [ ] `paperclips/dist/code-reviewer.md` contains the new "MCP wire-contract
      test" section verbatim
- [ ] No other dist files changed unexpectedly

**Dependencies:** Task 1

---

### Task 3 — Reference integration test: `test_mcp_wire_pattern.py`

**Owner:** PythonEngineer
**Files:**
- `services/palace-mcp/tests/integration/test_mcp_wire_pattern.py` (new)

**What to do:**
Create a reference integration test that demonstrates the
`streamablehttp_client` + `tools/call` pattern. Use `palace.memory.health`
as the sample tool (simple, no side-effects, always available).

The test must:
1. Import `mcp.client.streamable_http` (or the correct FastMCP client path)
2. Start the FastMCP app on a local port (use `uvicorn` or ASGI test server)
3. Connect via `streamablehttp_client`
4. `tools/list` — assert `palace.memory.health` is present, check its
   `inputSchema` shape
5. `tools/call("palace.memory.health", {})` with flat args — assert
   successful result
6. `tools/call` with malformed arguments — assert error response

Mark tests with `@pytest.mark.integration` so they can be skipped in
unit-only CI runs.

Include a module docstring explaining this is the canonical pattern for
future MCP wire-contract tests, referencing GIM-91.

**Acceptance criteria:**
- [ ] File exists at `services/palace-mcp/tests/integration/test_mcp_wire_pattern.py`
- [ ] Tests pass with `uv run pytest tests/integration/test_mcp_wire_pattern.py -m integration`
      against a running Neo4j (compose reuse or testcontainers)
- [ ] Pattern is clear enough that future tool tests can copy-paste and adapt
- [ ] `@pytest.mark.integration` applied

**Dependencies:** None (can run in parallel with Task 1)

---

### Task 4 — Regression test for `palace.code.search_graph` (GIM-89 proof)

**Owner:** PythonEngineer
**Files:**
- `services/palace-mcp/tests/integration/test_mcp_wire_pattern.py` (extend)
  OR a separate `test_code_wire_integration.py`

**What to do:**
Add an integration test for `palace.code.search_graph` that:
1. Connects via `streamablehttp_client`
2. Calls `tools/list` — asserts `palace.code.search_graph` present with
   correct flat `inputSchema` (must have `query` as top-level property,
   NOT nested under `arguments`)
3. Calls `tools/call("palace.code.search_graph", {"query": "test", "project": "gimle"})`
   with flat args — asserts it doesn't crash (result may be empty if no
   code graph data, but must not raise `TypeError`)

This test MUST fail against the pre-GIM-89 code (where `inputSchema` had
`_OpenArgs` wrapper causing `arguments` nesting) and pass against the
post-GIM-89 fix.

**Acceptance criteria:**
- [ ] Test exists and passes on current develop (post-GIM-89)
- [ ] Test would fail on pre-GIM-89 code (verified conceptually by
      checking the schema shape assertion)
- [ ] `@pytest.mark.integration`

**Dependencies:** Task 3 (uses the pattern established there)

---

## Phase assignments

| Phase | Agent | What |
|-------|-------|------|
| 1.1 Formalize | CTO | This plan (done) |
| 1.2 Plan-first review | CodeReviewer | Review plan, APPROVE or REQUEST CHANGES |
| 2 Implement | PythonEngineer | Tasks 1-4 (Task 1+3 parallel, then 2+4 sequential) |
| 3.1 Mechanical review | CodeReviewer | Lint/mypy/pytest + compliance checklist |
| 3.2 Adversarial review | OpusArchitectReviewer | Architecture + edge cases |
| 4.1 QA live smoke | QAEngineer | Run integration tests on iMac, real MCP call |
| 4.2 Merge | CTO | Squash-merge to develop, chain-trigger GIM-90 |

## Risks

- **FastMCP `streamablehttp_client` API:** verify import path against
  installed FastMCP version. Use `context7` to check docs if unsure.
- **Neo4j dependency in integration tests:** Tests 3+4 need a live Neo4j.
  Pattern should handle both testcontainers and compose-reuse (consistent
  with existing `test_gim75_integration.py`).
- **Code graph tools require `cm_session`:** Task 4's test may need
  `CLAUDE_CODE_HOST` or similar env to init the code-manager session.
  If not available in test, asserting `tools/list` schema shape +
  `tools/call` doesn't crash with connection error (vs `TypeError`) is
  acceptable.
