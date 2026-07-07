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
import functools
import json
import logging
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Callable

from renquant_common import Job, Pipeline, Task

from .retrain_common import (
    read_json_object,
    resolve_path,
    run_subprocess,
    staging_path,
    subrepo_pythonpath,
    validate_repo_dir,
)
from .runtime_paths import (
    default_github_root,
    default_repo_root,
    default_strategy_config_candidates,
)
from renquant_common.notify import send as post_ntfy  # canonical sender (campaign B6)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


log = logging.getLogger("renquant_orchestrator.retrain_alpha158_fund")


class InventoryUnavailableError(RuntimeError):
    """The panel training universe could not be established from a non-empty,
    fingerprinted inventory. This is a fail-closed condition: a required training
    input's universe is unprovable, so the refresh/guard must NOT proceed as if
    the universe were legitimately empty (that masked a total-inventory outage as
    an ``n_universe=0`` success)."""


class FreshnessUnprovableError(RuntimeError):
    """Freshness could not be proven: no OHLCV max dates were resolvable, or the
    independently-derived expected market session could not be computed. Failing
    closed here is the whole point — an unprovable-freshness state is exactly when
    a silent freeze slips through, so it must block rather than soft-skip."""

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
# One session (a narrowly-justified OPERATIONAL lag), NOT ten. The earlier
# default of 10 let every active ticker sit up to ten exchange sessions (~two
# calendar weeks) behind the expected session and still read n_bad=0 — even with
# max_stale_fraction pinned to 0.0 — because the fraction gate cannot see a
# per-name tolerance. For a cross-sectional daily panel a two-week date mismatch
# materially moves ranks and labels, so the guard now measures every name
# against the INDEPENDENTLY-derived expected latest completed market session and
# tolerates at most a SINGLE session of lag. Why one and not zero: the refresh
# can legitimately finish before a vendor publishes a name's T+0 bar, and a
# one-session input lag has zero label impact (the panel's fwd_60d clip puts the
# training frontier ~60 sessions back), so exactly one session is a deliberate,
# minimal allowance that still catches the ~two-month partial freeze and any
# multi-session drift. A wider tolerance is a documented per-run override (and is
# recorded in the freshness_report), never a silent default. See
# doc/progress/2026-07-01-panel-ohlcv-coverage-fix.md.
DEFAULT_FRESHNESS_STALE_AFTER_DAYS = 1
# STRICT by default (fail-closed). The earlier 0.10 default silently tolerated
# ~29/292 missing-or-frozen names — enough to materially move cross-sectional
# ranks — and had no sensitivity justification (coverage-loss vs rank/IC/turnover
# was never measured). Rather than ship an unjustified 10% escape hatch, the
# guard now blocks on ANY genuinely-stale name: delisted/retired names are pruned
# from the *versioned* inventory (``delisted_tickers`` / ``inactive_tickers``), so
# what remains is the active universe that MUST be fresh. Operators may still set
# a non-zero tolerance for a single run, but it is a deliberate, documented
# override — not a default that hides a partial freeze. See
# doc/progress/2026-07-01-panel-ohlcv-coverage-fix.md.
DEFAULT_FRESHNESS_MAX_STALE_FRACTION = 0.0
# NYSE is the shared exchange the whole stack prices against (base-data's
# _last_completed_nyse_session, the live path, and the panel build all use it).
DEFAULT_EXCHANGE = "NYSE"
DEFAULT_NTFY_TOPIC = "renquant"

# σ-head (QuantileHead) RAW-label panel. ``alpha158_291_fundamental_dataset.parquet``
# is the cross-sectionally z-scored ranker panel; ``build_raw_fwd60d_label.py``
# derives a sibling ``*_rawlabel.parquet`` that swaps the z-scored fwd_60d_excess
# for an UN-normalized (raw ticker return − SPY return) target so the QuantileHead
# can recover σ on the return scale. That derived panel had NO retrain cadence, so
# it drifted behind the ranker panel (fix #1 from the training-data investigation).
DEFAULT_PANEL_FILENAME = "alpha158_291_fundamental_dataset.parquet"
DEFAULT_RAWLABEL_FILENAME = "alpha158_291_fundamental_dataset_rawlabel.parquet"
DEFAULT_RAWLABEL_HORIZON = 60  # match production fwd_60d
# The un-normalized target ``build_raw_fwd60d_label.py`` derives (ticker fwd_60d
# return − SPY fwd_60d return); the σ-head/QuantileHead trains on this column.
RAWLABEL_COLUMN = "fwd_60d_excess_raw"
# Pre-swap validation floor: a staged corpus whose finite-label fraction is below
# this is treated as zero-row/all-NaN/corrupt and is REFUSED (never swapped). The
# production panel is truncated behind the OHLCV frontier so the vast majority of
# rows carry a realized fwd_60d return; 0.10 only trips on a broken build.
DEFAULT_RAWLABEL_MIN_FINITE_FRACTION = 0.10
# Sidecars next to the live corpus. The INVALID receipt is the durable
# data-integrity guarantee (an ntfy alert is not): it is written whenever a
# refresh does NOT certify the corpus in-lockstep with the current panel, and
# is cleared only on a fully-validated swap. ``assert_rawlabel_admissible`` lets
# downstream σ-head training ENFORCE it (refuse to consume an invalidated corpus).
RAWLABEL_INVALID_SUFFIX = ".INVALID.json"
RAWLABEL_PROVENANCE_SUFFIX = ".provenance.json"
# Schema version stamped into every provenance sidecar. A consumer that only
# understands an older/different schema must fail closed rather than guess at
# unknown-shape fields (Codex #218/#427 review: "preferably schema/version").
# Bump this whenever the provenance payload's field set or semantics change.
RAWLABEL_PROVENANCE_SCHEMA_VERSION = 1


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
    # Freshness is measured against an INDEPENDENTLY derived expected latest
    # completed market session — NOT max(known ticker dates), which would let a
    # uniform freeze (every name stuck on the same old date) look perfectly
    # fresh. ``expected_session`` pins it explicitly (tests / reproducibility);
    # otherwise ``now_fn`` (a tz-aware clock) feeds the shared NYSE exchange
    # calendar to resolve the last completed session (holiday / early-close
    # aware). ``session_gap_fn`` counts exchange sessions between two dates;
    # when None it resolves the NYSE calendar. All three are injectable so the
    # guard is unit-testable without a live clock or a calendar dependency, and
    # the resolved session is persisted into ``freshness_report``.
    exchange: str = DEFAULT_EXCHANGE
    expected_session: "dt.date | None" = None
    now_fn: "Callable[[], object] | None" = None
    session_gap_fn: "Callable[[dt.date, dt.date], int] | None" = None
    ntfy_topic: str = DEFAULT_NTFY_TOPIC
    quiet: bool = False

    # ── σ-head (QuantileHead) RAW-label refresh (lockstep with the panel) ────
    # Regenerates ``alpha158_291_fundamental_dataset_rawlabel.parquet`` right
    # after the fund-panel merge so the σ-head label never drifts behind the
    # ranker panel. The σ-head is a SEPARATE downstream model, so a failure here
    # alerts + logs but NEVER aborts the main XGB-ranker / calibrator retrain.
    refresh_rawlabel: bool = True
    # Dependency-injected raw-label build callable. Signature:
    #   build(panel_in: Path, panel_out: Path, ohlcv_dir: Path, horizon: int) -> None
    # When None it resolves to ``_default_rawlabel_build_fn`` (a path-parametrized
    # port of scripts/build_raw_fwd60d_label.py). Injected in tests so no real
    # build runs and no production ``_rawlabel`` parquet is ever written.
    rawlabel_build_fn: "Callable[..., None] | None" = None
    rawlabel_horizon: int = DEFAULT_RAWLABEL_HORIZON
    # Dependency-injected pre-swap validator. Signature:
    #   validate(staging: Path, panel_in: Path, horizon: int) -> dict  (report)
    # It MUST raise on any integrity failure so the staged file is NOT swapped.
    # When None it resolves to ``_default_rawlabel_validate_fn`` (schema / unique
    # (ticker,date) / exact source-panel coverage / finite-label floor). Injected
    # in wiring tests that use opaque staging bytes.
    rawlabel_validate_fn: "Callable[..., dict] | None" = None
    rawlabel_min_finite_fraction: float = DEFAULT_RAWLABEL_MIN_FINITE_FRACTION

    # Populated at runtime by the refresh / guard tasks (audit surface).
    ohlcv_max_dates: dict[str, "dt.date | None"] = field(default_factory=dict)
    ohlcv_refresh_summary: dict[str, int] = field(default_factory=dict)
    freshness_report: dict = field(default_factory=dict)
    panel_universe_provenance: dict = field(default_factory=dict)
    rawlabel_refresh_summary: dict = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        return self.repo_dir / "data"

    @property
    def ohlcv_dir(self) -> Path:
        return self.data_dir / DEFAULT_OHLCV_DIRNAME

    @property
    def panel_path(self) -> Path:
        return self.data_dir / DEFAULT_PANEL_FILENAME

    @property
    def rawlabel_path(self) -> Path:
        return self.data_dir / DEFAULT_RAWLABEL_FILENAME

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


