.PHONY: regen-ts-fixture regen-py-fixture regen-all

regen-ts-fixture:
	cd ts-mini-project && npm install && npx @sourcegraph/scip-typescript index --output index.scip

regen-py-fixture:
	cd py-mini-project && npx @sourcegraph/scip-python index --project-name pymini --output index.scip

regen-all: regen-ts-fixture regen-py-fixture
