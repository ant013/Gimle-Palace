# UNS-140 UAudit Subagent Runtime Regression Plan

Spec: `docs/superpowers/specs/2026-06-09-uns-140-uaudit-subagent-runtime-regression.md`
Grounded at `b256407177b2ca749921deb4e2e39be21d9cb4fd`.

## Plan

1. Confirm live failure evidence for `UNS-140` and `UNS-141`.
2. Review current UAudit infra and subagent installation contracts.
3. Update both infra overlays with a compact fallback contract.
4. Regenerate UAudit Codex bundles.
5. Add tests that lock the fallback and fail-closed behavior.
6. Run targeted validation.
7. Deploy UAudit bundles on iMac.
8. Resume Android and iOS daily audits from their existing FROM..TO artifacts.

## Review Gates

- Architecture review by subagent before implementation.
- Code review by subagent after implementation.
- Local targeted tests before deploy.
- Live smoke: both blocked daily audits continue without cursor rewind.
