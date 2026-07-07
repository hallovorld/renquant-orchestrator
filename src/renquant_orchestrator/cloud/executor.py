"""BacktestExecutor protocol and data objects — platform-agnostic interface."""
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

    def preflight(self, data_manifest: DataManifest) -> PreflightReport: ...

    def sync_data(self, local_paths: dict[str, str]) -> DataManifest: ...


def compute_result_checksum(result_dict: dict[str, Any]) -> str:
    d = {k: v for k, v in result_dict.items() if k != "result_checksum"}
    canonical = json.dumps(d, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
