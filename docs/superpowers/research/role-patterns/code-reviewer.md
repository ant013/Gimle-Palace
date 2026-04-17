# Code Reviewer — Research Notes

**Research date:** 2026-04-15
**Purpose:** inform `templates/roles/code-reviewer.md` in paperclip-shared-fragments
**Target deployment:** Gimle-Palace CodeReviewer role (Python/FastAPI + Docker Compose + MCP protocols + single-node infra; Red Team against GimleCTO/PythonEngineer/InfraEngineer)

## 1. Sources reviewed

| Source | Type | Credibility | Size / role | Signal |
|---|---|---|---|---|
| Medic `paperclips/roles/code-reviewer.md` | field-tested (in-prod on Medic CTO-lock flow) | author's own canonical | ~100 lines, Red Team adversarial | **primary field model** |
| voltagent/`code-reviewer.md` | community plugin (marketplace) | opus-model | 230+ lines prose/checklist | capability catalogue |
| voltagent/`architect-reviewer.md` | community plugin | opus-model | 220 lines | architecture axis |
| voltagent/`security-auditor.md` | community plugin | opus-model, Read/Grep/Glob only | 210 lines | security axis |
| voltagent/`error-detective.md` + `qa-expert.md` | community plugins | sonnet/opus | partial | error-correlation + QA strategy |
| pr-review-toolkit/`code-reviewer.md` | claude-plugins-official | opus-model | 75 lines | **confidence-scoring model** |
| pr-review-toolkit/`silent-failure-hunter.md` | claude-plugins-official | inherit-model | 140 lines | error-handling axis |
| pr-review-toolkit/`type-design-analyzer.md` | claude-plugins-official | inherit-model | 120 lines | invariants / type design axis |
| pr-review-toolkit/`pr-test-analyzer.md` | claude-plugins-official | inherit-model | 90 lines | test-coverage axis |
| pr-review-toolkit/`comment-analyzer.md` | claude-plugins-official | inherit-model | 90 lines | comment rot axis |
| pr-review-toolkit/`code-simplifier.md` | claude-plugins-official | opus-model | 90 lines | simplification axis |
| superpowers 5.0.7/`code-reviewer.md` | claude-plugins-official | inherit-model | 45 lines, plan-vs-impl focus | **plan-alignment axis** |
| claude-agents/comprehensive-review/{code,architect,security} | community plugin (wshobson-style) | opus-model, 2024/2025 | 3 files, 150-200 lines | modern tooling catalogue |
| claude-agents/backend-api-security/`backend-security-coder.md` | community plugin | sonnet-model | 180 lines | hands-on backend security rules |
| claude-agents/debugging-toolkit/`debugger.md` | community plugin | sonnet-model, 25 lines | concise debug loop | root-cause discipline |
| Google eng-practices (standard, looking-for) | canonical industry ref | Google public | web | review philosophy |
| OWASP Docker Cheat Sheet + compose-security cheatsheets (2025/2026) | canonical security | OWASP / vendor | web | Docker Compose rules |
| zhanymkanov `fastapi-best-practices`, OneUptime OWASP-for-FastAPI (2025), David Muraya security guide | community refs | GitHub/blogs | web | FastAPI review rules |
| Promptfoo/DeepTeam/Microsoft LLM red-team guides (2025/2026) | industry red-team refs | vendor/Microsoft | web | adversarial-review discipline |

16 agent prompts + 6 web references = solid signal. Medic's prompt is the **anchor** (proven in-prod); community prompts are a rule catalogue.

## 2. Common structural patterns

Section-frequency aggregate across the 7 most-directly-relevant reviewer prompts (Medic + voltagent code-reviewer + voltagent architect-reviewer + voltagent security-auditor + pr-review-toolkit code-reviewer + superpowers 5.0.7 + comprehensive-review code-reviewer):

| Section | Count | Notes |
|---|---|---|
| 1-2 line role statement | 7/7 | Universal |
| Adversarial / "assume broken" framing | 2/7 | **Only Medic + silent-failure-hunter** — minority but critical differentiator |
| Checklist of rules grouped by axis | 7/7 | Universal; Medic groups by client/server/testing/git |
| Confidence scoring (0-100 or severity levels) | 4/7 | pr-review-toolkit 0-100; Medic CRITICAL/WARNING/NOTE; silent-failure-hunter CRITICAL/HIGH/MEDIUM; voltagent critical/high/medium/low |
| Explicit output format template | 6/7 | Medic has canonical Markdown template (Summary → Findings by severity → Compliance → Verdict) |
| Plan review (pre-implementation) | 2/7 | Medic + superpowers 5.0.7 — rare but powerful |
| Rubber-stamp guardrail ("report only issues ≥ threshold" OR "assume broken") | 3/7 | pr-review-toolkit ≥80 confidence; Medic "assume broken"; silent-failure-hunter zero-tolerance |
| MCP / subagent / skill mapping | 1/7 | **Only Medic** — operational integration is a Medic innovation |
| Example interactions | 3/7 | claude-agents style; skip for our budget |
| JSON "Communication Protocol" stub | 2/7 | **voltagent only** — pure noise for Claude Code sub-agents, drop |

