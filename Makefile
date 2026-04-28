# Makefile — top-level helpers for Gimle Palace development.
# Run from the repository root.

PALACE_MCP_DIR := services/palace-mcp
TS_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/ts-mini-project
PY_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/py-mini-project

.PHONY: regen-ts-fixture regen-py-fixture

# Regenerate the committed TypeScript SCIP fixture.
# Requires: node/npm + @sourcegraph/scip-typescript (auto-installed via npx).
regen-ts-fixture:
	cd $(TS_FIXTURE_DIR) && npm install
	cd $(TS_FIXTURE_DIR) && npx @sourcegraph/scip-typescript index --output index.scip
	@echo "Regenerated $(TS_FIXTURE_DIR)/index.scip"

# Regenerate the committed Python SCIP fixture.
# Requires: node/npm + @sourcegraph/scip-python (auto-installed via npx).
regen-py-fixture:
	cd $(PY_FIXTURE_DIR) && npx @sourcegraph/scip-python index \
		--project-name pymini \
		--project-version 1.0.0 \
		--output index.scip src/
	@echo "Regenerated $(PY_FIXTURE_DIR)/index.scip"
