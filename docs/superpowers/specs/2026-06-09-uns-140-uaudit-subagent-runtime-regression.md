# UNS-140 UAudit Subagent Runtime Regression

Grounded at `b256407177b2ca749921deb4e2e39be21d9cb4fd` on `origin/develop`.
Branch: `fix/uns-140-typed-subagent-runtime`.

## Problem

UAudit daily Android `UNS-140` and iOS `UNS-141` block before reviewer fanout.
The live runtime exposes `multi_agent_v1.spawn_agent(message|items|fork_context)`
without `agent_type`, while UAudit infra bundles require exact `uaudit-*`
subagents through `spawn_agent.agent_type`.

## Assumptions

- UAudit-owned `uaudit-*.toml` profiles remain installed and read-only.
- Typed `agent_type` is still the preferred reviewer path when available.
- A generic/default agent without exact UAudit profile constraints is invalid.
- The current daily deltas are already materialized and cursors are unchanged.

## Scope

- Add a minimal, auditable fallback contract for runtimes without `agent_type`.
- Add tests so generated Android and iOS infra bundles mention the fallback.
- Keep dispatcher and reviewer instructions short.
- Preserve fail-closed validation: exact reviewer names, JSON shape, no cursor
  advance before Telegram delivery.

## Affected Areas

- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- Generated `paperclips/dist/uaudit/codex/*InfraEngineer.md`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- Optional runbook note for the runtime regression.

## Acceptance Criteria

- Android and iOS infra bundles prefer `agent_type` when available.
- If `agent_type` is unavailable, bundles allow only exact-profile fallback:
  one reviewer per required `uaudit-*` name, TOML/profile text applied, JSON
  `"agent"` matching the required name.
- Generic/default reviewer output without exact name remains blocking.
- Tests assert both infra bundles carry the compact fallback contract.
- UAudit docs validation and targeted pytest pass.
- After deploy, `UNS-140` and `UNS-141` can resume from existing FROM..TO
  artifacts and produce valid `audit.md` reports.

## Verification Plan

- `python -m pytest paperclips/tests/test_uaudit_dispatcher_bundles.py`
- `python -m pytest paperclips/tests/test_phase_f_uaudit_migration.py`
- `python paperclips/scripts/validate_uaudit_docs.py`
- `bash paperclips/build.sh --project uaudit --target codex`
- iMac deploy for `uaudit`.
- Re-run `UNS-140` and `UNS-141` from existing materialized deltas.

## Open Questions

- Whether Codex will restore `agent_type` in a later runtime. This fix remains
  compatible: typed launch stays first choice, fallback is only for missing
  schema support.
