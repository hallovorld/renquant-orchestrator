from __future__ import annotations

import importlib
import sys


def test_orchestrator_import_does_not_pull_live_broker_runtime() -> None:
    importlib.import_module("renquant_orchestrator")

    forbidden_prefixes = (
        "alpaca",
        "ib_insync",
        "live",
        "torch",
        "xgboost",
    )
    offenders = sorted(
        name for name in sys.modules
        if name in forbidden_prefixes or name.startswith(forbidden_prefixes)
    )
    assert offenders == []
