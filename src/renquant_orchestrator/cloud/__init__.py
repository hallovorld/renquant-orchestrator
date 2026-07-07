"""Cloud burst execution for the orchestrator's concentration-cap sweep.

This module provides a backend abstraction so the existing sweep runner
(scripts/run_concentration_cap_sweep.py) can dispatch variant backtests
to Modal instead of a local ProcessPoolExecutor. It is NOT a generic
cloud-backtest engine — it wraps the single sweep workflow that
orchestrator already owns. If a general cloud backtest substrate is
needed in the future, it belongs in renquant-backtesting.
"""
from __future__ import annotations
