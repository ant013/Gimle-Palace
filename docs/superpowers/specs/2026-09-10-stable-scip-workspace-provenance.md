# Stable Wallet SCIP workspace provenance - final design rev1

Base: origin/develop 70520a7260b4d29575c886645cd81f17ab1aff0c.
Branch: fix/stable-scip-workspace-provenance.
Status: ready for explicit user approval; implementation not started.

## Problem and goal

The authorized incremental update built a fresh Stable Wallet SCIP at
307e1bef2753fe2e3ee306100659c0fefffcb6e2 from Wallet.xcworkspace.
Both PREPARATION and CONSUMPTION reject it with package_path_mismatch even
though artifact and repository commits match. The shared validator recognizes
Wallet.xcworkspace only for uw-ios-app and incorrectly requires Package.swift
for stable-wallet-ios. The same bug exists in the deployed and integration code.

Success: the genuine Stable workspace artifact passes both policies and its
incremental symbol ingestion completes with indexed_commit equal to repository
HEAD. The existing UW and SwiftPM validation contracts remain covered by tests.

## Assumptions and scope

- stable-wallet-ios is the registered Xcode app and uses Wallet.xcworkspace,
  confirmed by registry, filesystem, successful build and emitted metadata.
- Extend the existing exact project-slug condition to include stable-wallet-ios.
- Keep the metadata-producer output truthful. Preserve commit, slug, emitter,
  source/destination path, host, digest and durable-baseline checks.
- No general workspace discovery, migrations, index reset, Periphery repair,
  changes to indexing profiles, or arbitrary project exemptions.
- Existing source checkout and index artifacts remain intact.

## Affected files and analog delta matrix

| Area / role | Verified analog | Required delta | Invariants / rejected changes |
| --- | --- | --- | --- |
| Validator, primary contract and implementation | src/palace_mcp/swift_scip_provenance.py:100, existing uw-ios-app condition | Require Wallet.xcworkspace for either uw-ios-app or stable-wallet-ios | All other projects still require Package.swift; all other checks unchanged |
| Tests, supporting | tests/unit/test_swift_scip_provenance.py:96 and :124, real Git/artifact fixtures | Add Stable/UW/SwiftPM acceptance and rejection matrix under both policies | Observe public provenance result; retain stale-commit and wrong-slug rejection |
| Consumer and error boundary | src/palace_mcp/extractors/symbol_index_swift.py:250 | No consumer change expected; verify existing ingest tests | Invalid artifacts must be rejected before graph mutation |

Paths above are relative to services/palace-mcp. Existing xcode emitter writes
the actual workspace basename and needs no change. Existing CLI cannot select
the Stable app emitter automatically; this operation already prepared its SCIP
with the generic Xcode helper, so expanding CLI orchestration is out of scope.

The family has one primary; supporting tests/consumer do not change its design.
No new component is introduced. The rejected broader alternative is trusting any
workspace named in metadata or relabelling the Stable artifact as Package.swift.

## Acceptance criteria and test plan

1. Reproduce Stable package_path_mismatch with the current real artifact before
   editing; this is already reproduced under both policies.
2. Add a regression that creates a real temporary Git repository and SCIP
   metadata for stable-wallet-ios / Wallet.xcworkspace; it fails before the fix
   and passes after it under PREPARATION and CONSUMPTION.
3. Confirm uw-ios-app / Wallet.xcworkspace and a SwiftPM kit / Package.swift pass.
4. Stable with Package.swift, ordinary kit with Wallet.xcworkspace, wrong slug,
   stale commit and wrong emitter remain rejected under both policies.
5. After all other incremental runs finish, deploy only this validated source
   delta onto the existing native serving baseline, restart its launchd job,
   verify health and both provenance policies, and run Stable incremental ingest.
6. Verify symbol_index_swift success, current indexed_commit and SCIP baseline;
   explicitly report optional missing audit inputs separately.

## Verification and rollout

From services/palace-mcp: run the narrow provenance tests first, then affected
symbol-index and CLI provenance tests, followed by repository-required ruff
check/format, mypy src and the full relevant pytest suite. Record unavailable
external-fixture checks honestly. Review diff for unrelated changes.

Commit implementation separately from this spec. Do not replace the serving
checkout with all unrelated origin/develop changes. Apply only the tested fix
commit to the current native serving baseline after the ongoing update queue
has no active runs. Restart only work.ant013.palace-mcp-native, verify /healthz
and MCP health, then ingest the already-created Stable artifact. No Docker or
remote deployment. On startup/validation regression, restore the prior serving
commit and leave Stable pending; do not modify artifact truth to bypass checks.

## Adversarial review

- Freshness/identity: exact current integration files independently checked;
  codebase-memory lacks this symbol, so no indexed-source claim drives design.
- Boundary/trust: adding one known app to the existing condition preserves all
  validation fields. Negative path/type/slug/commit cases test the boundary.
- Smaller alternative: metadata substitution would misrepresent the build;
  broad format relaxation would weaken unrelated projects. Both rejected.
- Lifecycle/rollback: no restart while runs are active; deploy the narrow delta
  and verify health before Stable writes. Index data is not reset.
- Test validity: regression exercises the actual public provenance inspection
  against a real Git HEAD and artifact metadata, not a copied condition.
- Result: ACCEPT. No unresolved high/critical design challenge.

## Open questions

None for the code delta. Explicit approval is required to implement, test and
locally deploy this rev1, then resume Stable incremental indexing. The user also
specified an independent operator policy: when a version branch disappears,
index the next numeric version (+1); this run uses UW version/0.52.