def _fund_strategy_config() -> str:
    sc = DEFAULT_STRATEGY_CONFIG if DEFAULT_STRATEGY_CONFIG.exists() else LEGACY_STRATEGY_CONFIG
    return str(sc)


def _run(ctx: RetrainContext, cmd: list[str], *, cwd: Path | None = None) -> None:
    run_subprocess(ctx, cmd, cwd=cwd, env_strategy_config=_fund_strategy_config())


def _validate_scorer_artifact(path: Path) -> None:
    payload = read_json_object(path, "GBDT training")
    if not payload.get("config_fingerprint"):
        raise ValueError(f"GBDT artifact missing config_fingerprint: {path}")
    expected = dt.datetime.utcnow().strftime("%Y-%m-%d")
    if payload.get("trained_date") != expected:
        raise ValueError(
            f"GBDT artifact trained_date={payload.get('trained_date')!r}; expected {expected}: {path}"
        )


def _validate_calibrator_artifact(path: Path) -> None:
    payload = read_json_object(path, "calibrator refit")
    if not payload:
        raise ValueError(f"calibrator artifact is empty: {path}")


def _fingerprint(payload: dict) -> str:
    """Stable content fingerprint (sha256 over canonical JSON) of a universe
    provenance payload, so every refresh/guard run is tied to a specific,
    reproducible inventory content — not just "some file existed"."""
    import hashlib  # noqa: PLC0415

    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


# Optional versioned-exclusion keys: names the *inventory itself* declares as no
# longer part of the active universe (delisted / retired / halted). Excluding
# them here is how delistings are handled — via a versioned universe — rather
# than being absorbed as "tolerated failures" by the stale-fraction slack.
_INVENTORY_DELISTED_KEYS = ("delisted_tickers", "inactive_tickers", "retired_tickers")


def _resolve_panel_universe(ctx: RetrainContext) -> "tuple[list[str], dict]":
    """Source the FULL panel training universe (tier_A + tier_B), NOT just the
    ~142-ticker live watchlist, and FAIL CLOSED if it cannot be established.

    This mirrors ``renquant_base_data.alpha158_qlib_panel.LoadUniverseJob``,
    which reads ``tier_A_tickers`` + ``tier_B_tickers`` from
    ``transformer_universe_inventory.json``. An explicit ``ctx.panel_universe``
    wins so callers can pin the universe.

    Returns ``(universe, provenance)`` where ``provenance`` carries a content
    ``fingerprint`` and the source metadata. It raises
    :class:`InventoryUnavailableError` when the universe cannot be established
    from a NON-EMPTY, fingerprinted inventory — a missing / unreadable / corrupt
    / non-inventory / empty file no longer degrades to an ``n_universe=0``
    success (which silently disabled the whole refresh + guard for a required
    training input). Names the inventory declares delisted/inactive/retired are
    pruned as a versioned exclusion (audited, not counted as stale failures).
    """
    if ctx.panel_universe is not None:
        universe = sorted(dict.fromkeys(str(t) for t in ctx.panel_universe))
        if not universe:
            raise InventoryUnavailableError(
                "explicit panel_universe is empty — refuse to run the refresh/guard "
                "on an empty universe (fail-closed)"
            )
        prov = {
            "source": "explicit",
            "n_universe": len(universe),
            "fingerprint": _fingerprint({"universe": universe}),
        }
        return universe, prov

    inv_path = ctx.resolved_inventory_path
    if not inv_path.exists():
        raise InventoryUnavailableError(
            f"panel universe inventory not found: {inv_path} — cannot establish the "
            f"required training universe (fail-closed)"
        )
    try:
        raw = inv_path.read_text()
    except OSError as exc:
        raise InventoryUnavailableError(
            f"panel universe inventory unreadable: {inv_path}: {exc} (fail-closed)"
        ) from exc
    try:
        inv = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InventoryUnavailableError(
            f"panel universe inventory is invalid JSON: {inv_path}: {exc} (fail-closed)"
        ) from exc
    if not isinstance(inv, dict):
        raise InventoryUnavailableError(
            f"panel universe inventory must be a JSON object: {inv_path} (fail-closed)"
        )
    # Reject a wrong/placeholder file that is not actually the tier inventory —
    # a "default"/empty stand-in must not silently resolve to an empty universe.
    if "tier_A_tickers" not in inv and "tier_B_tickers" not in inv:
        raise InventoryUnavailableError(
            f"panel universe inventory has no tier_A_tickers/tier_B_tickers keys: "
            f"{inv_path} — not a usable universe inventory (fail-closed)"
        )
    declared = sorted(
        str(t)
        for t in (set(inv.get("tier_A_tickers", [])) | set(inv.get("tier_B_tickers", [])))
    )
    delisted: set[str] = set()
    for key in _INVENTORY_DELISTED_KEYS:
        delisted |= {str(t) for t in inv.get(key, [])}
    universe = [t for t in declared if t not in delisted]
    if not universe:
        raise InventoryUnavailableError(
            f"panel universe inventory yields an EMPTY active universe: {inv_path} "
            f"(declared={len(declared)}, delisted-excluded={len(delisted & set(declared))}) "
            f"(fail-closed)"
        )
    prov = {
        "source": str(inv_path),
        "kind": inv.get("kind"),
        "generated_utc": inv.get("generated_utc"),
        "n_declared": len(declared),
        "n_delisted_excluded": len(delisted & set(declared)),
        "n_universe": len(universe),
        "fingerprint": _fingerprint(
            {
                "universe": universe,
                "delisted": sorted(delisted & set(declared)),
                "generated_utc": inv.get("generated_utc"),
                "kind": inv.get("kind"),
            }
        ),
    }
    return universe, prov


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


