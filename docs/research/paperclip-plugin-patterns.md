# Paperclip Ecosystem Plugin Patterns — Gimle-Palace Reference

> **Generated:** 2026-04-17  
> **Sources:** `mvanhorn/paperclip-plugin-discord`, `mvanhorn/paperclip-plugin-telegram`, `mvanhorn/paperclip-plugin-github-issues`, `@paperclipai/plugin-sdk@2026.416.0`, `paperclip-mcp@2.1.1`  
> **Research issues:** [GIM-39](/GIM/issues/GIM-39), [GIM-40](/GIM/issues/GIM-40), [GIM-41](/GIM/issues/GIM-41)  
> **Gap note:** `paperclip-plugin-hindsight` source not public — patterns around schema versioning and temporal-edge idempotency are not covered here. See [[MATERIAL GAP]](#material-gap--paperclip-plugin-hindsight) section.

---

## Pattern Table

| # | Pattern | Source plugin | Source file / function | Problem it prevents | Recommendation for Gimle-Palace | Slice |
|---|---------|--------------|----------------------|--------------------|---------------------------------|-------|
| 1 | **`withRetry` + exponential backoff** | discord | `src/retry.ts:46–72`, `src/adapter.ts:31–42` | Rate-limit hammering; transient failures silently dropped | Adopt: wrap all outbound HTTP calls (Neo4j, Anthropic, external APIs) in a `withRetry()` that retries on 429/500/502/503 with exponential backoff | N+1 |
| 2 | **`Retry-After` header parsing on 429** | discord | `src/retry.ts:18–28` | Back-pressure ignored — retries hit rate limit again immediately | Adopt alongside #1: parse `Retry-After` header and use its value as delay instead of the default backoff interval | N+1 |
| 3 | **In-memory event deduplication (5-min TTL Map)** | discord | `src/worker.ts:447–460` | Runtime may redeliver events on retry/replay → duplicate notifications | Adopt: any event-driven ingest handler should check `seenEvents.has(eventId)` before acting; evict entries after TTL | N+1 |
| 4 | **State-based completion deduplication** | discord | `src/worker.ts:530–545` | `issue.updated` fires multiple times for same `completedAt` → repeated processing | Adopt: for entities with a natural idempotency marker (timestamp, etag), store it in plugin state and skip processing if unchanged | N+1 |
| 5 | **Lazy company ID resolution (cached, never in `setup()`)** | discord | `src/company-resolver.ts:7–26` | Setup-time API calls hit 15 s worker-init RPC timeout → SIGKILL on startup | Adopt: any company/agent lookups done by Gimle on startup should be deferred to first use and cached in-memory | N+0 |
| 6 | **Config merge with manifest defaults** | discord | `src/worker.ts:261–266` | Missing optional config keys cause runtime `TypeError` crashes | Adopt: `cfg = {**DEFAULT_CONFIG, **raw_config}` pattern in all config reads; never assume optional keys are present | N+0 |
| 7 | **Best-effort enrichment (try/catch, log at DEBUG)** | discord, telegram | discord `src/worker.ts:224–229`; telegram `src/worker.ts:295–296` | Enrichment fetch failure blocks primary operation delivery | Adopt: all secondary enrichment (embedding generation, name lookups, metadata fetches) should degrade gracefully — catch, log at DEBUG, continue; never re-raise | N+1 |
| 8 | **Telegram `retry_after` in response body (not header)** | telegram | `src/telegram-api.ts:61–64` | Telegram signals rate limits in `data.parameters.retry_after`, not `Retry-After` header | Adopt if Gimle calls Telegram API directly; general lesson: verify API-specific rate-limit signaling format before coding generic header-only parsing | N+2 |
| 9 | **MarkdownV2 → plaintext fallback on format error** | telegram | `src/telegram-api.ts:68–75` | Formatting bugs cause total send failure | Adopt: any formatted output path (MCP tool responses, notifications) should retry as plaintext on parse/render failure | N+1 |
| 10 | **Secret UUID ref pattern (never raw tokens in config)** | telegram, discord | telegram `src/manifest.ts:44–51`; discord `src/worker.ts:272–275` | Raw API tokens embedded in plugin config appear in logs and state dumps | **Adopt immediately:** Anthropic API key, Neo4j password must be stored as Paperclip secret refs resolved via `ctx.secrets.resolve()`. Raw token strings must never appear in config JSON | N+0 |
| 11 | **Fire-and-forget slow init tasks** | telegram | `src/worker.ts:157–168` | `await slowExternalCall()` during `setup()` causes worker SIGKILL if call takes > 15 s | Adopt: slow startup operations (initial embedding warmup, first-time schema migration check) must be `.catch(err => logger.warning(...))` fire-and-forget, not awaited in `setup` | N+0 |
| 12 | **Bidirectional echo-loop prevention via bridge marker** | github-issues | `src/sync.ts:258–269` | A→B→A comment bridge loops infinitely | Adopt when building GitHub extractor (N+2): add `[synced from Gimle]` marker to all bridged content; skip inbound processing if marker present | N+2 |
| 13 | **Incremental sync cursor (`lastSyncAt` stored in state)** | github-issues | `src/sync.ts:15–22, 126–137`; `src/github.ts:112–114` | Re-fetching from epoch on every sync wastes API quota | Adopt: palace.memory ingest pipeline should track a cursor (`last_ingested_at` per entity type) in plugin state and pass it as `?since=` to source APIs | N+1 |
| 14 | **Two-index state for bidirectional entity lookup** | github-issues | `src/sync.ts:87–101` | Webhook events carry external ID (GH issue #N), not internal Paperclip ID | Adopt: Graphiti nodes for external entities need a reverse index `externalId → nodeId` so inbound events can resolve Graphiti nodes without a full graph scan | N+2 |
| 15 | **Explicit sync direction enum** | github-issues | `src/sync.ts:11–22` | Implicit bidirectional sync creates surprise mutations on the source system | Adopt: future extractors must declare `extractOnly` vs `bidirectional` in config, not as implicit logic scattered through handlers | N+2 |
| 16 | **`definePlugin` mock + `vi.hoisted()` for handler unit tests** | discord | `tests/event-dedup.test.ts:9–30` | Testing event handlers requires running a real plugin worker → slow, fragile | Adopt: use `vi.mock("@paperclipai/plugin-sdk", ...)` + `vi.hoisted()` to capture `setup()` and extract registered handlers for unit testing without a live worker | N+1 |
| 17 | **In-memory ctx stub with state Map** | discord | `tests/event-dedup.test.ts:36–135` | Full integration test hits real APIs; unit tests need isolated state | Adopt: `state_store = {}` as fake state backend + mock ctx capturing event registrations. Reusable scaffold for Gimle tool tests | N+1 |
| 18 | **`isError: true` + status-mapped recovery hints** | paperclip-mcp | `dist/tools/validation.js:handleApiError` (lines 38–118); `dist/tools/index.js:registerAllTools` (lines 41–55) | Raw tracebacks in MCP tool responses confuse LLM agents; non-actionable 500 messages cause retry-loops | Adopt: add `handle_tool_error()` in palace-mcp mapping Neo4j/HTTP errors to `{ isError: true, content: [{"type": "text", "text": "...recovery hint..."}] }` for: driver_unavailable, ServiceUnavailable, query timeout, unknown_entity_type, invalid_filter | N+0 |
| 19 | **Lifecycle hooks: `onHealth`, `onShutdown`, `onConfigChanged`** | plugin-sdk | `dist/define-plugin.d.ts` (PluginDefinition interface, lines 75–165); `dist/protocol.js` `HOST_TO_WORKER_REQUIRED_METHODS` | Host cannot distinguish "plugin crashed" from "plugin reports degraded"; no graceful shutdown truncates in-flight requests | Defer: add `GET /health` JSON endpoint `{ status, neo4j, uptime_seconds }` matching `PluginHealthDiagnostics` shape when palace-mcp is wrapped as a plugin or compose healthcheck requires machine-readable status | N+1 |
| 20 | **Server-side event filter scoping** | plugin-sdk | `dist/types.d.ts:EventFilter` + `PluginEventsClient.on()` (lines 43–52, 242–251) | Without scoping, every event crosses IPC boundary — wastes CPU, increases latency, causes queue backup at high throughput | Adopt pattern, defer implementation: document in `docs/mcp/ingest-design.md` that future event-driven ingest MUST register subscriptions scoped to `companyId + projectId` | N+1 |
| 21 | **Startup duplicate tool name detection** | paperclip-mcp | `dist/tools/index.js:registerAllTools` (lines 19–38) | Silent tool shadowing — wrong handler fires with no error when two modules register the same tool name | Adopt: add a startup assertion in `mcp_server.py` checking all registered tool names against a known set; process must crash at boot, not at first call | N+0 |
| 22 | **Response truncation + pagination metadata envelope** | paperclip-mcp | `dist/tools/format.js:applyCharLimit` + `paginate()` (lines 47–77); `dist/constants.js` (CHARACTER_LIMIT = 25 000) | Large result sets overflow LLM context windows or hit MCP message size limits; without a hint, agents don't know why output was cut off | Adopt: align `_meta` shape to `{ total, count, truncated_at, next_offset, has_more }`; add warning entry when truncated: `"Results truncated at {n}; use offset={next_offset} to fetch next page."` | N+0 |
| 23 | **Auth startup validation + configurable timeout + audit header** | paperclip-mcp | `dist/auth.js`; `dist/client.js:buildHeaders` | Lazy auth validation means first tool call fails instead of startup; missing run-ID header breaks audit trails | Adopt timeout pattern: add `PALACE_NEO4J_QUERY_TIMEOUT_MS` env var validated at startup with a clear error message, mirroring `PAPERCLIP_REQUEST_TIMEOUT_MS` pattern; startup validation already correct for Neo4j | N+1 |

---

## Priority Grouping

### N+0 — Adopt before next slice starts

| # | Pattern | Why now |
|---|---------|---------|
| 5 | Lazy company ID resolution | Startup 409/SIGKILL risk already present |
| 6 | Config merge with defaults | Prevents silent `KeyError` / `AttributeError` on optional config fields |
| 10 | Secret UUID ref pattern | Security: raw tokens must not appear in logs or state |
| 11 | Fire-and-forget slow init | Startup reliability — warmup calls can exceed timeout |
| 18 | `isError: true` + recovery hints | MCP clients expect `isError` flag; current error shape is non-standard |
| 21 | Startup duplicate tool detection | Low effort, fail-fast guarantee |
| 22 | Response truncation + pagination `_meta` | Aligns with already-landed GIM-37 `warnings` field; completes the spec |

### N+1 — Adopt in Graphiti / event-driven ingest slice

| # | Pattern |
|---|---------|
| 1 | `withRetry` + exponential backoff |
| 2 | `Retry-After` header parsing |
| 3 | In-memory event deduplication |
| 4 | State-based completion deduplication |
| 7 | Best-effort enrichment |
| 9 | MarkdownV2 → plaintext fallback |
| 13 | Incremental sync cursor |
| 16 | `vi.hoisted()` handler unit tests |
| 17 | In-memory ctx stub with state Map |
| 19 | Lifecycle hooks / structured health endpoint |
| 20 | Server-side event filter scoping |
| 23 | Configurable Neo4j query timeout |

### N+2 — Adopt in GitHub extractor slice

| # | Pattern |
|---|---------|
| 8 | Telegram `retry_after` in body |
| 12 | Echo-loop prevention via bridge marker |
| 14 | Two-index state for bidirectional entity lookup |
| 15 | Explicit sync direction enum |

---

## [MATERIAL GAP] — `paperclip-plugin-hindsight`

- Not published on npm under `@paperclipai/` or as `paperclip-plugin-hindsight`
- Not found in the `paperclipai` GitHub org
- `hindsight.vectorize.io/sdks/integrations/paperclip` has integration docs but source code is not public
- **Impact:** patterns around idempotency, schema versioning, temporal-edge handling, and embedding strategies are not covered
- **Recommendation:** If CTO has repo access, share source for a follow-up research pass. Otherwise, the N+1 Graphiti migration spec should define schema versioning strategy independently, drawing from Graphiti's own documentation rather than hindsight's approach.

---

## Adoption Checklist (N+0 items)

For each N+0 item, a micro-slice issue should be filed per GIM-39 acceptance criteria:

- [ ] **#5 + #11** — Review `palace-mcp` startup path; defer any API-dependent init or slow external calls
- [ ] **#6** — Add `DEFAULT_CONFIG` merge in all config reads
- [ ] **#10** — Audit config for raw token strings; replace with secret refs
- [ ] **#18** — Implement `handle_tool_error()` in `mcp_server.py`
- [ ] **#21** — Add startup tool name set assertion in `mcp_server.py`
- [ ] **#22** — Align `_meta` envelope shape; add truncation warning string

---

*Report compiled from raw findings in [GIM-39](/GIM/issues/GIM-39) comments by ResearchAgent ([GIM-40](/GIM/issues/GIM-40)) and MCPEngineer ([GIM-41](/GIM/issues/GIM-41)).*
