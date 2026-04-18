# Palace Memory — N+1c Agent MCP + record_note + provider UX

**Date:** 2026-04-18
**Slice:** N+1c (third of three N+1 sub-slices — final)
**Author:** Board
**Status:** Draft — awaiting CTO formalization as GIM-NN issue
**Related specs:** `docs/superpowers/specs/2026-04-15-gimle-palace-design.md` §4.2, §4.3; `docs/research/graphiti-core-verification.md`
**Predecessor slices:** N+1a (substrate swap), N+1b (multi-project)
**Closes:** the N+1 palace.memory.* substrate epic

## 1. Context

N+1a shipped substrate; N+1b shipped multi-project. This slice closes the loop:

1. **Agent-memory loop** — paperclip agents (11 live via `deploy-agents.sh`) gain direct read+write access to their own memory via `graphiti-mcp` on a second port. Agents can `record_note` during tasks and `search_nodes` / `search_facts` in future sessions, enabling the cross-session continuity the N+0 slice explicitly deferred.
2. **Provider installer UX** — `just setup` gains an embedding-provider prompt so new deployments don't need to hand-edit `.env`. Three concrete paths: external Ollama (default for the user's current iMac), cloud OpenAI-compatible (Alibaba / OpenAI), or local Ollama compose (opt-in for users with Apple Silicon or otherwise-fast local machine).
3. **Security tightening** — per-agent token auth on graphiti-mcp closes the 11-agent write-without-auth gap flagged in the REJECTED-N+1 review.
4. **Post-merge deploy automation** — closes `reference_post_merge_deploy_gap.md` while the slice is already touching compose.

## 2. Goal

After this slice:

- Paperclip agents connect to `http://graphiti:8002/mcp` using a per-agent token, call `add_triplet` / `search_nodes` / `search_facts`.
- External clients (Claude Code, Cursor, etc.) call `palace.memory.record_note(text, tags, scope, project)` on palace-mcp — curated entry point that uses `add_triplet` with `EntityNode(labels=["Note", "Entity"])`.
- `palace.memory.search(query, project, filters, top_k)` returns semantic matches over `:Issue`/`:Comment`/`:Note` nodes via `node_similarity_search` with scoring.
- `just setup` prompts once for embedding provider choice; writes the right env block.
- Merging to develop triggers automatic iMac deploy (pull + rebuild + up) — no manual intervention for typical slice merges.

**Success criterion:** A Claude Code session records a note via `palace.memory.record_note(text="Coordinator pattern used in Gimle bootstrap", tags=["pattern"], project="gimle")`; the session ends; a fresh Claude Code session calls `palace.memory.search(query="how did Gimle bootstrap work?", project="gimle")` and receives the note with similarity ≥ 0.5. Separately, a paperclip CodeReviewer agent connects to graphiti-mcp with its token, calls `search_nodes(query="bootstrap", group_ids=["project/gimle"])` and gets the same note.

## 3. Architecture

### 3.1 graphiti-mcp exposure with auth middleware

graphiti-core ships an official MCP server v1.0 (under `graphiti_core.mcp_server`). We wrap it with a thin auth middleware and expose on `:8002`.

```
┌──────────────────────────────────────────────┐
│ graphiti service (extends N+1a)              │
│  ├── :8001 internal RPC for palace-mcp       │
│  ├── :8002 graphiti-mcp streamable-HTTP      │
│  │   └── auth middleware: X-Agent-Token hdr  │
│  │       validated against GIMLE_AGENT_TOKENS│
│  │       env (comma-separated list)          │
│  └── /healthz (unchanged)                    │
└──────┬────────────────┬─────────────┬────────┘
       │ Bolt           │ HTTP        │
       ▼                ▼             │
 ┌────────────┐  ┌──────────────┐    │
 │ Neo4j      │  │ Embedder     │    │
 └────────────┘  └──────────────┘    │
                                     ▼
                       ┌──────────────────────┐
                       │ Paperclip agents via │
                       │ shared-fragments MCP │
                       │ config with token    │
                       └──────────────────────┘
```

Auth middleware (FastAPI/FastMCP middleware):