def _default_now() -> object:
    """Timezone-aware wall clock used to derive the expected market session."""
    import pandas as pd  # noqa: PLC0415

    return pd.Timestamp.now(tz="America/New_York")


def _expected_last_completed_session(exchange: str, now) -> "dt.date | None":
    """Most recent COMPLETED exchange session as of ``now`` (tz-aware).

    Campaign B5 (audit #296 XC-2): delegates to the canonical
    :func:`renquant_common.market_calendar.last_completed_session`. This was
    previously a hand-copied "mirror" of base-data's
    ``_last_completed_nyse_session`` that had already diverged (16-day vs
    14-day lookback) — semantics unchanged and equivalence-proven on a
    10-year fixture: today counts only once its (possibly early, half-day)
    close has passed; holidays are skipped by the calendar. Kept as a named
    seam so tests can monkeypatch the derivation. The canonical raises
    ``ValueError`` (fail-closed) where the old copy returned ``None``;
    ``_resolve_expected_session`` maps both to FreshnessUnprovableError.

    The "independently-derived expected session" contract of this gate means
    independence from the DATA under check (clock + calendar, never
    ``max(known dates)``) — not from the calendar library, which was always
    the same ``pandas_market_calendars`` dataset base-data reads.
    """
    from renquant_common.market_calendar import last_completed_session  # noqa: PLC0415

    return last_completed_session(now, calendar_name=exchange)


def _resolve_expected_session(ctx: RetrainContext) -> "dt.date":
    """Independently-derived expected latest completed market session.

    Priority: an explicitly-injected ``expected_session`` (reproducible pin) →
    the shared exchange calendar fed by ``now_fn`` / the wall clock. Raises
    :class:`FreshnessUnprovableError` when it cannot be resolved — freshness
    against an unknown reference is unprovable, so we fail closed rather than
    fall back to ``max(known dates)`` (which lets a uniform freeze look fresh).
    """
    if ctx.expected_session is not None:
        return ctx.expected_session
    now = (ctx.now_fn or _default_now)()
    try:
        sess = _expected_last_completed_session(ctx.exchange, now)
    except Exception as exc:  # calendar unavailable → cannot prove freshness
        raise FreshnessUnprovableError(
            f"cannot derive expected {ctx.exchange} session (calendar unavailable): "
            f"{exc} (fail-closed)"
        ) from exc
    if sess is None:
        raise FreshnessUnprovableError(
            f"cannot derive expected {ctx.exchange} session as of {now} (fail-closed)"
        )
    return sess


def _default_session_gap(exchange: str, start: "dt.date", end: "dt.date") -> int:
    """Number of exchange sessions strictly after ``start`` up to and including
    ``end`` (holiday / half-day aware). 0 when ``start >= end`` — half-days count
    as full sessions (they are open sessions, merely early-close). Campaign B5:
    counts via the canonical ``renquant_common.market_calendar`` primitive."""
    from renquant_common.market_calendar import sessions_between  # noqa: PLC0415

    if start >= end:
        return 0
    return int(
        len(
            sessions_between(
                start + dt.timedelta(days=1), end, calendar_name=exchange
            )
        )
    )


def _session_gap(ctx: RetrainContext, start: "dt.date", end: "dt.date") -> int:
    if ctx.session_gap_fn is not None:
        return ctx.session_gap_fn(start, end)
    return _default_session_gap(ctx.exchange, start, end)


def _freshness_overrides(ctx: RetrainContext) -> dict:
    """Record every freshness knob that deviates from its (fail-closed) default,
    plus whether the expected session was pinned rather than clock-derived. This
    is persisted into ``freshness_report`` so the run bundle shows exactly when an
    operator loosened the gate (e.g. widened the per-name lag or the tolerated
    stale fraction) and against which reference session — a loosened gate must
    never be silent."""
    overrides: dict = {}
    if ctx.freshness_stale_after_days != DEFAULT_FRESHNESS_STALE_AFTER_DAYS:
        overrides["stale_after_days"] = {
            "value": ctx.freshness_stale_after_days,
            "default": DEFAULT_FRESHNESS_STALE_AFTER_DAYS,
        }
    if ctx.freshness_max_stale_fraction != DEFAULT_FRESHNESS_MAX_STALE_FRACTION:
        overrides["max_stale_fraction"] = {
            "value": ctx.freshness_max_stale_fraction,
            "default": DEFAULT_FRESHNESS_MAX_STALE_FRACTION,
        }
    if not ctx.freshness_fail_on_stale:
        overrides["fail_on_stale"] = {"value": False, "default": True}
    if ctx.expected_session is not None:
        overrides["expected_session_pinned"] = ctx.expected_session.isoformat()
    return overrides


def _default_rawlabel_build_fn() -> "Callable[..., None]":
    """Resolve the σ-head RAW-label builder.

    This is a path-parametrized port of umbrella ``scripts/build_raw_fwd60d_label.py``:
    for each ticker in the fresh fund panel it computes the UN-normalized
    ``fwd_60d_excess_raw`` = (ticker fwd_60d return − SPY fwd_60d return) on the
    return scale, then writes the panel (identical schema, with the raw label
    column added) to ``panel_out``. It is dependency-injected via
    ``RetrainContext.rawlabel_build_fn`` so the orchestrator task is unit-testable
    without reading real panels / OHLCV or writing a production ``_rawlabel``
    parquet. The caller (the task) points ``panel_out`` at a staging path and
    atomically swaps on success, so this builder never mutates the live artifact.
    """

    def _build(panel_in: Path, panel_out: Path, ohlcv_dir: Path, horizon: int) -> None:
        import numpy as np  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        panel = pd.read_parquet(panel_in)
        panel["date"] = pd.to_datetime(panel["date"])

        spy = pd.read_parquet(ohlcv_dir / "SPY" / "1d.parquet")
        spy.index = pd.to_datetime(spy.index)
        spy_close = spy["close"].sort_index()
        spy_fwd_ret = (spy_close.shift(-horizon) / spy_close - 1.0)

        out_blocks = []
        for tkr, g in panel.groupby("ticker"):
            g = g.sort_values("date").reset_index(drop=True).copy()
            ohlcv_p = ohlcv_dir / tkr / "1d.parquet"
            if not ohlcv_p.exists():
                g[RAWLABEL_COLUMN] = np.nan
                out_blocks.append(g)
                continue
            ohlcv = pd.read_parquet(ohlcv_p)
            ohlcv.index = pd.to_datetime(ohlcv.index)
            close = ohlcv["close"].sort_index()
            ticker_fwd_ret = (close.shift(-horizon) / close - 1.0)
            g_dates = g["date"].values
            excess = (
                ticker_fwd_ret.reindex(g_dates).values
                - spy_fwd_ret.reindex(g_dates).values
            )
            g[RAWLABEL_COLUMN] = excess
            out_blocks.append(g)

        out = pd.concat(out_blocks, ignore_index=True)
        out.to_parquet(panel_out, index=False)

    return _build


class RawlabelValidationError(ValueError):
    """A staged σ-head ``_rawlabel`` failed pre-swap integrity validation.

    Raised BEFORE the atomic swap so a zero-row / corrupt / wrong-coverage /
    all-NaN parquet can never replace the live corpus.
    """


