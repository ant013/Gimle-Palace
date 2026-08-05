# fullAudit: disposable smoke handling and durable audit cursor

## Context and problem

The general fullAudit agent instructions require a complete RUNBOOK cycle.  A
disposable `smoke-probe-*` issue is therefore interpreted as an audit request
instead of a narrowly bounded runtime question, so the probe does not reply
inside its 90-second budget.  The same overlay also has stale bootstrap text
that says to continue `bitcoin-core-swift`, although its report and durable
state are complete.

## Assumptions

- A title beginning `smoke-probe-` or `smoke-e2e-` is created only by the
  controlled Paperclip smoke scripts and is disposable.
- Normal audit work must always take the next/resume decision from
  `bin/next_kit.py` and the on-disk run state; it must not depend on a prompt
  hardcoding a kit slug.

## Scope

- Add a highest-priority, narrow runtime-probe exception to the fullAudit
  shared overlay: answer the exact probe through Paperclip, do no audit work,
  and stop.
- Replace the stale BitcoinCore direction with the RUNBOOK cursor rule and a
  factual guard that its completed report must not be re-audited.
- Add focused assembly tests that bind the exception to exact disposable title
  prefixes and prevent accidental broad bypass.
- Redeploy instructions and run one controlled full smoke after the loopback
  control-plane configuration is active.

## Non-goals

- Do not change normal audit evidence thresholds, role responsibilities,
  writable roots, or agent IDs.
- Do not create or run the actual roadmap/audit cycle before all smoke gates
  pass.
- Do not treat arbitrary issue text as a smoke probe.

## Affected areas

- `paperclips/projects/fullaudit/overlays/codex/_common.md`
- `paperclips/tests/test_fullaudit_assembly.py`
- generated fullAudit Codex instructions

## Acceptance criteria

1. Only `smoke-probe-*` and `smoke-e2e-*` titles trigger the exception; the
   agent reads the question, posts exactly the requested response, and stops.
2. A non-smoke issue still follows the complete RUNBOOK workflow.
3. The overlay derives next/resume work from `bin/next_kit.py`; it explicitly
   does not re-audit completed `bitcoin-core-swift`.
4. Focused tests, instruction build, manifest validation, and CI pass.
5. A single controlled smoke run reaches a response through the iMac loopback
   control plane and deletes only its recorded disposable issues.

## Verification plan

1. Inspect rendered instructions and run focused fullAudit tests locally.
2. Run manifest validation and CI.
3. Deploy the merged instructions to iMac, inspect the effective config, and
   run one controlled smoke with a retained log.

## Open questions

None.