**Takeaway:** Medic's shape is tighter and more operational than community prompts. Community prompts are 150-250 lines of capability prose; Medic is ~100 lines with an enforceable checklist + a verdict template + MCP/subagent wiring. Our Gimle template should follow Medic's shape and budget.

## 3. Top 10 canonical rules (signal-ranked)

Rules appearing in 3+ sources, weighted by Medic inclusion:

1. **"Assume broken until proven correct" / adversarial default** — 5/7 explicit (Medic, silent-failure-hunter, LLM red-team guides, OWASP review mindset, pr-review-toolkit implicit via ≥80 threshold). **Prevents rubber-stamping.**
2. **Every finding = file:line + what's wrong + what's correct + rule reference** — 7/7. No "looks good" allowed; no vague comments. Medic explicitly forbids "looks good" phrasing.
3. **Severity-tiered output (CRITICAL blocks merge / WARNING nice-to-have / NOTE informational)** — 7/7. Some call it Critical/Important/Suggestion, some CRITICAL/HIGH/MEDIUM, some 0-100 confidence. Canonical tiers are 3 — more tiers dilute the signal.
4. **Project-rules compliance is mechanical, not subjective** — 6/7. Cross-check every claim against CLAUDE.md / style guide; treat project rules as hard spec. Medic uses a checkbox section verbatim.
5. **Bugs > style; function correctness > beauty** — 6/7. Google eng-practices + voltagent + pr-review-toolkit: reviewers primarily hunt logic errors, race conditions, null handling, security holes; style is secondary. Medic enforces this by putting logic/edge-case ahead of style in its review spec.
6. **Silent-failure zero-tolerance (no empty except/catch, no broad `except Exception`, no unreported fallback)** — 5/7. Dedicated pr-review-toolkit agent + voltagent code-reviewer + voltagent security + backend-security-coder + Medic ("Result<T>" + error handling).
7. **Test coverage is behavioral, not line-count — must prove new code would catch regressions** — 5/7. pr-test-analyzer explicitly: rate 1-10 by criticality, demand negative + edge cases, not 100% line coverage. Medic enforces "bug-case failing test first" rule.
8. **Plan review BEFORE implementation review** — 3/7 but high field-value. Medic reviews plans (cheaper fix); superpowers 5.0.7 reviews step completion against plan; Google eng-practices implicitly via design docs. **Huge ROI for Gimle (planning-first org).**
9. **Security checks first (injection, secrets in code, AuthN/AuthZ, unsafe deserialization, SSRF, path traversal)** — 6/7 across security-auditor, voltagent, backend-security-coder, FastAPI 2025 refs, OWASP. The FastAPI 2025 incident (default JWT secret leaked) shows this is non-optional.
10. **Verdict is binary enough — APPROVE / REQUEST CHANGES / REJECT; no "LGTM with concerns"** — 4/7 explicit (Medic, superpowers 5.0.7, pr-review-toolkit via confidence threshold, Google Critique-Before-Approve). Ambiguous verdicts destroy the review signal.

Secondary rules (2-3 sources, worth a line each in the role):

- Architectural deviations from plan = explicit finding, not "refactor later" (superpowers 5.0.7, Medic, architect-reviewer).
- Comment-rot is a real defect class — outdated comments > no comments (comment-analyzer).
- Over-engineering / premature abstraction is a finding — Google eng-practices explicit; voltagent + code-simplifier echo.
- Dependency freshness + vulnerability scan (voltagent, comprehensive-review, OWASP Docker).
- Concurrency review: async/await discipline, event-loop blocks, race conditions (FastAPI 2025 refs, error-detective, debugger).

## 4. Tooling — MCP / subagents / skills / external

### MCP servers (pre-wire for Gimle CodeReviewer)