class RawlabelStaleError(RuntimeError):
    """Downstream admission tripwire: the on-disk σ-head ``_rawlabel`` corpus is
    missing or carries an active invalidation receipt, so it must NOT be consumed
    by σ-head / QuantileHead training."""


def _sha256_file(path: Path) -> str:
    import hashlib  # noqa: PLC0415

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _fsync_file(path: Path) -> None:
    """Force ``path``'s contents to durable storage.

    Publication-ordering safety (Codex #218/#427 review): the corpus and its
    provenance sidecar are two SEPARATE files, so a crash between writing one
    and the other must never be able to make a stale/absent corpus look
    validated. Flushing the corpus to disk (this) BEFORE the atomic rename
    that publishes it, and flushing the provenance sidecar BEFORE its own
    atomic rename, ensures neither file's on-disk bytes can regress after the
    rename that exposes them — the rename is the only externally-visible
    publish step, so it must always publish fully-durable bytes.
    """
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    """fsync a directory so a preceding ``os.replace`` rename within it is
    itself durable (POSIX does not guarantee a rename survives a crash until
    the containing directory's own metadata is flushed). Best-effort: some
    platforms/filesystems disallow opening or fsync-ing a directory, and this
    is a durability hardening, not a correctness precondition (the atomic
    rename itself is still what prevents a torn/partial publish).
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:  # pragma: no cover - platform without dir-fd support
        return
    try:
        os.fsync(fd)
    except OSError:  # pragma: no cover - filesystem disallows dir fsync
        pass
    finally:
        os.close(fd)


def _default_rawlabel_validate_fn(
    min_finite_fraction: float = DEFAULT_RAWLABEL_MIN_FINITE_FRACTION,
) -> "Callable[..., dict]":
    """Resolve the pre-swap staged-``_rawlabel`` validator.

    Merely checking that the staging file exists lets a zero-row / corrupt /
    wrong-horizon / partial-coverage parquet replace the live corpus. This
    validator reads the staged parquet + the source panel and REFUSES the swap
    (raising ``RawlabelValidationError``) unless ALL hold:

    - schema: ``ticker`` / ``date`` / ``fwd_60d_excess_raw`` all present;
    - non-empty (``> 0`` rows);
    - unique ``(ticker, date)`` keys (no duplicated panel rows);
    - coverage: the staged ``(ticker, date)`` key-set EXACTLY equals the source
      panel's — this both proves expected ticker/date coverage AND rules out any
      future-dated / fabricated row absent from the panel (no-leakage);
    - finite fraction: ``isfinite(label)`` fraction ``>= min_finite_fraction``
      (``±inf`` counts as non-finite), catching an all-NaN / corrupt build.

    On success it returns a provenance report (rows, tickers, finite fraction,
    horizon, source-panel sha256 digest + frontier) that the task stamps beside
    the swapped corpus. This report describes the STAGED (pre-swap) file; the
    task itself adds ``rawlabel_sha256`` (the digest of the on-disk, PUBLISHED
    corpus bytes, computed AFTER the atomic swap — see
    ``RefreshSigmaHeadRawLabelTask``'s publication-ordering note) and
    ``schema_version`` before stamping the provenance sidecar, since those two
    fields describe the published artifact and its schema, not the staged
    candidate. Dependency-injected via ``RetrainContext.rawlabel_validate_fn``.
    """

    def _validate(staging: Path, panel_in: Path, horizon: int) -> dict:
        import numpy as np  # noqa: PLC0415
        import pandas as pd  # noqa: PLC0415

        try:
            staged = pd.read_parquet(staging)
        except Exception as exc:  # corrupt / non-parquet staging
            raise RawlabelValidationError(
                f"staged _rawlabel is unreadable as parquet: {staging}: {exc}"
            ) from exc

        required = {"ticker", "date", RAWLABEL_COLUMN}
        missing = required - set(map(str, staged.columns))
        if missing:
            raise RawlabelValidationError(
                f"staged _rawlabel missing required columns {sorted(missing)}: {staging}"
            )
        if len(staged) == 0:
            raise RawlabelValidationError(f"staged _rawlabel is empty (0 rows): {staging}")

        staged = staged.copy()
        staged["date"] = pd.to_datetime(staged["date"])
        dup_mask = staged.duplicated(subset=["ticker", "date"])
        if bool(dup_mask.any()):
            raise RawlabelValidationError(
                f"staged _rawlabel has {int(dup_mask.sum())} duplicate (ticker,date) rows: {staging}"
            )

        try:
            panel = pd.read_parquet(panel_in, columns=["ticker", "date"])
        except Exception as exc:
            raise RawlabelValidationError(
                f"source panel unreadable for coverage check: {panel_in}: {exc}"
            ) from exc
        panel = panel.copy()
        panel["date"] = pd.to_datetime(panel["date"])
        panel_keys = set(zip(panel["ticker"].astype(str), panel["date"]))
        staged_keys = set(zip(staged["ticker"].astype(str), staged["date"]))
        if staged_keys != panel_keys:
            raise RawlabelValidationError(
                "staged _rawlabel (ticker,date) coverage != source panel "
                f"(staged-only={len(staged_keys - panel_keys)}, "
                f"panel-only={len(panel_keys - staged_keys)}); a partial / wrong / "
                f"future-dated corpus must not replace the live one: {staging}"
            )

        label = pd.to_numeric(staged[RAWLABEL_COLUMN], errors="coerce").to_numpy(dtype="float64")
        finite = int(np.isfinite(label).sum())
        finite_fraction = finite / len(staged)
        if finite_fraction < min_finite_fraction:
            raise RawlabelValidationError(
                f"staged _rawlabel finite-label fraction {finite_fraction:.4f} < floor "
                f"{min_finite_fraction:.4f} ({finite}/{len(staged)} finite); a zero-row / "
                f"all-NaN / corrupt build must not replace the live corpus: {staging}"
            )

        return {
            "n_rows": int(len(staged)),
            "n_tickers": int(staged["ticker"].nunique()),
            "finite_fraction": round(finite_fraction, 6),
            "horizon": int(horizon),
            "source_panel_sha256": _sha256_file(panel_in),
            "source_panel_frontier": panel["date"].max().date().isoformat(),
        }

    return _validate


def rawlabel_receipt_path(rawlabel_path: Path) -> Path:
    """Path of the invalidation receipt sidecar for a ``_rawlabel`` corpus."""
    return rawlabel_path.with_name(rawlabel_path.name + RAWLABEL_INVALID_SUFFIX)


def rawlabel_provenance_path(rawlabel_path: Path) -> Path:
    """Path of the provenance sidecar stamped beside a validated corpus."""
    return rawlabel_path.with_name(rawlabel_path.name + RAWLABEL_PROVENANCE_SUFFIX)


def _write_invalidation_receipt(
    rawlabel_path: Path, *, reason: str, panel_in: Path, horizon: int
) -> Path:
    receipt = rawlabel_receipt_path(rawlabel_path)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "rawlabel": str(rawlabel_path),
                "panel": str(panel_in),
                "horizon": int(horizon),
                "reason": reason,
                "invalidated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            },
            indent=2,
        )
    )
    return receipt


def _clear_invalidation_receipt(rawlabel_path: Path) -> None:
    receipt = rawlabel_receipt_path(rawlabel_path)
    try:
        receipt.unlink()
    except FileNotFoundError:
        pass


def _write_rawlabel_provenance(rawlabel_path: Path, report: dict) -> Path:
    """Stamp the provenance sidecar — MUST be called strictly AFTER the
    corpus itself is durably published (see the publication-ordering note on
    :class:`RefreshSigmaHeadRawLabelTask`). ``report`` is expected to already
    carry ``rawlabel_sha256`` (the digest of the on-disk, post-swap corpus
    bytes) alongside the pre-swap validator's ``source_panel_sha256`` /
    ``horizon`` / coverage stats.

    Written atomically (temp file + fsync + ``os.replace``) so a reader can
    never observe a torn/partially-written provenance file: it either sees
    the PRIOR sidecar (stale, but internally consistent — and, per the digest
    binding, a consumer that checks ``rawlabel_sha256`` against the actual
    corpus bytes will correctly reject a mismatch) or the fully-written new
    one, never something in between.
    """
    prov = rawlabel_provenance_path(rawlabel_path)
    payload = dict(report)
    payload["schema_version"] = RAWLABEL_PROVENANCE_SCHEMA_VERSION
    payload["rawlabel"] = str(rawlabel_path)
    payload["built_at"] = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    tmp = prov.with_name(prov.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    _fsync_file(tmp)
    os.replace(tmp, prov)  # atomic publish of the sidecar itself
    _fsync_dir(prov.parent)
    return prov


def is_rawlabel_admissible(rawlabel_path: Path) -> bool:
    """True iff the corpus exists AND has no active invalidation receipt."""
    return rawlabel_path.exists() and not rawlabel_receipt_path(rawlabel_path).exists()


def assert_rawlabel_admissible(rawlabel_path: Path) -> None:
    """Reference admission check: raise ``RawlabelStaleError`` unless the σ-head
    ``_rawlabel`` corpus exists and carries no invalidation receipt.

    This repo does not run real σ-head / QuantileHead training (CLAUDE.md hard
    boundary), so this function is producer-side documentation of the RECEIPT
    contract (missing / invalidated corpus), not the full enforcement point.
    The full enforcement point — including binding the corpus to its exact
    validated bytes — is the actual training entrypoint,
    ``scripts/train_ngboost_proper.py`` in the ``RenQuant`` umbrella repo,
    which reimplements this same receipt check by file-contract AND ALSO
    verifies the provenance sidecar's ``source_panel_sha256`` (the INPUT the
    corpus was built from) and ``rawlabel_sha256`` (the OUTPUT corpus itself,
    added alongside ``schema_version`` in this PR) against what is live on
    disk right now — see RenQuant PR #427. That digest binding is what
    catches a corpus REPLACED OR EDITED after validation while its sidecar is
    left intact — a receipt-only check (this function) cannot see that, since
    the receipt is absent in that scenario. Do not claim end-to-end
    tamper-detection from this function alone; it is the receipt half of the
    contract, not the digest half.
    """
    if not rawlabel_path.exists():
        raise RawlabelStaleError(f"σ-head _rawlabel corpus is missing: {rawlabel_path}")
    receipt = rawlabel_receipt_path(rawlabel_path)
    if receipt.exists():
        try:
            reason = json.loads(receipt.read_text()).get("reason", "unknown")
        except (OSError, json.JSONDecodeError):
            reason = "unreadable receipt"
        raise RawlabelStaleError(
            f"σ-head _rawlabel corpus is INVALIDATED ({receipt.name}: {reason}); "
            f"a fresh, validated refresh must succeed before σ-head training may "
            f"consume {rawlabel_path}."
        )


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
    fatal. Records a summary (n_refreshed / n_stale / n_future / n_delisted /
    n_failed). Refresh COMPLETION is deliberately separate from the fail-closed
    freshness gate (:class:`PanelUniverseFreshnessGuardTask`) and from model
    promotion: this task always finishes so the audit summary is populated, then
    the guard is the authoritative block.
    """

    def run(self, ctx: RetrainContext) -> bool | None:
        if not ctx.refresh_ohlcv:
            log.info("OHLCV refresh disabled (refresh_ohlcv=False); skipping")
            ctx.ohlcv_refresh_summary = {"status": "disabled", "n_universe": 0}
            return True
        # Fail closed: a required training input's universe must be establishable
        # from a non-empty, fingerprinted inventory (raises InventoryUnavailableError).
        # A dry-run is a non-executing preview (no fetch, no promotion), so an
        # unresolvable universe degrades to a noted skip there rather than blocking
        # the command-plan preview.
        try:
            universe, provenance = _resolve_panel_universe(ctx)
        except InventoryUnavailableError:
            if ctx.dry_run:
                ctx.ohlcv_refresh_summary = {"status": "dry-run-no-inventory", "n_universe": 0}
                log.info("[dry-run] panel universe not resolvable; skipping refresh")
                return True
            raise
        ctx.panel_universe_provenance = provenance
        summary: dict = {
            "n_universe": len(universe),
            "n_refreshed": 0,
            "n_stale": 0,
            "n_future": 0,
            "n_delisted": 0,
            "n_failed": 0,
            "inventory_fingerprint": provenance["fingerprint"],
        }
        ctx.ohlcv_refresh_summary = summary
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

        # Classify each name into DISJOINT buckets (they sum to the universe
        # size) against the INDEPENDENTLY-derived expected session — not the
        # batch frontier, which a uniform freeze would drag backwards. If the
        # expected session cannot be derived the guard (next task) fails closed;
        # here we only degrade the audit label, never the counts.
        try:
            expected = _resolve_expected_session(ctx)
        except FreshnessUnprovableError:
            expected = None
        summary["expected_session"] = expected.isoformat() if expected else None
        for ticker, md in max_dates.items():
            if ticker in failed:
                summary["n_failed"] += 1
            elif md is None:
                summary["n_delisted"] += 1
            elif expected is not None and md > expected:
                summary["n_future"] += 1  # bar dated after the expected session (corrupt)
            elif (
                expected is not None
                and _session_gap(ctx, md, expected) > ctx.freshness_stale_after_days
            ):
                summary["n_stale"] += 1
            else:
                summary["n_refreshed"] += 1
        log.info(
            "OHLCV refresh: universe=%d refreshed=%d stale=%d future=%d delisted=%d failed=%d expected=%s",
            summary["n_universe"],
            summary["n_refreshed"],
            summary["n_stale"],
            summary["n_future"],
            summary["n_delisted"],
            summary["n_failed"],
            summary["expected_session"],
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
    lags the INDEPENDENTLY-derived expected latest completed market session
    (``_resolve_expected_session`` — the shared exchange calendar, NOT
    ``max(known dates)``) by more than ``freshness_stale_after_days`` exchange
    sessions (default 1 — a single-session operational lag; the tolerated
    *fraction* cannot see this per-name lag, so it is gated here). Measuring
    against the expected session is what catches a
    *globally-uniform* freeze: if the whole universe is stuck on one old date,
    ``max(known)`` would call everything fresh, but the expected session is
    recent, so every name reads stale and the guard trips.

    FAIL CLOSED: a missing / unreadable / empty inventory, no resolvable OHLCV
    max dates, or an underivable expected session all raise (freshness is
    unprovable) rather than soft-skipping to success. Missing bars and
    future-dated bars are counted as stale (never tolerated). If the stale
    fraction exceeds ``freshness_max_stale_fraction`` (strict 0.0 by default),
    emit a LOUD ntfy alert and — per ``freshness_fail_on_stale`` — either fail
    the retrain (default, fail-closed) or proceed with the warning.
    """

    def run(self, ctx: RetrainContext) -> bool | None:
        # A dry-run is a non-executing preview with no real data to assess; the
        # gate applies to real runs (which promote nothing until it passes).
        if ctx.dry_run:
            log.info("[dry-run] skipping panel freshness guard")
            return True
        # Fail closed on an unestablishable universe (raises).
        universe, provenance = _resolve_panel_universe(ctx)
        ctx.panel_universe_provenance = provenance
        # Independently-derived reference session (raises if underivable).
        expected = _resolve_expected_session(ctx)
        dates = {t: _resolve_ohlcv_max_date(ctx, t) for t in universe}
        known = {t: d for t, d in dates.items() if d is not None}
        if not known:
            raise FreshnessUnprovableError(
                f"freshness guard: no OHLCV max dates resolvable for any of "
                f"{len(universe)} panel tickers — freshness unprovable (fail-closed)"
            )

        missing = {t for t, d in dates.items() if d is None}
        future = {t: d for t, d in known.items() if d > expected}
        stale: dict[str, int] = {}
        for t, d in known.items():
            if t in future:
                continue
            lag = _session_gap(ctx, d, expected)
            if lag > ctx.freshness_stale_after_days:
                stale[t] = lag
        # Missing and future-dated bars are integrity failures, never tolerated.
        n_bad = len(stale) + len(missing) + len(future)
        fraction = n_bad / len(universe)
        frontier = max(known.values())
        worst = sorted(
            [(lag, t) for t, lag in stale.items()]
            + [(_session_gap(ctx, d, expected), t) for t, d in future.items()],
            reverse=True,
        )[:10]
        report = {
            "expected_session": expected.isoformat(),
            "as_of_frontier": frontier.isoformat(),
            "inventory_fingerprint": provenance["fingerprint"],
            "exchange": ctx.exchange,
            "n_universe": len(universe),
            "n_stale": n_bad,
            "n_missing": len(missing),
            "n_future": len(future),
            "stale_fraction": round(fraction, 4),
            "stale_after_days": ctx.freshness_stale_after_days,
            "max_stale_fraction": ctx.freshness_max_stale_fraction,
            "worst_examples": [[lag, t] for lag, t in worst],
            # FULL affected-name lists (not just the worst 10) so the run bundle
            # records every ticker that tripped the gate — the exact names an
            # operator must chase before promotion.
            "stale_names": {t: lag for t, lag in sorted(stale.items())},
            "missing_names": sorted(missing),
            "future_names": {t: d.isoformat() for t, d in sorted(future.items())},
            # Any deviation from the fail-closed defaults, persisted for audit.
            "overrides": _freshness_overrides(ctx),
        }
        ctx.freshness_report = report

        if fraction <= ctx.freshness_max_stale_fraction:
            log.info(
                "freshness guard OK: %d/%d stale (%.2f%% <= %.2f%%), expected_session=%s",
                n_bad,
                len(universe),
                fraction * 100,
                ctx.freshness_max_stale_fraction * 100,
                expected.isoformat(),
            )
            return True

        worst_str = ", ".join(f"{t}(-{lag}s)" for lag, t in worst[:8])
        title = "RenQuant retrain PANEL-FREEZE"
        body = (
            f"{n_bad}/{len(universe)} panel tickers stale "
            f"({fraction:.1%} > {ctx.freshness_max_stale_fraction:.1%}; "
            f"missing={len(missing)} future={len(future)}); "
            f"bars lag expected {ctx.exchange} session {expected.isoformat()} by "
            f">{ctx.freshness_stale_after_days} sessions. "
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


class RefreshSigmaHeadRawLabelTask(Task):
    """Rebuild the σ-head (QuantileHead) RAW ``_rawlabel`` panel in lockstep with
    the freshly-merged fund panel.

    ROOT CAUSE (fix #1 from the training-data investigation): the derived
    ``alpha158_291_fundamental_dataset_rawlabel.parquet`` sat at 2026-02-11 only
    because ``build_raw_fwd60d_label.py`` had no retrain cadence — its source
    (``alpha158_291_fundamental_dataset.parquet``) was already fresh once the
    panel build ran. This task regenerates the RAW-label panel right after the
    fund-panel merge so the σ-head label never drifts behind the ranker panel.

    Non-destructive + validated: builds to a ``.staging`` sibling, VALIDATES it
    (schema / unique (ticker,date) / exact source-panel coverage / finite-label
    floor) and only then atomically swaps. A zero-row / corrupt / wrong-coverage
    build is refused and never replaces the live corpus; the prior ``_rawlabel``
    survives untouched.

    Resilient but NOT fail-open: the σ-head is a SEPARATE downstream model, so any
    failure here logs + emits a LOUD ntfy alert but NEVER aborts the main
    XGB-ranker / calibrator retrain. Because a swallowed failure would otherwise
    leave a silently-stale corpus, every non-certified outcome (build failure,
    empty / rejected output, or a missing upstream panel) also writes a durable
    INVALIDATION RECEIPT beside the corpus. A successful, validated swap clears
    the receipt and stamps a provenance sidecar (schema_version, horizon,
    source-panel digest + frontier, row/ticker counts, finite fraction, and —
    critically — ``rawlabel_sha256``, the digest of the PUBLISHED corpus bytes
    themselves) . A missing upstream panel stays a soft skip (no alert — the
    ranker path surfaces that itself) but still records the receipt.

    Publication ordering (Codex #218/#427 review — the corpus and its
    provenance sidecar are two SEPARATE files, so a naive two-independent-
    ``os.replace`` sequence has an observable window where one is fresh and
    the other stale): this task (1) builds + validates to a ``.staging``
    sibling, (2) fsyncs it, (3) ``os.replace``s it into the corpus path
    (atomic — a reader never sees a partial file) and fsyncs the containing
    directory, (4) computes ``rawlabel_sha256`` from the now-published,
    on-disk corpus bytes, (5) writes the provenance sidecar LAST, atomically
    (temp file + fsync + ``os.replace``), referencing that digest, and only
    then (6) clears any prior invalidation receipt. Corpus-before-provenance
    is the load-bearing ordering: it means the provenance sidecar's
    ``rawlabel_sha256`` is always computed from bytes that are ALREADY
    durably on disk, so a reader that verifies the digest can never be misled
    by a sidecar that describes not-yet-written (or since-replaced) bytes. If
    an exception is raised anywhere after the swap but before the sidecar is
    stamped (e.g. a disk-full provenance write), the ``except`` clause below
    still catches it and writes an INVALIDATION RECEIPT, so the corpus is
    never left looking silently-valid with a provenance sidecar that doesn't
    match it — either the digest matches (certified) or a receipt / digest
    mismatch blocks admission (see ``assert_rawlabel_admissible``). A
    full generation-directory / current-pointer scheme (write to a new
    generation dir, then atomically flip a single pointer) would remove even
    the sub-microsecond exception-propagation window between steps (3)-(6);
    it was judged out of scope for this PR given the fixed-path file-contract
    the umbrella consumer already reads by (RenQuant PR #427), but is a
    natural follow-up if that window is ever shown to matter in practice.

    ``assert_rawlabel_admissible`` (below) is the enforcement CONTRACT this task
    writes for; this repo is producer-only (it does not run real σ-head training
    — see CLAUDE.md hard boundaries). The contract is enforced, end to end, at
    the ACTUAL σ-head training entrypoint — ``scripts/train_ngboost_proper.py``
    in the ``RenQuant`` umbrella repo — by a coordinated companion change,
    RenQuant PR #427 (which reimplements the same receipt/provenance check
    there by file-contract, not by cross-repo import, since RenQuant does not
    depend on this package). #427 verifies BOTH ``source_panel_sha256`` (the
    INPUT the corpus was built from) AND ``rawlabel_sha256`` (the OUTPUT
    corpus itself) against what is live on disk — closing the gap where a
    later replacement/edit of the corpus, with the sidecar left intact, would
    otherwise be indistinguishable from the originally-validated bytes.
    """

    def run(self, ctx: RetrainContext) -> bool | None:
        panel_in = ctx.panel_path
        rawlabel_out = ctx.rawlabel_path
        summary: dict = {
            "status": "skipped",
            "panel": str(panel_in),
            "rawlabel": str(rawlabel_out),
            "receipt": str(rawlabel_receipt_path(rawlabel_out)),
            "receipt_written": False,
        }
        ctx.rawlabel_refresh_summary = summary
        if not ctx.refresh_rawlabel:
            log.info("σ-head _rawlabel refresh disabled (refresh_rawlabel=False); skipping")
            return True
        if ctx.dry_run:
            summary["status"] = "dry-run"
            log.info("[dry-run] would rebuild σ-head _rawlabel %s from %s", rawlabel_out, panel_in)
            return True

        staging = rawlabel_out.with_name(rawlabel_out.name + ".staging")
        try:
            if not panel_in.exists():
                summary["status"] = "skipped-no-panel"
                # The corpus can no longer be certified in-lockstep with a (now
                # missing) panel, so invalidate it — but do NOT alert: the ranker
                # path surfaces the missing-panel failure on its own.
                _write_invalidation_receipt(
                    rawlabel_out,
                    reason="upstream panel missing; σ-head corpus not certified fresh",
                    panel_in=panel_in,
                    horizon=ctx.rawlabel_horizon,
                )
                summary["receipt_written"] = True
                log.warning(
                    "σ-head _rawlabel refresh: panel %s not found; skipping + invalidating "
                    "(upstream panel build produced no output)",
                    panel_in,
                )
                return True
            build_fn = ctx.rawlabel_build_fn or _default_rawlabel_build_fn()
            validate_fn = ctx.rawlabel_validate_fn or _default_rawlabel_validate_fn(
                ctx.rawlabel_min_finite_fraction
            )
            if staging.exists():
                staging.unlink()
            build_fn(panel_in, staging, ctx.ohlcv_dir, ctx.rawlabel_horizon)
            if not staging.exists():
                raise RuntimeError(f"σ-head rawlabel build produced no output: {staging}")
            # Validate the staged artifact BEFORE the swap; a failure raises and
            # falls to the except below (staging discarded, prior corpus kept).
            report = dict(validate_fn(staging, panel_in, ctx.rawlabel_horizon))
            # Publication ordering (see class docstring): fsync the validated
            # staging file, atomically publish it as the corpus, fsync the
            # containing directory, THEN compute the digest from the now-durable
            # on-disk bytes and stamp the provenance sidecar LAST — referencing
            # bytes that are ALREADY published, never bytes that are merely
            # about-to-be or used-to-be on disk.
            _fsync_file(staging)
            os.replace(staging, rawlabel_out)  # atomic swap ONLY after validation passes
            _fsync_dir(rawlabel_out.parent)
            report["rawlabel_sha256"] = _sha256_file(rawlabel_out)
            provenance = _write_rawlabel_provenance(rawlabel_out, report)
            _clear_invalidation_receipt(rawlabel_out)  # corpus certified in-lockstep
            summary["status"] = "refreshed"
            summary["report"] = report
            summary["provenance"] = str(provenance)
            log.info(
                "σ-head _rawlabel refreshed + validated: %s ← %s "
                "(rows=%s tickers=%s finite=%.3f frontier=%s)",
                rawlabel_out,
                panel_in,
                report.get("n_rows"),
                report.get("n_tickers"),
                report.get("finite_fraction", float("nan")),
                report.get("source_panel_frontier"),
            )
        except Exception as exc:  # downstream model — NEVER abort the ranker retrain
            summary["status"] = "failed"
            summary["error"] = str(exc)
            # A rejected / half-written staging must never linger as the next run's
            # "stale staging"; the prior live corpus is left untouched (not swapped).
            try:
                if staging.exists():
                    staging.unlink()
            except OSError:  # pragma: no cover - defensive
                pass
            # Durable, enforceable invalidation — an ntfy alert is not a guarantee.
            _write_invalidation_receipt(
                rawlabel_out, reason=str(exc), panel_in=panel_in, horizon=ctx.rawlabel_horizon
            )
            summary["receipt_written"] = True
            body = (
                f"σ-head _rawlabel refresh FAILED ({exc}). The XGB-ranker retrain "
                f"is UNAFFECTED, but the QuantileHead label is now stale relative to "
                f"{panel_in}; an INVALIDATION RECEIPT was written. Once RenQuant PR #427 "
                f"(consumer-side enforcement in scripts/train_ngboost_proper.py) is merged, "
                f"this BLOCKS σ-head training until a validated build_raw_fwd60d_label "
                f"refresh clears the receipt."
            )
            if not ctx.quiet:
                post_ntfy("RenQuant retrain SIGMA-HEAD-RAWLABEL", body, ctx.ntfy_topic)
            log.error("σ-head _rawlabel refresh failed (isolated, retrain continues): %s", exc)
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


def _stamp_calibrator_fingerprint(scorer_path: Path, calibrator_path: Path) -> None:
    """Stamp the calibrator metadata with the scorer's fingerprint identity.

    The runtime's ``_assert_calibrator_matches_scorer`` builds identity claims
    from ``metadata`` keys (``scorer_model_content_fingerprint``,
    ``artifact_fingerprint``, etc.) — NOT the top-level
    ``model_content_sha256``.  It computes scorer identity via the legacy
    ``stamp_artifact_metadata`` shim (path-based file hash) at load time.

    This function replicates that computation and writes the result into the
    calibrator's ``metadata`` dict so the legacy route matches.
    """
    import warnings  # noqa: PLC0415

    cal = read_json_object(calibrator_path, "calibrator for fingerprint")
    scorer = read_json_object(scorer_path, "scorer for fingerprint")
    try:
        from renquant_common.model_fingerprint import (  # noqa: PLC0415
            model_content_sha256_from_path,
            stamp_artifact_metadata,
        )
    except ImportError:
        log.warning(
            "StampCalibratorFingerprintTask: renquant_common.model_fingerprint "
            "not available — skipping stamp (calibrator will fail fingerprint "
            "verification at runtime)"
        )
        return
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        scorer_meta = stamp_artifact_metadata(
            {k: v for k, v in scorer.items() if k != "booster_raw_json"},
            scorer_path,
            payload=scorer,
        )
    legacy_hash = scorer_meta.get("model_content_fingerprint")
    artifact_hash = scorer_meta.get("artifact_fingerprint")
    if "metadata" not in cal:
        cal["metadata"] = {}
    cal["metadata"]["scorer_model_content_fingerprint"] = legacy_hash
    cal["metadata"]["scorer_artifact_fingerprint"] = artifact_hash
    cal["metadata"]["model_content_fingerprint"] = legacy_hash
    cal["metadata"]["artifact_fingerprint"] = artifact_hash
    cal["metadata"]["artifact_sha256"] = artifact_hash
    calibrator_path.write_text(json.dumps(cal, indent=1))
    log.info(
        "StampCalibratorFingerprintTask: stamped %s — "
        "legacy=%s artifact=%s",
        calibrator_path.name,
        legacy_hash,
        artifact_hash,
    )


class StampCalibratorFingerprintTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        if ctx.dry_run:
            return True
        _stamp_calibrator_fingerprint(ctx.xgb_artifact_out, ctx.calibrator_out)
        return True


class RetrainJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [
            RefreshFullUniverseOhlcvTask(),
            PanelUniverseFreshnessGuardTask(),
            BuildAlpha158PanelTask(),
            MergeFundFeaturesTask(),
            RefreshSigmaHeadRawLabelTask(),
            TrainGbdtScorerTask(),
            RefitCalibratorTask(),
            StampCalibratorFingerprintTask(),
        ]


def build_pipeline() -> Pipeline:
    return Pipeline([RetrainJob()], name="weekly-alpha158-fund-retrain")


def _default_xgb_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json"


def _default_calibrator_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "prod" / "panel-rank-calibration.json"


def _parse_cli_date(raw: str) -> "dt.date":
    """Parse an ISO ``YYYY-MM-DD`` for ``--expected-session`` (argparse type)."""
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected an ISO date (YYYY-MM-DD): {raw!r} ({exc})"
        ) from exc


def _parse_cli_as_of(raw: str) -> "dt.datetime":
    """Parse ``--as-of`` for the freshness reference clock.

    A full ISO timestamp (contains ``T`` or a ``:`` time) is used verbatim; a
    BARE date is interpreted as that day's end-of-session (23:59:59), so
    ``--as-of 2026-06-30`` treats 2026-06-30's session as completed rather than
    as midnight (which the calendar would read as the PRIOR session)."""
    has_time = ("T" in raw) or (":" in raw)
    if has_time:
        try:
            return dt.datetime.fromisoformat(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"expected an ISO datetime: {raw!r} ({exc})"
            ) from exc
    try:
        day = dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"expected an ISO date or datetime: {raw!r} ({exc})"
        ) from exc
    return dt.datetime(day.year, day.month, day.day, 23, 59, 59)


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
        "--refresh-rawlabel",
        default=True,
        action=argparse.BooleanOptionalAction,
        help=(
            "Rebuild the σ-head (QuantileHead) RAW _rawlabel panel in lockstep "
            "with the fresh fund panel after the merge (fix #1: it had no retrain "
            "cadence and drifted behind the ranker panel). Failure is isolated "
            "(alerts + logs, never aborts the ranker retrain). --no-refresh-rawlabel skips."
        ),
    )
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
        help=(
            "A panel ticker is stale when its newest bar lags the expected "
            "latest completed exchange session by MORE than this many sessions. "
            "Default 1 (a narrowly-justified single-session operational lag); "
            "the old default of 10 tolerated a ~two-week per-name mismatch that "
            "materially moves cross-sectional ranks. Widen it only as a "
            "deliberate, documented per-run override (recorded in the "
            "freshness_report)."
        ),
    )
    parser.add_argument(
        "--freshness-max-stale-fraction",
        type=float,
        default=DEFAULT_FRESHNESS_MAX_STALE_FRACTION,
        help=(
            "Tolerated fraction of the panel universe that may be stale before "
            "the guard trips. STRICT 0.0 by default (fail-closed on any stale "
            "name): delistings are pruned via the versioned inventory, so the "
            "active universe must be fresh. Raise it only as a deliberate, "
            "documented per-run override — the old 10% default was unjustified "
            "and could hide ~29 frozen names."
        ),
    )
    parser.add_argument(
        "--freshness-fail-on-stale",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Fail the retrain when the guard trips (default, fail-closed). --no-freshness-fail-on-stale only warns (ntfy) and proceeds.",
    )
    parser.add_argument(
        "--expected-session",
        type=_parse_cli_date,
        default=None,
        help=(
            "Pin the expected latest completed exchange session (YYYY-MM-DD) the "
            "freshness guard measures every panel ticker against, INSTEAD of "
            "deriving it from the wall clock. Use for deterministic historical "
            "replay / reproducible audits so freshness never depends on when the "
            "job happens to run. Persisted (as an override) in the "
            "freshness_report. Takes priority over --as-of."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=_parse_cli_as_of,
        default=None,
        help=(
            "Pin the wall clock (YYYY-MM-DD or an ISO timestamp) used to DERIVE "
            "the expected session through the shared exchange calendar (holiday / "
            "half-day aware), for historical replay that should still exercise "
            "the calendar. A bare date is treated as that day's end-of-session. "
            "--expected-session wins when both are given."
        ),
    )
    parser.add_argument("--ntfy-topic", default=DEFAULT_NTFY_TOPIC)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    validate_repo_dir(repo_dir, _REQUIRED_REPO_PATHS)
    xgb_artifact_out = (
        resolve_path(repo_dir, args.xgb_artifact_out)
        if args.xgb_artifact_out
        else _default_xgb_artifact(repo_dir)
    )
    calibrator_out = (
        resolve_path(repo_dir, args.calibrator_out)
        if args.calibrator_out
        else _default_calibrator_artifact(repo_dir)
    )
    if args.staged:
        if not args.xgb_artifact_out:
            xgb_artifact_out = staging_path(xgb_artifact_out)
        if not args.calibrator_out:
            calibrator_out = staging_path(calibrator_out)
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
    # Historical-replay / reproducibility injection: --expected-session pins the
    # reference session directly (fully deterministic, no clock / calendar); or
    # --as-of pins the wall clock and lets the exchange calendar derive it. Both
    # keep freshness from depending on the ambient wall clock.
    now_fn: "Callable[[], object] | None" = None
    if args.as_of is not None:
        _as_of = args.as_of
        now_fn = lambda: _as_of  # noqa: E731 - tiny closure over the pinned clock
    ctx = RetrainContext(
        repo_dir=repo_dir,
        xgb_artifact_out=xgb_artifact_out,
        calibrator_out=calibrator_out,
        strategy_config_path=args.strategy_config.expanduser().resolve() if args.strategy_config else None,
        drop_sentiment=args.drop_sentiment,
        truncate_to_sec_max=args.truncate_to_sec_max,
        dry_run=args.dry_run,
        refresh_ohlcv=args.refresh_ohlcv,
        refresh_rawlabel=args.refresh_rawlabel,
        panel_universe=panel_universe,
        inventory_path=inventory_path,
        ohlcv_timeout_sec=args.ohlcv_timeout_sec,
        freshness_stale_after_days=args.freshness_stale_after_days,
        freshness_max_stale_fraction=args.freshness_max_stale_fraction,
        freshness_fail_on_stale=args.freshness_fail_on_stale,
        expected_session=args.expected_session,
        now_fn=now_fn,
        ntfy_topic=args.ntfy_topic,
    )
    build_pipeline().run(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
