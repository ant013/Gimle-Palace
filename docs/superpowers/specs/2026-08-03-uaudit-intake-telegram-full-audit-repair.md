# UAudit Intake Repair and Explicit Full-Range Audit

Status: review-ready

Design revision: 1

Grounded repository state: `origin/develop` at `c634cda4f23075d7e98df3dbeae9271281a55ac1` (2026-08-03).

## Goal

Restore a deployable, reproducible UAudit intake path and add a one-shot,
explicitly authorized full-range audit for both Android and iOS `version/0.50`.
The one-shot flow must audit the entire operator-supplied range without the
daily `30 commits / 300 files / 3000 lines` limits, deliver its report through
the normal Telegram receipt path, and leave recurring daily limits, schedules,
and daily cursors unchanged.

## Evidence and assumptions

- The live native service currently runs
  `/Users/ant013/Android/Gimle-Palace-serving` at `0e9cf57c`, three commits
  behind `origin/develop`; the reviewed worktree is not the runtime source.
- Current `origin/develop` already contains the stable-key, revision-safe
  UAudit routine reconciler and `version/0.50` routine source. Deployment and
  reconciliation are therefore required even if no source defect is found.
- The daily dispatcher contract intentionally exits before artifact or Telegram
  delivery when its cursor equals head. It must keep that behavior.
- The observed Android no-op proof referred to an `uauthoritative` remote/SHA
  that cannot be reproduced from the checkout declared in the execution issue.
- “Без лимитов всего” is interpreted as a one-shot full-history range for both
  `version/0.50` repositories, not as weakening the protection on every future
  daily run.

## Scope

### In scope

1. Add a source-owned operator launcher for explicit full-range Android/iOS
   UAudit issues. It requires both immutable `from_sha` and `to_sha`, a
   `--confirm-unbounded` acknowledgement, and an explicit platform selection.
2. Add `forced_full_range` handling to both platform dispatcher and infra role
   sources, rendered UAudit bundles, and delivery helper contract.
3. Preserve the staged code/security/crypto/infra/QA chain and the existing
   receipt-led Telegram delivery validation for the full-range flow.
4. Make full-range completion write a receipt/workflow result but never mutate
   a daily cursor, daily lock, routine description, assignee, or schedule.
5. Add tests for launch validation, no cursor mutation, daily-limit isolation,
   receipt-before-completion behavior, generated prompt parity, and rejection
   of ambiguous/malformed source refs.
6. After merge, deploy the approved UAudit source to the active native serving
   checkout, reconcile both live routines, then create and run the two
   authorized full-range issues (Android and iOS) using verified source refs.

### Out of scope

- Permanently widening the daily limits or modifying schedule cadence.
- Advancing, deleting, or reconstructing daily cursors from a full-range run.
- Direct Telegram Bot API calls, chat-ID routing, tokens in source, or bypassing
  `uaudit_delivery_contract.py`.
- Changing report destinations, agent roster semantics, product code, or
  silently treating an empty/missing checkout as a no-op.

## Affected areas

