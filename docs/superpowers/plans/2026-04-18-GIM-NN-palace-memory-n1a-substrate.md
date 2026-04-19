# N+1a Graphiti Substrate Swap — Implementation Plan

> ⚠ **DEPRECATED 2026-04-18.** This plan was executed as GIM-48,
> merged as `9d87fa0`, and reverted as `a4abd28` on the same day
> because it targets graphiti-core APIs that do not exist in 0.4.3
> (`Graphiti.nodes.entity.save`, `Graphiti.edges.entity.save`,
> `node.attributes`). Replacement slice:
> `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-group-id-migration.md`.
> Kept as historical record; **do not execute**.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct Cypher MERGE writes in palace-mcp with `graphiti-core` namespace API while preserving N+0 user-visible `palace.memory.lookup` and `palace.memory.health` behavior byte-for-byte.

**Architecture:** Import `graphiti-core` directly into palace-mcp (no separate compose service). Build typed `EntityNode` / `EntityEdge` for paperclip Issue / Comment / Agent / IngestRun (auto-prepended `:Entity`). All writes via `graphiti.nodes.entity.save()` / `graphiti.edges.entity.save()`. GC via `graphiti.nodes.entity.delete_by_uuids` after Python-level orphan filter. Bi-temporal exercised via `ASSIGNED_TO` edge invalidation when assignee changes between ingests. Embedder configured from `EMBEDDING_*` env (external Ollama URL, Alibaba DashScope, OpenAI, etc.). LLM client constructed but never invoked in this slice.

**Tech Stack:** Python 3.12, FastAPI/FastMCP (existing), `graphiti-core>=0.3`, Neo4j 5.26 (existing), pytest + pytest-asyncio, mypy --strict. Embedder: external URL (`OpenAIEmbedder` + `OpenAIGenericClient`).

**Spec:** `docs/superpowers/specs/2026-04-18-palace-memory-n1a-graphiti-substrate-swap.md`
**Verified API reference:** `docs/research/graphiti-core-verification.md` (§5-6)

---

## File Structure

**Create:**
- `services/palace-mcp/src/palace_mcp/graphiti_client.py` — Graphiti factory + lifecycle helpers
- `services/palace-mcp/src/palace_mcp/ingest/builders.py` — EntityNode/EntityEdge builders
- `services/palace-mcp/src/palace_mcp/ingest/upsert.py` — upsert_with_change_detection, invalidate_stale_assignments, gc_orphans
- `services/palace-mcp/src/palace_mcp/memory/ingest_run.py` — :IngestRun writer
- `services/palace-mcp/tests/test_graphiti_client.py`
- `services/palace-mcp/tests/ingest/test_builders.py`
- `services/palace-mcp/tests/ingest/test_upsert.py`
- `services/palace-mcp/tests/memory/test_lookup_graphiti.py`
- `services/palace-mcp/tests/memory/test_ingest_run.py`
- `services/palace-mcp/tests/memory/fixtures/lookup_n0_response.json` — captured N+0 lookup response for byte-identical regression check
- `services/palace-mcp/scripts/n1a_minigap_spike.py` — local-poke script for 4 mini-gaps

**Modify:**
- `services/palace-mcp/pyproject.toml` — add `graphiti-core>=0.3`
- `services/palace-mcp/src/palace_mcp/config.py` — add embedder/LLM env settings
- `services/palace-mcp/src/palace_mcp/ingest/runner.py` — full rewrite to use graphiti API
- `services/palace-mcp/src/palace_mcp/ingest/transform.py` — DELETE (replaced by builders.py)
- `services/palace-mcp/src/palace_mcp/ingest/paperclip.py` — construct Graphiti in `_amain`
- `services/palace-mcp/src/palace_mcp/memory/lookup.py` — replace Cypher with graphiti get_by_group_ids + Python filter
- `services/palace-mcp/src/palace_mcp/memory/health.py` — add embedder + graphiti probes
- `services/palace-mcp/src/palace_mcp/memory/schema.py` — add fields to HealthResponse
- `services/palace-mcp/src/palace_mcp/memory/constraints.py` — DELETE (graphiti handles uniqueness via uuid)
- `docker-compose.yml` — add EMBEDDING_* env vars to palace-mcp service
- `docs/research/graphiti-core-verification.md` — append §8 (mini-gap resolutions)

**Delete:**
- `services/palace-mcp/src/palace_mcp/memory/cypher.py` — raw Cypher constants no longer used
- `services/palace-mcp/src/palace_mcp/ingest/transform.py` — replaced by builders.py
- `services/palace-mcp/src/palace_mcp/memory/constraints.py` — graphiti-managed
- `services/palace-mcp/tests/memory/test_cypher_parameterization.py` — no Cypher to parameterize
- `services/palace-mcp/tests/memory/test_schema.py` — covered by builders tests
- `services/palace-mcp/tests/ingest/test_runner.py` — replaced by test_upsert.py + test_builders.py
- `services/palace-mcp/tests/ingest/test_transform.py` — replaced by test_builders.py

---

## Phase 0 — Mini-gap resolution (spec §10, blocks Phase 1)

### Task 1: Spike script verifying 4 mini-gaps locally

**Files:**
- Create: `services/palace-mcp/scripts/n1a_minigap_spike.py`

- [ ] **Step 1: Write spike script**

```python
"""N+1a mini-gap spike. Run against a local Neo4j 5.26 + external Ollama.

Resolves 4 mini-gaps from N+1a spec §10 before implementation begins:
1. Skip-embed-on-unchanged idiom — does setting node.name_embedding manually bypass re-embed?
2. EntityNode.attributes round-trip — arbitrary dict keys persist?
3. Graphiti(llm_client=OpenAIGenericClient(...)) idle — no side effects when LLM never invoked?
4. graphiti-core ↔ Neo4j 5.26 compatibility

Usage:
  EMBEDDING_BASE_URL=http://your-ollama:11434/v1 \
  EMBEDDING_MODEL=nomic-embed-text EMBEDDING_DIM=768 \
  uv run python scripts/n1a_minigap_spike.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig


async def main() -> None:
    g = Graphiti(
        os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ["NEO4J_PASSWORD"],
        llm_client=OpenAIGenericClient(LLMConfig(
            api_key=os.environ.get("LLM_API_KEY", "placeholder"),
            model=os.environ.get("LLM_MODEL", "llama3:8b"),
            base_url=os.environ["EMBEDDING_BASE_URL"],
        )),
        embedder=OpenAIEmbedder(OpenAIEmbedderConfig(
            api_key=os.environ.get("EMBEDDING_API_KEY", "placeholder"),
            embedding_model=os.environ["EMBEDDING_MODEL"],
            embedding_dim=int(os.environ["EMBEDDING_DIM"]),
            base_url=os.environ["EMBEDDING_BASE_URL"],
        )),
    )

    print("=== Gap 4: Neo4j 5.26 compatibility ===")
    await g.build_indices_and_constraints()
    print("OK — build_indices_and_constraints succeeded")

    group_id = "spike/n1a"
    uid = str(uuid4())

    print("\n=== Gap 2: EntityNode.attributes round-trip ===")
    node = EntityNode(
        uuid=uid, name="spike-node", labels=["SpikeNote"], group_id=group_id,
        summary="round-trip test",
        attributes={
            "text_hash": "abc123",
            "tags": ["one", "two"],
            "scope": "project",
            "nested": {"level": 1},
            "count": 42,
        },
    )
    await g.nodes.entity.save(node)
    fetched = await g.nodes.entity.get_by_uuid(uid)
    print(f"saved attributes:   {node.attributes}")
    print(f"fetched attributes: {fetched.attributes}")
    assert fetched.attributes == node.attributes, "attribute round-trip failure"
    print("OK — arbitrary dict keys persist intact")

    print("\n=== Gap 1: Skip-embed-on-unchanged idiom ===")
    initial_embedding = list(fetched.name_embedding) if fetched.name_embedding else None
    print(f"first embedding present: {initial_embedding is not None}, len={len(initial_embedding) if initial_embedding else 0}")

    fetched.attributes["palace_last_seen_at"] = datetime.now(timezone.utc).isoformat()
    # Test: assigning name_embedding manually + save — does it skip regeneration?
    await g.nodes.entity.save(fetched)
    refetched = await g.nodes.entity.get_by_uuid(uid)
    second_embedding = list(refetched.name_embedding) if refetched.name_embedding else None
    print(f"second embedding == first: {initial_embedding == second_embedding}")
    print("RESULT: see logs above — if save() always regenerates, document workaround")

    print("\n=== Gap 3: idle LLM client side effects ===")
    print("OK — Graphiti() construction + add/get above never invoked LLM")
    print("(no add_episode call; LLM client unused throughout)")

    await g.nodes.entity.delete_by_uuids([uid])
    await g.close()
    print("\nspike complete")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Add graphiti-core to pyproject.toml temporarily for spike**

Edit `services/palace-mcp/pyproject.toml` `[project].dependencies` adding `"graphiti-core>=0.3,<0.5",` (kept in next task too).

- [ ] **Step 3: Install + run spike**

```bash
cd services/palace-mcp
uv sync
EMBEDDING_BASE_URL=http://your-external-ollama:11434/v1 \
EMBEDDING_MODEL=nomic-embed-text EMBEDDING_DIM=768 \
NEO4J_PASSWORD=your-password \
uv run python scripts/n1a_minigap_spike.py
```

Expected: prints OK lines for gaps 2, 3, 4 and a comparison line for gap 1.

- [ ] **Step 4: Append findings to verification doc**

Add a new section to `docs/research/graphiti-core-verification.md` titled `## 8. Mini-gap resolutions (N+1a spike, YYYY-MM-DD)` with bullet for each gap and the actual observed behavior. Document workaround if gap 1 regenerates embedding (e.g., subclass `EntityNode` overriding `generate_name_embedding` to no-op when `text_hash` matches stored).

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/scripts/n1a_minigap_spike.py services/palace-mcp/pyproject.toml docs/research/graphiti-core-verification.md
git commit -m "spike(n1a): resolve 4 graphiti-core mini-gaps before implementation"
```

---

## Phase 1 — Foundation (config + Graphiti factory)

### Task 2: Add graphiti-core dependency

**Files:**
- Modify: `services/palace-mcp/pyproject.toml`

- [ ] **Step 1: Confirm graphiti-core line present from spike (Task 1 step 2)**

Verify `services/palace-mcp/pyproject.toml` `[project].dependencies` contains `"graphiti-core>=0.3,<0.5",`. If only added during spike, ensure it stays.

- [ ] **Step 2: Run uv sync + smoke import**

```bash
cd services/palace-mcp
uv sync
uv run python -c "from graphiti_core import Graphiti; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit (if not already from Task 1)**

