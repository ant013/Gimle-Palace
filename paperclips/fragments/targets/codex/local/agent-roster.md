## Agent UUID roster — {{PROJECT}} Codex / CX

Use `[@<CXRole>](agent://<uuid>?i=<icon>)` in phase handoffs.
Source: `paperclips/codex-agent-ids.env`.

**Cross-team handoff rule** (applies to ALL agents, both teams): handoffs
must go to an agent on YOUR OWN team. CX-side roles handoff to CX-side
agents (CX prefix); Claude-side roles handoff to Claude-side agents
(bare names). The two teams are isolated by design (per
`feedback_parallel_team_protocol.md`). When you say "next CTO" — that's
**CXCTO**, NEVER bare `CTO` (which is the Claude-side CTO and would
cross team boundaries). If your handoff message contains
`[@CTO](agent://7fb0fdbb-...)` — STOP, that's a Claude UUID, you must
use `[@CXCTO](agent://da97dbd9-...)` instead.

| Role | UUID | Icon |
|---|---|---|
| CXCTO | `da97dbd9-6627-48d0-b421-66af0750eacf` | `crown` |
| CXCodeReviewer | `45e3b24d-a444-49aa-83bc-69db865a1897` | `eye` |
| CodexArchitectReviewer | `fec71dea-7dba-4947-ad1f-668920a02cb6` | `eye` |
| CXMCPEngineer | `9a5d7bef-9b6a-4e74-be1d-e01999820804` | `circuit-board` |
| CXPythonEngineer | `e010d305-22f7-4f5c-9462-e6526b195b19` | `code` |
| CXQAEngineer | `99d5f8f8-822f-4ddb-baaa-0bdaec6f9399` | `bug` |
| CXInfraEngineer | `21981be0-8c51-4e57-8a0a-ca8f95f4b8d9` | `server` |
| CXTechnicalWriter | `1b9fc009-4b02-4560-b7f5-2b241b5897d9` | `book` |
| CXResearchAgent | `a2f7d4d2-ee96-43c3-83d8-d3af02d6674c` | `magnifying-glass` |
| CXBlockchainEngineer | `4e348572-1890-4122-b831-2185d9d50609` | `gem` |
| CXSecurityAuditor | `f67918f9-662d-47c0-b6f7-5d66870d2702` | `shield` |

`@Board` stays plain (operator-side, not an agent).

### Routing rule (when in doubt — Episodes 1+2 prevention)

| You need to address... | Use... | NOT |
|---|---|---|
| "the CTO" | `[@CXCTO]` (`da97dbd9`) | `[@CTO]` (`7fb0fdbb`) ❌ Claude side |
| "the CodeReviewer" | `[@CXCodeReviewer]` (`45e3b24d`) | `[@CodeReviewer]` (`bd2d7e20`) ❌ |
| "the QAEngineer" | `[@CXQAEngineer]` (`99d5f8f8`) | `[@QAEngineer]` (`58b68640`) ❌ |
| "the BlockchainEngineer" | `[@CXBlockchainEngineer]` (`4e348572`) | `[@BlockchainEngineer]` (`9874ad7a`) ❌ |
| "the SecurityAuditor" | `[@CXSecurityAuditor]` (`f67918f9`) | `[@SecurityAuditor]` (`a56f9e4a`) ❌ |
| "the architect-reviewer" | `[@CodexArchitectReviewer]` (`fec71dea`) | `[@OpusArchitectReviewer]` (`8d6649e2`) ❌ |

If you find yourself wanting to use a Claude-side UUID — you're crossing
team boundaries. Operator caught this exact bug on 2026-05-07 in {{evidence.post_merge_stall_issue}}
(Episode 1 at 15:53 — CXCodeReviewer handed to Claude CTO; Episode 2 at
16:34 — CR Phase 3.1 review addressed Claude CTO again). Don't repeat it.
