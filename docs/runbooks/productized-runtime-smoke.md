# Productized Runtime Smoke — Operator Runbook

Repeat the Palace runtime smoke on a clean MacBook (or any macOS developer
machine) without reading chat history. This runbook covers environment setup,
recipe authoring, binding configuration, and the full smoke pipeline.

## Prerequisites

| Requirement | Minimum | How to check |
|---|---|---|
| macOS | 13+ (Ventura) | `sw_vers` |
| Xcode | 15+ with iOS Simulator runtime | `xcodebuild -version` |
| Xcode CLI Tools | installed | `xcode-select -p` |
| Xcode license | accepted | `xcodebuild -checkFirstLaunchStatus` |
| Docker Desktop | running | `docker info --format '{{.ServerVersion}}'` |
| Python | 3.11+ with `uv` | `python3 --version && uv --version` |
| Git | 2.x | `git --version` |
| Neo4j container | running on `localhost:7474` | `curl -sf http://localhost:7474` |
| palace-mcp | running (Streamable HTTP) | `curl -sf -X POST -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' http://localhost:8731/mcp` |

## 1. Start Palace services

```bash
cd services/palace-mcp
docker compose --profile code-graph up -d
```

Verify Neo4j is reachable and palace-mcp tools respond:

```bash
curl -sf http://localhost:7474
curl -sf -X POST \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8731/mcp | python3 -m json.tool | head -20
```

## 2. Understand the recipe/binding split

The smoke system separates **recipes** (versioned, committed, portable) from
**runtime bindings** (machine-local, never committed).

### Recipe (committed YAML)

Recipes live in the repo and contain no absolute paths. Example fields:

| Field | Purpose |
|---|---|
| `slug` | URL-safe project identifier (e.g. `uw-ios-app`) |
| `name` | Human-readable name |
| `language` | Currently `swift` |
| `build_system` | `swift_package`, `xcode_workspace`, or `xcode_project` |
| `source_roots` | First-party source directories (relative) |
| `workspace_package_roots` | Local SPM packages embedded in workspace |
| `dependency_roots` | Third-party/vendored dependency directories |
| `scip_path` | Relative path for SCIP index output (e.g. `scip/index.scip`) |
| `prepare_steps` | Typed steps run before build (e.g. copy config template) |
| `build` | Build configuration (workspace, scheme, destination, arch, signing) |
| `extractors` | Ordered list of extractors to run after SCIP |

### Runtime binding (local, not committed)

Bindings supply absolute paths and service URLs:

| Field | Required | Purpose |
|---|---|---|
| `repo_path` | yes | Absolute path to the checked-out repo |
| `parent_mount` | yes | Host-level parent directory containing all repos (absolute path) |
| `mount_name` | yes | Short identifier for the mount point (e.g. `ios`) |
| `mcp_mount_name` | yes | Short mount name MCP uses inside the container (e.g. `ios`); must match `^[a-z][a-z0-9-]{0,15}$` |
| `mcp_url` | yes | Palace MCP Streamable HTTP endpoint |
| `qodo_cache_path` | no | Path to local Qodo model cache |
| `swiftpm_cache_path` | no | Path to shared SwiftPM cache |
| `docker_compose_override` | no | Path to a Docker Compose override file |

Invariant: `repo_path` must resolve inside `parent_mount`.

> **Note:** `parent_mount` is the host-level absolute path used to compute `relative_path`.
> `mcp_mount_name` is the short name that MCP validates against `^[a-z][a-z0-9-]{0,15}$` — it is what Docker maps as a volume mount name inside the container. These are distinct fields and can differ if the host directory name does not conform to the short-name pattern.

## 3. Recipe examples

### Swift Package (e.g. bitcoin-kit)

```yaml
slug: bitcoin-kit
name: bitcoin-kit-ios
language: swift
build_system: swift_package
source_roots:
  - Sources
dependency_roots:
  - .build
scip_path: scip/index.scip
build:
  scheme: BitcoinKit
  package_resolution: locked
extractors:
  - symbol_index_swift
  - dead_code
```

### Xcode Workspace (e.g. unstoppable-wallet-ios)