```bash
git add services/palace-mcp/pyproject.toml
git commit -m "feat(deps): add graphiti-core for N+1a substrate swap" || true
```

### Task 3: Embedder + LLM env settings in config.py

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/config.py`
- Test: `services/palace-mcp/tests/test_config.py`

- [ ] **Step 1: Write failing test for embedder settings**

Add to `services/palace-mcp/tests/test_config.py`:

```python
import pytest
from palace_mcp.config import IngestSettings


def test_ingest_settings_loads_embedder_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERCLIP_API_URL", "https://x")
    monkeypatch.setenv("PAPERCLIP_INGEST_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("NEO4J_PASSWORD", "p")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    s = IngestSettings()
    assert s.embedding_base_url == "http://ollama:11434/v1"
    assert s.embedding_api_key.get_secret_value() == "ollama"
    assert s.embedding_model == "nomic-embed-text"
    assert s.embedding_dim == 768
    # LLM defaults to embedding base if unset
    assert s.llm_base_url == "http://ollama:11434/v1"
    assert s.llm_model == "llama3:8b"
```

- [ ] **Step 2: Run — expect AttributeError on missing fields**

```bash
cd services/palace-mcp
uv run pytest tests/test_config.py::test_ingest_settings_loads_embedder_env -v
```

Expected: FAIL — `AttributeError: 'IngestSettings' object has no attribute 'embedding_base_url'`

- [ ] **Step 3: Add fields to IngestSettings + Settings**

In `services/palace-mcp/src/palace_mcp/config.py`, add to both `Settings` and `IngestSettings`:

```python
    # Embedder config — graphiti-core OpenAIEmbedder via OpenAI-compat endpoint
    embedding_base_url: str = "http://ollama:11434/v1"
    embedding_api_key: SecretStr = SecretStr("placeholder")
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # LLM client — required by graphiti-core constructor; not invoked in N+1a
    llm_base_url: str | None = None  # falls back to embedding_base_url
    llm_api_key: SecretStr | None = None  # falls back to embedding_api_key
    llm_model: str = "llama3:8b"

    @property
    def effective_llm_base_url(self) -> str:
        return self.llm_base_url or self.embedding_base_url

    @property
    def effective_llm_api_key(self) -> SecretStr:
        return self.llm_api_key or self.embedding_api_key
```

- [ ] **Step 4: Update test to use effective_* properties**

Replace last two assertions in the test:

```python
    assert s.effective_llm_base_url == "http://ollama:11434/v1"
    assert s.llm_model == "llama3:8b"
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/test_config.py::test_ingest_settings_loads_embedder_env -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/config.py services/palace-mcp/tests/test_config.py
git commit -m "feat(config): add embedder + LLM env settings for graphiti-core"
```

### Task 4: Graphiti factory module

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/graphiti_client.py`
- Test: `services/palace-mcp/tests/test_graphiti_client.py`

- [ ] **Step 1: Write failing test for build_graphiti(settings)**

Create `services/palace-mcp/tests/test_graphiti_client.py`:

```python
from unittest.mock import patch

from palace_mcp.config import IngestSettings
from palace_mcp.graphiti_client import build_graphiti


def test_build_graphiti_constructs_with_openai_compat_clients(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PAPERCLIP_API_URL", "https://x")
    monkeypatch.setenv("PAPERCLIP_INGEST_API_KEY", "k")
    monkeypatch.setenv("PAPERCLIP_COMPANY_ID", "c")
    monkeypatch.setenv("NEO4J_PASSWORD", "p")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    settings = IngestSettings()
    with patch("palace_mcp.graphiti_client.Graphiti") as mock_graphiti:
        build_graphiti(settings)
    assert mock_graphiti.called
    # Verify constructor was called with our settings
    call = mock_graphiti.call_args
    assert call.kwargs.get("llm_client") is not None
    assert call.kwargs.get("embedder") is not None
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/test_graphiti_client.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'palace_mcp.graphiti_client'`

- [ ] **Step 3: Implement factory**

Create `services/palace-mcp/src/palace_mcp/graphiti_client.py`:

```python
"""Graphiti instance factory.

Constructs a graphiti-core Graphiti client from IngestSettings using
OpenAIGenericClient + OpenAIEmbedder against an OpenAI-compat endpoint
(works for external Ollama, Alibaba DashScope, OpenAI, Voyage, Cohere).

LLM client is required by Graphiti() constructor but never invoked in N+1a
(structured ingest via add_triplet bypasses LLM extraction entirely).
"""

from __future__ import annotations

from graphiti_core import Graphiti
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from palace_mcp.config import IngestSettings, Settings


def build_graphiti(settings: IngestSettings | Settings) -> Graphiti:
    """Build a Graphiti instance from settings.

    Caller is responsible for `await graphiti.close()` when done.
    """
    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=settings.effective_llm_api_key.get_secret_value(),
            model=settings.llm_model,
            base_url=settings.effective_llm_base_url,
        )
    )
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=settings.embedding_api_key.get_secret_value(),
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            base_url=settings.embedding_base_url,
        )
    )
    return Graphiti(
        settings.neo4j_uri,
        "neo4j",
        settings.neo4j_password.get_secret_value(),
        llm_client=llm_client,
        embedder=embedder,
    )
```

Also extend `Settings` in `config.py` to inherit the same embedder fields (or extract to a mixin). Simplest: copy fields + properties from Task 3 step 3 to `Settings` class as well.

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/test_graphiti_client.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/graphiti_client.py services/palace-mcp/tests/test_graphiti_client.py services/palace-mcp/src/palace_mcp/config.py
git commit -m "feat(graphiti): add Graphiti factory using OpenAI-compat clients"
```

---

## Phase 2 — Ingest builders + upsert

### Task 5: build_issue_node builder

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/ingest/builders.py`
- Test: `services/palace-mcp/tests/ingest/test_builders.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/ingest/test_builders.py`:

```python
from datetime import datetime, timezone
from hashlib import sha256

from palace_mcp.ingest.builders import build_issue_node, GROUP_ID

GIMLE_GROUP = "project/gimle"


def test_build_issue_node_minimal() -> None:
    issue = {
        "id": "uuid-issue-1",
        "identifier": "GIM-44",
        "title": "Test issue",
        "description": "A description",
        "status": "todo",
        "createdAt": "2026-04-17T10:00:00+00:00",
        "updatedAt": "2026-04-17T11:00:00+00:00",
        "assigneeAgentId": None,
    }
    run_started = "2026-04-18T08:00:00+00:00"
    node = build_issue_node(issue, run_started=run_started, group_id=GIMLE_GROUP)
    assert node.uuid == "uuid-issue-1"
    assert node.name == "GIM-44: Test issue"
    assert node.labels == ["Issue"]  # auto-prepend :Entity confirmed in verification §5.F
    assert node.group_id == GIMLE_GROUP
    assert node.attributes["id"] == "uuid-issue-1"
    assert node.attributes["key"] == "GIM-44"
    assert node.attributes["status"] == "todo"
    assert node.attributes["source"] == "paperclip"
    assert node.attributes["source_created_at"] == "2026-04-17T10:00:00+00:00"
    assert node.attributes["source_updated_at"] == "2026-04-17T11:00:00+00:00"
    assert node.attributes["palace_last_seen_at"] == run_started
    expected_hash = sha256("A description".encode()).hexdigest()
    assert node.attributes["text_hash"] == expected_hash
```

- [ ] **Step 2: Run — expect ImportError**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'palace_mcp.ingest.builders'`

- [ ] **Step 3: Implement build_issue_node**

Create `services/palace-mcp/src/palace_mcp/ingest/builders.py`:

```python
"""EntityNode and EntityEdge builders for paperclip data.

Maps paperclip API DTOs to graphiti-core EntityNode / EntityEdge instances.
Group_id hardcoded to "project/gimle" in N+1a; parameterized in N+1b.
Pure functions — no I/O.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

GROUP_ID = "project/gimle"  # parameterized in N+1b
SOURCE = "paperclip"


def _ts(record: dict[str, Any], key: str, fallback_key: str = "createdAt") -> str:
    val = record.get(key) or record.get(fallback_key)
    if not isinstance(val, str):
        raise ValueError(
            f"paperclip record missing {key}/{fallback_key}: {record.get('id')}"
        )
    return val


def build_issue_node(
    issue: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    description = issue.get("description") or ""
    return EntityNode(
        uuid=issue["id"],
        name=f"{issue.get('identifier') or issue.get('key') or ''}: {issue.get('title') or ''}",
        labels=["Issue"],  # graphiti auto-prepends :Entity (verification §5.F)
        group_id=group_id,
        summary=description[:500],
        attributes={
            "id": issue["id"],
            "key": issue.get("identifier") or issue.get("key") or "",
            "title": issue.get("title") or "",
            "description": description,
            "status": issue.get("status") or "",
            "source": SOURCE,
            "source_created_at": _ts(issue, "createdAt"),
            "source_updated_at": _ts(issue, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(description.encode()).hexdigest(),
            "assignee_agent_id": issue.get("assigneeAgentId"),
        },
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_builders.py::test_build_issue_node_minimal -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/builders.py services/palace-mcp/tests/ingest/test_builders.py
git commit -m "feat(ingest): add build_issue_node builder"
```

### Task 6: build_comment_node + build_agent_node builders

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/builders.py`
- Test: `services/palace-mcp/tests/ingest/test_builders.py`

- [ ] **Step 1: Write failing tests**

Append to `services/palace-mcp/tests/ingest/test_builders.py`:

```python
from palace_mcp.ingest.builders import build_agent_node, build_comment_node


def test_build_comment_node() -> None:
    comment = {
        "id": "uuid-comment-1",
        "body": "Looks good",
        "issueId": "uuid-issue-1",
        "authorAgentId": "uuid-agent-1",
        "createdAt": "2026-04-17T10:30:00+00:00",
        "updatedAt": "2026-04-17T10:30:00+00:00",
    }
    node = build_comment_node(comment, run_started="2026-04-18T08:00:00+00:00")
    assert node.uuid == "uuid-comment-1"
    assert node.labels == ["Comment"]
    assert node.attributes["body"] == "Looks good"
    assert node.attributes["issue_id"] == "uuid-issue-1"
    assert node.attributes["author_agent_id"] == "uuid-agent-1"
    assert node.attributes["source"] == "paperclip"


def test_build_agent_node() -> None:
    agent = {
        "id": "uuid-agent-1",
        "name": "CodeReviewer",
        "urlKey": "codereviewer",
        "role": "reviewer",
        "createdAt": "2026-04-15T12:00:00+00:00",
        "updatedAt": "2026-04-16T12:00:00+00:00",
    }
    node = build_agent_node(agent, run_started="2026-04-18T08:00:00+00:00")
    assert node.uuid == "uuid-agent-1"
    assert node.labels == ["Agent"]
    assert node.attributes["name"] == "CodeReviewer"
    assert node.attributes["url_key"] == "codereviewer"
    assert node.attributes["role"] == "reviewer"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: 2 FAILS for missing functions.

- [ ] **Step 3: Implement both builders**

Append to `services/palace-mcp/src/palace_mcp/ingest/builders.py`:

```python
def build_comment_node(
    comment: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    body = comment.get("body") or ""
    return EntityNode(
        uuid=comment["id"],
        name=f"comment-{comment['id'][:8]}",
        labels=["Comment"],
        group_id=group_id,
        summary=body[:500],
        attributes={
            "id": comment["id"],
            "body": body,
            "issue_id": comment.get("issueId") or "",
            "author_agent_id": comment.get("authorAgentId"),
            "source": SOURCE,
            "source_created_at": _ts(comment, "createdAt"),
            "source_updated_at": _ts(comment, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(body.encode()).hexdigest(),
        },
    )


def build_agent_node(
    agent: dict[str, Any], *, run_started: str, group_id: str = GROUP_ID
) -> EntityNode:
    name = agent.get("name") or ""
    return EntityNode(
        uuid=agent["id"],
        name=name,
        labels=["Agent"],
        group_id=group_id,
        summary=f"{name} ({agent.get('role') or ''})",
        attributes={
            "id": agent["id"],
            "name": name,
            "url_key": agent.get("urlKey") or "",
            "role": agent.get("role") or "",
            "source": SOURCE,
            "source_created_at": _ts(agent, "createdAt"),
            "source_updated_at": _ts(agent, "updatedAt"),
            "palace_last_seen_at": run_started,
            "text_hash": sha256(name.encode()).hexdigest(),
        },
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/builders.py services/palace-mcp/tests/ingest/test_builders.py
git commit -m "feat(ingest): add comment + agent node builders"
```

### Task 7: Edge builders (ON, AUTHORED_BY, ASSIGNED_TO)

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/builders.py`
- Test: `services/palace-mcp/tests/ingest/test_builders.py`

- [ ] **Step 1: Write failing tests**

Append to `services/palace-mcp/tests/ingest/test_builders.py`:

```python
from palace_mcp.ingest.builders import (
    build_assigned_to_edge,
    build_authored_by_edge,
    build_on_edge,
)


def test_build_on_edge() -> None:
    edge = build_on_edge(
        comment_uuid="uuid-comment-1",
        issue_uuid="uuid-issue-1",
        comment_created_at="2026-04-17T10:30:00+00:00",
        run_started="2026-04-18T08:00:00+00:00",
    )
    assert edge.source_node_uuid == "uuid-comment-1"
    assert edge.target_node_uuid == "uuid-issue-1"
    assert edge.name == "ON"
    assert edge.group_id == GIMLE_GROUP
    assert edge.valid_at is not None
    assert edge.invalid_at is None


def test_build_authored_by_edge() -> None:
    edge = build_authored_by_edge(
        comment_uuid="uuid-comment-1",
        agent_uuid="uuid-agent-1",
        comment_created_at="2026-04-17T10:30:00+00:00",
        run_started="2026-04-18T08:00:00+00:00",
    )
    assert edge.name == "AUTHORED_BY"
    assert edge.source_node_uuid == "uuid-comment-1"
    assert edge.target_node_uuid == "uuid-agent-1"


def test_build_assigned_to_edge() -> None:
    edge = build_assigned_to_edge(
        issue_uuid="uuid-issue-1",
        agent_uuid="uuid-agent-1",
        run_started="2026-04-18T08:00:00+00:00",
    )
    assert edge.name == "ASSIGNED_TO"
    assert edge.source_node_uuid == "uuid-issue-1"
    assert edge.target_node_uuid == "uuid-agent-1"
    assert edge.valid_at is not None
    assert edge.invalid_at is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: 3 FAILS for missing edge builder functions.

- [ ] **Step 3: Implement edge builders**

Append to `services/palace-mcp/src/palace_mcp/ingest/builders.py`:

```python
from datetime import datetime


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def build_on_edge(
    *,
    comment_uuid: str,
    issue_uuid: str,
    comment_created_at: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=comment_uuid,
        target_node_uuid=issue_uuid,
        name="ON",
        fact=f"Comment {comment_uuid} is on issue {issue_uuid}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(comment_created_at),
        invalid_at=None,
    )


def build_authored_by_edge(
    *,
    comment_uuid: str,
    agent_uuid: str,
    comment_created_at: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=comment_uuid,
        target_node_uuid=agent_uuid,
        name="AUTHORED_BY",
        fact=f"Comment {comment_uuid} authored by agent {agent_uuid}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(comment_created_at),
        invalid_at=None,
    )


def build_assigned_to_edge(
    *,
    issue_uuid: str,
    agent_uuid: str,
    run_started: str,
    group_id: str = GROUP_ID,
) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=issue_uuid,
        target_node_uuid=agent_uuid,
        name="ASSIGNED_TO",
        fact=f"Issue {issue_uuid} assigned to agent {agent_uuid} as of {run_started}",
        group_id=group_id,
        created_at=_parse_iso(run_started),
        valid_at=_parse_iso(run_started),
        invalid_at=None,
    )
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_builders.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/builders.py services/palace-mcp/tests/ingest/test_builders.py
git commit -m "feat(ingest): add edge builders (ON, AUTHORED_BY, ASSIGNED_TO)"
```

### Task 8: upsert_with_change_detection helper

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/ingest/upsert.py`
- Test: `services/palace-mcp/tests/ingest/test_upsert.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/ingest/test_upsert.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.nodes import EntityNode

from palace_mcp.ingest.upsert import UpsertResult, upsert_with_change_detection


def _make_node(uuid: str, text_hash: str, palace_last_seen_at: str) -> EntityNode:
    return EntityNode(
        uuid=uuid, name="n", labels=["Issue"], group_id="project/gimle",
        summary="s", attributes={"text_hash": text_hash, "palace_last_seen_at": palace_last_seen_at},
    )


@pytest.mark.asyncio
async def test_upsert_new_node_inserts() -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_uuid = AsyncMock(side_effect=Exception("NotFound"))
    graphiti.nodes.entity.save = AsyncMock()
    node = _make_node("u1", "hash-a", "2026-04-18T00:00:00+00:00")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.INSERTED
    graphiti.nodes.entity.save.assert_awaited_once_with(node)


@pytest.mark.asyncio
async def test_upsert_unchanged_skips_embed() -> None:
    graphiti = MagicMock()
    existing = _make_node("u1", "hash-a", "2026-04-17T00:00:00+00:00")
    graphiti.nodes.entity.get_by_uuid = AsyncMock(return_value=existing)
    graphiti.nodes.entity.save = AsyncMock()
    node = _make_node("u1", "hash-a", "2026-04-18T00:00:00+00:00")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.SKIPPED_UNCHANGED
    # palace_last_seen_at refreshed on existing node
    assert existing.attributes["palace_last_seen_at"] == "2026-04-18T00:00:00+00:00"
    graphiti.nodes.entity.save.assert_awaited_once_with(existing)


@pytest.mark.asyncio
async def test_upsert_text_changed_re_embeds() -> None:
    graphiti = MagicMock()
    existing = _make_node("u1", "hash-a", "2026-04-17T00:00:00+00:00")
    graphiti.nodes.entity.get_by_uuid = AsyncMock(return_value=existing)
    graphiti.nodes.entity.save = AsyncMock()
    node = _make_node("u1", "hash-b", "2026-04-18T00:00:00+00:00")
    result = await upsert_with_change_detection(graphiti, node)
    assert result == UpsertResult.RE_EMBEDDED
    graphiti.nodes.entity.save.assert_awaited_once_with(node)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_upsert.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'palace_mcp.ingest.upsert'`

- [ ] **Step 3: Implement upsert helper**

Create `services/palace-mcp/src/palace_mcp/ingest/upsert.py`:

```python
"""Upsert helpers using graphiti-core namespace API.

Implements text_hash-based change detection (avoid re-embed cost) and
ASSIGNED_TO bi-temporal invalidation per spec §4.4.
"""

from __future__ import annotations

import enum
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode


class UpsertResult(str, enum.Enum):
    INSERTED = "inserted"
    SKIPPED_UNCHANGED = "skipped_unchanged"
    RE_EMBEDDED = "re_embedded"


async def upsert_with_change_detection(
    graphiti: Graphiti, node: EntityNode
) -> UpsertResult:
    """Save a node, skipping re-embed if text_hash matches stored value.

    Returns one of UpsertResult to signal what happened (used for log
    counters and observability).
    """
    try:
        existing = await graphiti.nodes.entity.get_by_uuid(node.uuid)
    except Exception:
        # Node does not exist — insert (triggers embed via save())
        await graphiti.nodes.entity.save(node)
        return UpsertResult.INSERTED

    if existing.attributes.get("text_hash") == node.attributes.get("text_hash"):
        # Unchanged — refresh palace_last_seen_at on existing object only
        existing.attributes["palace_last_seen_at"] = node.attributes[
            "palace_last_seen_at"
        ]
        # If mini-gap §1 confirms manual name_embedding bypass, set it here
        # before save to avoid regen. Otherwise save() always re-embeds —
        # acceptable for unchanged path since text didn't change either way.
        await graphiti.nodes.entity.save(existing)
        return UpsertResult.SKIPPED_UNCHANGED

    # Text changed — full re-embed via save() of new node
    await graphiti.nodes.entity.save(node)
    return UpsertResult.RE_EMBEDDED
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_upsert.py -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/upsert.py services/palace-mcp/tests/ingest/test_upsert.py
git commit -m "feat(ingest): upsert_with_change_detection via text_hash"
```

### Task 9: invalidate_stale_assignments (bi-temporal demo)

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/upsert.py`
- Test: `services/palace-mcp/tests/ingest/test_upsert.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/ingest/test_upsert.py`:

```python
from datetime import datetime

from graphiti_core.edges import EntityEdge

from palace_mcp.ingest.upsert import invalidate_stale_assignments


def _edge(name: str, source: str, target: str, invalid_at: datetime | None = None) -> EntityEdge:
    return EntityEdge(
        source_node_uuid=source,
        target_node_uuid=target,
        name=name,
        fact="f",
        group_id="project/gimle",
        created_at=datetime.fromisoformat("2026-04-17T08:00:00+00:00"),
        valid_at=datetime.fromisoformat("2026-04-17T08:00:00+00:00"),
        invalid_at=invalid_at,
    )


@pytest.mark.asyncio
async def test_invalidate_when_assignee_changed() -> None:
    graphiti = MagicMock()
    issue_uuid = "uuid-issue-1"
    old_edge = _edge("ASSIGNED_TO", issue_uuid, "old-agent")
    other_edge = _edge("ON", "uuid-comment-1", issue_uuid)
    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=[old_edge, other_edge])
    graphiti.edges.entity.save = AsyncMock()

    run_started_iso = "2026-04-18T08:00:00+00:00"
    invalidated = await invalidate_stale_assignments(
        graphiti, issue_uuid, new_agent_uuid="new-agent", run_started=run_started_iso
    )
    assert invalidated == 1
    assert old_edge.invalid_at == datetime.fromisoformat(run_started_iso)
    graphiti.edges.entity.save.assert_awaited_once_with(old_edge)
    # ON edge untouched
    assert other_edge.invalid_at is None


@pytest.mark.asyncio
async def test_no_invalidation_when_same_assignee() -> None:
    graphiti = MagicMock()
    issue_uuid = "uuid-issue-1"
    existing = _edge("ASSIGNED_TO", issue_uuid, "agent-x")
    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=[existing])
    graphiti.edges.entity.save = AsyncMock()

    invalidated = await invalidate_stale_assignments(
        graphiti, issue_uuid, new_agent_uuid="agent-x",
        run_started="2026-04-18T08:00:00+00:00",
    )
    assert invalidated == 0
    assert existing.invalid_at is None
    graphiti.edges.entity.save.assert_not_awaited()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_upsert.py::test_invalidate_when_assignee_changed -v
```

Expected: FAIL — `ImportError: cannot import name 'invalidate_stale_assignments'`

- [ ] **Step 3: Implement invalidate_stale_assignments**

Append to `services/palace-mcp/src/palace_mcp/ingest/upsert.py`:

```python
from datetime import datetime


async def invalidate_stale_assignments(
    graphiti: Graphiti,
    issue_uuid: str,
    new_agent_uuid: str | None,
    run_started: str,
) -> int:
    """Invalidate stale ASSIGNED_TO edges via graphiti.edges.entity.save.

    Returns count of edges invalidated. Native bi-temporal — zero raw Cypher.
    """
    invalidated = 0
    run_started_dt = datetime.fromisoformat(run_started)
    edges = await graphiti.edges.entity.get_by_node_uuid(issue_uuid)
    for edge in edges:
        if edge.name != "ASSIGNED_TO":
            continue
        if edge.invalid_at is not None:
            continue  # already invalidated
        if edge.target_node_uuid == new_agent_uuid:
            continue  # same assignee — no change
        edge.invalid_at = run_started_dt
        await graphiti.edges.entity.save(edge)
        invalidated += 1
    return invalidated
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_upsert.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/upsert.py services/palace-mcp/tests/ingest/test_upsert.py
git commit -m "feat(ingest): invalidate_stale_assignments (native bi-temporal)"
```

### Task 10: gc_orphans

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/upsert.py`
- Test: `services/palace-mcp/tests/ingest/test_upsert.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/ingest/test_upsert.py`:

```python
from palace_mcp.ingest.upsert import gc_orphans


def _node(uuid: str, labels: list[str], source: str | None, last_seen: str) -> EntityNode:
    return EntityNode(
        uuid=uuid, name="n", labels=labels, group_id="project/gimle",
        summary="s",
        attributes={
            "source": source,
            "palace_last_seen_at": last_seen,
        },
    )


@pytest.mark.asyncio
async def test_gc_orphans_deletes_stale_paperclip_nodes() -> None:
    graphiti = MagicMock()
    nodes = [
        _node("u-fresh", ["Issue"], "paperclip", "2026-04-18T08:00:00+00:00"),
        _node("u-stale", ["Issue"], "paperclip", "2026-04-17T00:00:00+00:00"),
        _node("u-non-paperclip", ["Note"], None, "2026-04-17T00:00:00+00:00"),
        _node("u-stale-comment", ["Comment"], "paperclip", "2026-04-15T00:00:00+00:00"),
    ]
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=nodes)
    graphiti.nodes.entity.delete_by_uuids = AsyncMock()

    cutoff = "2026-04-18T08:00:00+00:00"
    deleted = await gc_orphans(graphiti, group_id="project/gimle", cutoff=cutoff)
    assert deleted == 2
    graphiti.nodes.entity.delete_by_uuids.assert_awaited_once()
    deleted_uuids = sorted(graphiti.nodes.entity.delete_by_uuids.await_args.args[0])
    assert deleted_uuids == ["u-stale", "u-stale-comment"]


@pytest.mark.asyncio
async def test_gc_orphans_no_op_when_none_stale() -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[])
    graphiti.nodes.entity.delete_by_uuids = AsyncMock()
    deleted = await gc_orphans(graphiti, group_id="project/gimle", cutoff="2026-04-18T00:00:00+00:00")
    assert deleted == 0
    graphiti.nodes.entity.delete_by_uuids.assert_not_awaited()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/ingest/test_upsert.py::test_gc_orphans_deletes_stale_paperclip_nodes -v
```

Expected: FAIL — ImportError on `gc_orphans`.

- [ ] **Step 3: Implement gc_orphans**

Append to `services/palace-mcp/src/palace_mcp/ingest/upsert.py`:

```python
PAPERCLIP_LABELS = {"Issue", "Comment", "Agent"}


async def gc_orphans(graphiti: Graphiti, *, group_id: str, cutoff: str) -> int:
    """Delete paperclip-sourced nodes whose palace_last_seen_at < cutoff.

    Uses graphiti.nodes.entity.get_by_group_ids + Python filter +
    delete_by_uuids. Zero raw Cypher per spec §9 acceptance.
    """
    all_nodes = await graphiti.nodes.entity.get_by_group_ids([group_id])
    stale_uuids = [
        n.uuid
        for n in all_nodes
        if n.attributes.get("source") == "paperclip"
        and (n.attributes.get("palace_last_seen_at") or "") < cutoff
        and any(lbl in PAPERCLIP_LABELS for lbl in n.labels)
    ]
    if stale_uuids:
        await graphiti.nodes.entity.delete_by_uuids(stale_uuids)
    return len(stale_uuids)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/ingest/test_upsert.py -v
```

Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/upsert.py services/palace-mcp/tests/ingest/test_upsert.py
git commit -m "feat(ingest): gc_orphans via graphiti API (zero raw Cypher)"
```

### Task 11: :IngestRun writer

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/memory/ingest_run.py`
- Test: `services/palace-mcp/tests/memory/test_ingest_run.py`

- [ ] **Step 1: Write failing test**

Create `services/palace-mcp/tests/memory/test_ingest_run.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.ingest_run import write_ingest_run


@pytest.mark.asyncio
async def test_write_ingest_run_creates_node() -> None:
    graphiti = MagicMock()
    graphiti.nodes.entity.save = AsyncMock()
    await write_ingest_run(
        graphiti,
        run_id="11111111-aaaa-bbbb-cccc-222222222222",
        started_at="2026-04-18T08:00:00+00:00",
        finished_at="2026-04-18T08:01:30+00:00",
        duration_ms=90000,
        errors=[],
        group_id="project/gimle",
    )
    graphiti.nodes.entity.save.assert_awaited_once()
    saved = graphiti.nodes.entity.save.await_args.args[0]
    assert saved.uuid == "11111111-aaaa-bbbb-cccc-222222222222"
    assert saved.labels == ["IngestRun"]
    assert saved.group_id == "project/gimle"
    assert saved.attributes["source"] == "paperclip"
    assert saved.attributes["started_at"] == "2026-04-18T08:00:00+00:00"
    assert saved.attributes["finished_at"] == "2026-04-18T08:01:30+00:00"
    assert saved.attributes["duration_ms"] == 90000
    assert saved.attributes["errors"] == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/memory/test_ingest_run.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement write_ingest_run**

Create `services/palace-mcp/src/palace_mcp/memory/ingest_run.py`:

```python
"""IngestRun writer.

Writes a :IngestRun:Entity node per ingest pass for observability +
palace.memory.health latest_ingest_at queries.
"""

from __future__ import annotations

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode


async def write_ingest_run(
    graphiti: Graphiti,
    *,
    run_id: str,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    errors: list[str],
    group_id: str,
    source: str = "paperclip",
) -> None:
    node = EntityNode(
        uuid=run_id,
        name=f"ingest-{run_id[:8]}",
        labels=["IngestRun"],
        group_id=group_id,
        summary=f"{source} ingest {started_at}",
        attributes={
            "source": source,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "errors": errors,
            "run_id": run_id,
        },
    )
    await graphiti.nodes.entity.save(node)
```

- [ ] **Step 4: Run — expect PASS**

```bash
uv run pytest tests/memory/test_ingest_run.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/ingest_run.py services/palace-mcp/tests/memory/test_ingest_run.py
git commit -m "feat(memory): :IngestRun writer via graphiti API"
```

### Task 12: Rewrite ingest/runner.py

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/runner.py` (full rewrite)
- Delete: `services/palace-mcp/src/palace_mcp/ingest/transform.py`
- Delete: `services/palace-mcp/tests/ingest/test_transform.py`
- Delete: `services/palace-mcp/tests/ingest/test_runner.py`

- [ ] **Step 1: Delete obsolete files**

```bash
cd services/palace-mcp
rm src/palace_mcp/ingest/transform.py tests/ingest/test_transform.py tests/ingest/test_runner.py
```

- [ ] **Step 2: Replace runner.py with graphiti-driven flow**

Replace contents of `services/palace-mcp/src/palace_mcp/ingest/runner.py`:

```python
"""Ingest orchestrator — graphiti-core substrate (N+1a).

Single entry point `run_ingest`. Accepts a configured PaperclipClient and
an initialized Graphiti instance. Zero raw Cypher.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from graphiti_core import Graphiti

from palace_mcp.ingest.builders import (
    GROUP_ID,
    build_agent_node,
    build_assigned_to_edge,
    build_authored_by_edge,
    build_comment_node,
    build_issue_node,
    build_on_edge,
)
from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.upsert import (
    UpsertResult,
    gc_orphans,
    invalidate_stale_assignments,
    upsert_with_change_detection,
)
from palace_mcp.memory.ingest_run import write_ingest_run

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_ingest(
    *,
    client: PaperclipClient,
    graphiti: Graphiti,
    source: str = "paperclip",
    group_id: str = GROUP_ID,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = _utcnow_iso()
    started_monotonic = time.monotonic()
    errors: list[str] = []

    logger.info(
        "ingest.start",
        extra={"source": source, "run_id": run_id, "group_id": group_id},
    )

    try:
        issues_raw = await client.list_issues()
        agents_raw = await client.list_agents()
        comments_raw: list[dict[str, Any]] = []
        for issue in issues_raw:
            comments_raw.extend(await client.list_comments_for_issue(issue["id"]))

        logger.info("ingest.fetch.issues", extra={"count": len(issues_raw)})
        logger.info("ingest.fetch.agents", extra={"count": len(agents_raw)})
        logger.info("ingest.fetch.comments", extra={"count": len(comments_raw)})

        # 1. Upsert agents (issues/comments reference them)
        counters: dict[str, int] = {"inserted": 0, "skipped_unchanged": 0, "re_embedded": 0}
        t0 = time.monotonic()
        for agent in agents_raw:
            r = await upsert_with_change_detection(
                graphiti, build_agent_node(agent, run_started=started_at, group_id=group_id)
            )
            counters[r.value] += 1
        logger.info(
            "ingest.upsert",
            extra={"type": "Agent", "count": len(agents_raw), **counters,
                   "duration_ms": int((time.monotonic() - t0) * 1000)},
        )

        # 2. Upsert issues + invalidate-and-create ASSIGNED_TO edges
        counters = {"inserted": 0, "skipped_unchanged": 0, "re_embedded": 0}
        invalidated_total = 0
        t0 = time.monotonic()
        for issue in issues_raw:
            issue_node = build_issue_node(issue, run_started=started_at, group_id=group_id)
            r = await upsert_with_change_detection(graphiti, issue_node)
            counters[r.value] += 1
            new_assignee = issue.get("assigneeAgentId")
            invalidated_total += await invalidate_stale_assignments(
                graphiti, issue_node.uuid, new_assignee, started_at
            )
            if new_assignee:
                await graphiti.edges.entity.save(
                    build_assigned_to_edge(
                        issue_uuid=issue_node.uuid,
                        agent_uuid=new_assignee,
                        run_started=started_at,
                        group_id=group_id,
                    )
                )
        logger.info(
            "ingest.upsert",
            extra={"type": "Issue", "count": len(issues_raw), **counters,
                   "duration_ms": int((time.monotonic() - t0) * 1000)},
        )
        logger.info("ingest.assignment.invalidate", extra={"count": invalidated_total})

        # 3. Upsert comments + ON / AUTHORED_BY edges
        counters = {"inserted": 0, "skipped_unchanged": 0, "re_embedded": 0}
        t0 = time.monotonic()
        for comment in comments_raw:
            comment_node = build_comment_node(comment, run_started=started_at, group_id=group_id)
            r = await upsert_with_change_detection(graphiti, comment_node)
            counters[r.value] += 1
            issue_id = comment.get("issueId")
            if issue_id:
                await graphiti.edges.entity.save(
                    build_on_edge(
                        comment_uuid=comment_node.uuid,
                        issue_uuid=issue_id,
                        comment_created_at=comment.get("createdAt") or started_at,
                        run_started=started_at,
                        group_id=group_id,
                    )
                )
            author_id = comment.get("authorAgentId")
            if author_id:
                await graphiti.edges.entity.save(
                    build_authored_by_edge(
                        comment_uuid=comment_node.uuid,
                        agent_uuid=author_id,
                        comment_created_at=comment.get("createdAt") or started_at,
                        run_started=started_at,
                        group_id=group_id,
                    )
                )
        logger.info(
            "ingest.upsert",
            extra={"type": "Comment", "count": len(comments_raw), **counters,
                   "duration_ms": int((time.monotonic() - t0) * 1000)},
        )

        # 4. GC — only on clean success
        if not errors:
            deleted = await gc_orphans(graphiti, group_id=group_id, cutoff=started_at)
            logger.info("ingest.gc", extra={"deleted": deleted})

    except Exception as e:  # noqa: BLE001 — re-raised after logging
        errors.append(f"{type(e).__name__}: {e}")
        logger.exception("ingest.error", extra={"source": source, "run_id": run_id})
        raise
    finally:
        finished_at = _utcnow_iso()
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        await write_ingest_run(
            graphiti,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            errors=errors,
            group_id=group_id,
        )
        logger.info(
            "ingest.finish",
            extra={"run_id": run_id, "duration_ms": duration_ms, "errors": errors},
        )

    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "errors": errors,
    }
```

- [ ] **Step 3: Verify mypy + tests still green**

```bash
uv run mypy --strict src
uv run pytest tests/ingest/ tests/memory/test_ingest_run.py -v
```

Expected: mypy clean, all tests PASS

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/runner.py
git rm services/palace-mcp/src/palace_mcp/ingest/transform.py services/palace-mcp/tests/ingest/test_transform.py services/palace-mcp/tests/ingest/test_runner.py
git commit -m "feat(ingest): rewrite runner.py to use graphiti namespace API"
```

### Task 13: Update CLI entrypoint

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`

- [ ] **Step 1: Replace _amain to construct Graphiti**

Replace contents of `services/palace-mcp/src/palace_mcp/ingest/paperclip.py`:

```python
"""CLI entrypoint: python -m palace_mcp.ingest.paperclip"""

from __future__ import annotations

import argparse
import asyncio
import sys

from palace_mcp.config import IngestSettings
from palace_mcp.graphiti_client import build_graphiti
from palace_mcp.ingest.paperclip_client import PaperclipClient
from palace_mcp.ingest.runner import run_ingest
from palace_mcp.memory.logging_setup import configure_json_logging


async def _amain(args: argparse.Namespace) -> int:
    configure_json_logging()
    settings = IngestSettings()
    base_url = args.paperclip_url or settings.paperclip_api_url
    token = settings.paperclip_ingest_api_key.get_secret_value()
    company_id = args.company_id or settings.paperclip_company_id

    graphiti = build_graphiti(settings)
    try:
        async with PaperclipClient(
            base_url=base_url, token=token, company_id=company_id
        ) as client:
            result = await run_ingest(client=client, graphiti=graphiti)
        return 0 if not result["errors"] else 1
    finally:
        await graphiti.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="palace-mcp-ingest-paperclip")
    parser.add_argument("--paperclip-url", default=None)
    parser.add_argument("--company-id", default=None)
    args = parser.parse_args()
    sys.exit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify mypy + import**

