# Forced-full Russian v1 delivery recovery

Grounded in `origin/develop` at `b34cc2cf32cb57e80fe39192df0ce931d412b17e`, live Android recovery `UNS-527`, and the English iOS delivery incident `UNS-528`.

## Assumptions

- The user has authorized completion of the existing Android delivery and correction of the iOS report form.
- A forced-full run has the same digest-bound input and staged audit chain as a daily delta, but must never reconcile or mutate a daily cursor/routine.

## Scope

- Add `forced_full` as an explicit delivery-contract kind sharing the daily staged inputs and Russian deterministic renderer.
- Require a held, distinct forced-full lock at bind time; preserve PR and daily-delta semantics.
- Add regression coverage for Android and iOS forced-full aggregation and Russian report generation.

## Acceptance criteria

- `forced_full` cannot bypass validated v1 aggregation or receipt creation.
- Generated report-facing text and Telegram caption remain Russian.
- No code path permits `reconcile-daily` for forced-full runs.

## Verification

- Run the UAudit delivery-contract suite and dispatcher-bundle contract tests.
- Run `git diff --check`.

## Open questions

- iOS correction delivery will use a separate, explicitly marked corrective receipt because the old English document already has a receipt.
