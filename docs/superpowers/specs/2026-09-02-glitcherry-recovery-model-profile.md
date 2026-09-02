# Glitcherry recovery model profile

Date: 2026-09-02  
Baseline: `51d5427a23e04426a13ce3da22de3fa405b29ed4` (`origin/develop`)  
Branch: `fix/glitcherry-disable-cheap-model-profile`

## Problem

Paperclip terminal-run recovery hard-codes the model-profile key `cheap`. During
GLA-15, the primary GlitcherryCTO configuration remained
`gpt-5.6-sol`/`xhigh`, but the recovery wake applied that profile and launched
the actual Codex process as `gpt-5.3-codex-spark`/`low`. This is an unacceptable
silent quality downgrade for specifications, reviews, implementation, and QA.

## Assumptions and decision

- All six Glitcherry agents keep `gpt-5.6-sol` as their primary model.
- Paperclip's existing recovery key cannot be renamed by project configuration;
  its value can be overridden per agent through
  `runtimeConfig.modelProfiles.cheap.adapterConfig`.
- Glitcherry maps that recovery key to `gpt-5.6-terra`.
- Recovery preserves each agent's primary reasoning effort (`high` or `xhigh`).
- No Glitcherry recovery path may select `gpt-5.3-codex-spark`, another 5.3
  model, or `low` reasoning.
- If both `gpt-5.6-sol` and `gpt-5.6-terra` are unavailable, the run fails and
  waits for a later retry; there is no second, cheaper fallback.

## Scope

1. Add an explicit Glitcherry recovery-model contract to the assembly manifest.
2. Teach the generic project bootstrap to materialize that optional contract in
   new agents and reconcile it in existing agents without replacing unrelated
   runtime configuration.
3. Add regression tests for the six-agent model/reasoning mapping and bootstrap
   reconciliation behavior.
4. Redeploy Glitcherry agents and verify the live Paperclip read-back.

Out of scope:

- changing primary agent models;
- changing recovery behavior for projects that do not opt in;
- patching installed Paperclip `node_modules`;
- accepting any direct issue-level override to a 5.3 model as a recovery path.

## Affected files and areas

- `paperclips/projects/glitcherry-android/paperclip-agent-assembly.yaml`
  — declare the approved recovery model and reasoning-preservation rule.
- `paperclips/scripts/bootstrap-project.sh`
  — create/reconcile only the managed recovery profile while preserving other
  `runtimeConfig` keys.
- `paperclips/tests/test_glitcherry_android_assembly.py`
  — assert the exact primary and recovery model contract.
- `paperclips/tests/test_phase_c_bootstrap_project.py`
  — assert opt-in, preservation, and idempotent reconciliation mechanics.

## Acceptance criteria

1. Every Glitcherry agent remains primarily configured for `gpt-5.6-sol`.
2. Every Glitcherry agent has an enabled Paperclip `cheap` profile whose actual
   adapter model is `gpt-5.6-terra`.
3. The profile reasoning effort exactly equals that agent's primary reasoning
   effort.
4. A project without the optional recovery contract retains existing bootstrap
   behavior.
5. Existing agents are reconciled in place; unrelated heartbeat and runtime
   keys are preserved.
6. Re-running bootstrap is idempotent.
7. No Glitcherry manifest or generated runtime payload contains
   `gpt-5.3-codex-spark` or `modelReasoningEffort: low`.
8. Live API read-back after deployment shows the expected primary/recovery pair
   for all six agents.
9. A subsequent recovery wake launches either primary `gpt-5.6-sol` or recovery
   `gpt-5.6-terra`; if neither is available it fails rather than downgrading.

## Verification plan

- Run the manifest validator.
- Run targeted Glitcherry assembly and bootstrap-project tests.
- Run `bash -n paperclips/scripts/bootstrap-project.sh`.
- Run the complete touched Paperclip test subset.
- Merge to `develop`, deploy Glitcherry agents from `develop`, and read back
  `adapterConfig` plus `runtimeConfig.modelProfiles.cheap` for all six agents.
- On the next real recovery, inspect the exact `codex exec --model ...` process
  and recorded run metadata. Do not manufacture a capacity failure.

## Rollback

Revert the implementation commit and redeploy. Until rollback is explicitly
completed, leave the current live `gpt-5.6-terra` recovery mapping in place;
returning to Paperclip's default `gpt-5.3-codex-spark` profile is not an
acceptable emergency rollback.

## Open questions

None. The owner selected `gpt-5.6-terra` and preservation of existing reasoning
effort on 2026-09-02.