- **serena** — `find_symbol`, `find_referencing_symbols`, `search_for_pattern` (mirrors Medic; all community security agents use Read/Grep/Glob — Serena is the semantic upgrade)
- **context7** — Python/FastAPI/Pydantic/Docker-Compose/MCP-protocol docs (rules change; don't trust training data)
- **github** — PR diff, comments, CI check status
- **sequential-thinking** — only for architectural reviews (optional; Medic uses it sparingly)

Explicitly **not** pre-wire: supabase (not in Gimle stack), playwright (reviewer doesn't run browsers), figma.

### Subagents (Key question — single generalist vs coordinator)

**Medic pattern (field-tested):** single CodeReviewer as generalist; *names* specialized subagents (`architect-reviewer`, `security-auditor`, `compliance-auditor`) but doesn't orchestrate them — they're listed as skills/personalities the reviewer *can invoke* from the plugin ecosystem when a finding crosses specialty lines.

**Community pattern:** no plugin does full multi-personality orchestration in a single role. pr-review-toolkit bundles 6 specialist agents (`code-reviewer`, `silent-failure-hunter`, `type-design-analyzer`, `pr-test-analyzer`, `comment-analyzer`, `code-simplifier`) and invokes them serially from a top-level `review-pr` skill. Comprehensive-review does the same with 3 agents (code + architect + security). Voltagent lists 16 adjacent agents but each is standalone; cross-agent integration is advisory text, not orchestration code.

**Recommendation for Gimle:** **(a) single generalist reviewer** with subagent *callouts* (matching Medic), NOT (b) a thin coordinator that mandatorily fans out to 6 personalities. Rationale:

- Gimle is single-node + small stack. 6 personalities = 6× context + 6× token cost + coordination overhead. Field-tested Medic explicitly chose generalist.
- The community's existing specialist agents (`security-auditor`, `silent-failure-hunter`, `pr-test-analyzer`) are plug-in skills — reference them by name for the reviewer to invoke **when triggered by finding class**, not upfront.
- Spec §6 proposes (b) 6-personality split — but none of the 16 reviewed prompts do this upfront, and the only plugin that bundles specialists (pr-review-toolkit) gates them behind an *orchestrating skill* (`review-pr`), not the reviewer role itself. The right place for orchestration is a skill, not the role prompt.
- Single generalist + triggered specialists = best of both: low base cost, specialist depth on demand.

**When the reviewer should invoke `security-auditor` subagent vs do it inline:**
- Inline: OWASP Top-10 basic checks, input validation, secret-in-code, auth/authz presence, injection on ORM.
- Hand off to security-auditor: compliance (SOC2/HIPAA/GDPR), threat modelling, cryptographic protocol review, supply-chain SBOM, full penetration test simulation.
- Threshold rule: "do it inline if CLAUDE.md rules cover it; hand off if requires external framework expertise."

### Skills (pre-wire)

Mirror Medic's skill stack + Gimle-specific additions:

- `pr-review-toolkit:review-pr` — first invocation, runs silent-failure + test-analyzer + simplifier in sequence
- `pr-review-toolkit:silent-failure-hunter` — FastAPI async error handling is high-risk; keep always-available
- `pr-review-toolkit:pr-test-analyzer` — test behavioral coverage (not line %)
- `pr-review-toolkit:type-design-analyzer` — on Pydantic schema / domain type changes
- `pr-review-toolkit:comment-analyzer` — on doc-heavy PRs
- `pr-review-toolkit:code-simplifier` — after architectural refactors
- `superpowers:verification-before-completion` — enforce evidence-before-assertions (Gimle spec §3)

### External references (cite in role doc)

- Google eng-practices "Standard of Code Review" + "What to look for"
- OWASP Docker Cheat Sheet (for Compose review axis)
- FastAPI 2025 security checklist (zhanymkanov + OneUptime OWASP-for-FastAPI)

## 5. Anti-patterns reviewers commonly miss

Aggregated across silent-failure-hunter, error-detective, voltagent security, backend-security-coder, comment-analyzer, FastAPI 2025 refs, OWASP Docker:

1. **Rubber-stamping** — "LGTM" or empty approval. Mitigation: require structured verdict + at least one concrete finding per axis OR explicit "N/A — no X in diff" statement.
2. **Style-only review** — tabs/spaces comments while missing SQL injection. Mitigation: logic/security/tests axes **must** be ticked before style comments are even allowed.
3. **Broad `except:` / `except Exception:` that swallows real errors** — silent-failure-hunter's #1 target.
4. **Async blocking inside `async def`** (FastAPI 2025 refs) — sync DB call in async route = event-loop starvation. Reviewer must check imports (requests, time.sleep, psycopg2 sync, SQLAlchemy non-async) in every async route.
5. **Default/placeholder secrets in config** (FastAPI 2024 incident) — `SECRET_KEY = "secret"` or tutorial defaults. Grep for known-bad strings + ensure `.env` not committed + ensure secret generation doc exists.
6. **Docker Compose anti-patterns** — `:latest` tags, running as root, missing `read_only: true`, missing `cap_drop: [ALL]`, env-vars with secrets instead of `secrets:`, exposing ports to 0.0.0.0 on single-node boxes, missing healthcheck, no resource limits (`mem_limit`, `cpus`).
7. **MCP protocol code** (Gimle-specific) — missing request validation on MCP tool inputs (same as API), leaking internal tool errors to client, no rate limiting on MCP endpoints.
8. **Comment rot** — stale docstring after refactor; TODO referencing already-closed ticket.
9. **Test tautology** — tests that mirror the implementation (mock everything, assert the mock was called). pr-test-analyzer: "tests must fail when behavior changes, not when implementation changes."
10. **Plan-drift** (superpowers pattern) — implementation quietly deviates from plan; reviewer misses because they read only the diff. Mitigation: reviewer loads the plan first, then diffs implementation against it.
11. **Scope creep in the PR** — "while I was there I also refactored X" — expands blast radius. Reviewer must flag unrelated changes.
12. **Config-as-code skipped** — changes to `docker-compose.yml`, `pyproject.toml`, env schemas often get zero review; treat as first-class code.

## 6. Recommendations for template + open questions

### Recommendations (for `templates/roles/code-reviewer.md`)

1. **Adopt Medic's structural shape verbatim** (Role → Principles → What you review → Compliance checklist → Output format template → MCP/Subagents/Skills → @include fragments). It is tighter, more operational, and already field-tested. ~100 lines, ~1800-2000 tokens — fits spec §4.1 budget.
2. **Go (a) single generalist**, not (b) 6-personality coordinator. Name specialist subagents/skills as *triggered invocations*, not as mandatory fan-out. Document the invocation-threshold rule (inline for CLAUDE.md-covered rules; hand off for framework-depth topics).
3. **Adversarial framing must be first paragraph.** "You are Red Team. Assume broken until proven correct. Your job is to find problems, not confirm quality." This single line is the most important anti-rubber-stamp mechanism — Medic's field experience + red-team guides + silent-failure-hunter all converge on this.
4. **Output template is non-negotiable** — CRITICAL / WARNING / NOTE + Compliance checklist + Verdict (APPROVE / REQUEST CHANGES / REJECT). No free-form commentary allowed. Forbid the phrase "looks good" / "LGTM" explicitly (Medic precedent).
5. **Stack-specific compliance checklist** must reflect Gimle reality, not Medic's KMP/iOS world:
   - Python/FastAPI axis: async discipline (no sync in async), Pydantic v2 on all boundaries, `Depends()` for DI (not globals), custom exception hierarchy, no default JWT/secret, mypy strict, pytest-asyncio, `httpx` not `requests`.
   - Docker Compose axis: pinned image tags, non-root user, `read_only: true`, `cap_drop: [ALL]`, `secrets:` not env, healthcheck, mem/cpu limits, port binding to 127.0.0.1 on single-node.
   - MCP protocol axis: tool-input validation, error-surface discipline, idempotency where relevant, rate-limit on MCP endpoints.
   - Infra/single-node axis: backups before migrations, forward-only migrations, no destructive ops, secrets via Vault/env not code, pgcron-equivalent via systemd timers.
   - Testing axis: behavioral coverage not line %, bug-case failing test REQUIRED for fixes, no test tautology.
   - Git axis: feature branch off develop, no force-push, pre-work discovery in PR body.
6. **Include plan-review as first-class responsibility** (Medic + superpowers 5.0.7 pattern). Gimle is a planning-heavy org — catching arch errors in plan is 10× cheaper than after implementation.

### Open questions

1. **Does Gimle want CRITICAL to auto-block merge via GitHub branch protection?** Medic currently requires manual CTO override; mechanism unspecified for Gimle. Affects whether the role should emit a machine-readable status.
2. **Is there a Compliance-Auditor role planned separately?** If yes, CodeReviewer should hand off SOC2/GDPR-class findings to it; if no, the compliance axis needs inlining.
3. **Language/Russian vs English for findings?** Medic uses Russian per project language fragment. Gimle-Palace language convention is unspecified in research scope — check docs/superpowers or ask.
4. **Does CodeReviewer review CTO's own plans?** If yes (Red Team independence principle), need explicit escalation path to Board-equivalent. Medic handles this via "независим от CTO — отчитываешься Board" — needs Gimle analogue.
5. **Skill bundle availability** — pr-review-toolkit, superpowers, etc. assumed installed; confirm they are pre-provisioned in Gimle-Palace environment or document as prereq.

## Sources

- [Google Engineering Practices — Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html)
- [Google Engineering Practices — What to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Docker Compose Security Best Practices (compose-it.top)](https://compose-it.top/posts/docker-compose-security-best-practices)
- [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [OneUptime — Secure FastAPI against OWASP Top 10 (2025)](https://oneuptime.com/blog/post/2025-01-06-fastapi-owasp-security/view)
- [Promptfoo — LLM Red Teaming Guide](https://www.promptfoo.dev/docs/red-team/)
- [Microsoft — Planning LLM Red Teaming](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/red-teaming)
- [Confident-AI DeepTeam — What Is LLM Red Teaming](https://www.trydeepteam.com/docs/what-is-llm-red-teaming)
