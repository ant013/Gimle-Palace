# UAudit: repair Telegram delivery registration and QA limitation validation

## Grounding

Base: `origin/develop` at `1e0316d4d4bd4897c0686447165bdc0fba97162e`.

Production evidence on 2026-08-15:

- Android forced-full audit `UNS-545` assembled a Russian document payload, but
  delivery to `/api/plugins/00000000-0000-0000-0000-000000000000/actions/send_to_telegram`
  returned HTTP 404 `Plugin not found`.
- iOS forced-full audit `UNS-546` stopped in QA because
  `qa-verify.findings.json.limitations[0].text` exceeded the delivery helper's
  existing 240-character bound.
- The UAudit Infra overlays resolve `{{plugins.telegram_plugin_id}}`; the current
  deployed output resolves it to the all-zero UUID. A prior UAudit baseline uses
  a concrete Telegram plugin UUID, but production registration must be verified
  rather than copied from that historical artifact.

## Scope

1. Make UAudit bootstrap/reconciliation verify and configure a real registered
   Telegram plugin ID before a delivery task can be emitted. The configured ID
   must never be the all-zero placeholder.
2. Preserve receipt-led, single-attempt delivery: a missing or invalid plugin
   blocks before POST; it must not silently fall back to another endpoint.
3. Make the generated QA instructions and validation path prevent overlong
   Russian limitation prose from blocking a valid audit solely after it has
   already performed analysis.
4. Add targeted tests for the registered-plugin contract and for a 241-character
   limitation rejection with a generated short-form remediation path.

## Non-scope

- Do not weaken the 240-character helper constraint globally without evidence.
- Do not add Telegram credentials or UUIDs to committed source, reports, or
  prompts.
- Do not mutate daily cursors, daily schedules, or resend the existing payload
  during tests.

## Affected areas

- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- UAudit bootstrap/plugin configuration and its tests
- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`
- QA overlay(s) and targeted UAudit contract/bundle tests

## Design and analog delta

| Slice | Existing spine | Required delta | Invariant |
| --- | --- | --- | --- |
| Telegram delivery | Receipt-led `daily_delivery` handoff | Validate a configured live plugin ID before dispatch and render that non-placeholder ID | One authorised POST only; no fallback or retry |
| QA limitations | `_validate_limitation(..., 240)` | Tell QA to produce bounded Russian limitation text and provide a deterministic pre-validation guard | Helper schema remains fail-closed |

## Acceptance criteria

1. No deployed UAudit delivery prompt can contain the all-zero plugin UUID.
2. Bootstrap/reconcile fails with an actionable error if the required Telegram
   plugin is not registered for UAudit; it succeeds only with the operator
   runtime binding, never a source-committed secret/UUID.
3. A forced-full delivery with a valid binding preserves its current receipt,
   no-retry, Russian-report semantics.
4. QA-generated limitation content is bounded before `validate-stage`; an
   overlong input is rejected with actionable remediation and a compliant
   rewritten limitation passes.
5. Targeted UAudit tests and shell/static checks pass.

## Verification plan

1. Reproduce the all-zero UUID rendering and 404 against a fixture/local
   configuration without contacting Telegram.
2. Exercise the plugin-binding validation success, missing, and placeholder
   cases.
3. Exercise 240/241-character limitation validation and the QA preflight guard.
4. Run `bash -n paperclips/scripts/bootstrap-project.sh` and targeted
   `paperclips/tests/test_uaudit_*` tests.

## Open questions resolved during implementation

The live plugin ID will be read only from the existing operator/runtime plugin
registration; it will not be inferred from historical generated output.
