# GIM-839 CEO Walker Handoff

## Paperclip Issue

Title: `GIM-839 Productized smoke + semantic quality CEO walker`

Assignee: CEO/roadmap walker.

Priority: high.

## Objective

Orchestrate GIM-839 productized runtime smoke and semantic-search quality work
from the approved spec branch. The CEO/walker dispatches slice-sized child
issues, keeps the parent status block current, and closes only after all
required slices are merged to `develop` with evidence.

The CEO/walker does not implement product code in this parent issue.

## Inputs

- Spec branch: `docs/GIM-839-productized-smoke-semantic-quality`
- Target branch: `develop`
- Spec:
  `docs/superpowers/specs/2026-05-25-GIM-839-productized-smoke-and-semantic-quality_spec.md`
- Plan:
  `docs/superpowers/plans/2026-05-25-GIM-839-productized-smoke-and-semantic-quality.md`

## Normative Rules

- The plan's Normative DAG table is the single scheduling source of truth.
- The canonical work unit is one slice row: `D0`, `A1-A7`, `B1-B6`, or
  `C1-C3`.
- Do not create track-sized children such as "all Track A" or "all Track B".
- Create one PR per slice, branched from current `develop`, squash-merged back
  to `develop`.
- Each slice branch has one writer. Ownership changes require explicit handoff
  in the child issue.
- Only `merged` with a merged-to-`develop` SHA counts as done for dependency
  checks.
- A child closed without a `develop` merge SHA is not done; reopen, respawn, or
  escalate it.
- The CEO may create independent ready slices while a blocking slice is active,
  but must not create work that depends on the active blocking slice.
- Keep B1-B6 on the same Claude CTO lane unless a child plan proves disjoint
  files.
- If preferred owner is unavailable for two consecutive pick cycles and the DAG
  declares a fallback owner, assign the fallback.
- If the graph, owner, or acceptance is ambiguous, comment on the CEO parent and
  wake the operator-facing agent instead of guessing.

## Initial Parent Status Block

Post this block in the parent issue and update it in place:

```markdown
<!-- GIM-839-WALKER-STATUS -->
| Slice | State | Owner | Issue | Branch | Merged SHA | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| D0 | pending | Claude CTO | - | - | - | contract lock |
| A1 | pending | Claude CTO | - | - | - | blocked by D0 |
| A2 | pending | Claude CTO | - | - | - | can run after spec approval |
| A3 | pending | Claude CTO | - | - | - | blocked by D0,A2 |
| A4 | pending | Claude CTO | - | - | - | blocked by D0,A1 |
| A5 | pending | Codex/CX CTO | - | - | - | blocked by D0,A1 |
| A6 | pending | Claude CTO | - | - | - | blocked by D0 |
| A7 | pending | Claude CTO | - | - | - | blocked by A3,A5,A6 |
| B1 | pending | Claude CTO | - | - | - | blocked by D0 |
| B2 | pending | Claude CTO | - | - | - | blocked by D0 |
| B3 | pending | Claude CTO | - | - | - | blocked by D0,B1 |
| B4 | pending | Claude CTO | - | - | - | blocked by D0,B3 |
| B5 | pending | Claude CTO | - | - | - | blocked by D0 |
| B6 | pending | Claude CTO | - | - | - | blocked by B3,B4,B5 |
| C1 | pending | Operator/Codex QA | - | - | - | blocked by A3,A4,A5,A6 |
| C2 | pending | Codex/CX QA | - | - | - | blocked by A3,A4,A5,A6,B1,B2 |
| C3 | pending | Claude QA | - | - | - | blocked by B3,B4,B5,B6,C2 |
<!-- /GIM-839-WALKER-STATUS -->
```

Allowed states: `pending`, `active`, `blocked`, `merged`, `skipped`.

## First Dispatch

1. Read the spec and plan paths above.
2. Create the parent status block.
3. Create child `D0: contract lock` for Claude CTO first.
4. Create `A2: MCP Streamable HTTP caller` only if a compatible free owner lane
   exists; it is not dependency-blocked by D0, but it still must obey the
   one-active-child-per-CTO rule.
5. After each child merges, verify the merged-to-`develop` SHA, update the
   status block, then rerun the pick rule from the plan.

## Parent Acceptance

- Parent issue contains the structured walker status block.
- Child issues are created only for DAG slices or explicitly justified bundles
  of adjacent same-owner slices.
- Every child issue includes parent id, slice id, owner, branch name, spec path,
  plan path, dependencies, acceptance criteria, verification path, and close
  requirement.
- No implementation edits are made in the CEO parent issue.
- Each completed slice records a merged-to-`develop` SHA.
- Final parent close comment includes merged slice table, runtime evidence
  status, semantic evidence status, and remaining follow-up issues if any.
