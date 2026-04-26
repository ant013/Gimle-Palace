---
slug: GIM-96-palace-memory-decide
status: rev2 (multi-reviewer findings + operator verdicts addressed)
branch: feature/GIM-96-palace-memory-decide
paperclip_issue: 95 (auto-assigned by paperclip; spec slug retained as GIM-96 for branch continuity)
predecessor: 9c87fb9 (develop tip after GIM-94 merge)
date: 2026-04-26
parent_initiative: N+2 Category 1 (USE-BUILT) — extract value from N+1a infrastructure
sequence_position: 1 of 4 — ENABLER (closes write-side loop for :Decision)
related: GIM-95a + GIM-95b (palace.memory.prime — read-back consumer)
---

# GIM-96 — `palace.memory.decide` — write-side `:Decision` MCP tool

## Goal

Close the **read-write loop** for `:Decision` nodes in Graphiti. Today read-side exists (`palace.memory.lookup`); no write-side. Result: 0 `:Decision` records despite N+1a foundation being live. After this slice, every committed-to choice (CR APPROVE / Opus verdict / operator design call) can be recorded.

## Sequence

Slice 1 of 4 in N+2 Category 1 (USE-BUILT) — **ENABLER**:

1. **`palace.memory.decide` — this slice** (write `:Decision`)
2. `palace.memory.prime` foundation — GIM-95a (renderer + universal core + operator role)
3. `palace.memory.prime` role cookbooks — GIM-95b (5 markdown fragments for cto/cr/pe/opus/qa)
4. `palace.code.test_impact` + `palace.code.semantic_search` — composite tools

This slice can ship before GIM-95a; prime will return non-empty `:Decision` lists once both shipped.

**Hard dependencies:**
- N+1a Graphiti foundation (GIM-75) — ✅ landed
- `save_entity_node` helper with `generate_name_embedding` (post-GIM-75 fix `036104e`) — ✅
- `palace.memory.lookup` filter whitelist mechanism — needs `slice_ref` filter added in **this** slice (Task 1)

## Decisions recorded (rev2 — multi-reviewer review + operator verdicts)

| Topic | Verdict | Rationale |
|---|---|---|
| `project` arg required | YES (default `None` → `palace_default_group_id`) | Convergence (Architect + API-designer + Security). Every other write-tool has it. |
| Error model | Validation/business → envelope `{ok: false, error_code, message}`. Infrastructure → `handle_tool_error(exc)` raise → FastMCP isError + recovery hint | Convergence (Architect + API-designer + Python-pro). Standardize `error_code` key (existing tools use `error`; backfill in followup) |
| `body` cap | 2000 chars (was 10000) | Convergence (Architect + API-designer). Prime-budget arithmetic: 5 × 10KB = 50KB > half of 2000-token budget |
| Array caps | `tags ≤ 16`, `evidence_ref ≤ 32` | Security finding. No objections from other reviewers |
| `decision_kind` | Optional `str | None = None`, free-form (NOT enum) | Convergence (Architect + API-designer). Free-form avoids breaking changes when adding values. Recommended vocabulary documented in description |
| `supersedes` | DROP from v1 | Architect: edge `(:Decision)-[:SUPERSEDES {valid_at}]->(:Decision)` is right thing in Graphiti, not attribute-list. Separate slice for proper edge-based supersession |
| `decision_maker_claimed` | Rename from `decision_maker` | Security: signals field is not attestation-verified. Future paperclip-attestation slice fills `attestation` field |
| `attestation` placeholder | Add `attestation: str = "none"` field NOW | v1 always returns `"none"`. Future slice (paperclip-attestation) fills with real values. Schema migration is non-trivial in Graphiti — cheaper to add placeholder now |
| `slice_ref` regex | `^GIM-\d+$ \| ^N\+\d+[a-z]*(\.\d+)?$ \| ^operator-decision-\d{8}$` | Tight + supports `N+1a.1` multi-part slugs we already use |
| `confidence` semantic | Writer self-assessment + Architect rubric in docstring; NO enforcement v1 | Soft-document `<0.3 → use IterationNote` rule; hard enforcement deferred until `IterationNote` MCP tool exists |
| `slice_ref` in filter whitelist | Add to `_WHITELIST["Decision"]` in `filters.py` in **this** slice (Task 1, NOT followup) | Python-pro 🟥: round-trip test would silently fail otherwise. unknown filter logged + ignored, not raised |
| Filter whitelist also needs | `decision_maker_claimed`, `decision_kind`, `tags`, `confidence` | For prime queries to actually filter (otherwise lookup is name-pattern only). Filter list documented in description |
| Prompt-injection rendering | Decide tool stores raw body unchanged; rendering policy lives in **GIM-95a** prime tool (untrusted-decision band + standing instruction) | Decide is storage; prime is rendering. Separation of concerns |

