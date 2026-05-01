# Slice 3 — iOS Swift extractor (`symbol_index_swift`) Implementation Plan (rev1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `symbol_index_swift` extractor + `uw-ios-mini-project` fixture to palace-mcp. Supports indexing Swift code via Apple-native IndexStoreDB → SwiftSCIPIndex (community) → SCIP. Phase 4.1 split: Track A (fixture-based on iMac, hard merge gate) + Track B (real UW-ios on operator's dev Mac, deferred-not-blocked).

**Architecture:** New extractor `symbol_index_swift` derived from `symbol_index_java` runtime (~150-200 LOC; not pure copy-paste — vendor noise filters and primary-language differ for Swift). Lang-agnostic 101a foundation reused unchanged. Parser gets Swift support added (`_SCIP_LANGUAGE_MAP` + `.swift` extension fallback) — small parser-only commit can merge first. Hybrid SPM + Xcode-app fixture (~30 files) exercises Swift core + SwiftUI + macros + Codable + UIKit interop. Build host = operator's dev Mac (Apple Silicon, current Xcode); runtime host = iMac (Intel x86_64, macOS 13, palace-mcp container only).

**Tech Stack:** Python 3.12 (palace-mcp), Swift 5.9+ (fixture + UW-ios), Xcode 15+, XcodeGen, IndexStoreDB (Apple-native), SwiftSCIPIndex (community converter), scip-java's protobuf format (Sourcegraph-compatible SCIP), pytest, testcontainers/compose-reuse Neo4j, Tantivy.

**Predecessor SHA:** `6492561` (GIM-127 Slice 1 Android merged 2026-04-30).
**Spec:** `docs/superpowers/specs/2026-04-30-ios-swift-extractor.md` (rev2).
**Companion (NOT a blocker):** GIM-126 (`palace.code.find_references` lang-agnostic fix) on `feature/GIM-126-find-references-any-extractor`. AC#7 evidence script uses Tantivy direct lookup until GIM-126 merges (Slice 1 pattern).

---

## Phase 1.0: Spike — toolchain validation + parser support (Board/operator, MANDATORY BEFORE PE Phase 2)

> **Plan-first / GIM-114 discipline gate.** Phase 1.0 is **NOT a paper exercise** — it's hands-on dev-Mac work that empirically determines the slice's viability. Output: REGEN.md draft with locked oracle + AC#4 branch decision + Swift-parser changes (small commit, can merge first to develop) + go/no-go signal on PE Phase 2.
>
> All Phase 1.0 work happens on operator's dev Mac (the host running this Claude session). iMac is NOT the build host — see spec rev2 §"Operator host setup".

### Task 0a — Pin SwiftSCIPIndex SHA + capture dev-Mac toolchain

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (draft sections; full oracle filled later in Task 0h)

- [ ] **Step 1: Install SwiftSCIPIndex on dev Mac**

```bash
mkdir -p ~/.local/opt
cd ~/.local/opt
test -d SwiftSCIPIndex || git clone https://github.com/Fostonger/SwiftSCIPIndex.git
cd SwiftSCIPIndex
SWIFT_SCIP_SHA=$(git rev-parse HEAD)
echo "Pinned SwiftSCIPIndex SHA: $SWIFT_SCIP_SHA"
swift build -c release
ls -la .build/release/SwiftSCIPIndex
```

Expected: build succeeds, binary at `.build/release/SwiftSCIPIndex`.

- [ ] **Step 2: Symlink into PATH**

```bash
mkdir -p ~/.local/bin
ln -sfn ~/.local/opt/SwiftSCIPIndex/.build/release/SwiftSCIPIndex ~/.local/bin/SwiftSCIPIndex
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshenv
SwiftSCIPIndex --help 2>&1 | head -5
```

Expected: prints help / usage.

- [ ] **Step 3: Capture dev Mac toolchain versions**

```bash
echo "Dev Mac toolchain snapshot ($(date -u +%FT%TZ)):"
sw_vers -productVersion
xcode-select -p
xcodebuild -version
swift --version
which xcodegen || brew install xcodegen
xcodegen --version
SwiftSCIPIndex --version 2>&1 | head -3 || echo "  SwiftSCIPIndex SHA: $SWIFT_SCIP_SHA"
```

Capture output for REGEN.md (next step).

- [ ] **Step 4: Initialize REGEN.md draft**

Write `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` with the following sections (oracle table values filled later in Task 0h):

```markdown
# uw-ios-mini-project — Fixture Regen Instructions

## Source

- **Repository (vendored 3 files only):** https://github.com/horizontalsystems/unstoppable-wallet-ios
- **License:** MIT
- **Phase 1.0 spike SHA:** <captured from `git rev-parse HEAD` on first clone>

## Toolchain (dev Mac, Phase 1.0 captured 2026-04-30)

| Component | Version |
|---|---|
| macOS | <sw_vers output> |
| Xcode (xcode-select) | <xcode-select -p output> |
| xcodebuild | <xcodebuild -version output> |
| Swift | <swift --version output> |
| XcodeGen | <xcodegen --version output> |
| SwiftSCIPIndex | <SHA: $SWIFT_SCIP_SHA> |

## iMac runtime (production palace-mcp ingestion only — NO build)

iMac is Intel x86_64 + macOS 13 + Xcode ≤Swift 5.8. CANNOT build modern Swift code (UW master uses Swift 5.9+). Receives pre-generated `.scip` files from dev Mac for ingestion.

## Vendoring strategy (per spec rev2)

- 3 of ~30 files truly vendored verbatim: `String+Hash.swift`, `ColorPalette.swift`, `DateFormatters.swift`
- ~27 synthesized in UW-ios idiom style (Codable, @Observable, SwiftUI views, UIKit interop)

## Manual oracle table (Phase 1.0 — fill BEFORE PE Phase 2)

> PE Phase 2 BLOCKED until oracle filled and AC#4 Branch locked.

| Metric | Value | Notes |
|---|---|---|
| N_TARGETS | 2 | UwMiniCore SPM package + UwMiniApp Xcode app |
| N_DOCUMENTS_TOTAL | <TBD-Phase1.0> | len(index.documents) |
| N_DEFS_TOTAL | <TBD> | source-defined |
| N_USES_TOTAL | <TBD> | use occurrences |
| N_OCCURRENCES_TOTAL | <TBD> | DEF + USE |
| N_TANTIVY_DOCS | <TBD> | post-dedup unique (used in integration test) |
| N_DEFS_CODABLE_GENERATED | <TBD or 0 if Branch B-2> | conditional on AC#4 outcome |
| N_DEFS_OBSERVABLE_GENERATED | <TBD or 0 if Branch B-2> | conditional |
| N_DEFS_PROPWRAPPER_PROJECTED | <TBD or 0 if Branch B-2> | conditional |
| AC#4 Branch | <A / B-1 / B-2> | locked outcome |
| document.language exact string from SwiftSCIPIndex | <e.g., "swift" or "Swift"> | drives `_SCIP_LANGUAGE_MAP` key |
| Vendor-noise paths | <enumerated list> | drives `symbol_index_swift` filter rules |
```

- [ ] **Step 5: Commit Phase 1.0 stub REGEN.md (no oracle values yet)**

```bash
cd /Users/ant013/Android/Gimle-Palace
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 stub REGEN.md (toolchain captured, oracle TBD)"
```

---

### Task 0b — Generate spike Swift project + emit spike.scip

> Smaller scope than full fixture. Just enough Swift code to verify SwiftSCIPIndex behavior on Phase 1.0 unknowns.

**Files:**
- Create: `/tmp/uw-ios-spike/` (scratch, NOT in repo) — minimal Swift project with Codable + @Observable + @State

- [ ] **Step 1: Create scratch SPM package + sample sources**

```bash
mkdir -p /tmp/uw-ios-spike/Sources/UwSpike
cd /tmp/uw-ios-spike
cat > Package.swift <<'EOF'
// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "UwSpike",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "UwSpike", targets: ["UwSpike"])],
    targets: [.target(name: "UwSpike")]
)
EOF
cat > Sources/UwSpike/Wallet.swift <<'EOF'
import Foundation
import Observation
import SwiftUI

struct Wallet: Codable {
    let id: Int
    let address: String
    let balance: Decimal
}

@Observable
final class WalletStore {
    var wallets: [Wallet] = []
    var selected: Wallet?
}

struct ContentView: View {
    @State private var counter: Int = 0

    var body: some View {
        VStack {
            Text("Count: \(counter)")
            Button("Inc") { counter += 1 }
        }
    }
}
EOF
```

- [ ] **Step 2: Build + extract IndexStoreDB**

```bash
cd /tmp/uw-ios-spike
swift build -Xswiftc -index-store-path -Xswiftc .build/index-store
ls -la .build/index-store/v5/units/ | head -5
```

Expected: directory created, has `*.unit` files. (`-index-store-path` flag tells swiftc to emit IndexStoreDB at given path.)

- [ ] **Step 3: Run SwiftSCIPIndex on the spike**

```bash
SwiftSCIPIndex --derived-data .build/index-store --output spike.scip 2>&1 | tee /tmp/uw-ios-spike/spike-run.log
ls -la spike.scip
```

Expected: `spike.scip` is non-empty binary. If SwiftSCIPIndex requires Xcode DerivedData specifically (not SPM `index-store`), adapt: build via `xcodebuild -workspace ... -scheme UwSpike -derivedDataPath .build/derived-data` instead. Document actual working invocation in REGEN.md.

- [ ] **Step 4: Verify spike.scip parses via palace-mcp's parser**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import Language, SymbolKind

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
print(f'Documents: {len(idx.documents)}')
for d in idx.documents:
    print(f'  language={d.language!r}  path={d.relative_path}')