```python
@app.middleware("http")
async def agent_token_auth(request: Request, call_next):
    token = request.headers.get("X-Agent-Token")
    valid_tokens = set(os.getenv("GIMLE_AGENT_TOKENS", "").split(","))
    if token not in valid_tokens or token == "":
        return JSONResponse(status_code=401, content={"error": "invalid_agent_token"})
    return await call_next(request)
```

Tokens are generated during `just setup` (one per agent role) and injected into each agent's MCP config via shared-fragments.

### 3.2 Compose service additions

```yaml
graphiti:
  # N+1a service extended
  ports:
    - "8002:8002"   # NEW — graphiti-mcp exposed
  environment:
    # NEW
    GIMLE_AGENT_TOKENS: "${GIMLE_AGENT_TOKENS}"   # comma-separated
    # existing N+1a env preserved

ollama-local:
  # NEW — opt-in only via profile
  image: ollama/ollama:0.5.0
  restart: unless-stopped
  mem_limit: 4g
  cpus: "2.0"
  profiles: [with-local-ollama]   # NOT in default profiles
  volumes:
    - ollama_models:/root/.ollama
  networks:
    - paperclip-agent-net
  healthcheck:
    test: ["CMD-SHELL", "ollama list | grep -q nomic-embed-text || exit 1"]
    interval: 30s
    timeout: 10s
    retries: 5
    start_period: 120s
```

Users with local machines capable of running Ollama enable `--profile with-local-ollama` at setup time; everyone else uses external-ollama or cloud-openai-compat and doesn't spin up a local Ollama container.

### 3.3 Installer UX (`just setup`)

Interactive prompt sequence:

```
Q1: Where is your embedding provider hosted?
  1) External Ollama (your hosted instance — fast path for current deployment)
  2) Cloud OpenAI-compatible (Alibaba DashScope, OpenAI, Voyage)
  3) Local Ollama (Docker compose spins up a local instance)

[User picks 1]

Q2: Ollama URL? [default: http://localhost:11434/v1]
> http://ollama-server.example.com:11434/v1

Q3: Embedding model? [default: nomic-embed-text]
>

Q4: Agent tokens — one token per live paperclip agent.
    Generate now or provide manually?
  1) Generate 11 random tokens (saved to .env — secret, not committed)
  2) I have a pre-generated list

[User picks 1]
→ writes .env with GIMLE_AGENT_TOKENS=<11 comma-separated tokens>
→ writes separate file .palace/agent-token-map.yaml (slug → token, gitignored)
```

