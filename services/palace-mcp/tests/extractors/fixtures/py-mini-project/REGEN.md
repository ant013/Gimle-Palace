# Regenerating index.scip

The committed `index.scip` is a pre-built fixture. To regenerate it after
changing the source files:

```bash
cd services/palace-mcp/tests/extractors/fixtures/py-mini-project
npx @sourcegraph/scip-python index \
  --project-name pymini \
  --project-version 1.0.0 \
  --output index.scip src/
```

Or use the top-level Makefile target:

```bash
make regen-py-fixture
```

## Fixture contents

- `src/pymini/greeter.py` — `Greeter` class, `Greeting` dataclass, `format_greeting` function
- `src/main.py` — usage site exercising all public symbols

The fixture intentionally has both defs (role=1) and uses (role=0) so 3-phase
bootstrap tests can verify phase1_defs and phase2_user_uses checkpoint writes.