occs = list(iter_scip_occurrences(idx, commit_sha='spike'))
print(f'Occurrences: {len(occs)}')
unknown = [o for o in occs if o.language == Language.UNKNOWN]
print(f'  UNKNOWN language: {len(unknown)}/{len(occs)} (BEFORE adding Swift to parser — expected high)')
"
```

Expected: at least 1 document for `Wallet.swift`. Capture exact `language=` string value (e.g., `"swift"` or `"Swift"` or empty) — this is the key for `_SCIP_LANGUAGE_MAP` in Task 0d.

- [ ] **Step 5: Save spike.scip + log to fixture for reference (optional)**

```bash
mkdir -p /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.phase1-artifacts
cp /tmp/uw-ios-spike/spike.scip /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.phase1-artifacts/spike.scip
cp /tmp/uw-ios-spike/spike-run.log /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.phase1-artifacts/spike-run.log
```

(Add `.phase1-artifacts/` to fixture's `.gitignore`. These are debugging aids, not committed.)

- [ ] **Step 6: No commit yet (Phase 1.0 in progress)**

---

### Task 0c — Verify `document.language` actual values

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (record findings)

- [ ] **Step 1: Inspect each document's language string + content**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file
idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
for d in idx.documents:
    print(f'language={d.language!r:20}  occs={len(d.occurrences)}  path={d.relative_path}')
"
```

Capture: actual `document.language` value SwiftSCIPIndex emits (e.g., empty string `''`, `'swift'`, `'Swift'`, `'swiftc'`, etc.).

- [ ] **Step 2: Document in REGEN.md "Toolchain" section**

Edit `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` — fill the row "document.language exact string from SwiftSCIPIndex" with captured value.

- [ ] **Step 3: Commit Phase 1.0 finding**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 — capture SwiftSCIPIndex document.language string"
```

---

### Task 0d — Add Swift to scip_parser (small standalone commit)

> Can merge to develop independently before main Slice 3 PR (smallest risk; benefits any Swift work).

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py:209` (`_SCIP_LANGUAGE_MAP`)
- Modify: `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py:230` (`_language_from_path`)
- Test: `services/palace-mcp/tests/extractors/unit/test_scip_parser_language.py` (add Swift cases)

- [ ] **Step 1: Read current parser**

```bash
sed -n '205,245p' services/palace-mcp/src/palace_mcp/extractors/scip_parser.py
```

Confirms current state: no `swift` key in `_SCIP_LANGUAGE_MAP`, no `.swift` in `_language_from_path`.

- [ ] **Step 2: Write failing test (TDD)**

Edit `services/palace-mcp/tests/extractors/unit/test_scip_parser_language.py` (or appropriate parser test file):

```python
# Add at end of file:

def test_language_map_recognizes_swift() -> None:
    """SwiftSCIPIndex emits document.language=<actual-string-from-Task-0c>; parser must map to Language.SWIFT."""
    from palace_mcp.extractors.scip_parser import _SCIP_LANGUAGE_MAP
    from palace_mcp.extractors.foundation.models import Language
    # Replace "swift" below with actual string captured in Task 0c
    assert _SCIP_LANGUAGE_MAP.get("swift") == Language.SWIFT


def test_language_from_path_recognizes_swift_extension() -> None:
    """`.swift` and `.swiftinterface` files map to Language.SWIFT via path fallback."""
    from palace_mcp.extractors.scip_parser import _language_from_path
    from palace_mcp.extractors.foundation.models import Language
    assert _language_from_path("Sources/UwSpike/Wallet.swift") == Language.SWIFT
    assert _language_from_path("ios-build/.swiftinterface/Module.swiftinterface") == Language.SWIFT
```

- [ ] **Step 3: Run failing test to verify**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser_language.py -v -k "swift" 2>&1 | tail -10
```

Expected: 2 FAILED (KeyError on map; UNKNOWN return on path).

- [ ] **Step 4: Apply parser edits**

Edit `services/palace-mcp/src/palace_mcp/extractors/scip_parser.py`:

In `_SCIP_LANGUAGE_MAP` (around line 209) — add the new key. Replace `"swift"` if Task 0c captured a different string:

```python
_SCIP_LANGUAGE_MAP: dict[str, Language] = {
    "python": Language.PYTHON,
    "typescript": Language.TYPESCRIPT,
    "TypeScriptReact": Language.TYPESCRIPT,
    "javascript": Language.JAVASCRIPT,
    "JavaScriptReact": Language.JAVASCRIPT,
    "java": Language.JAVA,
    "kotlin": Language.KOTLIN,
    "solidity": Language.SOLIDITY,
    "swift": Language.SWIFT,  # NEW (GIM-128 Phase 1.0)
}
```

In `_language_from_path` (around line 230) — add `.swift` and `.swiftinterface` cases. Add BEFORE the final `return Language.UNKNOWN`:

```python
    if relative_path.endswith((".swift", ".swiftinterface")):
        return Language.SWIFT
    return Language.UNKNOWN
```

- [ ] **Step 5: Run tests — verify pass**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser_language.py -v -k "swift" 2>&1 | tail -10
```

Expected: 2 PASSED.

- [ ] **Step 6: Run full parser test file (regression check)**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_scip_parser_language.py -v 2>&1 | tail -10
```

Expected: all tests pass (no regression on existing language entries).

- [ ] **Step 7: ruff format**

```bash
cd services/palace-mcp && uv run ruff format src/palace_mcp/extractors/scip_parser.py tests/extractors/unit/test_scip_parser_language.py 2>&1 | tail -3
```

- [ ] **Step 8: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/scip_parser.py services/palace-mcp/tests/extractors/unit/test_scip_parser_language.py
git commit -m "feat(GIM-128): scip_parser — recognize Swift via _SCIP_LANGUAGE_MAP + .swift path fallback

Phase 1.0 spike finding: SwiftSCIPIndex emits document.language='swift' (or
captured value from REGEN.md). Add to map + add .swift/.swiftinterface
extension fallback. Language.SWIFT enum existed at models.py:32 — no
addition needed there.

Required by Slice 3 PE Phase 2 (Tasks 1-15)."
```

- [ ] **Step 9: (Optional) Verify spike.scip now parses with Swift language**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python -c "
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import Language

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='spike-after-parser'))
swift = [o for o in occs if o.language == Language.SWIFT]
print(f'SWIFT occurrences: {len(swift)}/{len(occs)} (after parser fix)')
"
```

Expected: significantly more SWIFT-classified occurrences vs Task 0b Step 4 baseline.

---

### Task 0e — AC#4 generated-code visibility check (lock branch)

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (record AC#4 Branch decision)

- [ ] **Step 1: Codable synthesis check**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import SymbolKind

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='ac4-codable'))
defs = [o for o in occs if o.kind == SymbolKind.DEF]

# Codable: should see Wallet#init(from:) and Wallet#encode(to:)
codable = [o for o in defs if 'Wallet' in o.symbol_qualified_name and ('init(from:)' in o.symbol_qualified_name or 'encode(to:)' in o.symbol_qualified_name)]
print(f'Codable synthesis DEFs: {len(codable)}')
for o in codable[:5]:
    print(f'  {o.symbol_qualified_name}')
PYEOF
```

Capture: count and sample qualified_names. If non-zero → Codable visible (target a passes).

- [ ] **Step 2: `@Observable` macro check**

```bash
uv run python <<'PYEOF'
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import SymbolKind

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='ac4-observable'))
defs = [o for o in occs if o.kind == SymbolKind.DEF]

# @Observable: should see _$observationRegistrar, withMutation, access
observable = [o for o in defs if any(x in o.symbol_qualified_name for x in ['_$observationRegistrar', 'withMutation', 'access('])]
print(f'@Observable macro DEFs: {len(observable)}')
for o in observable[:5]:
    print(f'  {o.symbol_qualified_name}')
PYEOF
```

Capture count + samples.

- [ ] **Step 3: Property wrapper `$`-projection check**

```bash
uv run python <<'PYEOF'
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import SymbolKind

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='ac4-propwrapper'))
defs = [o for o in occs if o.kind == SymbolKind.DEF]

# @State property wrapper $-projection: _counter and $counter
projected = [o for o in defs if o.symbol_qualified_name.endswith('._counter') or '$counter' in o.symbol_qualified_name]
print(f'Property wrapper $-projection DEFs: {len(projected)}')
for o in projected[:5]:
    print(f'  {o.symbol_qualified_name}')
PYEOF
```

Capture count + samples.

- [ ] **Step 4: Decide AC#4 Branch**

Based on Steps 1-3 results:

- **All 3 visible** → Branch **A**. AC#4 hard, all 3 generated-code targets must appear in main fixture.
- **Some visible, some not** → Try Branch B-1 workarounds:
  - Add `-Xfrontend -emit-symbol-graph` to `swift build`
  - Try alternate SwiftSCIPIndex flags
  - Re-run Steps 1-3
  - If Branch B-1 fixes it → record workaround in REGEN.md
- **None visible after workarounds** → Branch **B-2**. AC#4 narrows to "Swift source-level symbols indexed correctly; generated-code visibility tracked as followup issue".

- [ ] **Step 5: Record decision in REGEN.md**

Edit `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` — fill row "AC#4 Branch" with `A`, `B-1`, or `B-2` + paragraph explaining decision rationale + sample qualified_names from spike.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 — lock AC#4 branch (<A/B-1/B-2>) based on spike.scip generated-code visibility"
```

---

### Task 0f — FQN format check vs GIM-105 expectations

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (record FQN format)

- [ ] **Step 1: Sample 5 Swift symbols from spike.scip**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import SymbolKind

idx = parse_scip_file(Path('/tmp/uw-ios-spike/spike.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='fqn-check'))
defs = [o for o in occs if o.kind == SymbolKind.DEF]
print('=== Sample 5 DEF qualified_names ===')
for o in defs[:5]:
    print(f'  {o.symbol_qualified_name!r}')
PYEOF
```

- [ ] **Step 2: Compare against GIM-105 rev2 §Per-language action map — Swift expectation**