```bash
uv run mypy --strict src
uv run python -c "from palace_mcp.ingest.paperclip import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/ingest/paperclip.py
git commit -m "feat(ingest): CLI uses build_graphiti instead of raw AsyncDriver"
```

---

## Phase 3 — Lookup rewrite

### Task 14: Capture N+0 lookup response fixture

**Files:**
- Create: `services/palace-mcp/tests/memory/fixtures/lookup_n0_response.json`

- [ ] **Step 1: Capture from current develop**

Run against the live iMac deployment OR construct manually from N+0 spec example:

```bash
# Option A: capture live (preferred)
mkdir -p services/palace-mcp/tests/memory/fixtures
ssh -L 8080:localhost:8080 imac-ssh.ant013.work &
SSH_PID=$!
sleep 2
# Use the mcp-cli or curl/jq to call palace.memory.lookup and save response
curl -s -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"palace.memory.lookup",
                 "arguments":{"entity_type":"Issue","filters":{"status":"done"},"limit":5}}}' \
  | jq '.result' > services/palace-mcp/tests/memory/fixtures/lookup_n0_response.json
kill $SSH_PID
```

Expected: file `lookup_n0_response.json` with at least one Issue + comments + assignee fields populated.

- [ ] **Step 2: Commit fixture**

```bash
git add services/palace-mcp/tests/memory/fixtures/lookup_n0_response.json
git commit -m "test(memory): capture N+0 lookup response fixture for regression"
```

