"""Deterministic data-dependency contract for remote sweep execution.

Enumerates every file the remote worker needs BEFORE spending cloud money,
so the preflight check is a bounded verification step — not a reactive
discovery mechanism that finds the next missing input on each paid run.

Two verification surfaces:

1. **Staged** (local, pre-sync) — checks that all required files exist in
   the local staging dirs / bundle before uploading to the Modal Volume.
   Called from run_sweep_modal.py's preflight step.

2. **Remote** (container, pre-backtest) — checks that all required files
   are reachable on the container's filesystem after Volume mount + bundle
   unpack.  Called from modal_app.py's worker function before importing any
   backtest code, so a missing file produces a clear enumerated error
   instead of a mid-backtest fail-close.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ContractCheck:
    name: str
    required: bool
    path: str
    exists: bool = False
    detail: str = ""


@dataclass
class ContractReport:
    passed: bool
    checks: list[ContractCheck] = field(default_factory=list)

    @property
    def failed(self) -> list[ContractCheck]:
        return [c for c in self.checks if c.required and not c.exists]

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            status = "PASS" if c.exists else ("FAIL" if c.required else "WARN")
            line = f"  [{status}] {c.name}: {c.path}"
            if c.detail:
                line += f" — {c.detail}"
            lines.append(line)
        return "\n".join(lines)


def verify_staged(
    *,
    bundle_dir: Path,
    ohlcv_staging: Path,
    data_staging: Path,
    base_config: dict[str, Any],
    manifest_path: str,
) -> ContractReport:
    """Verify all required files exist in local staging dirs before sync.

    This is the LOCAL half of the contract — run before uploading to the
    Modal Volume so missing files are caught without spending cloud money.
    """
    checks: list[ContractCheck] = []

    # ── 1. Bundle code entry points ──
    _code_entries = [
        ("kernel/panel_pipeline/job_panel_scoring.py", "kernel panel scorer"),
        ("sim/runner.py", "backtest runner"),
        ("scripts/run_concentration_cap_sweep.py", "sweep entry point"),
    ]
    for rel, label in _code_entries:
        p = bundle_dir / rel
        checks.append(ContractCheck(
            name=f"bundle:{label}",
            required=True,
            path=str(p),
            exists=p.exists(),
        ))

    # ── 2. Subrepo packages ──
    _required_packages = [
        "renquant-common", "renquant-pipeline", "renquant-model",
        "renquant-execution", "renquant-strategy-104", "renquant-backtesting",
    ]
    for repo in _required_packages:
        p = bundle_dir / "subrepos" / repo / "src"
        checks.append(ContractCheck(
            name=f"subrepo:{repo}",
            required=True,
            path=str(p),
            exists=p.is_dir(),
        ))

    # ── 3. Walk-forward manifest + artifacts ──
    manifest_file = bundle_dir / "kernel" / manifest_path
    checks.append(ContractCheck(
        name="wf_manifest",
        required=True,
        path=str(manifest_file),
        exists=manifest_file.exists(),
    ))
    if manifest_file.exists():
        wf = json.loads(manifest_file.read_text())
        for i, retrain in enumerate(wf.get("retrains", [])):
            for key in ("artifact_uri", "calibrator_uri"):
                uri = retrain.get(key)
                if not uri:
                    continue
                p = bundle_dir / "kernel" / uri
                checks.append(ContractCheck(
                    name=f"wf_artifact:{key}[{i}]",
                    required=True,
                    path=str(p),
                    exists=p.exists(),
                    detail=uri,
                ))

    # ── 4. Fundamentals ──
    _fund_files = [
        "sec_fundamentals_daily.parquet",
        "alpha158_291_fundamental_dataset.parquet",
    ]
    for fname in _fund_files:
        p = data_staging / fname
        checks.append(ContractCheck(
            name=f"fundamentals:{fname}",
            required=True,
            path=str(p),
            exists=p.exists(),
        ))

    # ── 4b. PEAD/SUE/sentiment feature dirs (warn-only) ──
    # job_panel_scoring.py's feature-health check only logs a warning for
    # all-zero PEAD/SUE/sentiment columns — it does not fail-close the day
    # the way missing fundamentals does. required=False here matches that
    # actual runtime behavior: absence degrades result quality silently
    # rather than timing out, so it's worth flagging in the preflight
    # report without blocking the sweep on it.
    for dir_name in ("earnings_surprise", "news_sentiment_alpaca"):
        p = data_staging / dir_name
        has_files = p.is_dir() and any(p.iterdir())
        checks.append(ContractCheck(
            name=f"feature_dir:{dir_name}",
            required=False,
            path=str(p),
            exists=has_files,
            detail="PEAD/SUE/sentiment features zero-impute if missing (warning-only, not fail-closed)",
        ))

    # ── 5. OHLCV per symbol ──
    watchlist = set(base_config.get("watchlist", []))
    watchlist |= set(base_config.get("sector_etf_map", {}).values())
    watchlist.add(base_config.get("benchmark", "SPY"))
    for sym in sorted(watchlist):
        p = ohlcv_staging / sym / "1d.parquet"
        checks.append(ContractCheck(
            name=f"ohlcv:{sym}",
            required=True,
            path=str(p),
            exists=p.exists(),
        ))

    # ── 6. Base config ──
    config_in_bundle = bundle_dir / "kernel" / "strategy_config.sim_kelly_ab_admoff.json"
    checks.append(ContractCheck(
        name="base_config_in_bundle",
        required=False,
        path=str(config_in_bundle),
        exists=config_in_bundle.exists(),
        detail="config is passed as JSON in request, not read from bundle",
    ))

    report = ContractReport(
        passed=all(c.exists for c in checks if c.required),
        checks=checks,
    )
    return report


def verify_remote(*, app_root: str) -> ContractReport:
    """Verify all required files exist on the remote container before backtest.

    Called inside the Modal worker function (modal_app.py) BEFORE importing
    any backtest code. Produces a clear, enumerated error if anything is
    missing — no mid-backtest fail-close discovery.
    """
    import os

    checks: list[ContractCheck] = []

    # ── 1. Code entry points ──
    _code_entries = [
        ("kernel/panel_pipeline/job_panel_scoring.py", "kernel panel scorer"),
        ("sim/runner.py", "backtest runner"),
        ("scripts/run_concentration_cap_sweep.py", "sweep entry point"),
    ]
    for rel, label in _code_entries:
        p = f"{app_root}/{rel}"
        checks.append(ContractCheck(
            name=f"code:{label}",
            required=True,
            path=p,
            exists=os.path.exists(p),
        ))

    # ── 2. Subrepo packages ──
    _required_packages = [
        "renquant-common", "renquant-pipeline", "renquant-model",
        "renquant-execution", "renquant-strategy-104", "renquant-backtesting",
    ]
    for repo in _required_packages:
        p = f"{app_root}/subrepos/{repo}/src"
        checks.append(ContractCheck(
            name=f"subrepo:{repo}",
            required=True,
            path=p,
            exists=os.path.isdir(p),
        ))

    # ── 3. Fundamentals — check ALL resolution paths ──
    _fund_names = [
        "sec_fundamentals_daily.parquet",
        "alpha158_291_fundamental_dataset.parquet",
    ]
    for fname in _fund_names:
        found = False
        searched = []
        for candidate in (
            f"/data/data/{fname}",
            f"/data/{fname}",
            f"{app_root}/data/{fname}",
        ):
            searched.append(candidate)
            if os.path.exists(candidate):
                found = True
                break
        checks.append(ContractCheck(
            name=f"fundamentals:{fname}",
            required=True,
            path=searched[0],
            exists=found,
            detail=f"searched: {', '.join(searched)}" if not found else "",
        ))

    # ── 3b. PEAD/SUE/sentiment feature dirs (warn-only, mirrors verify_staged) ──
    for dir_name in ("earnings_surprise", "news_sentiment_alpaca"):
        found = False
        searched = []
        for candidate in (
            f"/data/data/{dir_name}",
            f"/data/{dir_name}",
            f"{app_root}/data/{dir_name}",
        ):
            searched.append(candidate)
            if os.path.isdir(candidate) and os.listdir(candidate):
                found = True
                break
        checks.append(ContractCheck(
            name=f"feature_dir:{dir_name}",
            required=False,
            path=searched[0],
            exists=found,
            detail=(
                "PEAD/SUE/sentiment features zero-impute if missing (warning-only, not fail-closed)"
                if found else f"searched: {', '.join(searched)}"
            ),
        ))

    # ── 4. OHLCV directory ──
    ohlcv_dir = "/data/ohlcv"
    has_ohlcv = os.path.isdir(ohlcv_dir)
    n_symbols = 0
    if has_ohlcv:
        n_symbols = len([
            d for d in os.listdir(ohlcv_dir)
            if os.path.isdir(f"{ohlcv_dir}/{d}")
        ])
    checks.append(ContractCheck(
        name="ohlcv_dir",
        required=True,
        path=ohlcv_dir,
        exists=has_ohlcv and n_symbols > 0,
        detail=f"{n_symbols} symbols" if has_ohlcv else "directory missing",
    ))

    # ── 5. Walk-forward manifest (search common locations) ──
    wf_found = False
    wf_searched = []
    for candidate in (
        f"{app_root}/kernel/artifacts/sim/walkforward_manifest_v2_20260602.json",
        f"/data/artifacts/walkforward_manifest_v2_20260602.json",
    ):
        wf_searched.append(candidate)
        if os.path.exists(candidate):
            wf_found = True
            break
    checks.append(ContractCheck(
        name="wf_manifest",
        required=True,
        path=wf_searched[0],
        exists=wf_found,
        detail=f"searched: {', '.join(wf_searched)}" if not wf_found else "",
    ))

    # ── 6. Kernel-resolved parents[4] fundamentals path ──
    # The kernel copy of job_panel_scoring.py uses
    # Path(__file__).resolve().parents[4] / "data" / fname
    # On Modal, .resolve() follows the Volume symlink, producing a path
    # under /__modal/volumes/<id>/ — verify the symlinks placed by
    # modal_app.py's setup block actually landed.
    from pathlib import Path as _P
    kernel_scoring = _P(f"{app_root}/kernel/panel_pipeline/job_panel_scoring.py")
    if kernel_scoring.exists():
        resolved_parents4 = kernel_scoring.resolve().parents[4]
        for fname in _fund_names:
            resolved_path = resolved_parents4 / "data" / fname
            checks.append(ContractCheck(
                name=f"kernel_resolved:{fname}",
                required=True,
                path=str(resolved_path),
                exists=resolved_path.exists(),
                detail=f"parents[4]={resolved_parents4}",
            ))

    report = ContractReport(
        passed=all(c.exists for c in checks if c.required),
        checks=checks,
    )
    return report