```yaml
slug: uw-ios-app
name: unstoppable-wallet-ios
language: swift
build_system: xcode_workspace
source_roots:
  - Unstoppable
workspace_package_roots:
  - packages/WalletCore
dependency_roots:
  - Carthage
  - Pods
  - .build
generated_roots:
  - Unstoppable/Generated
derived_roots:
  - .palace-scip-derived-data
scip_path: scip/index.scip
prepare_steps:
  - type: ensure_config_from_template
    template: Config.template.xcconfig
    destination: Config.xcconfig
build:
  workspace: Wallet.xcworkspace
  scheme: Development
  destination: "generic/platform=iOS Simulator"
  simulator_arch: auto
  derived_data_path: .palace-scip-derived-data
  code_signing_allowed: false
  package_resolution: locked
extractors:
  - symbol_index_swift
  - dead_code
  - embedding_symbol
```

## 4. Write a runtime binding

Create a binding dict in your runner invocation or a local JSON/YAML file
(never commit it). Example for the iMac setup:

```python
from pathlib import Path
from palace_mcp.smoke.runtime_binding import RuntimeBinding

binding = RuntimeBinding(
    repo_path=Path("/Users/Shared/Ios/unstoppable-wallet-ios"),
    parent_mount=Path("/Users/Shared/Ios"),  # host-level absolute path
    mount_name="ios",
    mcp_mount_name="ios",  # short name MCP expects (^[a-z][a-z0-9-]{0,15}$)
    mcp_url="http://localhost:8731/mcp",
    qodo_cache_path=Path("/Users/Shared/models/qodo"),
)
```

## 5. Run the smoke

### From Python

```python
import asyncio
from palace_mcp.smoke.recipe import load_recipe_yaml
from palace_mcp.smoke.runner import SmokeRunner, write_report_json

recipe = load_recipe_yaml(Path("path/to/recipe.yaml"))

runner = SmokeRunner(recipe, binding)
report = asyncio.run(runner.run_smoke())
write_report_json(report, Path("smoke-report.json"))

print("PASSED" if report.passed else "FAILED")
for stage in report.stages:
    print(f"  {stage.stage}: {stage.status.value} ({stage.duration_ms}ms)")
if report.warnings:
    print("Warnings:")
    for w in report.warnings:
        print(f"  - {w}")
```

### Dry-run mode

Validates recipe and binding without mutating runtime state (no SCIP build,
no MCP registration, no extractor execution):

```python
runner = SmokeRunner(recipe, binding, dry_run=True)
report = asyncio.run(runner.run_smoke())
```

Dry-run skips `build_scip`, `register_project`, and `run_extractors` stages.
It still runs `preflight` and `prepare`.

## 6. Pipeline stages

The runner executes stages in this fixed order. A failure in any stage skips
all subsequent stages.

| # | Stage | What it does | Dry-run |
|---|---|---|---|
| 1 | `preflight` | Checks repo exists, SCIP parent writable, MCP reachable | runs |
| 2 | `prepare` | Runs typed prepare steps (e.g. copy config template) | runs |
| 3 | `build_scip` | Builds the project and emits SCIP index | skipped |
| 4 | `register_project` | Calls `palace.memory.register_project` via MCP | skipped |
| 5 | `run_extractors` | Runs each extractor in recipe order via MCP | skipped |
| 6 | `report` | Emits structured JSON report | runs |

## 7. Preflight checks

The preflight module (`palace_mcp.smoke.preflight`) runs 15 checks before
the smoke pipeline. Run it standalone to diagnose environment issues:

```python
import asyncio
from palace_mcp.smoke.preflight import run_preflight

report = asyncio.run(run_preflight(recipe, binding))
for check in report.checks:
    status = "PASS" if check.passed else "FAIL"
    print(f"  [{status}] {check.name}: {check.message or 'ok'}")
if report.actionable_failures:
    print("\nActionable failures:")
    for f in report.actionable_failures:
        print(f"  - {f}")
```

### Checks performed