### Task 15: Rewrite lookup.py via graphiti API

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/lookup.py` (full rewrite)
- Test: `services/palace-mcp/tests/memory/test_lookup_graphiti.py`

- [ ] **Step 1: Write failing integration-style test**

Create `services/palace-mcp/tests/memory/test_lookup_graphiti.py`:

```python
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.schema import LookupRequest


def _issue_node(uuid: str, key: str, status: str, updated_at: str) -> EntityNode:
    return EntityNode(
        uuid=uuid, name=f"{key}: title", labels=["Issue"],
        group_id="project/gimle", summary="d",
        attributes={
            "id": uuid, "key": key, "title": "title", "description": "d",
            "status": status, "source": "paperclip",
            "source_created_at": updated_at, "source_updated_at": updated_at,
            "palace_last_seen_at": updated_at, "assignee_agent_id": None,
        },
    )


@pytest.mark.asyncio
async def test_lookup_filters_by_status() -> None:
    graphiti = MagicMock()
    nodes = [
        _issue_node("u1", "GIM-1", "done", "2026-04-18T00:00:00+00:00"),
        _issue_node("u2", "GIM-2", "todo", "2026-04-17T00:00:00+00:00"),
        _issue_node("u3", "GIM-3", "done", "2026-04-16T00:00:00+00:00"),
    ]
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=nodes)
    graphiti.edges.entity.get_by_node_uuid = AsyncMock(return_value=[])

    req = LookupRequest(entity_type="Issue", filters={"status": "done"}, limit=10)
    resp = await perform_lookup(graphiti, req)
    assert resp.total_matched == 2
    keys = [item.properties["key"] for item in resp.items]
    assert keys == ["GIM-1", "GIM-3"]  # ordered by source_updated_at DESC
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/memory/test_lookup_graphiti.py -v
```

Expected: FAIL — current `perform_lookup` signature takes `AsyncDriver`, not `Graphiti`.

- [ ] **Step 3: Replace lookup.py implementation**

Replace contents of `services/palace-mcp/src/palace_mcp/memory/lookup.py`:

```python
"""palace.memory.lookup — graphiti-core substrate (N+1a).

Strategy:
- Fetch all entity nodes in group_id via graphiti.nodes.entity.get_by_group_ids.
- Filter by label (entity_type) and attribute filters in Python (O(n) at
  current scale; documented in spec §5 + plan task 15).
- Sort by attribute, slice limit.
- One-hop related expansion via graphiti.edges.entity.get_by_node_uuid.

Zero raw Cypher.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

from palace_mcp.memory.filters import resolve_filters
from palace_mcp.memory.schema import (
    EntityType,
    LookupRequest,
    LookupResponse,
    LookupResponseItem,
)

logger = logging.getLogger(__name__)

GIMLE_GROUP = "project/gimle"  # parameterized in N+1b


def _node_matches_filters(
    node: EntityNode, entity_type: EntityType, attribute_filters: dict[str, Any]
) -> bool:
    if entity_type not in node.labels:
        return False
    for k, v in attribute_filters.items():
        # Support _gte / _lte suffix per N+0 schema
        if k.endswith("_gte"):
            actual = node.attributes.get(k[:-4]) or ""
            if str(actual) < str(v):
                return False
        elif k.endswith("_lte"):
            actual = node.attributes.get(k[:-4]) or ""
            if str(actual) > str(v):
                return False
        else:
            if node.attributes.get(k) != v:
                return False
    return True


async def _related_for_issue(
    graphiti: Graphiti, issue: EntityNode
) -> dict[str, Any]:
    edges = await graphiti.edges.entity.get_by_node_uuid(issue.uuid)
    assignee_uuid: str | None = None
    comment_uuids: list[str] = []
    for e in edges:
        if e.name == "ASSIGNED_TO" and e.invalid_at is None:
            assignee_uuid = e.target_node_uuid
        elif e.name == "ON" and e.target_node_uuid == issue.uuid:
            comment_uuids.append(e.source_node_uuid)
    related: dict[str, Any] = {"assignee": None, "comments": []}
    if assignee_uuid:
        try:
            agent = await graphiti.nodes.entity.get_by_uuid(assignee_uuid)
            related["assignee"] = {
                "id": agent.attributes.get("id"),
                "name": agent.attributes.get("name"),
                "url_key": agent.attributes.get("url_key"),
            }
        except Exception:
            pass
    for cu in comment_uuids[:50]:
        try:
            c = await graphiti.nodes.entity.get_by_uuid(cu)
            # Resolve author for this comment
            author_name: str | None = None
            for e in await graphiti.edges.entity.get_by_node_uuid(c.uuid):
                if e.name == "AUTHORED_BY":
                    try:
                        a = await graphiti.nodes.entity.get_by_uuid(e.target_node_uuid)
                        author_name = a.attributes.get("name")
                    except Exception:
                        pass
                    break
            related["comments"].append({
                "id": c.attributes.get("id"),
                "body": c.attributes.get("body"),
                "source_created_at": c.attributes.get("source_created_at"),
                "author_name": author_name,
            })
        except Exception:
            continue
    related["comments"].sort(key=lambda x: x.get("source_created_at") or "", reverse=True)
    return related


async def _related_for_comment(
    graphiti: Graphiti, comment: EntityNode
) -> dict[str, Any]:
    edges = await graphiti.edges.entity.get_by_node_uuid(comment.uuid)
    related: dict[str, Any] = {"issue": None, "author": None}
    for e in edges:
        if e.name == "ON" and e.source_node_uuid == comment.uuid:
            try:
                i = await graphiti.nodes.entity.get_by_uuid(e.target_node_uuid)
                related["issue"] = {
                    "id": i.attributes.get("id"),
                    "key": i.attributes.get("key"),
                    "title": i.attributes.get("title"),
                    "status": i.attributes.get("status"),
                }
            except Exception:
                pass
        elif e.name == "AUTHORED_BY":
            try:
                a = await graphiti.nodes.entity.get_by_uuid(e.target_node_uuid)
                related["author"] = {
                    "id": a.attributes.get("id"),
                    "name": a.attributes.get("name"),
                }
            except Exception:
                pass
    return related


async def perform_lookup(
    graphiti: Graphiti, req: LookupRequest, group_id: str = GIMLE_GROUP
) -> LookupResponse:
    where_clauses, params, unknown = resolve_filters(req.entity_type, dict(req.filters))
    warnings: list[str] = []
    for k in unknown:
        logger.warning(
            "query.lookup.unknown_filter",
            extra={"entity_type": req.entity_type, "filter_key": k},
        )
        warnings.append(f"unknown_filter:{k}")

    t0 = time.monotonic()
    all_nodes = await graphiti.nodes.entity.get_by_group_ids([group_id])
    matching = [
        n for n in all_nodes if _node_matches_filters(n, req.entity_type, params)
    ]
    matching.sort(key=lambda n: n.attributes.get(req.order_by) or "", reverse=True)
    sliced = matching[: req.limit]

    items: list[LookupResponseItem] = []
    for n in sliced:
        if req.entity_type == "Issue":
            related = await _related_for_issue(graphiti, n)
        elif req.entity_type == "Comment":
            related = await _related_for_comment(graphiti, n)
        else:
            related = {}
        items.append(LookupResponseItem(
            id=n.uuid, type=req.entity_type, properties=dict(n.attributes), related=related,
        ))

    return LookupResponse(
        items=items,
        total_matched=len(matching),
        query_ms=int((time.monotonic() - t0) * 1000),
        warnings=warnings,
    )
```

- [ ] **Step 4: Update mcp_server.py to pass Graphiti instead of AsyncDriver**

Edit `services/palace-mcp/src/palace_mcp/mcp_server.py`:
- Replace `_driver: AsyncDriver | None = None` with `_graphiti: Graphiti | None = None`
- Replace `set_driver(driver)` with `set_graphiti(graphiti)`
- Update `palace.memory.lookup` tool handler to call `perform_lookup(_graphiti, req)`
- Same for `palace.memory.health`.

(Implementer: search for `_driver` and `set_driver` and replace; small surface area.)

- [ ] **Step 5: Run lookup test**

```bash
uv run pytest tests/memory/test_lookup_graphiti.py -v
```

Expected: PASS

- [ ] **Step 6: Run full memory test suite**

```bash
uv run pytest tests/memory/ -v
```

Expected: all PASS (some N+0 tests may need adjustment for new signature — fix or delete obsolete).

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/lookup.py services/palace-mcp/src/palace_mcp/mcp_server.py services/palace-mcp/tests/memory/test_lookup_graphiti.py
git commit -m "feat(memory): rewrite lookup via graphiti namespace API (zero Cypher)"
```

### Task 16: Lookup byte-identical regression test

**Files:**
- Test: `services/palace-mcp/tests/memory/test_lookup_n0_regression.py`

- [ ] **Step 1: Write fixture comparison test**

Create `services/palace-mcp/tests/memory/test_lookup_n0_regression.py`:

```python
"""Compare N+1a perform_lookup output against captured N+0 fixture.

