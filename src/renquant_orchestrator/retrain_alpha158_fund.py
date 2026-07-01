"""Weekly alpha158+fund retrain pipeline owned by renquant-orchestrator.

This is a transitional multirepo workflow: alpha158 materialization and
fund-panel merge run through ``renquant-base-data``. The GBDT scorer and
calibrator run through pinned ``renquant-model`` code.
It preserves the weekly trust boundary: callers provide staging output paths,
and this module never promotes production artifacts.
"""
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import TYPE_CHECKING, Callable

from renquant_common import Job, Pipeline, Task

from .runtime_paths import (
    default_github_root,
    default_repo_root,
    default_strategy_config_candidates,
    resolve_subrepo_root,
)
from .weekly_apy_monitor import post_ntfy

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


log = logging.getLogger("renquant_orchestrator.retrain_alpha158_fund")

# Panel training-universe sourcing + freshness. The panel build
# (renquant_base_data.alpha158_qlib_panel.LoadUniverseJob) reads the FULL
# training universe from ``transformer_universe_inventory.json`` (tier_A +
# tier_B tickers, ~292 names) — NOT the ~142-ticker live watchlist. Only the
# watchlist gets fresh daily bars as a live-path side effect, so the extra
# research tickers silently froze the panel (~2026-02-13 after the fwd_60d clip)
# in May 2026. These constants drive the refresh + guard tasks that fix that.
DEFAULT_INVENTORY_FILENAME = "transformer_universe_inventory.json"
DEFAULT_OHLCV_DIRNAME = "ohlcv"
DEFAULT_OHLCV_TIMEOUT_SEC = 30.0
DEFAULT_FRESHNESS_STALE_AFTER_DAYS = 10
DEFAULT_FRESHNESS_MAX_STALE_FRACTION = 0.10
DEFAULT_NTFY_TOPIC = "renquant"


GITHUB = default_github_root()
DEFAULT_REPO_DIR = default_repo_root()
_REQUIRED_REPO_PATHS = [
    Path("data"),
]
DEFAULT_STRATEGY_CONFIG, LEGACY_STRATEGY_CONFIG = default_strategy_config_candidates(
    repo_root=DEFAULT_REPO_DIR,
    github_root=GITHUB,
)


@dataclass
class RetrainContext:
    repo_dir: Path
    xgb_artifact_out: Path
    calibrator_out: Path
    python: str = sys.executable
    truncate_to_sec_max: bool = True
    # Canonical prod recipe (umbrella's scripts/train_production_model.py) keeps
    # the 3 sentiment features (mean_sentiment / n_articles_log /
    # sentiment_pos_share) and uses the runtime-zeroing gate via the trainer.
    # We mirror that here so the orchestrator path produces a 172-feature
    # artifact matching the WF v2 manifest cuts (config_fingerprint parity).
    # See CLAUDE.md §7.5 "single source of truth".
    drop_sentiment: bool = False
    strategy_config_path: Path | None = None
    dry_run: bool = False
    commands: list[list[str]] = field(default_factory=list)

    # ── Full-universe OHLCV refresh + partial-freeze guard ──────────────────
    # (the load-bearing model-staleness root cause; see module docstring above).
    refresh_ohlcv: bool = True
    # Explicit universe override; when None the universe is sourced from the
    # panel inventory (tier_A + tier_B) exactly as the panel build reads it.
    panel_universe: list[str] | None = None
    inventory_path: Path | None = None
    # Dependency-injected incremental fetch callable. When None it resolves to
    # the real ``renquant_base_data.loaders.data.fetch_ohlcv_incremental`` at
    # runtime (import-resolved via the retrain subrepo PYTHONPATH). Injected in
    # tests so no real network fetch / production data write ever happens.
    fetch_fn: "Callable[..., pd.DataFrame] | None" = None
    ohlcv_timeout_sec: float = DEFAULT_OHLCV_TIMEOUT_SEC
    # Optional injectable reader for a ticker's on-disk OHLCV max date. When
    # None the guard reads ``data/ohlcv/<ticker>/1d.parquet`` directly.
    ohlcv_max_date_fn: "Callable[[str], dt.date | None] | None" = None
    freshness_stale_after_days: int = DEFAULT_FRESHNESS_STALE_AFTER_DAYS
    freshness_max_stale_fraction: float = DEFAULT_FRESHNESS_MAX_STALE_FRACTION
    # Fail-closed by default, mirroring the umbrella data-scan's strict default:
    # >max-stale-fraction of the panel universe stale after a refresh is a real
    # training-input integrity failure. Set False to only warn (ntfy) + proceed.
    freshness_fail_on_stale: bool = True
    ntfy_topic: str = DEFAULT_NTFY_TOPIC
    quiet: bool = False
    # Populated at runtime by the refresh / guard tasks (audit surface).
    ohlcv_max_dates: dict[str, "dt.date | None"] = field(default_factory=dict)
    ohlcv_refresh_summary: dict[str, int] = field(default_factory=dict)
    freshness_report: dict = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        return self.repo_dir / "data"

    @property
    def ohlcv_dir(self) -> Path:
        return self.data_dir / DEFAULT_OHLCV_DIRNAME

    @property
    def resolved_inventory_path(self) -> Path:
        if self.inventory_path is not None:
            return self.inventory_path
        return self.data_dir / DEFAULT_INVENTORY_FILENAME

    @property
    def strategy_config(self) -> Path:
        if self.strategy_config_path is not None:
            return self.strategy_config_path
        if DEFAULT_STRATEGY_CONFIG.exists():
            return DEFAULT_STRATEGY_CONFIG
        return self.repo_dir / "backtesting" / "renquant_104" / "strategy_config.json"