GIM-105 rev2 expects:
- Manager token: `apple` (proxy for SwiftPM/Xcode)
- Package format: `<bundle-id>` or `<module-name>`
- Version token: `.` placeholder (Variant B strip)
- Descriptor chain: Type `#`, method `().`, property `.`
- Qualified_name: `<module>:<descriptor-chain>`

Check: do sample qualified_names match this shape?

- [ ] **Step 3: Document in REGEN.md**

Edit REGEN.md, add section:

```markdown
## FQN format finding (Phase 1.0)

Sample DEF qualified_names from spike.scip:
- <paste 5 samples>

Comparison to GIM-105 rev2 expectations: <match | divergence>

If divergence: <option (a) accept actual + cross-reference update, or (b) post-process in extractor>
```

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 — verify Swift FQN format vs GIM-105 expectations"
```

---

### Task 0g — Path-noise enumeration on real UW-ios

> This is the larger Phase 1.0 task — clone real UW-ios, build it on dev Mac, see what paths SwiftSCIPIndex emits.

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (record vendor-noise paths)

- [ ] **Step 1: Clone UW-ios on dev Mac (separate from iMac clone)**

```bash
mkdir -p ~/iOS-projects
cd ~/iOS-projects
test -d unstoppable-wallet-ios || git clone https://github.com/horizontalsystems/unstoppable-wallet-ios.git
cd unstoppable-wallet-ios
git rev-parse HEAD
```

- [ ] **Step 2: Build UW-ios on dev Mac**

```bash
xcodebuild build -workspace UnstoppableWallet/UnstoppableWallet.xcworkspace \
                -scheme UnstoppableWallet \
                -destination "generic/platform=iOS Simulator" 2>&1 | tail -10
```

Expected: build succeeds (operator's dev Mac has compatible Xcode).

- [ ] **Step 3: Run SwiftSCIPIndex on UW-ios**

```bash
DERIVED=$(ls -d ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* 2>/dev/null | head -1)
echo "DerivedData: $DERIVED"
SwiftSCIPIndex --derived-data "$DERIVED" --output uw-ios.scip 2>&1 | tail -5
ls -la uw-ios.scip
```

Expected: `uw-ios.scip` non-empty (likely 1-5 MB given 1704 .swift files).

- [ ] **Step 4: Enumerate path prefixes**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from pathlib import Path
from collections import Counter
from palace_mcp.extractors.scip_parser import parse_scip_file

idx = parse_scip_file(Path.home() / 'iOS-projects/unstoppable-wallet-ios/uw-ios.scip')
prefixes = Counter()
for d in idx.documents:
    parts = d.relative_path.split('/')
    prefix = '/'.join(parts[:2]) if len(parts) >= 2 else parts[0]
    prefixes[prefix] += 1

print('=== Top 20 path prefixes by document count ===')
for p, cnt in prefixes.most_common(20):
    print(f'  {cnt:>6}  {p}')
PYEOF
```

Capture top prefixes — typically expect:
- `UnstoppableWallet/UnstoppableWallet/...` (project source — KEEP)
- `<DerivedData>/.../Index.noindex/...` (intermediate — varies; usually noise)
- `.build/...` (SPM build artifacts — VENDOR/noise)
- `.swiftpm/...` (SPM caches — noise)
- `Pods/...` (CocoaPods deps — VENDOR)
- `Carthage/...` (Carthage deps — VENDOR)
- `SourcePackages/...` (SPM checkouts — VENDOR)
- `~/Library/...` (system frameworks — VENDOR)

- [ ] **Step 5: Classify each prefix**

For each prefix from Step 4, decide PROJECT (keep) or VENDOR (filter):

```
| Prefix | Documents | Classification |
|---|---|---|
| UnstoppableWallet/UnstoppableWallet | <count> | PROJECT |
| Pods/<lib> | <count> | VENDOR |
| ... | ... | ... |
```

- [ ] **Step 6: Document in REGEN.md**

Edit `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` — add section:

```markdown
## Vendor-noise paths (Phase 1.0 spike on real UW-ios)

The following path prefixes are filtered as VENDOR by `symbol_index_swift`:

- `Pods/`
- `Carthage/`
- `SourcePackages/`
- `.build/`
- `.swiftpm/`
- `~/Library/Developer/Xcode/DerivedData/`
- (other prefixes per real UW-ios scip — see "Phase 1.0 enumeration" below)

PROJECT prefixes (kept):
- `UnstoppableWallet/UnstoppableWallet/`
- (other project-internal prefixes)

The filter is implemented in `symbol_index_swift.py` via `_is_vendor(file_path)` — symmetric to `symbol_index_java._is_vendor()`.
```

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 — enumerate UW-ios path noise (vendor filter rules)"
```

---

### Task 0h — Lock REGEN.md final draft + go/no-go signal

**Files:**
- Update: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` (final review pass)

- [ ] **Step 1: Verify all sections of REGEN.md are filled**

```bash
grep -E "<TBD|<.*>" services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md | head -10
```

Expected: empty output. All `<TBD>` placeholders should be replaced with actual values.

- [ ] **Step 2: Verify go/no-go on PE Phase 2**

| Check | Result |
|---|---|
| SwiftSCIPIndex installs + runs (Task 0a) | PASS / FAIL |
| spike.scip produced + parses (Task 0b) | PASS / FAIL |
| document.language string captured (Task 0c) | PASS / FAIL |
| Swift parser support added (Task 0d) — separate commit | PASS / FAIL |
| AC#4 branch locked (Task 0e) | A / B-1 / B-2 |
| FQN format verified (Task 0f) | PASS / NEEDS POSTPROCESS |
| Vendor-noise paths enumerated (Task 0g) | PASS / FAIL |

If all PASS → **GO** for PE Phase 2 (Tasks 1-15).
If any FAIL → **NO-GO**, escalate to spec rev3.

- [ ] **Step 3: Commit final REGEN.md state**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "chore(GIM-128): Phase 1.0 — REGEN.md final state, GO/NO-GO signal locked"
```

- [ ] **Step 4: Push Phase 1.0 commits to FB**

```bash
cd /Users/ant013/Android/Gimle-Palace
git push origin feature/GIM-128-ios-swift-extractor
```

- [ ] **Step 5: Post Phase 1.0 outcome on GIM-128 paperclip**

Comment summary on GIM-128:
- Toolchain captured (versions in REGEN.md)
- AC#4 branch locked (A/B-1/B-2)
- Swift parser support landed in commit `<hash>`
- Go/no-go: GO → PE Phase 2 starts on Tasks 1-15
- Vendor-noise paths enumerated

---

## Phase 2: PE TDD implementation

### Task 1: Pre-flight verify Phase 1.0 outputs

**Files:**
- Read: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md`

- [ ] **Step 1: Confirm Phase 1.0 outputs present**

```bash
cd /Users/ant013/Android/Gimle-Palace
test -f services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md && echo "OK: REGEN.md present"
```

- [ ] **Step 2: Verify oracle table fields filled (no `<TBD>`)**

```bash
grep -c "<TBD>" services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
```

Expected: `0`. If non-zero → Phase 1.0 incomplete; STOP and escalate.

- [ ] **Step 3: Verify AC#4 Branch is locked**

```bash
grep -E "AC#4 Branch.*[: ]+(A|B-1|B-2)" services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
```

Expected: one match with concrete `A`, `B-1`, or `B-2`. If empty → STOP.

- [ ] **Step 4: Verify Swift parser support landed**

```bash
grep "swift" services/palace-mcp/src/palace_mcp/extractors/scip_parser.py | head -3
```

Expected: at least 2 matches (one in `_SCIP_LANGUAGE_MAP`, one in `_language_from_path`).

- [ ] **Step 5: Capture branch locked + lang-string for use in subsequent tasks**

Note: `LOCKED_BRANCH=$(grep -oE 'AC#4 Branch[: ]+[AB]-?[12]?' REGEN.md | grep -oE '[AB]-?[12]?')`. Use in Task 10 to gate skip-or-assert decisions.

- [ ] **Step 6: No commit — pre-flight only.**

---

### Task 2: Vendor fixture root configs (LICENSE, project.yml, regen.sh, .gitignore)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/LICENSE`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/project.yml`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/regen.sh`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.gitignore`

- [ ] **Step 1: Vendor LICENSE from UW-ios**

```bash
cp ~/iOS-projects/unstoppable-wallet-ios/LICENSE \
   /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/LICENSE
```

- [ ] **Step 2: Write `project.yml` (XcodeGen config)**

Create `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/project.yml`:

```yaml
name: UwMiniApp
options:
  bundleIdPrefix: io.horizontalsystems.uwmini
  deploymentTarget:
    iOS: "17.0"
  developmentLanguage: en
  createIntermediateGroups: true

settings:
  base:
    SWIFT_VERSION: "5.9"
    IPHONEOS_DEPLOYMENT_TARGET: "17.0"
    ENABLE_USER_SCRIPT_SANDBOXING: "NO"

packages:
  UwMiniCore:
    path: UwMiniCore

targets:
  UwMiniApp:
    type: application
    platform: iOS
    sources:
      - path: UwMiniApp/Sources
    info:
      path: UwMiniApp/Info.plist
      properties:
        UILaunchStoryboardName: ""
        UIApplicationSupportsMultipleScenes: false
    dependencies:
      - package: UwMiniCore
```

- [ ] **Step 3: Write `regen.sh`**

Create `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/regen.sh`:

```bash
#!/usr/bin/env bash
# Regenerate scip/index.scip for uw-ios-mini-project.
# Build host: dev Mac (Apple Silicon, Xcode ≥15). NOT iMac (Intel + macOS 13).
set -euo pipefail

cd "$(dirname "$0")"

# Guard: must be on capable Mac
if ! command -v xcodebuild >/dev/null; then
    echo "ERROR: xcodebuild not found. Need full Xcode.app on dev Mac."
    exit 1
fi
if ! command -v xcodegen >/dev/null; then
    echo "ERROR: xcodegen not found. Run: brew install xcodegen"
    exit 1
fi
if ! command -v SwiftSCIPIndex >/dev/null; then
    echo "ERROR: SwiftSCIPIndex not found in PATH. See REGEN.md toolchain setup."
    exit 1
fi

echo "==> 1/4 Generate Xcode project from project.yml"
xcodegen generate

echo "==> 2/4 Build (xcodebuild + IndexStoreDB)"
xcodebuild build -project UwMiniApp.xcodeproj \
                 -scheme UwMiniApp \
                 -destination "generic/platform=iOS Simulator" \
                 -derivedDataPath ./.derived 2>&1 | tail -5

echo "==> 3/4 Convert IndexStoreDB → SCIP"
mkdir -p scip
SwiftSCIPIndex --derived-data ./.derived --output ./scip/index.scip

echo "==> 4/4 Verify"
test -s scip/index.scip || { echo "ERROR: index.scip empty"; exit 1; }
echo "  size: $(wc -c < scip/index.scip) bytes"
```

```bash
chmod +x services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/regen.sh
```

- [ ] **Step 4: Write `.gitignore`**

Create `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/.gitignore`:

```
# Build artifacts (NOT committed)
.derived/
.build/
.swiftpm/
DerivedData/
.phase1-artifacts/

# XcodeGen-generated (NOT committed; regenerated)
UwMiniApp.xcodeproj/
UwMiniApp.xcworkspace/

# Local config
local.properties
```

- [ ] **Step 5: Commit root configs**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/{LICENSE,project.yml,regen.sh,.gitignore}
git commit -m "chore(GIM-128): fixture root configs (LICENSE, project.yml, regen.sh, .gitignore)"
```

---

### Task 3: Vendor 3 standalone Swift files from UW-ios

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Util/String+Hash.swift` (vendored)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/ColorPalette.swift` (vendored)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Legacy/DateFormatters.swift` (vendored)

- [ ] **Step 1: Identify exact UW-ios source paths**

```bash
cd ~/iOS-projects/unstoppable-wallet-ios
find . -name "*.swift" -path "*+Hash*" -o -name "*ColorPalette*" -o -name "*DateFormatters*" 2>/dev/null | head -10
```

Document candidates. If exact match not found, pick closest standalone files (Foundation/SwiftUI imports only, no UW-internal deps).

- [ ] **Step 2: Vendor String+Hash.swift**

```bash
mkdir -p /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Util
# Replace path with actual found in Step 1
cp ~/iOS-projects/unstoppable-wallet-ios/<actual-path>/String+Hash.swift \
   /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Util/String+Hash.swift
```

Add header comment AT THE TOP of the file:

```swift
// VENDORED VERBATIM from horizontalsystems/unstoppable-wallet-ios@<UW-ios-SHA-from-REGEN.md>
// Original: <actual-source-path>
```

- [ ] **Step 3: Verify imports are standalone (only Foundation)**

```bash
grep "^import " /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Util/String+Hash.swift
```

Expected: only `import Foundation`. If imports any UW-internal module → strip and replace, OR pick different file.

- [ ] **Step 4: Repeat Steps 2-3 for ColorPalette.swift (in UwMiniApp/Sources/Views)**

```bash
mkdir -p /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views
cp ~/iOS-projects/unstoppable-wallet-ios/<actual-path>/ColorPalette.swift \
   /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/ColorPalette.swift
# Add VENDORED header comment as in Step 2
grep "^import " <vendored-file>
```

Expected: only `import SwiftUI`.

- [ ] **Step 5: Repeat for DateFormatters.swift (UwMiniApp/Sources/Legacy)**

```bash
mkdir -p /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Legacy
cp ~/iOS-projects/unstoppable-wallet-ios/<actual-path>/DateFormatters.swift \
   /Users/ant013/Android/Gimle-Palace/services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Legacy/DateFormatters.swift
# Add VENDORED header comment
grep "^import " <vendored-file>
```

Expected: only `import Foundation`.

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Util/String+Hash.swift
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/ColorPalette.swift
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Legacy/DateFormatters.swift
git commit -m "chore(GIM-128): vendor 3 standalone Swift files from UW-ios (String+Hash, ColorPalette, DateFormatters)"
```

---

### Task 4: Synthesize `:UwMiniCore` SPM package (model + state + repository)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Package.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Model/Wallet.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Model/Transaction.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/State/WalletStore.swift`
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/Sources/UwMiniCore/Repository/WalletRepository.swift`

- [ ] **Step 1: `Package.swift`**

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "UwMiniCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "UwMiniCore", targets: ["UwMiniCore"]),
    ],
    targets: [
        .target(
            name: "UwMiniCore",
            path: "Sources/UwMiniCore"
        ),
    ]
)
```

- [ ] **Step 2: Wallet.swift (Codable struct — AC#4 Codable target)**

```swift
import Foundation

public struct Wallet: Codable, Identifiable, Equatable {
    public let id: Int
    public let address: String
    public let label: String
    public let balance: Decimal

    public init(id: Int, address: String, label: String, balance: Decimal) {
        self.id = id
        self.address = address
        self.label = label
        self.balance = balance
    }
}
```

- [ ] **Step 3: Transaction.swift (Codable struct + nested + enum with associated values)**

```swift
import Foundation

public struct Transaction: Codable, Identifiable, Equatable {
    public let id: Int
    public let walletId: Int
    public let amount: Decimal
    public let timestamp: Date
    public let type: TxType

    public init(id: Int, walletId: Int, amount: Decimal, timestamp: Date, type: TxType) {
        self.id = id
        self.walletId = walletId
        self.amount = amount
        self.timestamp = timestamp
        self.type = type
    }
}

public enum TxType: Codable, Equatable {
    case send(to: String)
    case receive(from: String)
    case swap(fromToken: String, toToken: String)
    case unknown
}
```

- [ ] **Step 4: WalletStore.swift (`@Observable` macro — AC#4 macro target)**

```swift
import Foundation
import Observation

@Observable
public final class WalletStore {
    public var wallets: [Wallet] = []
    public var selected: Wallet?
    public var isLoading: Bool = false

    public init() {}

    public func select(_ wallet: Wallet) {
        selected = wallet
    }

    public func append(_ wallet: Wallet) {
        wallets.append(wallet)
    }
}
```

- [ ] **Step 5: WalletRepository.swift (async/await + property wrappers + generics)**

```swift
import Foundation

public protocol WalletDataSource {
    func fetchAll() async throws -> [Wallet]
    func fetchTransactions(walletId: Int) async throws -> [Transaction]
}

public final class WalletRepository<DS: WalletDataSource> {
    private let dataSource: DS

    public init(dataSource: DS) {
        self.dataSource = dataSource
    }

    public func loadWallets(into store: WalletStore) async {
        store.isLoading = true
        defer { store.isLoading = false }
        do {
            let wallets = try await dataSource.fetchAll()
            store.wallets = wallets
        } catch {
            store.wallets = []
        }
    }

    public func transactions(for walletId: Int) async throws -> [Transaction] {
        try await dataSource.fetchTransactions(walletId: walletId)
    }
}
```

- [ ] **Step 6: Commit**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniCore/
git commit -m "feat(GIM-128): synthesize UwMiniCore SPM package — Codable + @Observable + async/await + generics"
```

---

### Task 5: Synthesize `:UwMiniApp` Xcode app target (App + Views + Legacy + Info.plist)

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/App/UwMiniApp.swift` (@main App)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/App/AppDelegate.swift` (UIKit interop)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/App/ContentView.swift` (SwiftUI root)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/WalletListView.swift` (SwiftUI + @State)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/WalletDetailView.swift` (SwiftUI + @Binding)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Views/ChartViewRepresentable.swift` (UIViewRepresentable)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Sources/Legacy/LegacyWalletViewController.swift` (UIKit ViewController)
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/Info.plist`

- [ ] **Step 1: UwMiniApp.swift (@main App)**

```swift
import SwiftUI
import UwMiniCore

@main
struct UwMiniApp: App {
    @State private var store = WalletStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(store)
        }
    }
}
```

- [ ] **Step 2: AppDelegate.swift (UIKit interop)**

```swift
import UIKit
import UwMiniCore

@MainActor
final class AppDelegate: NSObject, UIApplicationDelegate {
    static let shared = AppDelegate()

    var walletStore: WalletStore?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        walletStore = WalletStore()
        return true
    }
}
```

- [ ] **Step 3: ContentView.swift (SwiftUI root + @ViewBuilder)**

```swift
import SwiftUI
import UwMiniCore

struct ContentView: View {
    @Environment(WalletStore.self) private var store

    var body: some View {
        NavigationStack {
            WalletListView()
                .navigationTitle("Wallets")
        }
    }
}

#Preview {
    ContentView()
        .environment(WalletStore())
}
```

- [ ] **Step 4: WalletListView.swift (@State + observed @Observable — AC#4 property wrapper $-projection target)**

```swift
import SwiftUI
import UwMiniCore

struct WalletListView: View {
    @Environment(WalletStore.self) private var store
    @State private var searchText: String = ""

    var body: some View {
        @Bindable var bindable = store

        VStack {
            TextField("Search", text: $searchText)
                .padding()

            List(filtered(store.wallets, by: searchText)) { wallet in
                NavigationLink(value: wallet) {
                    Text(wallet.label)
                }
            }
            .navigationDestination(for: Wallet.self) { wallet in
                WalletDetailView(wallet: wallet, selectedId: $bindable.selected.map { $0.id })
            }
        }
    }

    private func filtered(_ wallets: [Wallet], by query: String) -> [Wallet] {
        guard !query.isEmpty else { return wallets }
        return wallets.filter { $0.label.localizedCaseInsensitiveContains(query) }
    }
}
```

- [ ] **Step 5: WalletDetailView.swift (@Binding + $projection)**

```swift
import SwiftUI
import UwMiniCore