## Non-goals

- Auto-recording from CR/Opus/QA APPROVE comments (out of scope)
- Decision supersession enforcement — separate slice with edge-based model
- Cross-slice decision linking — separate
- Browse UI — `palace.memory.lookup` is the read path
- Decision content sanitization (markdown stripping etc.) — rendering concern, lives in prime

## Architecture

### `:Decision` node schema

`EntityNode` with `labels=["Decision"]`, attributes envelope per GIM-77 metadata convention.

**Required fields:**
| Field | Location | Type | Notes |
|---|---|---|---|
| `name` | `EntityNode.name` | str (1..200) | title; used for `name_embedding` |
| `group_id` | `EntityNode.group_id` | str | `Settings.palace_default_group_id` if `project` arg None |
| `body` | `attributes` | str (1..2000) | Full text, Markdown allowed |
| `slice_ref` | `attributes` | str | Tight regex (see § Validation) |
| `decision_maker_claimed` | `attributes` | str | One of `cto/codereviewer/pythonengineer/opusarchitectreviewer/qaengineer/operator/board` |
| `provenance` | `attributes` | str | Fixed `"asserted"` |
| `confidence` | `attributes` | float (0.0..1.0) | Writer self-assessment |
| `decided_at` | `attributes` | ISO8601 str | Default `now(UTC)` |
| `extractor` | `attributes` | str | Fixed `"palace.memory.decide@0.1"` |
| `extractor_version` | `attributes` | str | Fixed `"0.1"` |
| `attestation` | `attributes` | str | Fixed `"none"` in v1 (placeholder for paperclip-attestation) |

**Optional fields:**
| Field | Location | Type | Notes |
|---|---|---|---|
| `decision_kind` | `attributes` | str \| null | Free-form. Recommended values in description: `design \| scope-change \| review-approve \| spec-revision \| postmortem-finding \| board-ratification` |
| `tags` | `attributes` | list[str] (≤ 16) | Free keywords |
| `evidence_ref` | `attributes` | list[str] (≤ 32) | URLs / commit SHAs / paperclip UUIDs / paths to long context |

**Auto-computed:**
- `uuid` (Graphiti)
- `created_at` (Graphiti)
- `name_embedding` (via `generate_name_embedding` per GIM-75 fix)

### MCP tool signature

```python
@_tool(
    name="palace.memory.decide",
    description=(
        "Record a :Decision node in Graphiti. Use after a verdict, design call, "
        "review APPROVE/REJECT, or any committed-to choice that future agents should see. "
        "Required: title, body, slice_ref, decision_maker_claimed. "
        "Optional decision_kind values (free-form, not enforced): "
        "'design' | 'scope-change' | 'review-approve' | 'spec-revision' | "
        "'postmortem-finding' | 'board-ratification'. "
        "Confidence rubric: 1.0 = revert-if-wrong, 0.7 = default-unless-evidence-against, "
        "0.4 = best-guess, <0.3 = consider IterationNote (not enforced in v1)."
    ),
)
async def palace_memory_decide(
    title: str,
    body: str,
    slice_ref: str,
    decision_maker_claimed: str,
    project: str | None = None,
    decision_kind: str | None = None,
    tags: list[str] | None = None,
    evidence_ref: list[str] | None = None,
    confidence: float = 1.0,
) -> dict[str, Any]:
    """..."""
```