| Check | What it verifies |
|---|---|
| `repo_path` | Checkout directory exists |
| `scip_path_writable` | SCIP output parent is a writable directory |
| `host_architecture` | Host CPU is arm64 or x86_64; resolves `simulator_arch=auto` |
| `docker_available` | Docker daemon is running (`docker info`) |
| `neo4j_reachable` | Neo4j responds on `localhost:7474` |
| `mcp_tools_list` | Palace MCP responds to `tools/list` JSON-RPC |
| `model_cache_path` | Qodo model cache directory exists (if configured) |
| `local_only_model_mode` | Reports `PALACE_EMBEDDING_LOCAL_ONLY` env status |
| `embedding_limits` | Validates `PALACE_EMBEDDING_LIMIT` env if set |
| `xcode_select` | `xcode-select -p` returns a valid developer directory |
| `xcodebuild_version` | `xcodebuild -version` succeeds |
| `xcode_license` | Xcode license is accepted (`-checkFirstLaunchStatus`) |
| `ios_sdk_runtime` | At least one iOS Simulator runtime is available |
| `swiftpm_cache` | `Package.resolved` exists when `package_resolution=locked` |
| `workspace_absolute_references` | No `absolute:` refs in `.xcworkspacedata` |

## 8. Troubleshooting

### Workspace vs. project confusion

Xcode workspace builds (`build_system: xcode_workspace`) require a
`.xcworkspace` path in `build.workspace`. Using an `.xcodeproj` path or
omitting the workspace field will fail validation. If your project uses a
standalone `.xcodeproj` without a workspace wrapper, use
`build_system: xcode_project` and set `build.project` instead.

### Absolute workspace references

The preflight check `workspace_absolute_references` parses
`contents.xcworkspacedata` inside the `.xcworkspace` bundle. If it finds
`location="absolute:/Users/..."` file references, builds may fail on other
machines. Fix by converting these to `group:` or `container:` references in
Xcode (right-click the reference > Show File Inspector > change Location).

### Missing Config.xcconfig

For `unstoppable-wallet-ios`, the build requires `Config.xcconfig` at the
repo root. The recipe's `ensure_config_from_template` prepare step copies
`Config.template.xcconfig` to `Config.xcconfig` if it is missing. If the
template itself is missing, the prepare step will fail. Verify the template
exists:

```bash
ls -la /path/to/unstoppable-wallet-ios/Config.template.xcconfig
```

### SwiftPM package resolution

When `package_resolution: locked` (the default), the build uses
`-disableAutomaticPackageResolution` and
`-onlyUsePackageVersionsFromResolvedFile`. This requires a valid
`Package.resolved` file. Locations checked:

- `<repo>/Package.resolved` (SPM packages)
- `<repo>/<workspace>/xcshareddata/swiftpm/Package.resolved` (Xcode workspaces)

If neither exists, switch to `package_resolution: automatic` in the recipe
or resolve packages manually first:

```bash
cd /path/to/repo
xcodebuild -resolvePackageDependencies -workspace Wallet.xcworkspace -scheme Development
```

### Xcode host setup

If preflight reports Xcode-related failures:

```bash
# Install/update Xcode CLI tools
xcode-select --install

# Accept license
sudo xcodebuild -license accept

# Verify iOS Simulator runtime is installed
xcrun simctl list runtimes --json | python3 -c "
import json, sys
rts = json.load(sys.stdin).get('runtimes', [])
ios = [r for r in rts if r.get('platform','').lower()=='ios' and r.get('isAvailable')]
print(f'{len(ios)} iOS runtime(s) available')
for r in ios: print(f\"  {r['name']} ({r['version']})\")"
```

If no iOS runtimes are listed, install one via Xcode > Settings > Platforms.

### Simulator architecture

The recipe field `build.simulator_arch` controls the target architecture:

- `auto` (default): resolves from the host machine (`arm64` on Apple Silicon,
  `x86_64` on Intel)
- `arm64` or `x86_64`: explicit override

On Apple Silicon Macs, `auto` resolves to `arm64`. If you get architecture
mismatch errors, verify with:

```bash
uname -m   # should print arm64 on Apple Silicon
```

### Docker resources

If Docker checks fail or builds OOM:

1. Ensure Docker Desktop is running: `docker info`
2. Allocate sufficient memory (8 GB+ recommended for Neo4j + extractors)
3. Verify the Neo4j container is healthy:

```bash
docker compose --profile code-graph ps
docker compose --profile code-graph logs neo4j --tail 20
```

### Bounded embeddings

