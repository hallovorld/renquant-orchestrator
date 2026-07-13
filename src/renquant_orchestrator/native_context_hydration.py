"""Hydrate the pinned pipeline's REAL InferenceContext from a native context JSON.

Closes the GOAL-1 blocker found by the first real §2a two-arm session
(2026-07-10 bundle): ``native-live-inference`` passed a
``SimpleNamespace(context_json)`` straight into the pinned pipeline's
``InferencePipeline.run(ctx)``, which needs the actual
``renquant_pipeline.context.InferenceContext`` dataclass (first missing
attribute: ``ctx.today`` at ``pp_inference.py:307``; then config / prices /
holdings / regime_state / ...). The native offboard path had only ever been
fixture-tested.

Seam choice (justified): hydration lives HERE, invoked by
``native_live_inference`` immediately before ``InferencePipeline.run`` — NOT
inside ``native-live-context``. The context JSON is a serializable,
digest-verified audit artifact (#456's sealed-snapshot verification is
unchanged and still gates it); runtime objects (OHLCV DataFrames, loaded
scorers, HoldingState instances) cannot live in JSON and must be materialized
in the process that runs the pipeline.

Boundary contract (§2a): every import here is pipeline-/pinned-repo-owned —
``renquant_pipeline.context.InferenceContext``, ``kernel.regime.RegimeState``,
``kernel.exits.HoldingState``, ``kernel.data.LocalStore`` (READONLY parquet
loads only; no network fetch, no writes). NO umbrella module is imported
anywhere on this path. The panel-scoring module alias installed by
:func:`install_native_panel_scoring_alias` routes one pipeline-internal module
to another pipeline-internal module — the SAME routing production's bridge
applies (``live_bridge._force_alias``) so Phase-3 runs the real
``kernel.panel_pipeline`` scorer (its ``LoadScorerTask`` loads the model, and
``ApplyGlobalCalibrationTask`` the calibrator, from the strategy config) —
without it, the bare ``renquant_pipeline.panel_scoring`` module resolves to
the renquant105 runtime job, which expects frozen snapshot scores this
experiment does not have.

Deliberate v1 simplifications (recorded, arm-symmetric so they cancel in the
§2a paired design):

* per-ticker tournament models load through the pipeline's own
  ``LoadUniverseJob`` (staleness/floor/auto-drop filters included) when a
  strategy dir is given; a missing ``models/`` dir degrades to an empty
  model map (sell-safe: ``_make_sell_tctx`` tolerates ``model=None``).
* holdings' ``entry_date`` uses the umbrella's own documented sentinel
  (today − 31d) when the account snapshot carries no entry date — shadow arm
  books start fresh, so tenure-gated rules see an aged position rather than a
  perpetually-locked day-0 one.
* ``gmm`` / ``corr_matrix`` / ``earnings_calendar`` are loaded best-effort
  from the standard artifact refs and default to ``None`` (RegimeJob is
  explicitly null-guarded: empty GMM probs → neutral regime).
"""
from __future__ import annotations

import datetime as dt
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

NATIVE_HYDRATION_SOURCE = "renquant_orchestrator.native_context_hydration"

#: The SAME module routing production's bridge installs (live_bridge
#: `_force_alias`), reproduced here for the native path — every target is a
#: PINNED-subrepo module (renquant_pipeline / renquant_backtesting), never
#: umbrella code:
#: * pp_inference Phase-3 (`from renquant_pipeline.panel_scoring import
#:   PanelScoringJob`) must resolve to the real kernel panel scorer;
#: * pp_inference's meta-label veto imports
#:   `renquant_pipeline.kernel.meta_label.task_meta_label_veto`, which lives
#:   in the pinned renquant-backtesting repo (the pipeline's own
#:   kernel/meta_label carries only the triple-barrier primitives).
PANEL_SCORING_ALIAS = "renquant_pipeline.panel_scoring"
PANEL_SCORING_TARGET = "renquant_pipeline.kernel.panel_pipeline.job_panel_scoring"
META_LABEL_ALIAS = "renquant_pipeline.kernel.meta_label"
META_LABEL_TARGET = "renquant_backtesting.meta_label"

