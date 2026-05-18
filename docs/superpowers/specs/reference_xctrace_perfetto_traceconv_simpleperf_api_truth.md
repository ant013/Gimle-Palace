# GIM-276 API Truth — xctrace / Perfetto / traceconv / simpleperf

**Verified:** 2026-05-12
**Scope:** planning evidence for `hot_path_profiler`; this is not an
implementation spike and does not claim local tool availability.

## Local availability check

Current runner does not have Apple Instruments CLI available:

```text
xcrun: error: unable to find utility "xctrace", not a developer tool or in PATH
```

Therefore GIM-276 must not require live `xctrace` capture in CI. The
merge gate is a committed, pre-recorded Track A fixture.

## Verified tool contracts

### xctrace

Reference: https://keith.github.io/xcode-man-pages/xctrace.1.html

Verified facts:

- `xctrace` can record, import, export, remodel and symbolicate
  Instruments `.trace` files.
- `xctrace export` accepts `--input`, optional `--output`, and either
  `--toc` or `--xpath`.
- The manpage describes export as producing parseable formats such as
  XML; no native JSON export contract was verified.

GIM-276 planning consequence:

- The required Track A fixture is a committed normalized JSON fixture
  derived from a real `xctrace export` table, not a claim that
  `xctrace export` itself emits JSON.
- The runbook must preserve the exact raw export command and source
  table/schema used to produce the normalized JSON fixture.

### Perfetto Trace Processor Python API

Reference: https://perfetto.dev/docs/analysis/trace-processor-python

Verified facts:

- The Python package is installed as `perfetto`.
- The main API entry point is `TraceProcessor`.
- `TraceProcessor(trace=...)` accepts a trace file path, file-like
  object, byte generator, or resolver URI.
- `query(sql)` returns an iterable query result; results can be
  converted to a pandas dataframe.

GIM-276 planning consequence:

- If the Perfetto parser remains in v1, it should use
  `perfetto.trace_processor.TraceProcessor` for `.pftrace` analysis
  rather than inventing a binary parser.

### traceconv

Reference: https://perfetto.dev/docs/quickstart/traceconv

Verified facts:

- `traceconv` converts Perfetto protobuf traces to other formats.
- The documented Linux/macOS bootstrap is downloading the wrapper from
  `https://get.perfetto.dev/traceconv`, making it executable, then
  running `./traceconv MODE [OPTIONS] [input_file] [output_file]`.
- Documented modes include `json`, `text`, `systrace`, `profile`, and
  `bundle`; `bundle` is preferred for symbolization/deobfuscation
  sharing.

GIM-276 planning consequence:

- `traceconv` use must be isolated behind fixture generation/runbook
  steps unless the implementer pins a deterministic binary path for
  tests.

### simpleperf

Reference: https://perfetto.dev/docs/getting-started/other-formats

Verified facts:

- Perfetto documents Simpleperf proto support and a command shape using
  `simpleperf report-sample --protobuf --show-callchain`.
- The command can emit a proto profile from `simpleperf.data`; optional
  symbol directories can improve symbolization.

GIM-276 planning consequence:

- simpleperf support should be parser-only and fixture-driven in v1; no
  Android-device capture is part of the merge gate unless explicitly
  added by QA.

## Not verified for v1

- `xcodetracemcp` was not verified as a required implementation API for
  this slice. Treat it as a deferred follow-up only.
- The prior xctrace JSON schema claim was not verified. Do not use that
  phrase as an implementation contract for GIM-276.
