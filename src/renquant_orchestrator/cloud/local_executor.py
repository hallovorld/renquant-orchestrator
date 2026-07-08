"""Local ProcessPoolExecutor backend — wraps the existing sweep runner."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .executor import (
    BacktestRequest,
    BacktestResult,
    BatchSummary,
    DataManifest,
    PreflightReport,
    compute_result_checksum,
)


class LocalExecutor:
    """ProcessPoolExecutor backend (today's behavior, wrapped in the protocol).

    Set use_threads=True for test contexts where the execute_fn is not picklable.
    """

    def __init__(self, max_workers: int | None = None, *, use_threads: bool = False):
        self._max_workers = max_workers or max(1, (os.cpu_count() or 4) - 2)
        self._use_threads = use_threads

    def execute_batch(
        self,
        requests: list[BacktestRequest],
        *,
        on_result: Callable[[BacktestResult], None],
        on_error: Callable[[str, Exception], None],
        max_concurrent: int = 100,
        execute_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> BatchSummary:
        from concurrent.futures import (
            ProcessPoolExecutor,
            ThreadPoolExecutor,
            as_completed,
        )

        if execute_fn is None:
            raise ValueError("LocalExecutor requires execute_fn")

        workers = min(self._max_workers, max_concurrent, len(requests))
        t0 = time.monotonic()
        summary = BatchSummary()

        pool_cls = ThreadPoolExecutor if self._use_threads else ProcessPoolExecutor
        with pool_cls(max_workers=workers) as pool:
            futures = {}
            for req in requests:
                fut = pool.submit(execute_fn, req)
                futures[fut] = req.variant_name

            for fut in as_completed(futures):
                vname = futures[fut]
                try:
                    raw = fut.result()
                    result = BacktestResult(
                        variant_name=raw["variant_name"],
                        role=raw.get("role", "candidate"),
                        config_fingerprint=raw.get("config_fingerprint", ""),
                        worker_id=f"local-pid-{os.getpid()}",
                        volume_commit_id=None,
                        code_image_id=None,
                        started_at=raw.get("started_at", ""),
                        finished_at=raw.get("finished_at", ""),
                        elapsed_seconds=raw.get("elapsed_seconds", 0.0),
                        peak_memory_mb=raw.get("peak_memory_mb", 0.0),
                        seeds=raw.get("seeds", []),
                        per_seed=raw.get("per_seed", []),
                    )
                    on_result(result)
                    summary.n_completed += 1
                except Exception as exc:
                    on_error(vname, exc)
                    summary.n_failed += 1

        summary.total_seconds = time.monotonic() - t0
        return summary

    def preflight(
        self,
        data_manifest: DataManifest,
        *,
        n_variants: int = 0,
        n_seeds_per_variant: int = 0,
    ) -> PreflightReport:
        return PreflightReport(passed=True, checks={"local": True})

    def sync_data(self, local_paths: dict[str, str]) -> DataManifest:
        files: dict[str, str] = {}
        total_bytes = 0
        for label, path_str in local_paths.items():
            p = Path(path_str)
            if p.is_file():
                files[label] = hashlib.sha256(p.read_bytes()).hexdigest()
                total_bytes += p.stat().st_size
            elif p.is_dir():
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        files[str(f.relative_to(p))] = hashlib.sha256(
                            f.read_bytes()
                        ).hexdigest()
                        total_bytes += f.stat().st_size
        return DataManifest(
            commit_id=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            files=files,
            total_bytes=total_bytes,
        )
