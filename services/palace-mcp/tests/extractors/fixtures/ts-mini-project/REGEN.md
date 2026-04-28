# Regenerating index.scip

The committed `index.scip` is a pre-built fixture. To regenerate it after
changing the source files:

```bash
cd services/palace-mcp/tests/extractors/fixtures/ts-mini-project
npm install
npx @sourcegraph/scip-typescript index --output index.scip
```

Or use the top-level Makefile target:

```bash
make regen-ts-fixture
```

## Fixture contents

- `src/greeter.ts` — `Greeter` class, `Greeting` interface, `formatGreeting` function
- `src/index.ts` — usage site exercising all public symbols

The fixture intentionally has both defs (role=1) and uses (role=0) so 3-phase
bootstrap tests can verify phase1_defs and phase2_user_uses checkpoint writes.
