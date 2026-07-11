"""BacktestExecutor protocol and data objects — platform-agnostic interface.

Scope (doc/design/2026-07-07-cloud-backtest-compute.md §0/§9, r2, approved):
this abstraction exists so W1 (concentration-cap / Kelly-style parameter
sweeps) and W4 (placebo/shuffle significance) share ONE local-vs-Modal
execution interface, per Phase 1's "refactor run_concentration_cap_sweep.py
to use BacktestExecutor" step. It is NOT a general-purpose "run any Python
function on any cloud backend" engine — W2/W12 (GPU model training) are
explicitly out of scope here (belongs in renquant-model), and a
general-purpose cloud-backtest substrate beyond W1/W4 belongs in
renquant-backtesting, not orchestrator. Keep new BacktestExecutor
implementations and call sites scoped to W1/W4-shaped variant sweeps.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class BacktestRequest:
    variant_name: str
    role: str
    config_json: str
    volume_commit_id: str | None
    seeds: list[int]
    start: str
    end: str
    initial_cash: float
    incumbent_turnover: float | None


@dataclass(frozen=True)
class BacktestResult:
    variant_name: str
    role: str
    config_fingerprint: str
    worker_id: str
    volume_commit_id: str | None
    code_image_id: str | None
    started_at: str
    finished_at: str
    elapsed_seconds: float
    peak_memory_mb: float
    seeds: list[int]
    per_seed: list[dict[str, Any]]
    equity_curves: dict[int, bytes] | None = None
    trade_logs: dict[int, bytes] | None = None
    result_checksum: str = ""
    # sha256 of the operator-approved pre-registration (workload manifest)
    # the dispatching executor verified this run against; empty for
    # backends that don't pre-register (e.g. local).
    workload_manifest_sha256: str = ""


@dataclass
class BatchSummary:
    total_seconds: float = 0.0
    cost_usd: float = 0.0
    n_completed: int = 0
    n_failed: int = 0


@dataclass(frozen=True)
class DataManifest:
    commit_id: str | None
    timestamp: str
    files: dict[str, str]
    total_bytes: int


@dataclass
class PreflightReport:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)


class BacktestExecutor(Protocol):
    def execute_batch(
        self,
        requests: list[BacktestRequest],
        *,
        on_result: Callable[[BacktestResult], None],
        on_error: Callable[[str, Exception], None],
        max_concurrent: int = 100,
    ) -> BatchSummary: ...

    def preflight(
        self,
        data_manifest: DataManifest,
        *,
        n_variants: int = 0,
        n_seeds_per_variant: int = 0,
    ) -> PreflightReport: ...

    def sync_data(self, local_paths: dict[str, str]) -> DataManifest: ...


def compute_result_checksum(result_dict: dict[str, Any]) -> str:
    d = {k: v for k, v in result_dict.items() if k != "result_checksum"}
    canonical = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
