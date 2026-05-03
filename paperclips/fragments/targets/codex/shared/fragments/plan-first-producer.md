## Plan-first discipline (multi-agent tasks)

Any issue requiring **3+ subtasks** OR **handoff between agents** — REQUIRED to use the Codex `create-plan` skill BEFORE decomposing in comments.

**Output:** plan file at `docs/superpowers/plans/YYYY-MM-DD-GIM-NN-<slug>.md` with per-step:
- description + acceptance criteria
- suggested owner (subagent / agent role)
- affected files / paths
- dependencies between steps

**Why:**
- Plan = source of truth, **comments = events log only**.
- Subsequent agents read **only their step**, not the whole issue + comment chain.
- Token saving: O(1) per agent vs O(N) bloat.
- CodeReviewer reviews the plan **before** implementation (cheaper to catch arch errors here).

**After plan ready:** issue body → link to plan, subsequent agents reassigned with their step number.