- `paperclips/scripts/launch_uaudit_forced_full_audit.py` (new)
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`
- `paperclips/projects/uaudit/roles-codex/{uwa,uwi}-platform-dispatcher.md`
- `paperclips/projects/uaudit/overlays/codex/{UWA,UWI}InfraEngineer.md`
- generated `paperclips/dist/uaudit/codex/*.md` and resolved assembly
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`
- focused launcher and delivery-contract tests
- operator delivery/runbook documentation

## Design and delta matrix

| Slice | Verified analog family | Preserved invariant | Required delta | Rejected delta | Tests/verification |
| --- | --- | --- | --- | --- | --- |
| Live routine identity | `reconcile_uaudit_routines._match_live_routine` + `apply_plan` | Stable `routine_key`, read-before-revision PATCH, no implicit creation | Deploy current `develop` and reconcile only actual daily routine drift | Recreate routines or alter schedules | Dry-run, apply, and converged no-op against live API |
| Full-range dispatch | Daily platform dispatchers | Canonical repo/ref validation, distinct lock, staged handoff | Accept only a marked `forced_full_range` issue with exact SHA endpoints and explicit unbounded confirmation; ignore daily cursor/limits for that issue | Make normal daily no-op/limits permissive | Source/prompt tests reject missing refs/confirmation and prove daily rules unchanged |
| Delivery lifecycle | `uaudit_delivery_contract.reconcile_daily` + Infra delivery overlay | Validate payload, record Telegram receipt before terminal completion | Add a full-range terminal path with receipt/workflow proof but no cursor reconciliation | Direct-send or cursor advancement | Contract tests prove no cursor/lock mutation before or after delivery and reject malformed receipt |
| Deployment | `imac-agents-deploy.sh --from-develop` | Rendered bundles come from reviewed source and are rollbackable | Deploy only merged source; record SHA and bundle/helper hashes before live audit | Copy unreviewed files into serving checkout | Deploy log, health SHA, rendered-bundle and helper manifest checks |

The primary spine is the current stable-key reconciler. The delivery helper is
supporting lifecycle evidence, while the legacy direct-send baseline is an
explicitly rejected counterexample.

## Full-range execution contract

The launcher creates one issue per selected platform with all of:

- marker `UAudit forced full-range audit`;
- `mode=forced_full_range`;
- `branch=version/0.50`, canonical repo path, immutable `from_sha` and
  `to_sha`, and `audit_kind=forced_full`;
- `daily_limits_bypassed=true` and an operator acknowledgement stored in the
  issue description;
- a run directory and lock namespace distinct from daily audit namespaces.

The dispatcher verifies each ref exists in the checkout it names and that
`from_sha` is an ancestor of `to_sha`. It must block on a remote/check-out
identity mismatch rather than use an undeclared remote. The full-range flow
uses the existing staged team, produces receipt-validated Telegram delivery,
and finishes without writing `state/*-version-audit.json`.

## Acceptance criteria

1. The running native service and deployed UAudit agent bundle hashes match the
   merged source SHA; the native health endpoint is healthy after restart.
2. Reconciliation maps each source `routine_key` to exactly one live routine,
   applies only needed description/assignee changes, and a second dry-run is a
   no-op.
3. Normal daily runs retain 30/300/3000 limits and cursor=head no-op behavior.
4. Each forced full-range issue rejects absent, non-hex, non-ancestor, or
   undeclared-checkout refs and requires `--confirm-unbounded`.
5. A successful Android and iOS forced run produces a receipt-validated
   Telegram response (`ok:true`, `routeSource:file_route`, `routeName:UAudit`,
   correct issue, message ID) and a terminal workflow marker.
6. Before and after both forced runs, the two daily cursor file contents and
   recurring routine trigger configuration are byte-for-byte unchanged.

## Verification plan

Before source changes: add focused failing launcher/prompt/helper tests.

After implementation:

```bash
cd paperclips
uv run pytest tests/test_uaudit_dispatcher_bundles.py tests/test_uaudit_delivery_contract.py -v
python3 scripts/build_project_compat.py --project uaudit --target codex --inventory skip
python3 scripts/validate_uaudit_docs.py
```

After merge/deploy, collect readback for live routine revisions, deployed SHA,
health, helper manifest, two Telegram receipt objects, immutable daily cursor
hashes, and unchanged schedule trigger definitions.

## Risks and mitigations

- Full-history diff can exceed normal runtime/token budgets: it is allowed only
  by the explicit one-shot acknowledgement, emits progress/partial evidence,
  and never converts failure into a daily cursor update.
- A wrong checkout could silently skip code: require the declared checkout,
  verified remote/ref identity, and exact immutable SHAs in the issue.
- Delivery can be at-least-once: retain the receipt-led helper and make retries
  reconcile the receipt before sending again.
- Deployment drift can reappear: report the deployed source SHA and bundle
  hashes as a mandatory gate before issue creation.

## Open questions

None that block design. The exact `from_sha` and `to_sha` values will be
resolved from the canonical product remotes only after the deployment/readback
gate; they must not be guessed from the stale shared checkouts.
