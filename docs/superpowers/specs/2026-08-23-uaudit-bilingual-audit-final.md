# UAudit: bilingual `audit-final` Telegram attachments

Status: proposed, revision 1

## Goal

For every UAudit run that currently produces `audit-final.md`, deliver two
Markdown attachments to the configured `UAudit` Telegram route: a Russian
report and a complete English translation. The Russian report remains the
canonical audit result; the English file is a digest-bound translation of it.

The current Telegram plugin accepts one Markdown document per action. The two
attachments will therefore be delivered as two ordered Telegram document
messages for the same issue: Russian first (with the existing caption), then
English. This deliberately avoids changing the separate Telegram-plugin
repository or assuming unsupported multi-file request parameters.

## Assumptions

- “`audit-final`” means the daily and forced-full document report, not PR
  `audit.md` and not no-change `daily_status` messages.
- Two ordered document messages satisfy the requested two attached files. A
  single Telegram media-group message is out of scope; that would require a
  plugin feature in another repository.
- English must translate titles, evidence, impact, recommendations,
  limitations, headings, and technical labels; copying Russian findings into an
  English-named file is not acceptable.
- A missing or invalid English translation prevents document delivery; it must
  not silently fall back to a single-language audit report.

## Scope

In scope:

- Create `audit-final.ru.md` and `audit-final.en.md` for daily/forced-full
  document reports.
- Add a UAudit TechnicalWriter translation handoff between canonical Russian
  aggregation and final delivery publication.
- Extend the delivery contract, receipt, and Infra prompts for two ordered
  document deliveries and restart-safe recovery.
- Update focused helper and prompt-bundle tests.

Out of scope:

- Changing the Telegram plugin API or its route configuration.
- Changing cursor rules, locks, audit finding severity, or no-change daily
  status delivery.
- Translating PR `audit.md` in this change.

## Verified current behavior and analogs

The helper’s `aggregate` function renders exactly one Russian `audit-final.md`
and places one report digest in `delivery-summary.json`; `verify_payload` and
`record_delivery` then enforce one document and one message id. This is the
primary implementation and lifecycle spine.

Both `UWAInfraEngineer` and `UWIInfraEngineer` consume that one report and use
one `send_to_telegram` document action. Existing focused tests cover aggregate,
receipt, and generated dispatcher/prompt content. `daily_status` is the
counterexample: it deliberately has no audit report and must stay single
message.

The deployed Telegram plugin source was inspected read-only on iMac: its
action accepts one `markdownContent` / `markdownFileName` pair. This supports
two ordered existing actions, but not one unverified multi-document action.

## Design

### 1. Canonical Russian report and translation input

`aggregate` continues to validate and canonicalize the reviewer stage
sidecars. For a document-producing daily/forced-full run it will:

1. render the canonical Russian file as `audit-final.ru.md`;
2. write an immutable `translation-input.json` containing the Russian report
   digest, run binding digest, source report filename, and structured
   translation units for every visible finding and limitation;
3. stop before publishing the final delivery summary/aggregate marker until
   translation has completed.

The input has stable IDs derived from the canonical findings, so a translation
cannot omit, add, or reorder findings without detection.

### 2. TechnicalWriter translation stage

`UWATechnicalWriter` / `UWITechnicalWriter` receive
`mode=daily_audit_translation`, the run directory, and the immutable
translation-input digest. They write:

- `audit-final.en.md`;
- `translation-result.json`, binding the input digest to all translated units
  and the English file digest.

The writers translate only supplied audit content. They do not change
findings, severity, locations, SHA values, range, verdict, or technical
counts. The helper validates identity coverage, digest binding, required
English units, bounded file size, and exact stable ordering before it publishes
the bilingual delivery summary.

### 3. Bilingual delivery contract

The final summary replaces singular `report` with ordered `reports` entries:

`ru` first, `en` second, each with file and SHA-256. Its document mode means
both entries are present; message mode remains unchanged for complete zero
finding reports.

`verify-payload` returns both validated paths/digests. Infra sends the Russian
document first with the existing caption and sends the English document second
without a duplicate caption, using the existing plugin `params` envelope and
`UAudit` route.