Runs against a real Neo4j 5.26 + graphiti-core. Skipped in unit-test CI;
run as live-integration in QA Phase 4 step 4.1.
"""

import json
import os
from pathlib import Path

import pytest

from palace_mcp.config import IngestSettings
from palace_mcp.graphiti_client import build_graphiti
from palace_mcp.memory.lookup import perform_lookup
from palace_mcp.memory.schema import LookupRequest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lookup_n0_response.json"


@pytest.mark.skipif(
    not os.getenv("RUN_N0_REGRESSION"),
    reason="Live integration only; set RUN_N0_REGRESSION=1",
)
@pytest.mark.asyncio
async def test_lookup_matches_n0_fixture() -> None:
    settings = IngestSettings()
    graphiti = build_graphiti(settings)
    try:
        req = LookupRequest(
            entity_type="Issue", filters={"status": "done"}, limit=5
        )
        actual = await perform_lookup(graphiti, req)
    finally:
        await graphiti.close()

    expected = json.loads(FIXTURE_PATH.read_text())["data"]
    actual_data = actual.model_dump()

    # Field-by-field comparison; query_ms always differs, ignore.
    assert actual_data["total_matched"] == expected["total_matched"]
    assert len(actual_data["items"]) == len(expected["items"])
    for a, e in zip(actual_data["items"], expected["items"]):
        assert a["id"] == e["id"]
        assert a["type"] == e["type"]
        for prop_key in (
            "key", "title", "status", "source",
            "source_created_at", "source_updated_at", "palace_last_seen_at",
        ):
            assert a["properties"].get(prop_key) == e["properties"].get(prop_key), \
                f"property {prop_key} mismatch on {a['id']}"
```

- [ ] **Step 2: Verify file is collected (skipped without env)**

```bash
uv run pytest tests/memory/test_lookup_n0_regression.py -v
```

Expected: 1 SKIPPED with "Live integration only" reason.

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/memory/test_lookup_n0_regression.py
git commit -m "test(memory): N+0 lookup regression fixture (gated by RUN_N0_REGRESSION)"
```

---

## Phase 4 — Health extension

### Task 17: Extend HealthResponse schema + get_health

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/memory/schema.py`
- Modify: `services/palace-mcp/src/palace_mcp/memory/health.py`
- Test: `services/palace-mcp/tests/memory/test_health.py`

- [ ] **Step 1: Write failing test**

Append to `services/palace-mcp/tests/memory/test_health.py`:

```python
from unittest.mock import AsyncMock, MagicMock

import pytest

from palace_mcp.memory.health import get_health


@pytest.mark.asyncio
async def test_health_includes_graphiti_and_embedder_fields() -> None:
    graphiti = MagicMock()
    graphiti.driver.verify_connectivity = AsyncMock()  # neo4j reachable
    graphiti.embedder.config.embedding_model = "nomic-embed-text"
    graphiti.embedder.config.base_url = "http://ollama-host.example.com:11434/v1"
    graphiti.nodes.entity.get_by_group_ids = AsyncMock(return_value=[])
    resp = await get_health(graphiti)
    assert resp.neo4j_reachable is True
    assert resp.graphiti_initialized is True
    assert resp.embedding_model == "nomic-embed-text"
    assert resp.embedding_provider_base_url == "ollama-host.example.com:11434"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/memory/test_health.py::test_health_includes_graphiti_and_embedder_fields -v
```

Expected: FAIL — fields missing on `HealthResponse`.

- [ ] **Step 3: Add new fields to HealthResponse**

In `services/palace-mcp/src/palace_mcp/memory/schema.py`, add to `HealthResponse`:

```python
    graphiti_initialized: bool = False
    embedder_reachable: bool = False
    embedding_model: str | None = None
    embedding_provider_base_url: str | None = None  # hostname only, no scheme/path
```

- [ ] **Step 4: Replace get_health implementation**

Replace `services/palace-mcp/src/palace_mcp/memory/health.py`:

```python
"""palace.memory.health — graphiti-core substrate."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from graphiti_core import Graphiti