#: Umbrella-documented fallback when a held position has no recorded entry
#: date (see RunnerAdapter.make_context ENTRY-DATE-SEED sentinel).
ENTRY_DATE_SENTINEL_DAYS = 31

#: Best-effort context artifacts (all optional; None-tolerated by the
#: pipeline). Refs resolve through the single artifact_resolver authority.
OPTIONAL_CONTEXT_ARTIFACT_REFS = {
    "gmm": "artifacts/spy-gmm-regime.json",
    "corr_matrix": "artifacts/watchlist-correlation.json",
    "earnings_calendar": "artifacts/earnings-calendar.json",
}

OhlcvLoader = Callable[[str], Any]


class HydrationError(RuntimeError):
    """The context payload cannot be hydrated into a runnable pipeline context."""


def install_native_pipeline_aliases() -> list[str]:
    """Install the pinned-subrepo module routings production's bridge forces.

    Byte-identical in effect to the ``_force_alias`` calls live_bridge
    applies before every live run, limited to the two the InferencePipeline
    path needs. Idempotent. Returns the alias strings for audit metadata.
    Every target module belongs to a pinned subrepo — no umbrella import.
    """
    installed: list[str] = []
    for alias, target_name in (
        (PANEL_SCORING_ALIAS, PANEL_SCORING_TARGET),
        (META_LABEL_ALIAS, META_LABEL_TARGET),
    ):
        target = importlib.import_module(target_name)
        sys.modules[alias] = target
        # submodule imports (`renquant_pipeline.kernel.meta_label.task_...`)
        # resolve through the parent package attribute + sys.modules entries,
        # so also alias every already-importable child the target exposes.
        target_path = getattr(target, "__path__", None)
        if target_path is not None:
            import pkgutil  # noqa: PLC0415

            for info in pkgutil.iter_modules(target_path):
                child = importlib.import_module(f"{target_name}.{info.name}")
                sys.modules[f"{alias}.{info.name}"] = child
        installed.append(f"{alias}<-{target_name}")
    return installed


def install_native_panel_scoring_alias() -> str:
    """Back-compat single-alias entry; prefer install_native_pipeline_aliases."""
    return install_native_pipeline_aliases()[0]


def _default_ohlcv_loader(
    *,
    ohlcv_dir: str | Path | None,
    repo_root: str | Path | None,
) -> OhlcvLoader:
    """READONLY parquet loads through the pinned pipeline's own LocalStore.

    Never fetches from the network and never writes — the daily data jobs own
    freshness; DataFreshnessGateTask inside the pipeline is the staleness
    authority and fails closed on stale frames.
    """
    from renquant_pipeline.public import LocalStore  # noqa: PLC0415

    if ohlcv_dir is not None:
        data_dir: Path | None = Path(ohlcv_dir)
    elif repo_root is not None:
        data_dir = Path(repo_root) / "data" / "ohlcv"
    else:
        data_dir = None  # LocalStore's own env-based resolution
    store = LocalStore(data_dir)

    def _load(symbol: str):
        return store.load(symbol)

    return _load