struct WalletDetailView: View {
    let wallet: Wallet
    @Binding var selectedId: Int?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(wallet.label).font(.title)
            Text(wallet.address).font(.system(.body, design: .monospaced))
            Text("Balance: \(wallet.balance.description)")
            Button("Select") {
                selectedId = wallet.id
            }
        }
        .padding()
    }
}
```

- [ ] **Step 6: ChartViewRepresentable.swift (UIViewRepresentable — UIKit↔SwiftUI bridge)**

```swift
import SwiftUI
import UIKit
import UwMiniCore

struct ChartViewRepresentable: UIViewRepresentable {
    let transactions: [Transaction]

    func makeUIView(context: Context) -> ChartUIView {
        ChartUIView(frame: .zero)
    }

    func updateUIView(_ uiView: ChartUIView, context: Context) {
        uiView.update(with: transactions)
    }
}

final class ChartUIView: UIView {
    private var values: [Decimal] = []

    func update(with transactions: [Transaction]) {
        values = transactions.map { $0.amount }
        setNeedsDisplay()
    }

    override func draw(_ rect: CGRect) {
        guard !values.isEmpty else { return }
        let ctx = UIGraphicsGetCurrentContext()
        ctx?.setStrokeColor(UIColor.systemBlue.cgColor)
        ctx?.setLineWidth(2)
        ctx?.beginPath()
        for (i, _) in values.enumerated() {
            let x = CGFloat(i) / CGFloat(values.count) * rect.width
            ctx?.addLine(to: CGPoint(x: x, y: rect.height / 2))
        }
        ctx?.strokePath()
    }
}
```

- [ ] **Step 7: LegacyWalletViewController.swift (UIKit ViewController)**

```swift
import UIKit
import UwMiniCore

@MainActor
final class LegacyWalletViewController: UIViewController {
    private let wallet: Wallet
    private let store: WalletStore

    init(wallet: Wallet, store: WalletStore) {
        self.wallet = wallet
        self.store = store
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) not used")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
        title = wallet.label

        let label = UILabel()
        label.text = wallet.address
        label.numberOfLines = 0
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 16),
            label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -16),
        ])
    }
}
```

- [ ] **Step 8: Info.plist (minimal)**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>$(EXECUTABLE_NAME)</string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>UILaunchScreen</key>
    <dict/>
</dict>
</plist>
```

- [ ] **Step 9: Verify file count**

```bash
find services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project -name "*.swift" -type f | wc -l
```

Expected: ~14-16 .swift files (3 vendored + 5 in UwMiniCore + 7 in UwMiniApp).

- [ ] **Step 10: Commit `:UwMiniApp` synthesis**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/UwMiniApp/
git commit -m "feat(GIM-128): synthesize UwMiniApp Xcode app target — SwiftUI + UIKit interop + @Observable consumer"
```

---

### Task 6: Run regen.sh end-to-end + commit `index.scip`

**Files:**
- Create: `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip` (binary)

- [ ] **Step 1: Run regen.sh**

```bash
cd services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project
bash regen.sh 2>&1 | tail -20
```

Expected: BUILD SUCCESSFUL, SwiftSCIPIndex emits index.scip, "size: <N> bytes" line.

- [ ] **Step 2: Verify index.scip is committed-able**

```bash
test -s scip/index.scip && echo "OK: $(wc -c < scip/index.scip) bytes" || echo "MISSING"
```

Expected: ~150-300 KB.

- [ ] **Step 3: Verify parses + count occurrences**

```bash
cd /Users/ant013/Android/Gimle-Palace/services/palace-mcp
uv run python <<'PYEOF'
from pathlib import Path
from palace_mcp.extractors.scip_parser import parse_scip_file, iter_scip_occurrences
from palace_mcp.extractors.foundation.models import SymbolKind, Language

idx = parse_scip_file(Path('tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip'))
occs = list(iter_scip_occurrences(idx, commit_sha='task-6-regen'))
defs = [o for o in occs if o.kind == SymbolKind.DEF]
uses = [o for o in occs if o.kind == SymbolKind.USE]
swift = [o for o in occs if o.language == Language.SWIFT]
print(f'Documents: {len(idx.documents)}')
print(f'Total: {len(occs)}, DEF={len(defs)}, USE={len(uses)}')
print(f'Language SWIFT: {len(swift)}/{len(occs)} ({100*len(swift)/max(len(occs),1):.1f}%)')
PYEOF
```

Expected: ≥10 documents, ≥100 occurrences, ≥95% SWIFT.

- [ ] **Step 4: Update REGEN.md oracle table with locked numbers**

Edit `services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md` — fill rows N_DOCUMENTS_TOTAL, N_DEFS_TOTAL, N_USES_TOTAL, N_OCCURRENCES_TOTAL, N_TANTIVY_DOCS (post-dedup) with concrete numbers.

- [ ] **Step 5: Commit fixture index + REGEN.md final oracle**

```bash
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/scip/index.scip
git add services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project/REGEN.md
git commit -m "feat(GIM-128): regen fixture index.scip + lock REGEN.md oracle table

Fixture build pipeline (xcodegen → xcodebuild → SwiftSCIPIndex) verified
end-to-end. Oracle counts captured for unit + integration test assertions."
```

---

### Task 7: Add `requires_scip_uw_ios` marker to `pyproject.toml`

**Files:**
- Modify: `services/palace-mcp/pyproject.toml` (in `[tool.pytest.ini_options].markers` block)

- [ ] **Step 1: Locate markers list**

```bash
grep -A 12 "^markers = \[" services/palace-mcp/pyproject.toml
```

- [ ] **Step 2: Add new marker**

Edit `services/palace-mcp/pyproject.toml`. After `requires_scip_uw_android` line, insert:

```toml
    "requires_scip_uw_ios: tests requiring uw-ios-mini-project/index.scip fixture (Swift)",
```

- [ ] **Step 3: Verify marker registered**

```bash
cd services/palace-mcp && uv run pytest --markers 2>&1 | grep "requires_scip_uw_ios"
```

Expected: line showing the new marker.

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/pyproject.toml
git commit -m "test(GIM-128): register requires_scip_uw_ios pytest marker"
```

---

### Task 8: Implement `symbol_index_swift` extractor

**Files:**
- Create: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py` (~150-200 LOC)
- Reference: `services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py` (existing template)

- [ ] **Step 1: Read existing `symbol_index_java.py` for runtime structure**

```bash
wc -l services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py
head -60 services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py
```

Expected: ~250 LOC. Note 3-phase ingest pattern, error handling, language filter.

- [ ] **Step 2: Copy as starting template**

```bash
cp services/palace-mcp/src/palace_mcp/extractors/symbol_index_java.py \
   services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py
```

- [ ] **Step 3: Adapt header + class name + literals**

Edit `services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py`:

Replace at top:
```python
"""SymbolIndexSwift — Swift extractor on 101a foundation (GIM-128 Slice 3).

Symmetric copy of SymbolIndexJava for Swift symbols (via SwiftSCIPIndex
community converter reading Apple's IndexStoreDB output).
3-phase bootstrap reading pre-generated .scip files:
  Phase 1: defs + decls only (always runs)
  Phase 2: user-code uses above importance threshold (if budget < 50% used)
  Phase 3: vendor uses (only if budget < 30% used)

Build host = operator's dev Mac (Apple Silicon, Xcode 15+); runtime host
(palace-mcp container) ingests pre-generated .scip files only.
"""
```

Replace class name + name constant:
- Find `class SymbolIndexJava(BaseExtractor):` → replace with `class SymbolIndexSwift(BaseExtractor):`
- Find `name: ClassVar[str] = "symbol_index_java"` → replace with `name: ClassVar[str] = "symbol_index_swift"`
- Find `description: ClassVar[str]` value (block) → rewrite for Swift:

```python
    description: ClassVar[str] = (
        "Ingest Swift symbols + occurrences from pre-generated SCIP file "
        "(SwiftSCIPIndex via Apple IndexStoreDB) into Tantivy + Neo4j. "
        "Handles .swift / .swiftinterface in one pass via per-document "
        "language auto-detection. 3-phase bootstrap: defs/decls → user "
        "uses → vendor uses. Build host = dev Mac; runtime host = iMac."
    )
    primary_lang: ClassVar[Language] = Language.SWIFT
```

- [ ] **Step 4: Update vendor-noise filter (`_is_vendor`)**

Find `_is_vendor` function (likely at module level). Replace JVM-specific paths with Swift-specific (per Phase 1.0 Task 0g):

```python
_VENDOR_PREFIXES_SWIFT = (
    "Pods/",
    "Carthage/",
    "SourcePackages/",
    ".build/",
    ".swiftpm/",
    "DerivedData/",
    # Add additional from REGEN.md "Vendor-noise paths" enumeration
)


def _is_vendor(file_path: str) -> bool:
    """Return True if file_path is in a vendor (deps/build artifacts) directory.

    Symmetric with symbol_index_java._is_vendor() but Swift-specific paths.
    Source: Phase 1.0 Task 0g enumeration of UW-ios DerivedData output.
    """
    if not file_path:
        return False
    return file_path.startswith(_VENDOR_PREFIXES_SWIFT)
```

(If `symbol_index_java.py` doesn't have `_is_vendor` as a module function — check phase2/3 filter site and replace inline `_is_vendor` calls with this Swift version.)

- [ ] **Step 5: Update error_code references (if Java-specific exist)**

Search for any Java-literal error codes in the file:

```bash
grep -nE "java" services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py
```

Expected: only references that are now `swift` after Step 3 rewrites; if any literal "java" remains in error messages or codes, update.

- [ ] **Step 6: Verify Language filter is SWIFT**

```bash
grep -n "Language.SWIFT\|primary_lang" services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py
```

Expected: at least 2 references, both correctly using `Language.SWIFT`.

- [ ] **Step 7: ruff format**

```bash
cd services/palace-mcp && uv run ruff format src/palace_mcp/extractors/symbol_index_swift.py 2>&1 | tail -3
```

- [ ] **Step 8: mypy strict**

```bash
cd services/palace-mcp && uv run mypy src/palace_mcp/extractors/symbol_index_swift.py 2>&1 | tail -3
```

Expected: `Success: no issues found in 1 source file`.

- [ ] **Step 9: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/symbol_index_swift.py
git commit -m "feat(GIM-128): symbol_index_swift extractor — Swift via SwiftSCIPIndex on 101a foundation"
```