### Error model (split-brain → standardized)

**Validation/business errors** (envelope, no exception raised):
```json
{"ok": false, "error_code": "validation_error", "message": "<details>"}
{"ok": false, "error_code": "unknown_project", "message": "<slug not registered>"}
```

**Infrastructure failures** (`handle_tool_error(exc)` → FastMCP `isError=true` + recovery hint, NOT envelope):
- Embedder unreachable / OpenAI API failure → `EmbedderUnavailableError`
- Neo4j unreachable → `DriverUnavailableError`
- Graphiti not initialized → `DriverUnavailableError("graphiti not initialized")` — same as `palace.memory.lookup` pattern

This matches `palace.memory.lookup` existing behavior (per Architect convergence).

### `Settings` integration

Existing `Settings.palace_default_group_id` provides `project/gimle` default. If `project: str` arg passed, validate via existing `_resolve_project_to_group_id` helper (same as `palace.memory.lookup`). Unknown project → envelope `error_code: unknown_project`.

### Validation rules

Pydantic `DecideRequest`:

```python
SLICE_REF_PATTERN = r"^GIM-\d+$|^N\+\d+[a-z]*(\.\d+)?$|^operator-decision-\d{8}$"
VALID_DECISION_MAKERS = {
    "cto", "codereviewer", "pythonengineer",
    "opusarchitectreviewer", "qaengineer",
    "operator", "board",
}

class DecideRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=2_000)
    slice_ref: str = Field(..., pattern=SLICE_REF_PATTERN)
    decision_maker_claimed: str
    project: str | None = None
    decision_kind: str | None = Field(None, max_length=80)
    tags: list[str] | None = Field(None, max_length=16)
    evidence_ref: list[str] | None = Field(None, max_length=32)
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("decision_maker_claimed")
    @classmethod
    def _maker_allowed(cls, v: str) -> str:
        if v not in VALID_DECISION_MAKERS:
            raise ValueError(
                f"decision_maker_claimed '{v}' not in {VALID_DECISION_MAKERS}"
            )
        return v
```

Pydantic `ValidationError` → caught in MCP wrapper → envelope with `error_code: validation_error`.

### Filter whitelist update (Task 1, critical for round-trip test)

In `services/palace-mcp/src/palace_mcp/memory/filters.py` (per Python-pro 🟥 finding), extend `_WHITELIST["Decision"]`:

```python
_WHITELIST["Decision"] = {
    "name": "n.name = $name",
    "name_pattern": "n.name CONTAINS $name_pattern",
    "slice_ref": "n.slice_ref = $slice_ref",
    "decision_maker_claimed": "n.decision_maker_claimed = $decision_maker_claimed",
    "decision_kind": "n.decision_kind = $decision_kind",
    "tags_any": "ANY(t IN n.tags WHERE t IN $tags_any)",
    # confidence range etc. can be added in followup
}
```

Without this, `palace.memory.lookup(filters={"slice_ref": ...})` returns ALL `:Decision` nodes (filter logged + ignored). Round-trip integration test (Task 6) silently passes vacuously.

## Tasks

