PYTHON ?= python3
COMMON_SRC ?= ../renquant-common/src
BASE_DATA_SRC ?= ../renquant-base-data/src
ARTIFACTS_SRC ?= ../renquant-artifacts/src
STRATEGY_SRC ?= ../renquant-strategy-104/src
GBDT_SRC ?= ../renquant-model-gbdt/src
PATCHTST_SRC ?= ../renquant-model-patchtst/src
PIPELINE_SRC ?= ../renquant-pipeline/src
EXECUTION_SRC ?= ../renquant-execution/src
BACKTESTING_SRC ?= ../renquant-backtesting/src
export PYTHONPATH := $(COMMON_SRC):$(BASE_DATA_SRC):$(ARTIFACTS_SRC):$(STRATEGY_SRC):$(GBDT_SRC):$(PATCHTST_SRC):$(PIPELINE_SRC):$(EXECUTION_SRC):$(BACKTESTING_SRC):src:$(PYTHONPATH)

.PHONY: test doctor

test:
	$(PYTHON) -m pytest -q

doctor:
	$(PYTHON) -c "from renquant_orchestrator import DailyRunPipeline; from renquant_common import Pipeline; print('renquant-orchestrator ok')"