---

### Task 9: Register extractor in `registry.py`

**Files:**
- Modify: `services/palace-mcp/src/palace_mcp/extractors/registry.py`

- [ ] **Step 1: Read current registry**

```bash
cat services/palace-mcp/src/palace_mcp/extractors/registry.py
```

- [ ] **Step 2: Add import + registration**

Edit `services/palace-mcp/src/palace_mcp/extractors/registry.py`:

After existing imports, add:
```python
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
```

In the `EXTRACTORS` dict, add (after `symbol_index_java`):
```python
    "symbol_index_swift": SymbolIndexSwift(),
```

- [ ] **Step 3: Verify registration**

```bash
cd services/palace-mcp && uv run python -c "
from palace_mcp.extractors.registry import EXTRACTORS
for name in EXTRACTORS:
    print(f'  {name}')
" 2>&1 | tail -10
```

Expected: list includes `symbol_index_swift`.

- [ ] **Step 4: ruff format + mypy**

```bash
cd services/palace-mcp && uv run ruff format src/palace_mcp/extractors/registry.py && uv run mypy src/palace_mcp/extractors/registry.py 2>&1 | tail -3
```

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit**

```bash
git add services/palace-mcp/src/palace_mcp/extractors/registry.py
git commit -m "feat(GIM-128): register symbol_index_swift in extractors registry"
```

---

### Task 10: `TestUwIosMiniProjectFixture` — unit-level oracle assertions

**Files:**
- Modify: `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py` (append new test class at end of file)

> **TDD:** Write all ~14 assertions referencing oracle values from REGEN.md FIRST. Then run; concrete-number assertions pass against committed index.scip.

- [ ] **Step 1: Read existing test file structure**

```bash
grep -nE "^class Test|^@requires_scip" services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py
```

- [ ] **Step 2: Add fixture path constant + marker at top of file**

Edit `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py`. After existing fixture path constants:

```python
UW_IOS_SCIP = FIXTURES / "uw-ios-mini-project" / "scip" / "index.scip"
```

After existing skipif markers:

```python
requires_scip_uw_ios = pytest.mark.skipif(
    not UW_IOS_SCIP.exists(),
    reason="uw-ios-mini-project/scip/index.scip not present",
)
```

- [ ] **Step 3: Add oracle constants**

After existing oracle blocks:

```python
# uw-ios-mini oracle (Phase 1.0 — REGEN.md authoritative)
_UW_IOS_N_OCCURRENCES_TOTAL = <FROM_REGEN_MD>  # fill from REGEN.md Task 6
_UW_IOS_N_DEFS = <FROM_REGEN_MD>
_UW_IOS_N_USES = <FROM_REGEN_MD>
_UW_IOS_N_DOCUMENTS = <FROM_REGEN_MD>
_UW_IOS_N_TANTIVY_DOCS = <FROM_REGEN_MD>  # post-dedup, used in integration test
_UW_IOS_AC4_BRANCH = "<A | B-1 | B-2>"  # from REGEN.md Task 0e
```

> **Replace `<FROM_REGEN_MD>` with locked numbers from REGEN.md.** No `<>` placeholders may remain after this step.

- [ ] **Step 4: Add `TestUwIosMiniProjectFixture` class**

Append to `services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py`:

```python
@requires_scip_uw_ios
class TestUwIosMiniProjectFixture:
    """Oracle assertions for uw-ios-mini-project fixture (GIM-128 Slice 3).

    AC#4 (generated-code visibility) conditional — see _UW_IOS_AC4_BRANCH.
    """

    def test_parses_without_error(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        assert index is not None

    def test_yields_swift_occurrences(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        swift = [o for o in occs if o.language == Language.SWIFT]
        assert len(swift) > 0, "Expected at least one Swift occurrence"

    def test_occurrence_total_matches_oracle(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        lo, hi = int(_UW_IOS_N_OCCURRENCES_TOTAL * 0.95), int(_UW_IOS_N_OCCURRENCES_TOTAL * 1.05)
        assert lo <= len(occs) <= hi, (
            f"Oracle: {_UW_IOS_N_OCCURRENCES_TOTAL}±5%, got {len(occs)}"
        )

    def test_def_count_matches_oracle(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        defs = [o for o in occs if o.kind == SymbolKind.DEF]
        lo, hi = int(_UW_IOS_N_DEFS * 0.95), int(_UW_IOS_N_DEFS * 1.05)
        assert lo <= len(defs) <= hi, f"Oracle: {_UW_IOS_N_DEFS}±5% DEF, got {len(defs)}"

    def test_documents_count_matches_oracle(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        assert len(index.documents) == _UW_IOS_N_DOCUMENTS, (
            f"Oracle: {_UW_IOS_N_DOCUMENTS} docs, got {len(index.documents)}"
        )

    def test_wallet_struct_def_present(self) -> None:
        # Wallet Codable struct in UwMiniCore
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("Wallet" in n for n in names), f"Expected Wallet DEF, sample: {sorted(names)[:5]}"

    def test_wallet_store_observable_present(self) -> None:
        # @Observable WalletStore class in UwMiniCore
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("WalletStore" in n for n in names), "Expected WalletStore @Observable DEF"

    def test_main_app_swift_def_present(self) -> None:
        # @main App in UwMiniApp
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("UwMiniApp" in n for n in names), "Expected UwMiniApp @main DEF"

    def test_codable_synthesis_visibility(self) -> None:
        # AC#4 target (a) — Codable: Wallet#init(from:) + Wallet#encode(to:)
        if _UW_IOS_AC4_BRANCH == "B-2":
            pytest.skip("AC#4 Branch B-2 — Codable synthesis not visible to SwiftSCIPIndex")
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any("init(from:)" in n for n in names), (
            f"AC#4(a) Branch {_UW_IOS_AC4_BRANCH}: expected Codable init(from:) generated DEF"
        )

    def test_observable_macro_visibility(self) -> None:
        # AC#4 target (b) — @Observable: _$observationRegistrar / withMutation
        if _UW_IOS_AC4_BRANCH == "B-2":
            pytest.skip("AC#4 Branch B-2 — @Observable macro internals not visible")
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        assert any(
            "_$observationRegistrar" in n or "withMutation" in n for n in names
        ), f"AC#4(b) Branch {_UW_IOS_AC4_BRANCH}: expected @Observable macro DEFs"

    def test_property_wrapper_projection_visibility(self) -> None:
        # AC#4 target (c) — @State $-projection
        if _UW_IOS_AC4_BRANCH == "B-2":
            pytest.skip("AC#4 Branch B-2 — property wrapper projection not visible")
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        names = {o.symbol_qualified_name for o in occs if o.kind == SymbolKind.DEF}
        # Look for backing _foo or $foo projected — exact pattern depends on SwiftSCIPIndex output
        has_projection = any(
            ("_searchText" in n) or ("$searchText" in n) or ("_counter" in n)
            for n in names
        )
        assert has_projection, (
            f"AC#4(c) Branch {_UW_IOS_AC4_BRANCH}: expected property wrapper $-projection symbols"
        )

    def test_cross_target_use_store_in_view(self) -> None:
        # AC#5 pair 1/5 — app→SPM: WalletListView USEs WalletStore
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        view_uses_store = any(
            "WalletStore" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "WalletListView" in (o.file_path or "")
            for o in occs
        )
        assert view_uses_store, "AC#5 pair 1/5 — Expected WalletListView USE WalletStore (app→SPM)"

    def test_cross_target_use_wallet_in_detail(self) -> None:
        # AC#5 pair 2/5 — app→SPM: WalletDetailView USEs Wallet (Codable)
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        detail_uses_wallet = any(
            "Wallet" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "WalletDetailView" in (o.file_path or "")
            for o in occs
        )
        assert detail_uses_wallet, "AC#5 pair 2/5 — Expected WalletDetailView USE Wallet (app→SPM Codable)"

    def test_cross_target_use_transaction_in_chart(self) -> None:
        # AC#5 pair 3/5 — app→SPM: ChartViewRepresentable USEs Transaction (UIKit interop ↔ SPM)
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        chart_uses_tx = any(
            "Transaction" in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "ChartViewRepresentable" in (o.file_path or "")
            for o in occs
        )
        assert chart_uses_tx, "AC#5 pair 3/5 — Expected ChartViewRepresentable USE Transaction"

    def test_intra_spm_use_wallet_in_repository(self) -> None:
        # AC#5 pair 4/5 — intra-SPM: WalletRepository USEs Wallet
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        repo_uses_wallet = any(
            "Wallet" in o.symbol_qualified_name
            and "WalletStore" not in o.symbol_qualified_name
            and o.kind == SymbolKind.USE
            and "WalletRepository" in (o.file_path or "")
            for o in occs
        )
        assert repo_uses_wallet, "AC#5 pair 4/5 — Expected WalletRepository USE Wallet"

    def test_qualified_names_no_scheme_prefix(self) -> None:
        index = parse_scip_file(UW_IOS_SCIP)
        occs = list(iter_scip_occurrences(index, commit_sha="test"))
        for occ in occs:
            qn = occ.symbol_qualified_name
            assert not qn.startswith("scip-swift"), f"qualified_name leaks scheme: {qn!r}"
            assert not qn.startswith("apple"), f"qualified_name leaks scheme: {qn!r}"
```