_SUBREPO_NAMES = [
    "renquant-orchestrator",
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
    "renquant-strategy-104",
    "renquant-backtesting",
]


def _subrepo_srcs(repo_dir: Path) -> list[Path]:
    subrepo_root = resolve_subrepo_root(repo_dir)
    return [subrepo_root / name / "src" for name in _SUBREPO_NAMES]


def _subrepo_pythonpath(repo_dir: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(os.environ if env is None else env)
    srcs = _subrepo_srcs(repo_dir)
    missing = [src for src in srcs if not src.is_dir()]
    if out.get("RENQUANT_STRICT_SUBREPO_PATHS") == "1" and missing:
        joined = ", ".join(str(src) for src in missing)
        raise FileNotFoundError(f"missing multirepo source paths: {joined}")
    existing = out.get("PYTHONPATH", "")
    out["PYTHONPATH"] = os.pathsep.join([*(str(src) for src in srcs), existing])
    out.setdefault("RENQUANT_REPO_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_DATA_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_STRATEGY_DIR", str(repo_dir / "backtesting" / "renquant_104"))
    strategy_config = DEFAULT_STRATEGY_CONFIG if DEFAULT_STRATEGY_CONFIG.exists() else LEGACY_STRATEGY_CONFIG
    out.setdefault("RENQUANT_STRATEGY_CONFIG", str(strategy_config))
    return out


def _run(ctx: RetrainContext, cmd: list[str], *, cwd: Path | None = None) -> None:
    ctx.commands.append(cmd)
    if ctx.dry_run:
        return
    result = subprocess.run(cmd, cwd=str(cwd or ctx.repo_dir), env=_subrepo_pythonpath(ctx.repo_dir))
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(cmd)}")