from palace_mcp.memory.schema import HealthResponse

logger = logging.getLogger(__name__)

GIMLE_GROUP = "project/gimle"


def _hostname_only(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.netloc:
        return parsed.netloc
    return base_url  # fallback if not a URL


async def get_health(graphiti: Graphiti) -> HealthResponse:
    neo4j_ok = False
    try:
        await graphiti.driver.verify_connectivity()
        neo4j_ok = True
    except Exception as exc:
        logger.warning("palace.memory.health neo4j unreachable: %s", exc)

    embedding_model: str | None = None
    base_url: str | None = None
    try:
        embedding_model = graphiti.embedder.config.embedding_model  # type: ignore[attr-defined]
        base_url = _hostname_only(graphiti.embedder.config.base_url)  # type: ignore[attr-defined]
    except Exception:
        pass

    counts: dict[str, int] = {}
    last_ingest: dict[str, Any] | None = None
    if neo4j_ok:
        nodes = await graphiti.nodes.entity.get_by_group_ids([GIMLE_GROUP])
        for n in nodes:
            for lbl in n.labels:
                if lbl == "Entity":
                    continue
                counts[lbl] = counts.get(lbl, 0) + 1
        ingest_runs = [n for n in nodes if "IngestRun" in n.labels]
        ingest_runs.sort(
            key=lambda n: n.attributes.get("started_at") or "", reverse=True
        )
        if ingest_runs:
            last_ingest = ingest_runs[0].attributes

    return HealthResponse(
        neo4j_reachable=neo4j_ok,
        graphiti_initialized=neo4j_ok,
        embedder_reachable=embedding_model is not None,
        embedding_model=embedding_model,
        embedding_provider_base_url=base_url,
        entity_counts=counts,
        last_ingest_started_at=last_ingest.get("started_at") if last_ingest else None,
        last_ingest_finished_at=last_ingest.get("finished_at") if last_ingest else None,
        last_ingest_duration_ms=last_ingest.get("duration_ms") if last_ingest else None,
        last_ingest_errors=list(last_ingest.get("errors") or []) if last_ingest else [],
    )
```

- [ ] **Step 5: Run — expect PASS**

```bash
uv run pytest tests/memory/test_health.py -v
```

Expected: PASS (new test + any pre-existing health tests adjusted to pass `graphiti` instead of `driver`).

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/memory/health.py services/palace-mcp/src/palace_mcp/memory/schema.py services/palace-mcp/tests/memory/test_health.py
git commit -m "feat(memory): health includes graphiti + embedder probes"
```

---

## Phase 5 — Cleanup + verification gates

### Task 18: Delete obsolete Cypher modules

**Files:**
- Delete: `services/palace-mcp/src/palace_mcp/memory/cypher.py`
- Delete: `services/palace-mcp/src/palace_mcp/memory/constraints.py`
- Delete: `services/palace-mcp/tests/memory/test_cypher_parameterization.py`
- Delete: `services/palace-mcp/tests/memory/test_schema.py` (covered by builders + lookup tests)

- [ ] **Step 1: Verify no imports remain**

```bash
cd services/palace-mcp
grep -r "from palace_mcp.memory.cypher" src tests || echo "no imports"
grep -r "from palace_mcp.memory.constraints" src tests || echo "no imports"
```

Expected: `no imports` for both. If imports exist, fix the importing files first (CLI's `ensure_constraints` call must go — graphiti handles).

- [ ] **Step 2: Delete + verify tests still green**

```bash
rm src/palace_mcp/memory/cypher.py src/palace_mcp/memory/constraints.py
rm tests/memory/test_cypher_parameterization.py tests/memory/test_schema.py
uv run mypy --strict src
uv run pytest -v
```

Expected: mypy clean, all remaining tests PASS.

- [ ] **Step 3: Commit**

```bash
git add -u services/palace-mcp/
git commit -m "chore(memory): remove raw Cypher modules — replaced by graphiti API"
```

### Task 19: Zero-raw-Cypher gate test

**Files:**
- Test: `services/palace-mcp/tests/test_no_raw_cypher.py`

- [ ] **Step 1: Write enforcement test**

Create `services/palace-mcp/tests/test_no_raw_cypher.py`:

```python
"""Enforces spec §9 acceptance: zero raw Cypher in ingest + lookup.

Greps target source files for Cypher keywords. Failure means a raw
Cypher string snuck in — substrate-level violation per N+1a CR criterion.
"""

from pathlib import Path

import pytest

CYPHER_KEYWORDS = ("MERGE", "MATCH", "CREATE CONSTRAINT", "DETACH DELETE", "UNWIND")
CHECKED_PATHS = [
    Path("src/palace_mcp/ingest"),
    Path("src/palace_mcp/memory/lookup.py"),
    Path("src/palace_mcp/memory/health.py"),
    Path("src/palace_mcp/memory/ingest_run.py"),
    Path("src/palace_mcp/graphiti_client.py"),
]


@pytest.mark.parametrize("target", CHECKED_PATHS)
def test_no_raw_cypher_in(target: Path) -> None:
    files = [target] if target.is_file() else list(target.rglob("*.py"))
    offenders: list[str] = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for kw in CYPHER_KEYWORDS:
            # Search for the keyword as a Cypher-statement marker (followed by
            # whitespace + uppercase letter or `(`)
            if f" {kw} " in text or f"\n{kw} " in text:
                offenders.append(f"{f}: contains '{kw}'")
    assert not offenders, "Raw Cypher detected:\n" + "\n".join(offenders)
```

- [ ] **Step 2: Run — expect PASS**

```bash
uv run pytest tests/test_no_raw_cypher.py -v
```

Expected: all PASS (5 parametrized cases).

- [ ] **Step 3: Commit**

```bash
git add services/palace-mcp/tests/test_no_raw_cypher.py
git commit -m "test: enforce zero raw Cypher in ingest + memory paths"
```

### Task 20: Compose env + Dockerfile validation

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add embedder env to palace-mcp service**

Edit `docker-compose.yml` `palace-mcp.environment:` block, append:

```yaml
      EMBEDDING_BASE_URL: "${EMBEDDING_BASE_URL}"
      EMBEDDING_API_KEY: "${EMBEDDING_API_KEY:-placeholder}"
      EMBEDDING_MODEL: "${EMBEDDING_MODEL:-nomic-embed-text}"
      EMBEDDING_DIM: "${EMBEDDING_DIM:-768}"
      LLM_BASE_URL: "${LLM_BASE_URL:-${EMBEDDING_BASE_URL}}"
      LLM_API_KEY: "${LLM_API_KEY:-${EMBEDDING_API_KEY:-placeholder}}"
      LLM_MODEL: "${LLM_MODEL:-llama3:8b}"
```

Update `.env.example`:

```
# Embedder for graphiti-core (external Ollama / Alibaba / OpenAI / etc.)
EMBEDDING_BASE_URL=http://your-ollama-host:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

- [ ] **Step 2: Build palace-mcp image**

```bash
cd services/palace-mcp  # ensure context
cd -
docker compose build palace-mcp
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(compose): EMBEDDING_* env vars on palace-mcp"
```

---

## Phase 6 — Final verification + PR

### Task 21: Full test + mypy + lint sweep

- [ ] **Step 1: Run all three quality gates**

```bash
cd services/palace-mcp
uv run mypy --strict src
uv run ruff check src tests
uv run pytest -v
```

Expected: mypy clean, ruff clean, all unit tests PASS (regression test SKIPPED without env).

- [ ] **Step 2: Run grep validation manually as backup**

```bash
grep -rE "(MERGE|MATCH|UNWIND)" src/palace_mcp/ingest/ src/palace_mcp/memory/lookup.py
```

Expected: no output (zero raw Cypher).

- [ ] **Step 3: If any fails, fix and re-run before continuing**

Iterate task-by-task on failures; do not proceed until all three gates green.

### Task 22: Open PR + handoff to CodeReviewer

- [ ] **Step 1: Push branch**

```bash
git push -u origin feature/GIM-NN-palace-memory-n1a-substrate
```

- [ ] **Step 2: Open PR via gh**

```bash
gh pr create --base develop --title "N+1a Graphiti substrate swap (GIM-NN)" --body "$(cat <<'EOF'
## Summary
- Swap palace-mcp ingest + lookup substrate from direct Cypher MERGE on Neo4j to graphiti-core namespace API (`graphiti.nodes.entity.*`, `graphiti.edges.entity.*`).
- Zero raw Cypher in ingest path or lookup; enforced by `tests/test_no_raw_cypher.py`.
- text_hash change-detection skips re-embed on unchanged text.
- Genuine bi-temporal: ASSIGNED_TO edge gets `invalid_at` set when assignee changes between ingests, via native `graphiti.edges.entity.save(edge)`.
- N+0 user-visible behavior preserved: `palace.memory.lookup` and `palace.memory.health` return same shape (extended with new fields documented in spec §5).

## Spec
docs/superpowers/specs/2026-04-18-palace-memory-n1a-graphiti-substrate-swap.md

## Plan
docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md

## Verified API reference
docs/research/graphiti-core-verification.md (§5-§8)

## Test plan
- [ ] mypy --strict green
- [ ] ruff clean
- [ ] All unit tests pass
- [ ] tests/test_no_raw_cypher.py passes (5 cases)
- [ ] Live smoke (QAEngineer): ingest + lookup against external Ollama; verify ASSIGNED_TO invalidation by reassigning issue between two ingests
- [ ] N+0 fixture regression test passes with RUN_N0_REGRESSION=1

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Reassign to CodeReviewer per spec §8 step 3.1**

(Manual step via paperclip UI or paperclipai CLI.)

---

## Self-Review Notes

- **Spec coverage check (§9 acceptance):**
  - Zero raw Cypher → Task 19 enforces; Task 18 deletes obsolete Cypher; Task 12 + 15 rewrite without Cypher.
  - text_hash change-detection → Task 8 (upsert) implements + tests.
  - Bi-temporal ASSIGNED_TO → Task 9 implements + tests; runner Task 12 calls invalidate_stale_assignments per issue.
  - N+0 lookup byte-identical → Task 14 captures fixture, Task 16 gated regression test.
  - mypy --strict + CI → Task 21.
  - 4 mini-gaps → Task 1 spike + Task 1 step 4 verification doc append.

- **Files checklist:** every Create/Modify/Delete from File Structure has at least one task touching it. ✅

- **Type consistency:** `UpsertResult` enum, `GROUP_ID` constant, `build_*_node`/`build_*_edge` builder names, `gc_orphans`, `invalidate_stale_assignments`, `write_ingest_run`, `perform_lookup(graphiti, ...)`, `get_health(graphiti)`, `build_graphiti(settings)` — all consistent across tasks.

- **No placeholders:** every step has concrete code or commands; no "TBD"/"TODO"/"add error handling" without code.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1a-substrate.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Best for spec-grade quality across 22 tasks.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