- [ ] **Step 5: Run new test class**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwIosMiniProjectFixture -v 2>&1 | tail -20
```

Expected: 16 passed (or 13 + 3 skipped if Branch B-2). If any fail unexpectedly → diagnose oracle drift OR symbol-name pattern mismatch.

- [ ] **Step 6: ruff format**

```bash
cd services/palace-mcp && uv run ruff format tests/extractors/unit/test_real_scip_fixtures.py 2>&1 | tail -3
```

- [ ] **Step 7: Commit**

```bash
git add services/palace-mcp/tests/extractors/unit/test_real_scip_fixtures.py
git commit -m "test(GIM-128): TestUwIosMiniProjectFixture — oracle assertions for Swift fixture (Codable/Observable/property wrapper conditional on AC#4 branch)"
```

---

### Task 11: Integration test — `test_symbol_index_swift_uw_integration.py` (NEW pattern)

**Files:**
- Create: `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_uw_integration.py`
- Reference: `services/palace-mcp/tests/extractors/integration/test_symbol_index_java_uw_integration.py` (Slice 1 rev2 pattern)

- [ ] **Step 1: Write integration test**

Create `services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_uw_integration.py`:

```python
"""Integration test: SymbolIndexSwift on real fixture .scip + real Neo4j (GIM-128 Slice 3).

Symmetric with test_symbol_index_java_uw_integration.py (Slice 1 rev2 pattern).
Reads committed uw-ios-mini-project/scip/index.scip from disk + uses real
Neo4j (testcontainers/compose-reuse) + asserts Tantivy doc count via
post-dedup oracle constant _UW_IOS_N_TANTIVY_DOCS.

Skipped via requires_scip_uw_ios marker if fixture .scip missing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from palace_mcp.extractors.base import ExtractorRunContext
from palace_mcp.extractors.foundation.tantivy_bridge import TantivyBridge
from palace_mcp.extractors.symbol_index_swift import SymbolIndexSwift
from tests.extractors.unit.test_real_scip_fixtures import (
    _UW_IOS_N_TANTIVY_DOCS,
    requires_scip_uw_ios,
)

FIXTURE_SCIP = (
    Path(__file__).parent.parent / "fixtures" / "uw-ios-mini-project" / "scip" / "index.scip"
)
_RUN_ID = "uw-ios-integration-001"


@pytest.mark.integration
@requires_scip_uw_ios
class TestSymbolIndexSwiftUwIntegration:
    @pytest.mark.asyncio
    async def test_full_ingest_cycle_real_fixture(
        self, driver: object, tmp_path: Path
    ) -> None:
        """Ingest committed UW-ios fixture, verify Neo4j + Tantivy state."""
        settings = MagicMock()
        settings.palace_scip_index_paths = {"uw-ios-mini": str(FIXTURE_SCIP)}
        tantivy_dir = tmp_path / "tantivy"
        tantivy_dir.mkdir()
        settings.palace_tantivy_index_path = str(tantivy_dir)
        settings.palace_tantivy_heap_mb = 100
        settings.palace_max_occurrences_total = 50_000_000
        settings.palace_max_occurrences_per_project = 10_000_000
        settings.palace_importance_threshold_use = 0.0
        settings.palace_max_occurrences_per_symbol = 5_000
        settings.palace_recency_decay_days = 30.0

        ctx = ExtractorRunContext(
            project_slug="uw-ios-mini",
            group_id="project/uw-ios-mini",
            repo_path=tmp_path,
            run_id=_RUN_ID,
            duration_ms=0,
            logger=MagicMock(),
        )

        extractor = SymbolIndexSwift()
        graphiti = MagicMock()

        with (
            patch("palace_mcp.mcp_server.get_driver", return_value=driver),
            patch("palace_mcp.mcp_server.get_settings", return_value=settings),
        ):
            stats = await extractor.run(graphiti=graphiti, ctx=ctx)

        # Assert 1: extractor wrote occurrences
        assert stats.nodes_written > 0, "extractor wrote zero occurrences"

        # Assert 2: IngestRun in Neo4j
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (r:IngestRun {run_id: $rid}) RETURN r.success AS success",
                rid=_RUN_ID,
            )
            record = await result.single()
            assert record is not None, "IngestRun node not found in Neo4j"
            assert record["success"] is True, "IngestRun marked failure"

        # Assert 3: Phase 1 checkpoint persisted
        async with driver.session() as session:  # type: ignore[union-attr]
            result = await session.run(
                "MATCH (c:IngestCheckpoint {run_id: $rid, phase: 'phase1_defs'}) "
                "RETURN c.expected_doc_count AS count",
                rid=_RUN_ID,
            )
            record = await result.single()
            assert record is not None, "phase1_defs checkpoint missing"
            assert record["count"] > 0, "phase1_defs wrote zero documents"

        # Assert 4: Tantivy doc count matches oracle ±2%
        async with TantivyBridge(
            tantivy_dir, heap_size_mb=settings.palace_tantivy_heap_mb
        ) as bridge:
            phase1 = await bridge.count_docs_for_run_async(_RUN_ID, "phase1_defs")
            phase2 = await bridge.count_docs_for_run_async(_RUN_ID, "phase2_user_uses")
            phase3 = await bridge.count_docs_for_run_async(_RUN_ID, "phase3_vendor_uses")
        tantivy_total = phase1 + phase2 + phase3

        lo = int(_UW_IOS_N_TANTIVY_DOCS * 0.98)
        hi = int(_UW_IOS_N_TANTIVY_DOCS * 1.02)
        assert lo <= tantivy_total <= hi, (
            f"Tantivy doc count {tantivy_total} (p1={phase1}, p2={phase2}, p3={phase3}) "
            f"outside oracle {_UW_IOS_N_TANTIVY_DOCS}±2% (range [{lo}, {hi}])"
        )
```

- [ ] **Step 2: Run integration test (requires Neo4j)**

```bash
cd services/palace-mcp
docker compose --profile review up -d neo4j
sleep 5
COMPOSE_NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=$(grep NEO4J_PASSWORD ../../.env | cut -d= -f2) \
  uv run pytest tests/extractors/integration/test_symbol_index_swift_uw_integration.py -v -m integration 2>&1 | tail -10
```

Expected: `1 passed` (or `1 skipped` if fixture missing).

- [ ] **Step 3: ruff format**

```bash
cd services/palace-mcp && uv run ruff format tests/extractors/integration/test_symbol_index_swift_uw_integration.py 2>&1 | tail -3
```

- [ ] **Step 4: Commit**

```bash
git add services/palace-mcp/tests/extractors/integration/test_symbol_index_swift_uw_integration.py
git commit -m "test(GIM-128): integration test for symbol_index_swift — real fixture .scip + real Neo4j (Slice 1 rev2 pattern)"
```

---

### Task 12: Update `docker-compose.yml` — bind-mount for `uw-ios-mini` (Track A)

**Files:**
- Modify: `docker-compose.yml` (palace-mcp.volumes block)

- [ ] **Step 1: Verify current state**

```bash
grep -A 3 "uw-android" docker-compose.yml
```

Expected: existing uw-android bind-mount.

- [ ] **Step 2: Add uw-ios-mini bind-mount**

Edit `docker-compose.yml`. After the line:
```yaml
      - /Users/Shared/Android/unstoppable-wallet-android:/repos/uw-android:ro
```

Add:
```yaml
      - ./services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project:/repos/uw-ios-mini:ro
      # uw-ios (real UW-ios) — added per Phase 4.1 Track B post-merge once dev Mac generates index.scip
```

- [ ] **Step 3: Validate compose syntax**

```bash
docker compose config --quiet 2>&1
```

Expected: empty output (success).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(GIM-128): docker-compose bind-mount uw-ios-mini (Track A fixture); uw-ios real-source mount added per Track B followup"
```

---

### Task 13: Update `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Find current PALACE_SCIP_INDEX_PATHS example**

```bash
grep -B 1 -A 2 "PALACE_SCIP_INDEX_PATHS" .env.example
```

- [ ] **Step 2: Update example to include Swift slug**

Edit `.env.example`. Change `PALACE_SCIP_INDEX_PATHS` example to:

```
# JSON map of project slug → SCIP index path (operator generates outside container)
# Track A (fixture, all language slices): paths are container-relative under /repos/...-mini
# Track B (real source, post-merge): operator generates index.scip on capable host, transfers to iMac
PALACE_SCIP_INDEX_PATHS={"gimle":"/repos/gimle/scip/index.scip","oz-v5-mini":"/repos/oz-v5-mini/index.scip","uw-android":"/repos/uw-android/scip/index.scip","uw-ios-mini":"/repos/uw-ios-mini/scip/index.scip"}
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs(GIM-128): show Swift slug example in PALACE_SCIP_INDEX_PATHS"
```

---

### Task 14: Update `CLAUDE.md` — Operator workflow Swift + project mount table

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate Extractors section**

```bash
grep -n "^### Operator workflow" CLAUDE.md
```

Expected: existing Operator-workflow subsections for Python/Java/etc.

- [ ] **Step 2: Add Swift operator workflow subsection**

Edit `CLAUDE.md`. After existing "Operator workflow: Android symbol index" subsection, add:

```markdown
### Operator workflow: iOS Swift symbol index (Apple IndexStoreDB + SwiftSCIPIndex)

iOS projects index via Apple-native IndexStoreDB (generated by `swiftc`/`clang`
during `swift build`/`xcodebuild` for Debug) → SwiftSCIPIndex (community
converter) → SCIP. Build host = capable Mac (Apple Silicon, current Xcode);
iMac (Intel + macOS 13) is runtime-only.

1. One-time toolchain install (dev Mac):
   ```bash
   brew install xcodegen
   git clone https://github.com/Fostonger/SwiftSCIPIndex.git ~/.local/opt/SwiftSCIPIndex
   cd ~/.local/opt/SwiftSCIPIndex && swift build -c release
   ln -sfn ~/.local/opt/SwiftSCIPIndex/.build/release/SwiftSCIPIndex ~/.local/bin/SwiftSCIPIndex
   ```

2. Generate `.scip` on dev Mac (build host):
   ```bash
   cd ~/iOS-projects/unstoppable-wallet-ios
   xcodebuild build -workspace UnstoppableWallet/UnstoppableWallet.xcworkspace \
                   -scheme UnstoppableWallet \
                   -destination "generic/platform=iOS Simulator"
   SwiftSCIPIndex --derived-data ~/Library/Developer/Xcode/DerivedData/UnstoppableWallet-* \
                 --output ./scip/index.scip
   ```

3. Transfer to iMac mount (Track B):
   ```bash
   scp ./scip/index.scip imac-ssh.ant013.work:/Users/Shared/Ios/unstoppable-wallet-ios-scip/index.scip
   ```

4. Set env var in iMac `.env`:
   ```
   PALACE_SCIP_INDEX_PATHS={..., "uw-ios":"/repos/uw-ios-scip/index.scip"}
   ```

5. Run extractor:
   ```
   palace.ingest.run_extractor(name="symbol_index_swift", project="uw-ios")
   ```

6. Query references (post-GIM-126):
   ```
   palace.code.find_references(qualified_name="WalletManager", project="uw-ios")
   ```
```

- [ ] **Step 3: Update project mount table**

In `CLAUDE.md`, find the project mount table (`## Mounting project repos for palace.git.*`). Add row:

```markdown
| `uw-ios-mini` | `./services/palace-mcp/tests/extractors/fixtures/uw-ios-mini-project` | `/repos/uw-ios-mini:ro` | Track A iOS fixture |
| `uw-ios`      | `/Users/Shared/Ios/unstoppable-wallet-ios-scip` (or operator path) | `/repos/uw-ios-scip:ro` | Track B real UW-ios .scip (operator transfers from dev Mac) |
```

- [ ] **Step 4: Verify CLAUDE.md edit**

```bash
grep -E "uw-ios|Operator workflow: iOS" CLAUDE.md | wc -l
```

Expected: ≥4 matches.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(GIM-128): CLAUDE.md — iOS Swift operator workflow + uw-ios-mini + uw-ios mounts"
```

---

### Task 15: Final pre-CR mechanical review (lint + format + typecheck + tests + gh pr checks)

**Files:**
- Verify all changes from Tasks 0-14

- [ ] **Step 1: Ruff check**

```bash
cd services/palace-mcp && uv run ruff check src/ tests/ 2>&1 | tail -3
```

Expected: `All checks passed!`.

- [ ] **Step 2: Ruff format check**

```bash
cd services/palace-mcp && uv run ruff format --check src/ tests/ 2>&1 | tail -3
```

Expected: `XXX files already formatted`.

- [ ] **Step 3: mypy strict**

```bash
cd services/palace-mcp && uv run mypy src/ 2>&1 | tail -3
```

Expected: `Success: no issues found in N source files`.

- [ ] **Step 4: pytest GIM-128-scoped unit**

```bash
cd services/palace-mcp && uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwIosMiniProjectFixture -v 2>&1 | tail -15
```

Expected: 16 passed (or 13 + 3 skipped on Branch B-2).

- [ ] **Step 5: pytest full unit suite (regression)**

```bash
cd services/palace-mcp && uv run pytest -v -m "not integration and not slow" 2>&1 | tail -10
```

Expected: all passed; no new failures.

- [ ] **Step 6: pytest integration**

```bash
cd services/palace-mcp
docker compose --profile review up -d neo4j && sleep 5
COMPOSE_NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=$(grep NEO4J_PASSWORD ../../.env | cut -d= -f2) \
  uv run pytest tests/extractors/integration/test_symbol_index_swift_uw_integration.py -v -m integration 2>&1 | tail -5
```

Expected: 1 passed.

- [ ] **Step 7: docker compose syntax check**

```bash
docker compose config --quiet 2>&1
```

Expected: empty.

- [ ] **Step 8: git status — verify expected commits**

```bash
git log --oneline origin/develop..HEAD
```

Expected: ~15-18 commits (Phase 1.0 + Phase 2 tasks).

- [ ] **Step 9: Push branch + verify CI on origin**

```bash
git push origin feature/GIM-128-ios-swift-extractor
sleep 30
gh pr checks --watch 2>&1 | tail -10
```

Expected: all CI checks pass (lint, typecheck, test, docker-build, etc.).

- [ ] **Step 10: Open draft PR**

```bash
gh pr create --draft --title "feat(GIM-128): iOS Swift extractor — symbol_index_swift via Apple IndexStoreDB + SwiftSCIPIndex" --body "$(cat <<'PRBODY'
## Summary

- New `symbol_index_swift` extractor (~150-200 LOC) on existing 101a foundation.
- `scip_parser.py` extended: `_SCIP_LANGUAGE_MAP` adds `"swift": Language.SWIFT` + `_language_from_path` adds `.swift`/`.swiftinterface` fallback.
- Hybrid SPM + Xcode app fixture (`uw-ios-mini-project`, ~30 files, 3 vendored from UW-ios + ~27 synthesized).
- Phase 1.0 spike captured AC#4 generated-code visibility branch (A/B-1/B-2) on dev Mac before PE Phase 2.
- Track A (fixture-based) is hard merge gate; Track B (real UW-ios) deferred to operator's dev Mac post-merge.

## Test plan

- [x] `uv run ruff check src/ tests/` → 0 issues
- [x] `uv run ruff format --check src/ tests/` → all formatted
- [x] `uv run mypy src/` → Success
- [x] `uv run pytest tests/extractors/unit/test_real_scip_fixtures.py::TestUwIosMiniProjectFixture -v` → 16 passed (or 13+3 skipped if Branch B-2)
- [x] `uv run pytest tests/extractors/integration/test_symbol_index_swift_uw_integration.py -m integration` → passes against Neo4j
- [ ] Phase 4.1 Track A live-smoke on iMac (QA — fixture-based, not real UW-ios)
- [ ] Phase 4.1 Track B follow-up evidence on operator's dev Mac (post-merge)

## QA Evidence

(Phase 4.1 Track A QAEngineer fills with REAL transcripts after iMac deploy. Per Slice 1 incident discipline: must include actual `palace.ingest.run_extractor` JSON response + Neo4j cypher transcript + timestamps. NO oracle-constants copy-paste.)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PRBODY
)"
```

- [ ] **Step 11: Reassign in paperclip — Phase 3.1 CodeReviewer**

(Operator/CTO action via paperclip API — outside this plan's scope. Plan deliverable ends here.)

---

## Self-review checklist

Before marking plan complete, verify:

**1. Spec coverage:**
- [x] AC#1 (fixture compiles via xcodegen + xcodebuild) — Task 6 Step 1
- [x] AC#2 (SwiftSCIPIndex emits valid index.scip) — Task 6 Steps 1-3
- [x] AC#3 (oracle counts match) — Task 10 (TestUwIosMiniProjectFixture)
- [x] AC#4 (CONDITIONAL Phase 1.0 gate) — Task 0e + Task 10 conditional skip on Branch B-2
- [x] AC#5 (5 cross-target USE pairs) — Task 10 5 test methods
- [x] AC#6 (all DEFs language=SWIFT) — Task 10 `test_yields_swift_occurrences` + `test_qualified_names_no_scheme_prefix`
- [x] AC#7 (integration test green) — Task 11
- [x] AC#7.5 (substantive live-smoke) — Phase 4.1 Track A (iMac fixture) + Track B (dev Mac real-source) — outside this plan, captured in spec
- [x] AC#8 (docker-compose 1 bind-mount uw-ios-mini) — Task 12
- [x] AC#9 (.env.example documented) — Task 13
- [x] AC#10 (CLAUDE.md updated) — Task 14

**2. Placeholder scan:**
- `<FROM_REGEN_MD>` in Task 10 Step 3 is a deliberate fillable placeholder pointing to REGEN.md oracle table — instruction is concrete: "Replace with locked numbers from REGEN.md." This is acceptable per writing-plans skill (deterministic action, not vague TODO). PE replaces during Step 3, not at execution time. Task 1 Step 2 enforces this gate.
- `<TBD>` in REGEN.md draft sections (Task 0a Step 4) — gated by Task 0h Step 1 (verify all filled before PE Phase 2 starts).
- `<UW-ios-SHA-from-REGEN.md>` in Task 3 Step 2 — concrete instruction to substitute from REGEN.md before vendoring.
- No vague "TBD" / "TODO" remains in actual implementation steps.

**3. Type / API consistency:**
- `parse_scip_file`, `iter_scip_occurrences`, `Language.SWIFT`, `SymbolKind.DEF/USE` — match existing imports.
- `SymbolIndexSwift` class name + `name = "symbol_index_swift"` consistent across Tasks 8, 9, 10, 11.
- `_UW_IOS_N_*` oracle constants — defined Task 10 Step 3, used Task 10 Step 4 + Task 11 Step 1.
- `requires_scip_uw_ios` marker — consistent across pyproject.toml + test files.

**4. Phase ordering:**
- Phase 1.0 (Tasks 0a-0h) gates Phase 2 (Tasks 1-15) — Task 1 Steps 1-4 enforces.
- Phase 3.1 / 3.2 / 4.1 / 4.2 are downstream (out of plan scope) — Task 15 Steps 9-11 hands off.

**5. Process discipline (per Slice 1 lessons):**
- Phase 4.1 Track A evidence script in spec rev2 §"Phase 4.1 live-smoke evidence" mandates real timestamps + transcripts + JSON responses. Plan Task 15 doesn't include Phase 4.1 directly (out of scope) but Task 15 Step 10 PR body template explicitly notes "NO oracle-constants copy-paste" per `feedback_pe_qa_evidence_fabrication.md`.
- CR Phase 3.1 must run `gh pr checks` per `feedback_cr_phase31_ci_verification.md` — Task 15 Step 9 ensures CI is green before draft PR opens.
