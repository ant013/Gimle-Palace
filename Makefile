# Makefile — top-level helpers for Gimle Palace development.
# Run from the repository root.

PALACE_MCP_DIR := services/palace-mcp
TS_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/ts-mini-project
PY_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/py-mini-project
JVM_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/jvm-mini-project
SOLIDITY_FIXTURE_DIR := $(PALACE_MCP_DIR)/tests/extractors/fixtures/oz-v5-mini-project

.PHONY: regen-ts-fixture regen-py-fixture regen-jvm-fixture regen-solidity-fixture

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

# Regenerate the committed JVM SCIP fixture.
# Requires: Java 17+, Gradle 8+, and scip-java (npx @sourcegraph/scip-java).
regen-jvm-fixture:
	cd $(JVM_FIXTURE_DIR) && gradle wrapper
	cd $(JVM_FIXTURE_DIR) && ./gradlew compileKotlin compileJava
	cd $(JVM_FIXTURE_DIR) && npx @sourcegraph/scip-java index --output index.scip
	@echo "Regenerated $(JVM_FIXTURE_DIR)/index.scip"

# Regenerate the committed Solidity SCIP fixture.
# Requires: slither-analyzer>=0.11.5 (pip install slither-analyzer) + solc 0.8.20+.
# slither-analyzer is NOT in pyproject.toml (cbor2 Rust dep); install manually first.
regen-solidity-fixture:
	cd $(PALACE_MCP_DIR) && uv run python -m palace_mcp.scip_emit.solidity \
		--project-root $(abspath $(SOLIDITY_FIXTURE_DIR)) \
		--output $(abspath $(SOLIDITY_FIXTURE_DIR))/index.scip
	@echo "Regenerated $(SOLIDITY_FIXTURE_DIR)/index.scip"
