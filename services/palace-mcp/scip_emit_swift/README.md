# palace-swift-scip-emit

Custom Swift emitter that reads Xcode IndexStoreDB and emits canonical
Sourcegraph SCIP protobuf for ingestion by palace-mcp's `symbol_index_swift`
extractor.

## Build

```bash
cd services/palace-mcp/scip_emit_swift
xcrun swift build -c release
```

The release binary is `.build/release/palace-swift-scip-emit-cli`.

## Run

```bash
palace-swift-scip-emit-cli \
  --derived-data ~/Library/Developer/Xcode/DerivedData/MyProject-xxxxx \
  --project-root /path/to/MyProject \
  --output myproject.scip
```

The output file is a Sourcegraph SCIP protobuf consumable by
`palace-mcp`'s `parse_scip_file()`.
