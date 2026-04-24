---
slug: GIM-69-watchdog-install-fix
status: proposed
branch: feature/GIM-69-watchdog-install-fix
predecessor: 053d93f (GIM-63 agent watchdog)
paperclip_issue: 69 (5468fb03-84bd-4d16-b93d-d867141af001)
date: 2026-04-24
---

# GIM-69 — Watchdog install broken: argparse regression fix

## 1. Context

GIM-63 (merged as `053d93f`) shipped `services/watchdog` — a host-native
launchd/systemd daemon that polls paperclip for stuck issues and kills
idle-hang Claude subprocesses.

First real `install` on the iMac (post-merge operator deploy) failed:
daemon crashes on startup, launchd enters a restart loop with
`LastExitStatus=512`.

## 2. Problem

Two defects merged in GIM-63 compound to break `install`:

**Defect A — argparse shape.**
`services/watchdog/src/gimle_watchdog/__main__.py:27` adds `--config`
only to the top-level parser:

```python
parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
sub = parser.add_subparsers(dest="command")
sub.add_parser("run", ...)   # no --config inherited
```

argparse with subcommands treats flags occurring **after** the
subcommand as belonging to the subparser. Subparser `run` has no
`--config`, so it rejects it.

**Defect B — renderer shape.**
`services/watchdog/src/gimle_watchdog/service.py:28` (`render_plist`)
and `:53` (`render_systemd_unit`) emit `ProgramArguments` /
`ExecStart` with `--config` **after** the subcommand:

```
python -m gimle_watchdog run --config <path>
                             ↑ after-subcommand flag → rejected
```

Either shape alone is fine. Together they collide.

**Verified on iMac** (2026-04-24):

```
$ ~/.paperclip/watchdog.err
watchdog: error: unrecognized arguments: --config /Users/anton/.paperclip/watchdog-config.yaml
...
$ launchctl list work.ant013.gimle-watchdog
"LastExitStatus" = 512;
```

## 3. Why QA Phase 4.1 missed it

Phase 4.1 smoke covered:

| Command | What it did | Why it didn't expose the bug |
|---|---|---|
| `install --dry-run` | rendered plist, did not `launchctl load` | no actual daemon start |
| `tick` | subcommand with no `--config` | argparse fell back to `DEFAULT_CONFIG_PATH` silently |
| `status` | subcommand with no `--config` | same |

Unit test `test_render_plist_matches_fixture` compares render output
bit-for-bit against `tests/fixtures/plist_expected.xml` — cannot catch
semantic drift between renderer shape and parser shape.

The root process gap — no *"install → launchctl load → daemon alive
through one tick"* path — is tracked separately; out of scope here.

## 4. Solution

**Accept the renderer shape as canonical** (it's the shape users also
use at the command line: `watchdog run --config foo` reads naturally;
`watchdog --config foo run` feels backwards). **Fix the parser** to
accept it.

Approach: move `--config` off the top-level parser onto each subparser
via `argparse.ArgumentParser(parents=[...])`. One shared parent parser
holds `--config`; every subparser inherits it through `parents=[parent]`.

This closes the entire class of bug, not just this one instance. It
also matches how the CLI is documented in `services/watchdog/README.md`
(`gimle-watchdog tail -n 100`, `gimle-watchdog escalate --issue ...`).

Pseudocode:

```python
def _build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    parser = argparse.ArgumentParser(prog="watchdog", parents=[common])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", parents=[common], help="...")
    sub.add_parser("tick", parents=[common], help="...")
    # ... each subparser gets parents=[common]
```

Renderers in `service.py` stay byte-identical. Fixture
`tests/fixtures/plist_expected.xml` stays byte-identical.

## 5. New regression test

Add a renderer-roundtrip test that *exercises argparse on the string
the renderer emits* — not just a fixture-compare:

```python
# tests/test_cli_roundtrip.py
def test_rendered_plist_args_parse(tmp_path):
    rendered = service.render_plist(
        venv_python=Path("/x/python"),
        config_path=Path("/x/cfg.yaml"),
        log_path=Path("/x/log"), err_path=Path("/x/err"))
    # extract everything after the venv_python path in ProgramArguments
    # args = ["-m", "gimle_watchdog", "run", "--config", "/x/cfg.yaml"]
    args = _program_arguments_after_python(rendered)
    assert args[0:2] == ["-m", "gimle_watchdog"]
    # drop `-m module` — argparse sees args from sys.argv[1:] onward
    parsed = __main__._build_parser().parse_args(args[2:])
    assert parsed.command == "run"
    assert str(parsed.config) == "/x/cfg.yaml"

def test_rendered_systemd_exec_args_parse():
    # same for systemd ExecStart
    ...
```

Pre-fix these tests must fail (argparse raises `SystemExit`); post-fix
they pass.

## 6. Acceptance criteria

- New roundtrip tests fail on pre-fix code (`053d93f`), pass on post-fix.
- Existing test suite stays green (ruff/mypy/pytest; 80/80 tests).
- On iMac (operator verifies): `install` followed by
  `launchctl list work.ant013.gimle-watchdog` shows a **stable PID**
  surviving at least two poll intervals (≥ 5 min).
- `~/.paperclip/watchdog.err` empty after the first minute post-install.
- `~/.paperclip/watchdog.log` contains at least one `tick_start` /
  `tick_end` pair from the daemon loop.

## 7. Out of scope

- Phase 4.1 QA methodology overhaul — spec §7.4 of GIM-63 already
  requires real post-install smoke ("install → launchctl load →
  daemon stays up"); the role execution drifted from the spec rather
  than the spec being wrong. Fix goes in a separate followup slice.
- Changing any behavior or config of the watchdog itself. This is a
  pure CLI-plumbing bug.
- Optional `--force` / `--discover-companies` flag wiring on `install`
  (currently present in `_build_parser` but ignored by `_cmd_install`).
  Tracked as a separate micro-issue if deemed useful.

## 8. References

- Paperclip issue 69 (`5468fb03-84bd-4d16-b93d-d867141af001`) —
  original reproduction and operator-side diagnosis.
- GIM-63 spec (`docs/superpowers/specs/2026-04-21-GIM-63-agent-watchdog-design.md`)
  — §7.4 live smoke test, §9 step 4 "Install on iMac".
- GIM-63 merge: `053d93f` (develop tip at time of this spec).
- Broken source locations:
  - `services/watchdog/src/gimle_watchdog/__main__.py:26-46` (`_build_parser`)
  - `services/watchdog/src/gimle_watchdog/service.py:11-60` (renderers)
  - `services/watchdog/tests/test_service.py` (fixture-only test)