def _normalized_positions(account_snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize the sealed account snapshot's positions through the pinned
    pipeline's own live-state contract normalizer (single implementation)."""
    from renquant_pipeline import account_snapshot_from_live_state  # noqa: PLC0415

    normalized = account_snapshot_from_live_state(dict(account_snapshot))
    positions = normalized.get("positions") or {}
    return {str(t): dict(p) for t, p in positions.items() if isinstance(p, dict)}


def _load_optional_artifacts(
    *,
    strategy_dir: str | Path | None,
    repo_root: str | Path | None,
) -> dict[str, Any]:
    """Best-effort gmm/corr/earnings artifacts; None on any miss (pipeline
    is null-guarded for all three)."""
    out: dict[str, Any] = {name: None for name in OPTIONAL_CONTEXT_ARTIFACT_REFS}
    if strategy_dir is None and repo_root is None:
        return out
    from .artifact_resolver import resolve_artifact  # noqa: PLC0415

    for name, ref in OPTIONAL_CONTEXT_ARTIFACT_REFS.items():
        try:
            resolved = resolve_artifact(
                ref,
                strategy_dir=strategy_dir or repo_root,
                repo_root=repo_root or strategy_dir,
                verify_sha=False,
            )
            out[name] = json.loads(resolved.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, FileNotFoundError):
            out[name] = None
    return out


def _required_closed_session(session_date: "dt.date") -> tuple["dt.date", str]:
    """The last COMPLETED NYSE session as of the session-close watermark
    (session_date 16:00:01 America/New_York) — via the pinned pipeline's own
    calendar helper, weekday fallback if the calendar package is missing.
    Returns (required_session_date, watermark_iso)."""
    import pandas as pd  # noqa: PLC0415
    from renquant_pipeline.public import (  # noqa: PLC0415
        last_completed_nyse_session as _last_completed_nyse_session,
    )

    watermark = pd.Timestamp(
        f"{session_date.isoformat()} 16:00:01", tz="America/New_York"
    )
    required = _last_completed_nyse_session(watermark)
    if required is None:  # calendar unavailable — weekday approximation
        required = session_date
        while required.weekday() >= 5:
            required -= dt.timedelta(days=1)
    return required, watermark.isoformat()


def validate_market_bars(
    ohlcv: dict[str, Any],
    *,
    session_date: "dt.date",
) -> dict[str, Any]:
    """Seal + validate every consumed bar against the session window (r2).

    Each symbol's LAST bar timestamp must land inside
    ``[required_closed_session, session_date]``: a bar AFTER the decision
    cutoff is lookahead (future data on a rerun), a bar BEFORE the required
    closed session is stale — both REJECT the whole hydration (fail-closed;
    the arm exits nonzero and the runner's paired rule invalidates BOTH
    arms). Returns the sealed validity block (per-symbol bar timestamps +
    session-close watermark + window bounds) for the run bundle."""
    required_session, watermark_iso = _required_closed_session(session_date)
    bar_timestamps: dict[str, str] = {}
    stale: list[str] = []
    future: list[str] = []
    for symbol in sorted(ohlcv):
        frame = ohlcv[symbol]
        try:
            last_ts = frame.index[-1]
            bar_date = last_ts.date() if hasattr(last_ts, "date") else None
        except Exception:  # noqa: BLE001
            bar_date = None
            last_ts = None
        if bar_date is None:
            stale.append(f"{symbol}@<unreadable-bar-timestamp>")
            continue
        bar_timestamps[symbol] = str(last_ts)
        if bar_date > session_date:
            future.append(f"{symbol}@{bar_date.isoformat()}")
        elif bar_date < required_session:
            stale.append(f"{symbol}@{bar_date.isoformat()}")
    if stale or future:
        raise HydrationError(
            "market bars outside the valid session window "
            f"[required_closed_session={required_session.isoformat()}, "
            f"decision_cutoff={session_date.isoformat()}]: "
            f"future(lookahead)={future[:5]} ({len(future)} total), "
            f"stale={stale[:5]} ({len(stale)} total) — refusing to score a "
            "stale or rerun-poisoned world"
        )
    return {
        "required_closed_session": required_session.isoformat(),
        "decision_cutoff": session_date.isoformat(),
        "session_close_watermark": watermark_iso,
        "bar_timestamps": bar_timestamps,
    }


def rewrite_config_artifact_refs(
    config: dict[str, Any],
    *,
    strategy_dir: str | Path | None,
    repo_root: str | Path | None,
    artifact_store: str | Path,
) -> dict[str, str]:
    """Rewrite the config's panel model/calibrator refs to RESOLVED absolute
    paths (in-memory only — the config file on disk is never touched).

    Why: the kernel's ``LoadScorerTask`` joins relative ``artifact_path`` refs
    lexically against ``config["_strategy_dir"]``; prod configs author them as
    umbrella-layout parent walks (``../../artifacts/<...>``), which resolve to
    nothing from a pinned checkout. With a manifest-declared artifact store,
    the SINGLE resolution authority (:mod:`..artifact_resolver`) resolves the
    ref here and the kernel receives an absolute path it uses as-is.

    Identity safety: the paired-world config sha is computed from the RAW
    config file bytes at precheck (unchanged by this rewrite), artifact
    identity is separately enforced by ``model_content_sha256`` verification
    against what this config resolves, and ``artifact_path`` is NOT in
    ``renquant_common.config_consistency._model_relevant_fields`` — so the
    panel config fingerprint (P-CONFIG-FP) is unaffected. Returns
    ``{ref: resolved_absolute_path}`` for the hydration report.
    """
    from .artifact_resolver import resolve_artifact  # noqa: PLC0415
    from .native_live_context import panel_artifact_refs  # noqa: PLC0415

    try:
        model_ref, calibrator_ref = panel_artifact_refs(config)
    except ValueError as exc:
        raise HydrationError(f"cannot rewrite artifact refs: {exc}") from exc

    anchor = strategy_dir or repo_root
    if anchor is None:
        raise HydrationError(
            "artifact_store rewrite needs strategy_dir or repo_root as the "
            "geometric fallback anchor"
        )

    rewritten: dict[str, str] = {}

    def _resolve(ref: str) -> str:
        try:
            resolved = resolve_artifact(
                ref,
                strategy_dir=anchor,
                repo_root=repo_root or anchor,
                artifact_store=artifact_store,
                verify_sha=False,
            )
        except FileNotFoundError as exc:
            raise HydrationError(str(exc)) from exc
        rewritten[ref] = str(resolved.path)
        return str(resolved.path)

    panel = (
        (config.get("ranking") or {}).get("panel_scoring")
        or config.get("panel_ltr")
        or {}
    )
    panel["artifact_path"] = _resolve(model_ref)
    if calibrator_ref is not None:
        (panel.get("global_calibration") or {})["artifact_path"] = _resolve(
            calibrator_ref
        )
    return rewritten


def rewrite_config_log_containment(
    config: dict[str, Any],
    *,
    log_containment_dir: str | Path,
) -> dict[str, str]:
    """Redirect strategy-dir-relative kernel log WRITERS into
    ``log_containment_dir`` (in-memory only — the config file on disk is
    never touched).

    Write containment (2026-07-11 incident): the kernel's
    ``AdmissionShadowLoggerTask`` defaults its JSONL under
    ``config["_strategy_dir"]/logs`` — on the §2a arm path that is the
    MANIFEST-PINNED strategy checkout, so a successful arm run dirties the
    tree and the NEXT session's ``verify_run_manifest`` fails closed
    (self-poisoning). This rewrites every known strategy-dir-relative
    WRITER's target path to live under the arm's own directory instead.

    ONLY known write-destination keys are touched
    (``admission_shadow.path``, ``sleeve.log_path`` when present) — no
    other config field is read or modified, so nothing that affects a
    trading DECISION or OUTPUT (sizing, scoring, gating, order generation)
    can be altered by this rewrite; see
    ``test_rewrite_config_log_containment_*`` for the exact-diff proof.

    Identity safety: same argument as :func:`rewrite_config_artifact_refs`
    — the paired-world config sha is computed from the RAW config file
    bytes at precheck (unchanged by this in-memory rewrite), and these
    keys are not in ``renquant_common.config_consistency
    ._model_relevant_fields`` (the P-CONFIG-FP projection).

    Returns ``{writer_name: contained_absolute_path}`` for the hydration
    report.
    """
    containment = Path(log_containment_dir)
    contained_logs: dict[str, str] = {}

    shadow_cfg = config.get("admission_shadow")
    if not isinstance(shadow_cfg, dict):
        shadow_cfg = {}
        config["admission_shadow"] = shadow_cfg
    target = str(containment / "admission_shadow.jsonl")
    shadow_cfg["path"] = target
    contained_logs["admission_shadow"] = target

    sleeve_cfg = config.get("sleeve")
    if isinstance(sleeve_cfg, dict) and sleeve_cfg.get("log_path"):
        target = str(containment / Path(str(sleeve_cfg["log_path"])).name)
        sleeve_cfg["log_path"] = target
        contained_logs["sleeve"] = target

    return contained_logs


def hydrate_pipeline_context(
    context_payload: dict[str, Any],
    *,
    session_date: str,
    broker_name: str | None = None,
    strategy_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    ohlcv_dir: str | Path | None = None,
    ohlcv_loader: OhlcvLoader | None = None,
    data_revision: str | None = None,
    artifact_store: str | Path | None = None,
    log_containment_dir: str | Path | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build the pinned pipeline's real ``InferenceContext`` from the verified
    context JSON payload. Returns ``(ctx, hydration_report)``.

    Sources, per the §2a contract:

    * ``today`` ← ``session_date`` (the runner's frozen session identity);
    * ``config`` ← the resolved strategy config already inside the payload
      (digest/artifact-verified by native-live-context, #456);
    * OHLCV frames + spy_returns ← the pinned pipeline's LocalStore in
      READONLY mode (universe = config watchlist + benchmark + held tickers);
    * prices ← broker marks derived from the SEALED account snapshot
      (market_value / quantity), falling back to last local close;
    * holdings / cash / portfolio value ← the SEALED account snapshot,
      normalized by the pipeline's own live-state contract;
    * models / calibrator ← loaded downstream by the pipeline's OWN
      LoadScorerTask / ApplyGlobalCalibrationTask from this config (see
      :func:`install_native_panel_scoring_alias`);
    * ``regime_state`` ← a fresh ``RegimeState()`` (REQUIRED — the dataclass
      default of ``None`` crashes CUSUMTask), with the regime then computed
      by the pipeline's own RegimeJob.
    """
    from renquant_pipeline.context import InferenceContext  # noqa: PLC0415
    from renquant_pipeline.public import HoldingState  # noqa: PLC0415
    from renquant_pipeline.public import RegimeState  # noqa: PLC0415

    config = context_payload.get("config")
    if not isinstance(config, dict) or not config:
        raise HydrationError("context payload has no resolved strategy config")
    config = dict(config)
    watchlist = [str(t) for t in (config.get("watchlist") or [])]
    if not watchlist:
        raise HydrationError("strategy config has an empty watchlist")
    try:
        today = dt.date.fromisoformat(str(session_date))
    except ValueError as exc:
        raise HydrationError(f"invalid session_date {session_date!r}: {exc}") from exc
    if strategy_dir is not None:
        # the kernel panel scorer resolves relative artifact_path refs
        # against config["_strategy_dir"] — same convention the umbrella
        # adapter uses.
        config.setdefault("_strategy_dir", str(strategy_dir))
    if artifact_store is not None:
        rewritten = rewrite_config_artifact_refs(
            config,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            artifact_store=artifact_store,
        )
    else:
        rewritten = {}
    if log_containment_dir is not None:
        contained_logs = rewrite_config_log_containment(
            config, log_containment_dir=log_containment_dir,
        )
    else:
        contained_logs = {}

    account_snapshot = context_payload.get("account_snapshot") or {}
    if not isinstance(account_snapshot, dict):
        raise HydrationError("context payload account_snapshot must be an object")
    positions = _normalized_positions(account_snapshot)
    cash = float(account_snapshot.get("cash") or 0.0)
    portfolio_value = float(account_snapshot.get("portfolio_value") or 0.0)

    benchmark = str(config.get("benchmark") or "SPY")
    # DataFreshnessGateTask's expected set is watchlist + holdings +
    # benchmark + every sector_etf_map value — load exactly that universe
    # (the first real replay failed closed on the sector/bond ETFs).
    sector_etfs = [
        str(sym) for sym in (config.get("sector_etf_map") or {}).values() if sym
    ]
    symbols = list(dict.fromkeys(
        [*watchlist, benchmark, *sector_etfs, *positions.keys()]
    ))

    load_ohlcv = ohlcv_loader or _default_ohlcv_loader(
        ohlcv_dir=ohlcv_dir, repo_root=repo_root,
    )
    ohlcv: dict[str, Any] = {}
    missing_ohlcv: list[str] = []
    for symbol in symbols:
        try:
            frame = load_ohlcv(symbol)
        except Exception as exc:  # noqa: BLE001 - one bad frame must not dark the run
            frame = None
            missing_ohlcv.append(f"{symbol}:{type(exc).__name__}")
        if frame is None:
            if symbol not in missing_ohlcv:
                missing_ohlcv.append(symbol)
            continue
        ohlcv[symbol] = frame
    if not ohlcv:
        raise HydrationError(
            "no OHLCV frame loaded for any symbol — cannot run inference on "
            "an empty market (checked readonly local store only; the daily "
            "data jobs own freshness)"
        )

    # r2 (Codex on #460): prove every consumed bar is the last CLOSED bar
    # for the session — reject stale (before the required closed session)
    # and future (after the decision cutoff, i.e. rerun lookahead) bars,
    # and seal the per-symbol bar timestamps + session-close watermark.
    bar_validity = validate_market_bars(ohlcv, session_date=today)

    # prices: broker marks from the sealed account snapshot, local close fallback
    prices: dict[str, float] = {}
    for ticker, pos in positions.items():
        try:
            quantity = float(pos.get("quantity") or 0.0)
            market_value = float(pos.get("market_value") or 0.0)
        except (TypeError, ValueError):
            continue
        if quantity > 0 and market_value > 0:
            prices[ticker] = market_value / quantity
    for symbol, frame in ohlcv.items():
        if symbol in prices:
            continue
        try:
            close = float(frame["close"].iloc[-1])
        except Exception:  # noqa: BLE001
            continue
        if close > 0:
            prices[symbol] = close

    spy_returns: list[float] = []
    benchmark_frame = ohlcv.get(benchmark)
    if benchmark_frame is not None:
        try:
            spy_returns = [
                float(v)
                for v in benchmark_frame["close"].pct_change().dropna().values[-100:]
            ]
        except Exception:  # noqa: BLE001
            spy_returns = []

    sentinel_entry = today - dt.timedelta(days=ENTRY_DATE_SENTINEL_DAYS)
    holdings: dict[str, Any] = {}
    for ticker, pos in positions.items():
        try:
            quantity = float(pos.get("quantity") or 0.0)
        except (TypeError, ValueError):
            continue
        if quantity <= 0:
            continue
        entry_price = float(pos.get("avg_entry_price") or prices.get(ticker, 0.0) or 0.0)
        mark = prices.get(ticker, entry_price)
        holdings[ticker] = HoldingState(
            entry_price=entry_price,
            entry_date=sentinel_entry,
            high_watermark=max(entry_price, mark),
            shares=quantity,
        )

    optional = _load_optional_artifacts(strategy_dir=strategy_dir, repo_root=repo_root)

    # Per-ticker tournament models through the pipeline's OWN loader job —
    # the same LoadUniverseJob production's runner calls (staleness /
    # universe-floor / auto-drop filters included). Without these the legacy
    # candidate funnel can never produce a buy (buy-admission gates on the
    # per-ticker tournament, not the panel), which would leave both §2a arms
    # permanently at deployed fraction 0.
    models: dict[str, Any] = {}
    universe_rejections: list[tuple[str, str]] = []
    if strategy_dir is not None:
        from renquant_pipeline.public import (  # noqa: PLC0415
            LoadUniverseJob,
            UniverseContext,
        )

        uctx = UniverseContext(
            config=config,
            strategy_dir=Path(strategy_dir),
            broker_name=broker_name,
            held_tickers=set(holdings),
            as_of_date=today,
        )
        LoadUniverseJob().run(uctx)
        models = dict(uctx.loaded_models)
        universe_rejections = list(uctx.rejections)
        # same downstream-visibility convention the production runner uses
        config["_universe_rejections"] = dict(universe_rejections)

    ctx = InferenceContext(
        config=config,
        today=today,
        run_timestamp=dt.datetime.now(dt.timezone.utc),
        broker_name=broker_name,
        ohlcv=ohlcv,
        spy_returns=spy_returns,
        models=models,
        gmm=optional["gmm"],
        corr_matrix=optional["corr_matrix"],
        earnings_calendar=optional["earnings_calendar"],
        holdings=holdings,
        prices=prices,
        portfolio_value=portfolio_value,
        cash=cash,
        hwm=portfolio_value,
        regime_state=RegimeState(),
        regime_counts={},
    )
    # Snapshot-extraction quality + runtime-contract compatibility: the
    # output extractor (live_context_snapshot_from_live_context) and the
    # runtime panel job read these getattr-style.
    ctx.strategy_config = config
    ctx.market_snapshot = dict(context_payload.get("market_snapshot") or {})
    ctx.order_intents = []
    open_orders = account_snapshot.get("open_orders") or []
    ctx.pending_broker_tickers = sorted({
        str(o.get("symbol") or o.get("ticker"))
        for o in open_orders
        if isinstance(o, dict) and (o.get("symbol") or o.get("ticker"))
    })

    report = {
        "source": NATIVE_HYDRATION_SOURCE,
        "session_date": str(session_date),
        "broker_name": broker_name,
        "benchmark": benchmark,
        "watchlist_size": len(watchlist),
        "ohlcv_loaded": len(ohlcv),
        "ohlcv_missing": missing_ohlcv,
        "holdings": sorted(holdings),
        "priced_symbols": len(prices),
        "spy_return_bars": len(spy_returns),
        "cash": cash,
        "portfolio_value": portfolio_value,
        "pending_broker_tickers": list(ctx.pending_broker_tickers),
        "optional_artifacts": {k: v is not None for k, v in optional.items()},
        "entry_date_sentinel": sentinel_entry.isoformat(),
        "models_loaded": len(models),
        "model_rejections": len(universe_rejections),
        "ohlcv_source": str(ohlcv_dir) if ohlcv_dir is not None else (
            str(Path(repo_root) / "data" / "ohlcv") if repo_root is not None
            else "<env-resolved LocalStore>"
        ),
        "data_revision": data_revision,
        "bar_validity": bar_validity,
        "artifact_store": (
            str(artifact_store) if artifact_store is not None else None
        ),
        "artifact_refs_rewritten": rewritten,
        "log_containment": contained_logs,
    }
    return ctx, report


__all__ = [
    "ENTRY_DATE_SENTINEL_DAYS",
    "rewrite_config_artifact_refs",
    "HydrationError",
    "NATIVE_HYDRATION_SOURCE",
    "OPTIONAL_CONTEXT_ARTIFACT_REFS",
    "META_LABEL_ALIAS",
    "META_LABEL_TARGET",
    "PANEL_SCORING_ALIAS",
    "PANEL_SCORING_TARGET",
    "hydrate_pipeline_context",
    "install_native_panel_scoring_alias",
    "install_native_pipeline_aliases",
    "validate_market_bars",
]
