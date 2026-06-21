# GIM-1638 error_handling_policy semgrep timeout unblock

Grounded in `origin/develop` at `f9615bfc` (`fix(cross-repo-skew): use canonical bundle membership`).

## Assumptions

- The GIM-1638 rebaseline path runs natively on the MacBook against launchd
  `work.ant013.palace-mcp-native` and native Neo4j. Docker and iMac smoke are
  out of scope for this unblock.
- The target corpus is the seven dedicated iOS repos under
  `/Users/Shared/Ios/Gimle-Repos/HorizontalSystems`.
- The full sequential rebaseline evidence already exists under
  `/tmp/gim-1638-rebaseline/`; the only remaining hard failure is
  `error_handling_policy` for `uw-ios-app`.
- Raising the semgrep subprocess timeout is acceptable for explicit full
  rebaseline runs. The default should stay conservative enough for normal local
  development.

## Problem

The GIM-1638 rerun repaired the native launchd PATH and recovered 20 of 21
semgrep-backed extractor runs. The remaining failure is:

```text
error_handling_policy / uw-ios-app:
semgrep timed out after 120s on
/Users/Shared/Ios/Gimle-Repos/HorizontalSystems/unstoppable-wallet-ios
```

Runtime verification showed `Settings.extra=forbid`, while
`Settings.model_fields` contains neither `palace_crypto_semgrep_timeout_s` nor
`palace_error_handling_semgrep_timeout_s`. The extractor tries to read those
attributes and falls back to `120`, so `.env` cannot currently raise the
timeout for the native service.

## Scope

- Add explicit `Settings` fields for the semgrep timeout values already read by
  the semgrep-backed extractors:
  - `palace_crypto_semgrep_timeout_s`
  - `palace_error_handling_semgrep_timeout_s`
- Give `error_handling_policy` the same bounded class-level extractor runner
  timeout shape already used by neighboring semgrep-backed extractors, so the
  runner does not kill app-scale rebaseline runs at the generic 300-second
  default.
- Preserve existing extractor behavior by keeping the default at `120` seconds.
- Add unit coverage proving defaults, env overrides, and invalid bounds.
- Restart the native MacBook service with a larger
  `PALACE_ERROR_HANDLING_SEMGREP_TIMEOUT_S` value and rerun only
  `error_handling_policy` for `uw-ios-app`.
- Update the GIM-1638 Paperclip evidence with the rerun result.

## Out Of Scope

- Rewriting `error_handling_policy` batching or semgrep target selection.
- Changing `localization_accessibility` or `crypto_domain_model` logic.
- Re-running the full 112-step rebaseline unless the targeted rerun exposes a
  new graph consistency issue.
- iMac deploy or smoke. The iMac remains a downstream handoff target only if a
  merged code change needs deployment.

## Affected Files And Areas

- `services/palace-mcp/src/palace_mcp/config.py`
- `services/palace-mcp/src/palace_mcp/extractors/error_handling_policy/extractor.py`
- `services/palace-mcp/tests/unit/test_settings_foundation.py`
- `services/palace-mcp/tests/extractors/unit/test_error_handling_policy.py`
- Native operator env / launchd runtime only for the final one-project rerun.
- GIM-1638 Paperclip issue comments for evidence handoff.

## Acceptance Criteria

- `Settings()` exposes both semgrep timeout fields with default `120`.
- `PALACE_CRYPTO_SEMGREP_TIMEOUT_S` and
  `PALACE_ERROR_HANDLING_SEMGREP_TIMEOUT_S` override their respective fields.
- Invalid values below `1` are rejected by Pydantic validation.
- `error_handling_policy` advertises a bounded class-level runner timeout of
  `1800` seconds.
- The targeted unit tests pass.
- Native `palace-mcp` health remains `{"status":"ok","neo4j":"reachable"}`
  after restart.
- Targeted native rerun for `error_handling_policy` on `uw-ios-app` completes
  without the 120-second timeout, or returns a new explicit bounded failure with
  evidence.
- GIM-1638 has a final numeric comment referencing:
  - `/tmp/gim-1638-rebaseline/extractor-results.json`
  - `/tmp/gim-1638-rebaseline/semgrep-rerun-results.json`
  - `/tmp/gim-1638-rebaseline/final-sanity.json`
  - the targeted `error_handling_policy/uw-ios-app` rerun evidence

## Verification Plan

1. In `services/palace-mcp`, run:

   ```bash
   uv run pytest tests/unit/test_settings_foundation.py
   uv run pytest tests/extractors/unit/test_error_handling_policy.py
   uv run ruff check
   uv run ruff format --check
   ```

2. Restart native MacBook launchd service after setting
   `PALACE_ERROR_HANDLING_SEMGREP_TIMEOUT_S` high enough for the app-scale
   semgrep run.

3. Confirm native service health:

   ```bash
   curl -s http://127.0.0.1:8765/healthz
   ```

4. Rerun only:

   ```text
   palace.ingest.run_extractor(name="error_handling_policy", project="uw-ios-app")
   ```

5. Re-query latest ingest outcome and `ErrorFinding` counts for `uw-ios-app`,
   then post Paperclip evidence.

## Open Questions

- What final timeout value should the native `.env` carry after GIM-1638:
  keep the higher value for future full rebaselines, or restore the default
  after the one targeted rerun?
- If `error_handling_policy/uw-ios-app` still exceeds the larger timeout, the
  next slice should be batching/target-pruning rather than further timeout
  inflation.