| # | Task | Owner | Deps |
|---|---|---|---|
| 1 | Pydantic input model `DecideRequest` + add filter whitelist entries in `memory/filters.py` for `slice_ref`/`decision_maker_claimed`/`decision_kind`/`tags_any` | PE | — |
| 2 | Implementation `decide()` in `services/palace-mcp/src/palace_mcp/memory/decide.py` (new file) | PE | T1 |
| 3 | MCP tool registration `palace.memory.decide` in `mcp_server.py` (Pattern #21 dedup) with split error model | PE | T2 |
| 4 | Unit tests — validation paths (envelope) + infrastructure paths (raise via handle_tool_error mock) | PE | T2 |
| 5 | Integration test through real MCP HTTP+SSE (per GIM-91 wire-contract rule) | PE | T3 |
| 6 | Round-trip integration test — write via decide, read via lookup with `slice_ref` filter, assert match | PE | T3, T1 |
| 7 | Update `services/palace-mcp/README.md` with example call + read-back via lookup | PE | T2 |
| 8 | QA Phase 4.1 — operator records 1 real `:Decision` for this slice itself; verifies via lookup + health | QA | T1-T7 |

### Task 1 — DecideRequest + filter whitelist

`services/palace-mcp/src/palace_mcp/memory/decide_models.py`:

```python
from datetime import datetime, UTC
from re import match as re_match
from pydantic import BaseModel, Field, field_validator, ValidationError

SLICE_REF_PATTERN = r"^GIM-\d+$|^N\+\d+[a-z]*(\.\d+)?$|^operator-decision-\d{8}$"
VALID_DECISION_MAKERS = {
    "cto", "codereviewer", "pythonengineer",
    "opusarchitectreviewer", "qaengineer",
    "operator", "board",
}

class DecideRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=2_000)
    slice_ref: str = Field(..., pattern=SLICE_REF_PATTERN)
    decision_maker_claimed: str
    project: str | None = None
    decision_kind: str | None = Field(None, max_length=80)
    tags: list[str] | None = Field(None, max_length=16)
    evidence_ref: list[str] | None = Field(None, max_length=32)
    confidence: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("decision_maker_claimed")
    @classmethod
    def _maker_allowed(cls, v: str) -> str:
        if v not in VALID_DECISION_MAKERS:
            raise ValueError(
                f"decision_maker_claimed '{v}' not in {VALID_DECISION_MAKERS}"
            )
        return v
```

In `services/palace-mcp/src/palace_mcp/memory/filters.py` extend `_WHITELIST["Decision"]` with whitelist entries above.

### Task 2 — decide implementation

`services/palace-mcp/src/palace_mcp/memory/decide.py`:

```python
from datetime import datetime, UTC
from typing import Any
from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode

from palace_mcp.graphiti_runtime import save_entity_node
from palace_mcp.memory.errors import EmbedderUnavailableError, DriverUnavailableError
from palace_mcp.memory.decide_models import DecideRequest

async def decide(req: DecideRequest, *, g: Graphiti, default_group_id: str) -> dict[str, Any]:
    """Pure inner function — raises on infra errors, returns envelope on validation."""
    group_id = req.project or default_group_id

    node = EntityNode(
        name=req.title,
        group_id=group_id,
        labels=["Decision"],
        attributes={
            "body": req.body,
            "slice_ref": req.slice_ref,
            "decision_maker_claimed": req.decision_maker_claimed,
            "decision_kind": req.decision_kind,
            "provenance": "asserted",
            "confidence": req.confidence,
            "decided_at": datetime.now(UTC).isoformat(),
            "extractor": "palace.memory.decide@0.1",
            "extractor_version": "0.1",
            "attestation": "none",
            "tags": req.tags or [],
            "evidence_ref": req.evidence_ref or [],
        },
    )

    # save_entity_node calls generate_name_embedding then node.save (per GIM-75 fix)
    # Embedder/Neo4j failures bubble up — caller wraps in handle_tool_error
    await save_entity_node(g, node)

    return {
        "ok": True,
        "uuid": node.uuid,
        "name": node.name,
        "slice_ref": req.slice_ref,
        "decision_maker_claimed": req.decision_maker_claimed,
        "decided_at": node.attributes["decided_at"],
        "name_embedding_dim": len(node.name_embedding) if node.name_embedding else 0,
    }
```

### Task 3 — MCP registration with split error model

In `services/palace-mcp/src/palace_mcp/mcp_server.py`:

```python
from palace_mcp.memory.decide import decide
from palace_mcp.memory.decide_models import DecideRequest
from pydantic import ValidationError

@_tool(name="palace.memory.decide", description="...")
async def palace_memory_decide(
    title: str,
    body: str,
    slice_ref: str,
    decision_maker_claimed: str,
    project: str | None = None,
    decision_kind: str | None = None,
    tags: list[str] | None = None,
    evidence_ref: list[str] | None = None,
    confidence: float = 1.0,
) -> dict[str, Any]:
    g = _graphiti
    if g is None:
        # Infrastructure: graphiti not initialised → handle_tool_error
        handle_tool_error(DriverUnavailableError("graphiti not initialized"))

    # Validation: envelope (no raise)
    try:
        req = DecideRequest(
            title=title, body=body, slice_ref=slice_ref,
            decision_maker_claimed=decision_maker_claimed,
            project=project, decision_kind=decision_kind,
            tags=tags, evidence_ref=evidence_ref, confidence=confidence,
        )
    except ValidationError as e:
        return {
            "ok": False,
            "error_code": "validation_error",
            "message": str(e),
        }

    # Project resolution: envelope on unknown
    if project is not None:
        try:
            resolved_group_id = await _resolve_project_to_group_id(_driver, project)
        except UnknownProjectError as e:
            return {
                "ok": False,
                "error_code": "unknown_project",
                "message": str(e),
            }

    # Infrastructure: embedder/neo4j failures bubble up → handle_tool_error
    try:
        return await decide(req, g=g, default_group_id=_default_group_id)
    except (EmbedderUnavailableError, DriverUnavailableError) as e:
        handle_tool_error(e)
    except Exception as e:
        # Unexpected — also handle_tool_error to give recovery hint
        handle_tool_error(e)
```

### Task 4 — unit tests

`tests/memory/test_decide_unit.py`:

**Validation paths (envelope assertion):**
- title=""  → `error_code: validation_error`
- body too long (2001 chars) → `error_code: validation_error`
- slice_ref="bad-format" → `error_code: validation_error`
- decision_maker_claimed="hacker" → `error_code: validation_error`
- confidence=1.5 → `error_code: validation_error`
- tags=[...×17] → `error_code: validation_error`
- evidence_ref=[...×33] → `error_code: validation_error`

**Infrastructure paths (handle_tool_error called):**
- `_graphiti = None` → handle_tool_error called with DriverUnavailableError
- save_entity_node raises EmbedderUnavailableError → handle_tool_error called
- save_entity_node raises generic Exception → handle_tool_error called

**Happy path:**
- Valid input → mock save_entity_node returns; verify EntityNode constructed with correct attributes envelope (all 11 required + 3 optional present, no `supersedes`)

Coverage target ≥ 90% on `decide.py` + new code in `mcp_server.py`.

### Task 5 — integration test through real MCP

```python
# tests/integration/test_palace_memory_decide_wire.py
async def test_decide_via_streamablehttp_writes_to_graphiti():
    async with streamablehttp_client("http://localhost:8080/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            result = await s.call_tool("palace.memory.decide", arguments={
                "title": "Test decision for GIM-96 wire-contract",
                "body": "Body for integration test",
                "slice_ref": "GIM-96",
                "decision_maker_claimed": "qaengineer",
            })
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True
            assert payload["uuid"]
            assert payload["slice_ref"] == "GIM-96"
            assert payload["decision_maker_claimed"] == "qaengineer"
```

### Task 6 — round-trip lookup test

```python
# tests/integration/test_decide_lookup_roundtrip.py
async def test_decide_then_lookup_returns_match():
    write = await call_decide(
        title="Roundtrip", slice_ref="GIM-96",
        body="...", decision_maker_claimed="qaengineer",
    )
    uuid = write["uuid"]

    # Lookup with slice_ref filter (requires Task 1 whitelist update)
    items = await call_lookup(
        entity_type="Decision",
        filters={"slice_ref": "GIM-96"},
    )
    matches = [it for it in items["items"] if it["id"] == uuid]
    assert matches, f"slice_ref filter returned no match — check filters._WHITELIST[Decision]"
    assert matches[0]["properties"]["decision_maker_claimed"] == "qaengineer"
    assert matches[0]["properties"]["confidence"] == 1.0
    assert matches[0]["properties"]["extractor"] == "palace.memory.decide@0.1"
    assert matches[0]["properties"]["attestation"] == "none"
```

### Task 7 — README update

`services/palace-mcp/README.md` — add usage example.

### Task 8 — QA Phase 4.1 live smoke

Operator drives:

1. Verify GIM-94 deploy-checklist runbook still passes
2. Call via MCP:
   ```
   palace.memory.decide(
     title="Adopt palace.memory.decide as Slice 1 of N+2 Cat 1",
     body="Closes write-side loop for :Decision. Enables real priming snapshot in GIM-95a/b.",
     slice_ref="GIM-96",
     decision_maker_claimed="operator",
     decision_kind="board-ratification",
     tags=["n+2","category-1","enabler"],
   )
   ```
3. Expect `{ok: true, uuid: "..."}`
4. Read back: `palace.memory.lookup(entity_type="Decision", filters={"slice_ref": "GIM-96"})` — expect ≥1 record matching above
5. `palace.memory.health` — `entity_counts.Decision >= 1` (was 0 before)
6. Trigger validation error: call with `decision_maker_claimed="hacker"` → expect envelope `error_code: validation_error`
7. Trigger handle_tool_error path: stop graphiti container temporarily, call decide → expect FastMCP `isError=true` (NOT envelope)
8. Paste outputs as QA evidence

## Acceptance

1. Tool callable via real MCP HTTP+SSE; returns `ok: true` + UUID for valid input
2. Validation errors return envelope with `error_code` (NOT a tool error / FastMCP isError)
3. Infrastructure errors (graphiti down, embedder down) raise via `handle_tool_error` (FastMCP `isError=true`)
4. `:Decision` records visible via `palace.memory.lookup(filters={"slice_ref": ...})` (whitelist entry works)
5. `palace.memory.health.entity_counts.Decision` increases by ≥1 after smoke
6. Round-trip integration test (Task 6) passes — write returns same data on read with filter
7. `name_embedding` non-null in Neo4j after save (verified via Cypher)
8. Pattern #21 dedup-aware registration — `palace.memory.decide` appears in `tools/list` exactly once
9. All MCP wire-contract test rule criteria met (per GIM-91)

## Out of scope (defer)

- Auto-record from CR APPROVE / Opus verdict / QA evidence comment — separate slice
- Decision supersession — separate slice with edge-based `(:Decision)-[:SUPERSEDES {valid_at}]->(:Decision)` model (Architect's correct approach, not attribute-list)
- `IterationNote` MCP tool + hard `confidence < 0.3` enforcement — separate slice
- Cross-project decision sharing (group_id federation) — separate large slice
- Existing tools' error_code standardization — backfill in followup slice (currently they use `error` key)

## References

- `services/palace-mcp/src/palace_mcp/graphiti_runtime.py` — `save_entity_node` helper (post-GIM-75 QA fix)
- `services/palace-mcp/src/palace_mcp/mcp_server.py:139-` — `_tool()` decorator (Pattern #21)
- `services/palace-mcp/src/palace_mcp/memory/filters.py` — `_WHITELIST` requires `slice_ref` entry (Task 1)
- `services/palace-mcp/src/palace_mcp/memory/lookup.py` — pattern for `_resolve_project_to_group_id`
- Memory `reference_graphiti_core_0_28_api_truth` — confirmed embedder API + EntityNode.attributes is first-class
- `paperclip-shared-fragments/fragments/compliance-enforcement.md` — MCP wire-contract test rule (GIM-91, post-compression)
- GIM-77 bridge extractor — establishes metadata envelope convention
- GIM-95a / GIM-95b sister slices — read-back consumer of `:Decision`
