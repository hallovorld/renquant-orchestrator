ifneq ("$(wildcard ../RenQuant/.venv/bin/python)","")
PYTHON ?= ../RenQuant/.venv/bin/python
else
PYTHON ?= python3
endif
COMMON_SRC ?= ../renquant-common/src
BASE_DATA_SRC ?= ../renquant-base-data/src
ARTIFACTS_SRC ?= ../renquant-artifacts/src
STRATEGY_SRC ?= ../renquant-strategy-104/src
# GBDT + PatchTST families merged into renquant-model (RFC P3); the standalone
# renquant-model-gbdt / renquant-model-patchtst repos are archived. Point both at
# the merged repo so we import the current engine, not the pre-merge package.
GBDT_SRC ?= ../renquant-model/src
PATCHTST_SRC ?= ../renquant-model/src
PIPELINE_SRC ?= ../renquant-pipeline/src
EXECUTION_SRC ?= ../renquant-execution/src
BACKTESTING_SRC ?= ../renquant-backtesting/src
export PYTHONPATH := $(COMMON_SRC):$(BASE_DATA_SRC):$(ARTIFACTS_SRC):$(STRATEGY_SRC):$(GBDT_SRC):$(PATCHTST_SRC):$(PIPELINE_SRC):$(EXECUTION_SRC):$(BACKTESTING_SRC):src:$(PYTHONPATH)

.PHONY: test doctor daily-contract engineering-census agent-identity-codex agent-identity-claude

test:
	$(PYTHON) -m pytest -q

doctor:
	$(PYTHON) -c "from renquant_orchestrator import DailyRunPipeline; from renquant_common import Pipeline; print('renquant-orchestrator ok')"

agent-identity-codex:
	bash scripts/check_agent_gh_identity.sh codex haorensjtu-dev

agent-identity-claude:
	bash scripts/check_agent_gh_identity.sh claude hallovorld

engineering-census:
	$(PYTHON) -m renquant_orchestrator engineering-census --strict

daily-contract:
	$(PYTHON) -m renquant_orchestrator daily-contract \
		--strategy-config $(STRATEGY_CONFIG) \
		--output-dir $(OUTPUT_DIR) \
		--run-id $(RUN_ID) \
		--as-of $(AS_OF) \
		--code-commit $(CODE_COMMIT)