For cloud choice (Q1=2): prompts for `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` with sensible defaults for Alibaba DashScope (user's current cheap option).

For local choice (Q1=3): writes `COMPOSE_PROFILES=full,with-local-ollama` and uses `http://ollama-local:11434/v1` as base URL.

## 4. Schema additions

### 4.1 `:Note` entity

```python
EntityNode(
    uuid=str(uuid4()),
    name=f"note-{uuid[:8]}",
    labels=["Note", "Entity"],
    group_id=f"project/{project_slug}",
    summary=text[:500],
    attributes={
        "text": text,                              # full markdown
        "tags": tags,                              # ["pattern", "bootstrap"]
        "scope": scope,                            # "project" | "module" | "global"
        "author_kind": author_kind,                # "agent" | "external-client"
        "author_id": author_id,                    # agent fqn or MCP session id
        "source_created_at": now_iso(),
        "palace_last_seen_at": now_iso(),
        "text_hash": sha256(text).hexdigest(),     # change detection
    }
)
```

No edges required by default — notes are standalone nodes. If a note relates to an existing entity (e.g., references an Issue), the `palace.memory.link_items` tool creates a typed edge separately.

### 4.2 Change detection on record_note

Before writing:

```python
existing_notes = await graphiti.search_nodes(
    query=text[:200],
    group_ids=[f"project/{project_slug}"],
    labels=["Note"],
    limit=5,
    min_score=0.95   # very high — only near-identical
)
if existing_notes:
    return {"ok": true, "data": {"note_id": existing_notes[0].uuid, "deduplicated": true}}
# else proceed with new node save
```

Prevents duplicate notes from noisy agent loops (agent retries, idempotent tool call replays).

## 5. MCP tool surface — 3 new

| Tool | N+1c behavior |
|---|---|
| `palace.memory.record_note(text, tags, scope, project, author_id)` | **NEW**. Builds `EntityNode(labels=["Note", "Entity"])`, calls `graphiti.save(node)` (triggers auto-embed), returns `note_id`. Deduplicates against near-identical existing notes (§4.2). |
| `palace.memory.search(query, project, filters, top_k)` | **NEW**. Semantic search via `node_similarity_search(query_embedding, labels=["Issue", "Comment", "Note"], group_ids=..., min_score=0.4)`. Returns `list[SearchHit]` with node, score, labels. |
| `palace.memory.link_items(from_id, to_id, relation, project)` | **NEW**. Whitelisted relations: `:RELATES_TO`, `:SIMILAR_TO`, `:SEE_ALSO`, `:DEPRECATES`. Builds `EntityEdge` + `add_triplet` against existing nodes. |

Tool schemas (Pydantic v2):

```python
class RecordNoteRequest(BaseModel):
    text: str = Field(min_length=10, max_length=10000)
    tags: list[str] = Field(default_factory=list)
    scope: Literal["project", "module", "global"] = "project"
    project: str | None = None
    author_id: str | None = None

class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    project: str | list[str] | Literal["*"] | None = None
    filters: dict[str, Any] = {}   # per-label filters, whitelisted
    top_k: int = Field(default=10, ge=1, le=50)

class SearchHit(BaseModel):
    uuid: str
    labels: list[str]
    name: str
    summary: str
    score: float   # 0.0-1.0 similarity
    project: str
    attributes: dict[str, Any]
```

## 6. Shared-fragments update (paperclip agents)

New fragment file in `ant013/paperclip-shared-fragments` repo: `fragments/palace-memory-mcp.md`.

```markdown
## Palace Memory MCP access

You have two MCP servers for memory:

1. **palace-memory** — curated tools (structured queries, typed writes):
   - URL: http://palace-mcp:8080/mcp (from within Docker network)
   - Primary write: `palace.memory.record_note(text, tags, scope, project)` — use this for observations during tasks.
   - Primary search: `palace.memory.search(query, project)` — use this to find prior knowledge.

2. **graphiti** — raw graph access (advanced, read-focused):
   - URL: http://graphiti:8002/mcp (from within Docker network)
   - Auth: header `X-Agent-Token: ${YOUR_AGENT_TOKEN}` — provided via env var in your runtime config.
   - Tools: `search_nodes`, `search_facts`, `get_episodes` — use for graph traversal beyond what palace-memory curated tools expose.
   - **Writes via graphiti-mcp are discouraged** — prefer `palace.memory.record_note` for any memory writing. Only use direct `add_triplet` via graphiti-mcp for advanced graph operations (e.g., creating `:RELATES_TO` edges between existing nodes with domain-specific fact text).

Project scoping: pass `project="<your current project slug>"` to palace-memory tools, or `group_ids=["project/<slug>"]` to graphiti tools.

Default project for paperclip agents: "gimle" (Gimle-Palace's own paperclip instance).
```

Shared-fragments commit + deploy via `paperclips/deploy-agents.sh` after N+1c merges.

## 7. Post-merge deploy automation

### 7.1 Problem (from `reference_post_merge_deploy_gap.md`)

Merging to develop does NOT auto-rebuild iMac container. Until now: manual `pull && docker compose pull && up -d`. With N+1a/b/c adding 2-3 services + profiles, manual deploy gap widens.

### 7.2 Solution: GitHub Actions + iMac webhook listener

New service: `palace-deploy-listener` (tiny Python webhook; existing FastAPI skeleton in `services/`).

```yaml
palace-deploy-listener:
  build:
    context: services/deploy-listener
  restart: unless-stopped
  mem_limit: 128m
  profiles: [full]
  environment:
    DEPLOY_SECRET: "${DEPLOY_SECRET}"
    COMPOSE_DIR: "/compose"
    BRANCH: "develop"
  volumes:
    - /Users/Shared/Ios/Gimle-Palace:/compose
    - /var/run/docker.sock:/var/run/docker.sock
  ports:
    - "9090:9090"
```

GitHub Actions workflow `.github/workflows/deploy-on-merge.yml`:

```yaml
name: Deploy on merge to develop
on:
  push:
    branches: [develop]
jobs:
  trigger-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Notify iMac
        run: |
          curl -X POST https://palace.ant013.work/deploy \
            -H "X-Deploy-Secret: ${{ secrets.DEPLOY_SECRET }}" \
            -d '{"branch": "develop", "sha": "${{ github.sha }}"}'
```

Listener receives webhook → runs `git pull && docker compose pull && docker compose up -d` within the compose dir. Logs to `/var/log/palace-deploy.log`.

Fail-safe: if webhook fails (iMac offline, network issue), listener has an idle-loop cron (every 15 min) that checks git for new commits on develop and deploys if behind. Redundant but reliable.

### 7.3 Rollback

`just rollback <commit-sha>` command: checks out target SHA, rebuilds, redeploys. Simple manual recovery if auto-deploy breaks.

## 8. Decomposition (plan-first ready)

Expected plan-file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1c-agent-mcp.md`.

| Phase | Step | Owner | Description |
|---|---|---|---|
| 1 | 1.1 | CTO | Create GIM-NN issue + plan file. |
| 1 | 1.2 | CodeReviewer | Plan-first compliance; verify N+1b merged + green. APPROVE → Phase 2. |
| 2 | 2.1 | MCPEngineer | Expose graphiti-mcp on :8002 with auth middleware (X-Agent-Token); GIMLE_AGENT_TOKENS env. |
| 2 | 2.2 | MCPEngineer | Implement `palace.memory.record_note` with dedup + auto-embed + `:Note` EntityNode. |
| 2 | 2.3 | MCPEngineer | Implement `palace.memory.search` via `node_similarity_search` with project scoping + labels filter. |
| 2 | 2.4 | MCPEngineer | Implement `palace.memory.link_items` with whitelisted relations. |
| 2 | 2.5 | MCPEngineer | Add `ollama-local` compose service under `with-local-ollama` profile with auto-pull init. |
| 2 | 2.6 | MCPEngineer | Rewrite `just setup` interactive prompt; .env generation logic; .palace/agent-token-map.yaml. |
| 2 | 2.7 | MCPEngineer | Create `services/deploy-listener/` — tiny FastAPI webhook + idle poll; `.github/workflows/deploy-on-merge.yml`. |
| 2 | 2.8 | MCPEngineer | Shared-fragments PR: add `palace-memory-mcp.md` fragment + deploy script. |
| 2 | 2.9 | MCPEngineer | Unit tests — record_note dedup, search min_score, auth middleware, deploy webhook signature check (≥40 new tests). |
| 3 | 3.1 | CodeReviewer | PR mechanical review: compliance, auth correctly enforced (401 on missing token), dedup logic sane, deploy-listener does not execute untrusted commits. |
| 3 | 3.2 | OpusArchitectReviewer | (If wired) context7 cross-check on graphiti-mcp server config + FastAPI middleware patterns. |
| 4 | 4.1 | QAEngineer | Full smoke: compose up with external-Ollama choice. External client: record_note → restart session → search returns note (similarity ≥ 0.5). Paperclip agent smoke: connect CodeReviewer to graphiti-mcp with its token, search_nodes over recorded notes, verify result matches. Try invalid token → 401. Merge unrelated docs PR to develop → verify auto-deploy fires → health shows new SHA within 60s. |
| 4 | 4.2 | MCPEngineer | Squash-merge. Update plan-file checkboxes. Close N+1 epic. |

## 9. Acceptance criteria

- [ ] PR against develop; squash-merged on APPROVE.
- [ ] Plan file at `docs/superpowers/plans/2026-04-18-GIM-NN-palace-memory-n1c-agent-mcp.md`.
- [ ] graphiti-mcp exposed on :8002 with X-Agent-Token auth; invalid/missing token → 401.
- [ ] `palace.memory.record_note(text, tags, scope, project)` creates `:Note:Entity` node; returned `note_id` retrievable via `lookup`.
- [ ] `palace.memory.search(query, project)` returns similarity-scored results; same-query-identical-text note returns score ≥ 0.95 (dedup threshold).
- [ ] `palace.memory.link_items` creates whitelisted edge; non-whitelisted relation → `ok: false` with error.
- [ ] `just setup` interactive prompt; 3 provider choices; agent-tokens generated into `.env` + `.palace/agent-token-map.yaml` (gitignored).
- [ ] `ollama-local` compose service starts only with explicit `COMPOSE_PROFILES=full,with-local-ollama`.
- [ ] Shared-fragments `palace-memory-mcp.md` deployed to all 11 agents via `deploy-agents.sh`; agent env injected with its own `GIMLE_AGENT_TOKEN`.
- [ ] Paperclip agent (CodeReviewer) can call `search_nodes(query="...", group_ids=["project/gimle"])` through graphiti-mcp with its token; returns nodes from all labels.
- [ ] Post-merge deploy: merging a trivial docs PR to develop triggers webhook to palace-deploy-listener; iMac compose rebuilds + ups within 60s; `palace.memory.health()` returns new git SHA in meta.
- [ ] Rollback: `just rollback <sha>` restores prior state.
- [ ] End-to-end success scenario from §2 passes live (record note → restart → search → find).
- [ ] `uv run mypy --strict` green.
- [ ] CI green on all four jobs + new deploy-listener docker-build.
- [ ] Post-merge: (automatic via new mechanism!) user verifies all N+1c features from fresh Claude Code session.

## 10. Out of scope (explicit)

- **Further agent auth tightening** (mTLS, rotation). Per-agent static token in env is the MVP; rotation automation is a follow-up slice.
- **record_decision / record_finding / create_paperclip_issue.** These require `:Decision` / `:Finding` node types from extractor slices N+3+. record_note is the general-purpose predecessor.
- **search across custom entity types from extractors.** N+1c search targets `:Issue`, `:Comment`, `:Note`. When N+2+ adds `:Module`, `:Symbol`, etc., search expands by extending the `labels=[...]` list in `node_similarity_search` — trivial.
- **Hybrid search (BM25 + vector + graph expansion).** Pure similarity in N+1c. Hybrid is a performance slice after `find_context_for_task` is wired.
- **graphiti-mcp write tool exposure to external clients.** Only palace-mcp is external-facing. graphiti-mcp reads for external would need a separate port + auth story — deferred.
- **Scheduled ingest.** Still manual trigger; scheduler is a dedicated slice.
- **Per-project auth** (different tokens per project). Current tokens are per-agent, scope-agnostic. Per-project tokens come if the threat model requires it (e.g., Medic team should not read Gimle data) — deferred.
- **Deploy-listener hardening** (mutual TLS, signature verification beyond shared-secret, rollback on health-check failure). Basic shared-secret + idle-poll fallback ships in N+1c; production hardening is its own slice.
- **User-invoked record_note auto-enrichment** (auto-tag via LLM, auto-link to related notes). Pure explicit-input in N+1c.

## 11. Estimated size

- Code: ~600 LOC (graphiti-mcp wrapping + auth ~120, record_note + dedup ~80, search ~80, link_items ~50, ollama-local compose + init ~50, installer rewrite ~120, deploy-listener + webhook ~100, tests ~100).
- Plan + docs: ~70 LOC.
- Shared-fragments PR: separate, ~30 LOC.
- 2 PRs (main + shared-fragments), 4-5 handoffs main PR.
- Expected duration: 3 days agent-time.

## 12. Followups

- N+2 brainstorm unblocked immediately after N+1c merges — see `docs/research/extractor-library/report.md` §8 roadmap.
- Evaluate record_note usage patterns after 1 week of agent activity; if agents hit dedup threshold frequently, tune min_score; if dedup is bypassed too often, lower to 0.90.
- GitHub Actions secret rotation: document `DEPLOY_SECRET` rotation procedure in `docs/paperclip-operations/`.
- Consider `find_context_for_task` as the N+2 tool-surface flagship — the research-identified high-value tool that does faceted cross-project retrieval. Needs extractor data first.
- Monitor agent-token management burden over 2 weeks. If token rotation is painful manually, prioritize rotation automation over other N+2 slice candidates.
- Close `reference_post_merge_deploy_gap.md` memory entry once deploy automation is confirmed stable for 1 week.