def _read_json_object(path: Path, label: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{label} did not produce {path}")
    if path.stat().st_size <= 2:
        raise ValueError(f"{label} artifact is too small: {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return payload


def _validate_scorer_artifact(path: Path) -> None:
    payload = _read_json_object(path, "GBDT training")
    if not payload.get("config_fingerprint"):
        raise ValueError(f"GBDT artifact missing config_fingerprint: {path}")
    expected = dt.datetime.utcnow().strftime("%Y-%m-%d")
    if payload.get("trained_date") != expected:
        raise ValueError(
            f"GBDT artifact trained_date={payload.get('trained_date')!r}; expected {expected}: {path}"
        )


def _validate_calibrator_artifact(path: Path) -> None:
    payload = _read_json_object(path, "calibrator refit")
    if not payload:
        raise ValueError(f"calibrator artifact is empty: {path}")


def _resolve_panel_universe(ctx: RetrainContext) -> list[str]:
    """Source the FULL panel training universe (tier_A + tier_B), NOT just the
    ~142-ticker live watchlist.

    This mirrors ``renquant_base_data.alpha158_qlib_panel.LoadUniverseJob``,
    which reads ``tier_A_tickers`` + ``tier_B_tickers`` from
    ``transformer_universe_inventory.json``. An explicit ``ctx.panel_universe``
    wins so callers can pin the universe. Returns a sorted, de-duplicated list;
    an unreadable / missing inventory yields an empty list (logged), so the
    refresh + guard degrade to safe no-ops rather than aborting the retrain.
    """
    if ctx.panel_universe:
        return sorted(dict.fromkeys(str(t) for t in ctx.panel_universe))
    inv_path = ctx.resolved_inventory_path
    if not inv_path.exists():
        log.warning("panel universe inventory not found: %s — universe empty", inv_path)
        return []
    try:
        inv = json.loads(inv_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("failed to read panel universe inventory %s: %s", inv_path, exc)
        return []
    universe = set(inv.get("tier_A_tickers", [])) | set(inv.get("tier_B_tickers", []))
    return sorted(str(t) for t in universe)


def _default_fetch_fn() -> "Callable[..., pd.DataFrame]":
    """Resolve the real base-data incremental OHLCV primitive at runtime.

    ``fetch_ohlcv_incremental`` lives in ``renquant-base-data``
    (``renquant_base_data.loaders.data``) and is import-resolved via the subrepo
    PYTHONPATH the retrain sets up. It is dependency-injected via
    ``RetrainContext.fetch_fn`` so this orchestrator task is unit-testable
    without a network fetch. Non-destructive: cache-first, incremental delta
    only, append-merge, timeout-protected; delisted names return their stale
    cache with a warning rather than raising.
    """
    from renquant_base_data.loaders.data import fetch_ohlcv_incremental  # noqa: PLC0415

    return fetch_ohlcv_incremental


def _df_max_date(df: "pd.DataFrame | None") -> "dt.date | None":
    """Latest bar date of an OHLCV frame (DatetimeIndex or a ``date`` column)."""
    if df is None:
        return None
    try:
        import pandas as pd  # noqa: PLC0415

        if getattr(df, "empty", True):
            return None
        idx = df.index
        if isinstance(idx, pd.DatetimeIndex):
            return idx.max().date()
        for col in ("date", "Date", "datetime"):
            if col in getattr(df, "columns", []):
                return pd.to_datetime(df[col]).max().date()
        return pd.to_datetime(idx).max().date()
    except Exception:  # pragma: no cover - defensive; malformed frame
        return None


def _default_ohlcv_max_date(ohlcv_dir: Path, ticker: str) -> "dt.date | None":
    path = ohlcv_dir / ticker / "1d.parquet"
    if not path.exists():
        return None
    try:
        import pandas as pd  # noqa: PLC0415

        return _df_max_date(pd.read_parquet(path))
    except Exception:  # pragma: no cover - defensive; unreadable parquet
        return None


def _resolve_ohlcv_max_date(ctx: RetrainContext, ticker: str) -> "dt.date | None":
    # Prefer the refresh-captured map (avoids re-reading parquet); otherwise use
    # an injectable reader, defaulting to the on-disk raw OHLCV bars.
    if ticker in ctx.ohlcv_max_dates:
        return ctx.ohlcv_max_dates[ticker]
    if ctx.ohlcv_max_date_fn is not None:
        return ctx.ohlcv_max_date_fn(ticker)
    return _default_ohlcv_max_date(ctx.ohlcv_dir, ticker)


def _frontier(dates) -> "dt.date | None":
    known = [d for d in dates if d is not None]
    return max(known) if known else None


def _trading_days_between(start: "dt.date", end: "dt.date") -> int:
    """Business-day gap (Mon-Fri) between two dates — a holiday-agnostic proxy
    for trading days. Non-negative; 0 when ``start >= end``."""
    if start >= end:
        return 0
    import numpy as np  # noqa: PLC0415

    return int(np.busday_count(start, end))


class RefreshFullUniverseOhlcvTask(Task):
    """Refresh daily OHLCV bars for the FULL panel training universe.

    ROOT CAUSE (2026-05 panel freeze): only the ~142-ticker live watchlist gets
    fresh bars daily (a live-path side effect). The ~150 extra research tickers
    in the ~292-ticker panel universe had no refresh cadence, so half the panel
    froze at ~2026-02-13 (after the correct fwd_60d label clip). This task
    iterates the WHOLE panel universe and calls the incremental (append-merge,
    non-destructive, timeout-protected) fetch for each ticker BEFORE the panel
    build. It is resilient: a single ticker's failure or delisting NEVER aborts
    the retrain — delisted names return their stale cache and are counted, not
    fatal. Records a summary (n_refreshed / n_stale / n_delisted / n_failed).
    """

    def run(self, ctx: RetrainContext) -> bool | None:
        universe = _resolve_panel_universe(ctx)
        summary = {
            "n_universe": len(universe),
            "n_refreshed": 0,
            "n_stale": 0,
            "n_delisted": 0,
            "n_failed": 0,
        }
        ctx.ohlcv_refresh_summary = summary
        if not ctx.refresh_ohlcv:
            log.info("OHLCV refresh disabled (refresh_ohlcv=False); skipping")
            return True
        if not universe:
            log.warning("panel universe empty; nothing to refresh")
            return True
        if ctx.dry_run:
            log.info("[dry-run] would refresh OHLCV for %d panel tickers", len(universe))
            return True

        fetch_fn = ctx.fetch_fn or _default_fetch_fn()
        max_dates: dict[str, dt.date | None] = {}
        failed: set[str] = set()
        for ticker in universe:
            try:
                df = fetch_fn(ticker, timeout_sec=ctx.ohlcv_timeout_sec)
            except Exception as exc:  # one ticker must never abort the retrain
                failed.add(ticker)
                max_dates[ticker] = None
                log.warning("OHLCV refresh failed for %s: %s", ticker, exc)
                continue
            max_dates[ticker] = _df_max_date(df)
        ctx.ohlcv_max_dates = max_dates

        # Classify against the batch frontier (freshest bar any ticker returned)
        # into disjoint buckets so the counts sum to the universe size.
        frontier = _frontier(max_dates.values())
        for ticker, md in max_dates.items():
            if ticker in failed:
                summary["n_failed"] += 1
            elif md is None:
                summary["n_delisted"] += 1
            elif (
                frontier is not None
                and _trading_days_between(md, frontier) > ctx.freshness_stale_after_days
            ):
                summary["n_stale"] += 1
            else:
                summary["n_refreshed"] += 1
        log.info(
            "OHLCV refresh: universe=%d refreshed=%d stale=%d delisted=%d failed=%d",
            summary["n_universe"],
            summary["n_refreshed"],
            summary["n_stale"],
            summary["n_delisted"],
            summary["n_failed"],
        )
        return True


class PanelUniverseFreshnessGuardTask(Task):
    """Guard against a *partial* panel-universe freeze — the silent failure mode
    that let ~148 tickers sit at 2026-05-12 while the ~142-ticker watchlist
    stayed fresh and the watchlist-only scan passed.

    It reads each panel ticker's RAW OHLCV bar max date — NOT the built panel,
    which legitimately ends ~today-60 trading days after the (correct) fwd_60d
    label clip. Reading raw bars means an on-frontier panel never trips this
    guard: genuine input staleness (the bars themselves old) is distinguished
    from the expected fwd_60d frontier. A ticker is 'stale' when its newest bar
    lags the universe frontier (the freshest bar any ticker has) by more than
    ``freshness_stale_after_days`` trading days. If more than
    ``freshness_max_stale_fraction`` of the universe is stale, emit a LOUD ntfy
    alert and — per ``freshness_fail_on_stale`` — either fail the retrain
    (default, fail-closed) or proceed with the warning.
    """

    def run(self, ctx: RetrainContext) -> bool | None:
        universe = _resolve_panel_universe(ctx)
        if not universe:
            log.warning("freshness guard: panel universe empty; cannot assess — skipping")
            return True
        dates = {t: _resolve_ohlcv_max_date(ctx, t) for t in universe}
        known = {t: d for t, d in dates.items() if d is not None}
        if not known:
            log.warning("freshness guard: no OHLCV max dates resolvable — skipping")
            return True

        frontier = max(known.values())
        stale = {
            t: d
            for t, d in known.items()
            if _trading_days_between(d, frontier) > ctx.freshness_stale_after_days
        }
        missing = {t for t, d in dates.items() if d is None}
        n_stale = len(stale) + len(missing)
        fraction = n_stale / len(universe)
        worst = sorted(
            ((_trading_days_between(d, frontier), t) for t, d in stale.items()),
            reverse=True,
        )[:10]
        report = {
            "as_of_frontier": frontier.isoformat(),
            "n_universe": len(universe),
            "n_stale": n_stale,
            "n_missing": len(missing),
            "stale_fraction": round(fraction, 4),
            "stale_after_days": ctx.freshness_stale_after_days,
            "max_stale_fraction": ctx.freshness_max_stale_fraction,
            "worst_examples": [[lag, t] for lag, t in worst],
        }
        ctx.freshness_report = report

        if fraction <= ctx.freshness_max_stale_fraction:
            log.info(
                "freshness guard OK: %d/%d stale (%.1f%% <= %.1f%%), frontier=%s",
                n_stale,
                len(universe),
                fraction * 100,
                ctx.freshness_max_stale_fraction * 100,
                frontier.isoformat(),
            )
            return True

        worst_str = ", ".join(f"{t}(-{lag}d)" for lag, t in worst[:8])
        title = "RenQuant retrain PANEL-FREEZE"
        body = (
            f"{n_stale}/{len(universe)} panel tickers stale "
            f"({fraction:.1%} > {ctx.freshness_max_stale_fraction:.0%}); "
            f"bars lag frontier {frontier.isoformat()} by "
            f">{ctx.freshness_stale_after_days} trading days. "
            f"Worst: {worst_str}. "
            f"{'FAILING retrain' if ctx.freshness_fail_on_stale else 'proceeding with warning'}."
        )
        if not ctx.quiet:
            post_ntfy(title, body, ctx.ntfy_topic)
        log.error("freshness guard TRIPPED: %s", body)
        if ctx.freshness_fail_on_stale:
            raise RuntimeError(body)
        return True


class BuildAlpha158PanelTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        _run(
            ctx,
            [
                ctx.python,
                "-m",
                "renquant_base_data.alpha158_qlib_panel",
                "--data-dir",
                str(ctx.data_dir),
            ],
        )
        return True


class MergeFundFeaturesTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_base_data.alpha158_fund_panel",
            "--data-dir",
            str(ctx.data_dir),
        ]
        if ctx.truncate_to_sec_max:
            cmd.append("--truncate-to-sec-max")
        _run(ctx, cmd)
        return True


class TrainGbdtScorerTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_orchestrator.train_gbdt",
            "--data-dir",
            str(ctx.data_dir),
            "--strategy-config",
            str(ctx.strategy_config),
            "--output-path",
            str(ctx.xgb_artifact_out),
        ]
        if ctx.drop_sentiment:
            cmd.append("--drop-sentiment")
        _run(ctx, cmd, cwd=ctx.repo_dir)
        if ctx.dry_run:
            return True
        _validate_scorer_artifact(ctx.xgb_artifact_out)
        return True


class RefitCalibratorTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_model_gbdt.fit_calibrator_alpha158_fund",
            "--data-dir",
            str(ctx.data_dir),
            "--scorer-artifact",
            str(ctx.xgb_artifact_out),
            "--out",
            str(ctx.calibrator_out),
        ]
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_calibrator_artifact(ctx.calibrator_out)
        return True


class RetrainJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [
            RefreshFullUniverseOhlcvTask(),
            PanelUniverseFreshnessGuardTask(),
            BuildAlpha158PanelTask(),
            MergeFundFeaturesTask(),
            TrainGbdtScorerTask(),
            RefitCalibratorTask(),
        ]


def build_pipeline() -> Pipeline:
    return Pipeline([RetrainJob()], name="weekly-alpha158-fund-retrain")


def _resolve(repo_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_dir / path


def _default_xgb_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json"


def _default_calibrator_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-rank-calibration.json"


def _staging_path(path: Path) -> Path:
    return path.with_suffix(".staging.json")


def _validate_repo_dir(repo_dir: Path) -> None:
    missing = [rel for rel in _REQUIRED_REPO_PATHS if not (repo_dir / rel).exists()]
    if missing:
        joined = ", ".join(str(rel) for rel in missing)
        raise FileNotFoundError(f"repo-dir is not a usable RenQuant checkout; missing: {joined}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--xgb-artifact-out", default=None)
    parser.add_argument("--calibrator-out", default=None)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Use default *.staging.json candidate artifact paths when explicit outputs are omitted.",
    )
    parser.add_argument("--strategy-config", type=Path, default=None)
    parser.add_argument(
        "--drop-sentiment",
        default=False,
        action=argparse.BooleanOptionalAction,
        help=(
            "Drop the 3 sentiment features (mean_sentiment / n_articles_log / "
            "sentiment_pos_share) → 169-feature artifact. DEFAULT IS FALSE to "
            "match the canonical prod recipe in umbrella's "
            "scripts/train_production_model.py (172 features w/ runtime "
            "sentiment gate). Override with --drop-sentiment only for research."
        ),
    )
    parser.add_argument("--truncate-to-sec-max", default=True, action=argparse.BooleanOptionalAction)
    parser.add_argument("--dry-run", action="store_true")
    # ── Full-universe OHLCV refresh + partial-freeze guard ──────────────────
    parser.add_argument(
        "--refresh-ohlcv",
        default=True,
        action=argparse.BooleanOptionalAction,
        help=(
            "Refresh daily OHLCV for the FULL panel universe (tier_A + tier_B) "
            "before the panel build, so the ~150 research tickers outside the "
            "live watchlist do not silently freeze (2026-05 root cause). "
            "--no-refresh-ohlcv skips (guard still runs)."
        ),
    )
    parser.add_argument("--ohlcv-timeout-sec", type=float, default=DEFAULT_OHLCV_TIMEOUT_SEC)
    parser.add_argument(
        "--panel-universe-file",
        type=Path,
        default=None,
        help=(
            "Optional JSON file: a plain list of tickers, OR an inventory object "
            "with tier_A_tickers/tier_B_tickers. Default: "
            "<data-dir>/transformer_universe_inventory.json (what the panel "
            "build reads)."
        ),
    )
    parser.add_argument(
        "--freshness-stale-after-days",
        type=int,
        default=DEFAULT_FRESHNESS_STALE_AFTER_DAYS,
        help="A panel ticker is stale when its newest bar lags the universe frontier by more than this many trading days.",
    )
    parser.add_argument(
        "--freshness-max-stale-fraction",
        type=float,
        default=DEFAULT_FRESHNESS_MAX_STALE_FRACTION,
        help="Guard trips when the stale fraction of the panel universe exceeds this.",
    )
    parser.add_argument(
        "--freshness-fail-on-stale",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Fail the retrain when the guard trips (default, fail-closed). --no-freshness-fail-on-stale only warns (ntfy) and proceeds.",
    )
    parser.add_argument("--ntfy-topic", default=DEFAULT_NTFY_TOPIC)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    _validate_repo_dir(repo_dir)
    xgb_artifact_out = (
        _resolve(repo_dir, args.xgb_artifact_out)
        if args.xgb_artifact_out
        else _default_xgb_artifact(repo_dir)
    )
    calibrator_out = (
        _resolve(repo_dir, args.calibrator_out)
        if args.calibrator_out
        else _default_calibrator_artifact(repo_dir)
    )
    if args.staged:
        if not args.xgb_artifact_out:
            xgb_artifact_out = _staging_path(xgb_artifact_out)
        if not args.calibrator_out:
            calibrator_out = _staging_path(calibrator_out)
    panel_universe: list[str] | None = None
    inventory_path: Path | None = None
    if args.panel_universe_file:
        puf = args.panel_universe_file.expanduser().resolve()
        try:
            payload = json.loads(puf.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"--panel-universe-file unreadable: {puf}: {exc}")
        if isinstance(payload, list):
            panel_universe = [str(t) for t in payload]
        elif isinstance(payload, dict):
            inventory_path = puf
        else:
            raise SystemExit(f"--panel-universe-file must be a JSON list or object: {puf}")
    ctx = RetrainContext(
        repo_dir=repo_dir,
        xgb_artifact_out=xgb_artifact_out,
        calibrator_out=calibrator_out,
        strategy_config_path=args.strategy_config.expanduser().resolve() if args.strategy_config else None,
        drop_sentiment=args.drop_sentiment,
        truncate_to_sec_max=args.truncate_to_sec_max,
        dry_run=args.dry_run,
        refresh_ohlcv=args.refresh_ohlcv,
        panel_universe=panel_universe,
        inventory_path=inventory_path,
        ohlcv_timeout_sec=args.ohlcv_timeout_sec,
        freshness_stale_after_days=args.freshness_stale_after_days,
        freshness_max_stale_fraction=args.freshness_max_stale_fraction,
        freshness_fail_on_stale=args.freshness_fail_on_stale,
        ntfy_topic=args.ntfy_topic,
    )
    build_pipeline().run(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