The `embedding_symbol` extractor generates embeddings for a bounded subset of
symbols. Key environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `PALACE_EMBEDDING_LIMIT` | Max symbols to embed per run | unlimited |
| `PALACE_EMBEDDING_LOCAL_ONLY` | Use only local Qodo model (no API calls) | not set |

The extractor uses deterministic source-first candidate ordering: first-party
project symbols are embedded before dependencies, generated code, and SDK
symbols. Coverage is disclosed in the extractor result.

If embedding fails, verify the Qodo model cache exists and is populated:

```bash
ls -la /path/to/qodo/cache/
```

### SCIP index reuse (Swift Package)

For `swift_package` recipes, the adapter checks if
`<repo_path>/<scip_path>` already exists and has non-zero size. If so, it
skips the build and reuses the existing index. Delete the SCIP file to force
a rebuild:

```bash
rm /path/to/repo/scip/index.scip
```

### MCP connection failures

If the `mcp_tools_list` preflight check or the `register_project` stage
fails:

1. Verify palace-mcp is running:
   ```bash
   curl -sf -X POST \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
     http://localhost:8731/mcp
   ```
2. Check the MCP URL in your runtime binding matches the running service
3. Review palace-mcp logs: `docker compose logs palace-mcp --tail 50`

### Extractor failures

If `run_extractors` reports `ok=false` for an extractor:

- The runner logs the failure but continues running remaining extractors
- Check the extractor result's `error_code` and `message` fields in the
  JSON report
- Common causes: Neo4j connection timeout, missing SCIP index, project
  not registered

## 9. Report format

The runner produces a JSON report with this structure:

```json
{
  "recipe_slug": "uw-ios-app",
  "mode": "smoke",
  "dry_run": false,
  "started_at": "2026-05-25T10:00:00+00:00",
  "finished_at": "2026-05-25T10:05:30+00:00",
  "stages": [
    {
      "stage": "preflight",
      "status": "passed",
      "duration_ms": 1200,
      "error": null,
      "details": { "repo_path_exists": true, "mcp_reachable": true }
    }
  ],
  "passed": true,
  "warnings": []
}
```

Stage status values: `passed`, `failed`, `skipped`.

## 10. End-to-end example: bitcoin-kit on a MacBook

```bash
# 1. Start services
cd /path/to/Gimle-Palace/services/palace-mcp
docker compose --profile code-graph up -d

# 2. Verify services
curl -sf http://localhost:7474 && echo "Neo4j OK"
curl -sf -X POST -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  http://localhost:8731/mcp > /dev/null && echo "MCP OK"

# 3. Run smoke from Python
cd /path/to/Gimle-Palace
python3 -c "
import asyncio
from pathlib import Path
from palace_mcp.smoke.recipe import load_recipe_yaml
from palace_mcp.smoke.runtime_binding import RuntimeBinding
from palace_mcp.smoke.runner import SmokeRunner, write_report_json

recipe = load_recipe_yaml(
    Path('services/palace-mcp/tests/smoke/fixtures/swift_package_recipe.yaml')
)
binding = RuntimeBinding(
    repo_path=Path('/Users/Shared/Ios/bitcoin-kit-ios'),
    parent_mount=Path('/Users/Shared/Ios'),  # host-level absolute path
    mount_name='ios',
    mcp_mount_name='ios',  # short name MCP expects (^[a-z][a-z0-9-]{0,15}$)
    mcp_url='http://localhost:8731/mcp',
)

runner = SmokeRunner(recipe, binding)
report = asyncio.run(runner.run_smoke())
write_report_json(report, Path('bitcoin-kit-smoke-report.json'))

print('PASSED' if report.passed else 'FAILED')
for s in report.stages:
    print(f'  {s.stage}: {s.status.value} ({s.duration_ms}ms)')
"
```

## 11. Local artifacts (gitignored)

These files are created during smoke and should not be committed:

| Artifact | Location | Purpose |
|---|---|---|
| `Config.xcconfig` | repo root (UW only) | Copied from template by prepare step |
| `.palace-scip-derived-data/` | repo root | Isolated Xcode DerivedData |
| `scip/index.scip` | repo root | SCIP index artifact |
| `smoke-report.json` | operator-chosen | Structured smoke result |
| Docker volumes | system | Neo4j data, model caches |