`record-delivery` records two per-language plugin receipts and a final
`delivery-result.json`. On a retry it validates existing receipts and sends
only the missing language. Once both receipts are present it writes the
existing `status/telegram.done` marker. The current crash window remains
at-least-once only for the individual send whose plugin accepted the request
before its receipt was persisted.

### 4. Prompt composition

For daily/forced-full documents, the dispatcher chain gains:

`QA -> dispatcher aggregate -> platform TechnicalWriter translation ->
dispatcher finalization -> Infra bilingual delivery`.

Status-only no-change delivery and PR delivery do not enter the writer stage.
Both Infra overlays will explicitly use the two entries from the helper output,
not construct English text or filename ad hoc.

## Affected areas

- `paperclips/projects/uaudit/runtime/uaudit_delivery_contract.py`
- `paperclips/projects/uaudit/roles-codex/uwa-platform-dispatcher.md`
- `paperclips/projects/uaudit/roles-codex/uwi-platform-dispatcher.md`
- `paperclips/projects/uaudit/overlays/codex/UWAInfraEngineer.md`
- `paperclips/projects/uaudit/overlays/codex/UWIInfraEngineer.md`
- UAudit TechnicalWriter role overlays/prompts, if no existing task-specific
  translation contract can be composed from their base role.
- generated `paperclips/dist/uaudit/*` outputs
- `paperclips/tests/test_uaudit_delivery_contract.py`
- `paperclips/tests/test_uaudit_dispatcher_bundles.py`

## Acceptance criteria

1. A daily or forced-full audit with findings or partial status produces
   `audit-final.ru.md` and `audit-final.en.md`; both cover the same ordered
   findings, severities, locations, verdict, and counts.
2. Telegram receives two route-aware document messages for one audit issue:
   Russian then English, with separate positive message ids recorded.
3. A restart after Russian receipt but before English delivery does not resend
   Russian; it sends and records English only.
4. A missing, stale, malformed, or incomplete English translation prevents
   delivery and does not mutate cursor/lock.
5. Complete zero-finding reports, daily no-change status, and PR `audit.md`
   preserve their existing one-message/no-attachment behavior.
6. Existing single-report persisted runs remain readable and reconcilable;
   they are never retranslated or resent solely due to this feature.
7. The normal iMac deployment regenerates and applies the changed prompts.

## Delta matrix

| Slice | Preserved invariant | Required change | Explicitly not changed | Tests |
| --- | --- | --- | --- | --- |
| Report generation | Helper owns deterministic Russian canonical report | Add translation input/result and ordered RU/EN reports | Finding schema and audit verdict rules | bilingual artifact/digest tests |
| Delivery | Route-aware plugin and receipt-led recovery | Two ordered sends and per-language receipts | Plugin API, route, cursor/lock rules | partial-receipt restart test |
| Agent flow | Infra is sole delivery owner | Insert platform writer translation stage | no-change/PR flow | generated prompt-chain tests |
| Failure behavior | No receipt means no completion mutation | Missing/invalid EN blocks before delivery; missing EN receipt resumes only EN | broad retry/preflight redesign | malformed translation and receipt conflict tests |

## Verification plan

1. Add focused helper tests for both artifacts, bilingual summary validation,
   missing/invalid translation, and Russian-only receipt recovery.
2. Update prompt bundle tests for writer handoff and two-document delivery
   instructions while asserting no-change/PR exclusions.
3. Run `python3 -m pytest paperclips/tests/test_uaudit_delivery_contract.py
   paperclips/tests/test_uaudit_dispatcher_bundles.py`.
4. Run `./paperclips/build.sh --project uaudit --target codex` and
   `python3 paperclips/scripts/validate_uaudit_docs.py`.
5. Deploy with `imac-agents-deploy.sh uaudit --target-sha <commit>` and execute
   one controlled document-mode audit only after implementation approval.

## Open question

The default design sends two consecutive Telegram document messages because the
current plugin supports one document per action. If you specifically require
both files inside a single Telegram media-group message, the scope must expand
to the Telegram-plugin repository and its deployment.
