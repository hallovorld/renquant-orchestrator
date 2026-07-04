#!/usr/bin/env python3
"""M4-b relative-conviction-floor replay harness (READ-ONLY, run-gated).

Implements the frozen evaluation protocol of
``doc/design/2026-07-03-m4b-relative-conviction-floor.md`` (#260, merged) §4:
replay the four candidate floor re-derivations against the CURRENT absolute
floor on the S5/S8 substrate at MATCHED ADMISSION RATES, scoring realized
forward excess with date-block bootstrap statistics and per-regime / per-era
cuts, evaluating the five frozen Stage 1 win criteria verbatim.

STAGE / RUN GATE (stated per the two-stage contract, design §3):
  This tool NOMINATES at most a ``candidate-for-shadow``; it never authorizes
  a live enable. The CONFIRMATORY Stage 1 run is GATED on the substrate:
  >= MIN_STAGE1_SESSIONS (10) canonical sessions produced under the CURRENT
  scorer/calibrator pairing (P1 restore 2026-07-03: prod scorer restored to
  the 06-21 model + calibrator refit against it) WITH resolved primary-horizon
  outcomes. Pairing membership is established per bar by the fidelity check
  (replayed ER(raw) reproduces the stored prod mu to <= PAIRING_FIDELITY_TOL),
  never assumed from dates. Until the gate is met every replay output is
  stamped PRE-GATE EXPLORATORY (design §4 criterion 6: deviations downgrade
  the run to exploratory).

CANDIDATE ARMS (design §2, all on the recentered mu cross-section):
  baseline      mu_stored >= 0.03           (exactly today's production rule)
  (a) quantile  mu_rec >= Q_{1-K}(bar) AND mu_rec > 0        [PRIMARY]
  (b) dispersion mu_rec >= k*MAD(bar) AND mu_rec > 0         [CHALLENGER]
  (c) absolute  mu_rec >= c                                  [fallback]
  (d) NGBoost sigma-band: SKIPPED. Deferral note (design §2(d), verbatim
      posture): the sigma head is trained+promoted but the sigma-wire is OFF
      per the 2026-05-17 A/B (global NULL, per-regime SUSPECT-negative,
      consistent with E55); reopening the sigma-wire is a separate decision
      with its own recorded negative history and must be re-pitched on its
      own merits, never smuggled in as a floor re-derivation. Additionally
      gated on a sigma-calibration check before any expectancy read counts.

MATCHED BREADTH (design §4): target B = baseline mean floor-clearing count
over the replay window; each candidate's single parameter is set ONCE on the
window such that its mean floor-clearing count is within +/-BREADTH_TOL of B.
No per-bar retuning. Per-bar statistics (center, quantile, MAD) are computed
on the FULL scored candidate cross-section (pre-veto) — the pipeline #147
footgun lesson.

VETO STACK (identical across arms): rows vetoed UPSTREAM of the conviction
gate (VetoWeakBuys rank floor, regime admission, fundamentals fail-close —
recorded in ``score_distribution.blocked_by``; those tasks run BEFORE
ConvictionGateTask, so upstream-vetoed rows never reached the floor) are
excluded from every arm's floor universe. Rows blocked AT the floor
(``conviction:*``) or DOWNSTREAM of it (``qp_*``, ``kelly_*``, ``size_*``,
``correlation``) remain floor-eligible in all arms. BL-4 (signal-direction)
is applied at the OUTCOME stage on a selectable basis (--bl4-basis):
``prod-raw`` (default: raw>0 for every arm — the design §4 sentence "BL-4
... applied identically to all arms" read literally, and today's production
BL-4 semantics), ``arm`` (each arm's own deployed world — baseline tests
raw>0, recentered arms test raw>center, i.e. the post-M4 BL-4; sensitivity),
or ``off`` (sensitivity). Note for (a)/(b) the mu_rec>0 side-condition
already implies raw>center, so the basis choice binds mainly the baseline
and (c) arms.

WINDOW (--window): ``pairing`` (default) restricts the replay to bars scored
under the CURRENT scorer/calibrator pairing — the harness re-measures the
current pairing's baseline breadth B before replaying, per the P1-restore
context (the pre-restore June bars carry the retired pairing's intercept and
would poison B). ``all`` widens to every canonical bar (cross-era,
exploratory; recorded as a deviation).

STATISTICS: date-block bootstrap of the admitted-set expectancy delta,
block-5 primary, block-1 sensitivity. SMALL-N BRANCH (V3 method note,
orchestrator #269): with < SMALL_N_DATES (15) resolved dates the block
bootstrap distribution is enumerated EXACTLY over all block-start tuples and
significance reduces to exact tail masses P(delta<=0) / P(delta>=0) — no
Monte Carlo noise, no seed, no quantile-indexing convention. MC (seeded) is
used only when exact enumeration is infeasible, and is recorded as a
deviation when n_dates < SMALL_N_DATES.

CONTROLS (V3 lesson — the machinery must be validated before its verdict
counts):
  POSITIVE (S-REL): plant a floor-detectable admitted-set effect (candidate
  minus baseline symmetric difference gets +/-gap/2) at realistic noise
  scale; report detection power of frozen criterion 1 per gap size.
  TRUE-NULL (two): (i) iid noise outcomes independent of admission; (ii)
  within-date permutation of the REAL outcomes (breaks the admission->
  outcome link, preserves date marginals). Report criterion-1 false-fire
  rates (nominal 2.5%); both run through the SAME small-n exact-tail /
  MC dispatch as the verdict path.

MODES:
  --replay           full Stage-1 protocol run (default; --window pairing
                     restricts to current-pairing bars and re-measures the
                     current pairing's baseline B first — the P1-restore
                     requirement; --window all = cross-era exploratory)
  --baseline-report  P1 A/B reader: per-run intercept / sign-laundering /
                     floor-clearing / mu-center stats for the last N full
                     runs, replayed against the CURRENT calibrator artifact
                     with a fidelity (pairing) check. This is the reader for
                     the #280 registered prediction (sign_laundered collapses
                     from ~45 to single digits under the restored pairing).
  --controls         run positive + true-null controls only
  --gate-check       report Stage-1 run-gate status and exit

STRICTLY READ-ONLY: sqlite opened with mode=ro; the calibrator JSON is read,
never written. No pipeline imports — pure-python knot interpolation and
zero-crossing per the V5-verified (#272) independent recomputation, which
reproduced prod mu to <= 4e-18.

Usage:
  scripts/m4b_floor_replay.py --replay --json-out doc/research/evidence/....json
  scripts/m4b_floor_replay.py --baseline-report --runs 10
  scripts/m4b_floor_replay.py --controls --control-reps 400
  scripts/m4b_floor_replay.py --gate-check
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import itertools
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from renquant_orchestrator.expkit.replay import canonical_runs as _expkit_canonical_runs  # noqa: E402

# ------------------------------------------------------------------ paths
DEFAULT_DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
# The LIVE calibrator artifact: strategy_config.json ranking.panel_scoring
# pins artifacts/prod/panel-rank-calibration.json (the P1-restore refit,
# trained 2026-07-03 against the restored 06-21 scorer, neutral ~= -0.267).
DEFAULT_CALIBRATOR = (
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/"
    "prod/panel-rank-calibration.json"
)

# ---------------------------------------------------- PRE-REGISTERED (§4)
# Frozen BEFORE any confirmatory run; changing any value after results are
# seen downgrades the run to exploratory (design §4 criterion 6).
FLOOR = 0.03                # baseline: production conviction floor (mu_stored)
COST_PROXY = 0.0011         # 11 bps round-trip winner threshold (M3 convention)
TOP_N = 3                   # panel_buy_top_n (A-2 contract: stays 3)
BLOCK_PRIMARY = 5           # block-5 primary (M3: block-13 degenerate here)
BLOCK_SENS = 1              # block-1 sensitivity, carried alongside
N_BOOT = 5000
SEED = 20260703
SMALL_N_DATES = 15          # V3: < 15 dates => exact tail masses required
EXACT_ENUM_LIMIT = 300_000  # max block-start tuples to enumerate exactly
MIN_FULL_RUN_CANDIDATES = 40
MAX_EFFDATE_LAG_DAYS = 4    # weekend-run mapping, exactly as M3
BREADTH_TOL = 0.5           # matched mean floor-clearing count tolerance (§4)
MIN_CUT_DATES = 5           # criterion 2: cuts with >= 5 resolved dates
MIN_STAGE1_SESSIONS = 10    # run gate: current-pairing sessions w/ outcomes
PAIRING_FIDELITY_TOL = 1e-9  # replayed-vs-stored mu match => current pairing
HORIZONS = ("fwd_20d", "fwd_60d", "fwd_10d", "fwd_5d")
PRIMARY_HORIZON = "fwd_20d"  # fwd_60d unresolvable until ~Aug 2026 (§4/§7)

# Criterion 5 admission-distribution tolerances, PRE-REGISTERED HERE (the
# design required them set in the replay-implementation PR before results
# are seen). A candidate must match baseline on ALL FOUR to clear criterion
# 5; a mean-matched candidate that diverges is reported explicitly as an
# A-2-adjacent finding either way.
TOL_SATURATION_FREQ = 0.10  # |top_n saturation freq - baseline| <= 0.10
TOL_P90_COUNT = 2.0         # |p90 admitted-count - baseline| <= 2 names
TOL_P95_COUNT = 2.0         # |p95 admitted-count - baseline| <= 2 names
TOL_SPILL_FREQ = 0.10       # |QP spill freq - baseline| <= 0.10
TOL_ZERO_STREAK_EXTRA = 1   # max zero-streak <= baseline max + 1

# QP spill pressure: measured as floor-clearing names beyond panel_buy_top_n
# (frequency of bars where count > TOP_N, plus the p90 of the excess). The
# design asks for spill against the ACTUAL QP step's caps
# (correlation/sector/whole-share); a full QP replay needs per-bar prices +
# guards and is NOT reconstructable read-only from stored scores. RECORDED
# DEVIATION: this proxy pins distributional spill behavior beyond the mean
# (the reviewer's ask) but is not the full QP-cap computation; the Stage-1
# results doc must carry this note.
SPILL_PROXY_NOTE = (
    "qp_spill computed as floor-clearing count > panel_buy_top_n (3); "
    "full QP-cap replay (correlation/sector/whole-share) deferred - "
    "recorded deviation, see design §4 criterion 6"
)

# blocked_by prefixes UPSTREAM of the conviction gate (excluded from every
# arm's floor universe). Everything else (floor-layer conviction:*, and
# downstream qp_*/kelly_*/size_*/correlation) stays floor-eligible.
# Taxonomy verified against job_panel_scoring task order + the DB's distinct
# blocked_by values: veto:rank_score_below_floor (VetoWeakBuysTask),
# regime_admission:failed:* and panel_fundamentals_missing (fail-closed
# scoring) all run BEFORE ConvictionGateTask.
UPSTREAM_VETO_PREFIXES = (
    "veto:", "regime_admission:", "panel_fundamentals_missing")

NGBOOST_SKIP_NOTE = (
    "candidate (d) NGBoost sigma-band SKIPPED per design §2(d): sigma head "
    "trained+promoted (ngb 30b0460a, 2026-05-17) but the sigma-wire is OFF "
    "per the 2026-05-17 A/B (global sigma-on NULL; per-regime SUSPECT-neg; "
    "consistent with E55). Reopening the sigma-wire is a separate operator "
    "decision with its own recorded negative history — it must be re-pitched "
    "on its own merits, never smuggled in as a floor re-derivation; its "
    "expectancy read additionally requires a sigma-calibration check "
    "(predicted sigma rank-correlates with realized |mu - fwd|) first."
)

_LEGACY_TOURNAMENT_TYPES = {"Classification", "Manual", "QLearning", "XGBoost"}


# ------------------------------------------------------------- calibrator
class Calibrator:
    """Pure-python global panel calibration reader (no pipeline imports).

    Interpolation, zero-crossing and horizon scaling follow
    ``renquant_pipeline.kernel.panel_pipeline.global_calibrator`` /
    ``job_panel_scoring._calibrator_expected_return_at_horizon`` exactly;
    the V5 verification (#272) demonstrated this reproduction is exact.
    """

    def __init__(self, doc: dict, path: str = "<mem>", sha256: str = ""):
        self.path = path
        self.sha256 = sha256
        self.trained_date = doc.get("trained_date")
        self.metadata = dict(doc.get("metadata") or {})
        er = doc.get("expected_return") or {}
        self.er_clip_bound = self._clip_bound()
        self.er_x = np.asarray(er.get("x") or [], dtype=float)
        # pipeline clips er_y to +/-er_clip_bound at LOAD time
        self.er_y = np.clip(
            np.asarray(er.get("y") or [], dtype=float),
            -self.er_clip_bound, self.er_clip_bound,
        )

    @classmethod
    def load(cls, path: str) -> "Calibrator":
        raw = Path(path).read_bytes()
        return cls(json.loads(raw), path=str(path),
                   sha256=hashlib.sha256(raw).hexdigest())

    def _clip_bound(self) -> float:
        try:
            b = float((self.metadata or {}).get("er_clip_bound", 0.20))
            if math.isfinite(b) and b > 0:
                return b
        except (TypeError, ValueError):
            pass
        return 0.20

    @property
    def neutral_raw(self) -> float | None:
        """ER=0 crossing, pipeline-exact rule: scan from the low-raw end;
        a knot exactly at 0 returns that knot's x (flat-span LEFT edge);
        a strict sign change interpolates; never crossing returns None."""
        xs, ys = self.er_x, self.er_y
        if len(xs) < 2:
            return None
        for i in range(len(ys) - 1):
            if ys[i] == 0.0:
                return float(xs[i])
            if ys[i] * ys[i + 1] < 0.0:
                x0, x1 = float(xs[i]), float(xs[i + 1])
                return x0 + (x1 - x0) * (0.0 - ys[i]) / (ys[i + 1] - ys[i])
        if ys[-1] == 0.0:
            return float(xs[-1])
        return None

    def native_lookahead_days(self) -> int | None:
        for key in ("lookahead_days_used", "lookahead_days", "er_lookahead"):
            try:
                d = int(self.metadata.get(key))
            except (TypeError, ValueError):
                continue
            if d > 0:
                return d
        return None

    def er_native(self, raws: np.ndarray) -> np.ndarray:
        if len(self.er_x) == 0:
            return np.zeros(np.shape(raws), dtype=float)
        return np.interp(raws, self.er_x, self.er_y,
                         left=self.er_y[0], right=self.er_y[-1])

    def mu_at_horizon(self, raws: np.ndarray,
                      horizon_days: int | None) -> np.ndarray:
        """ER scaled native->horizon with re-clip to +/-er_clip_bound
        (job_panel_scoring R2-audit behavior)."""
        vals = self.er_native(raws)
        native = self.native_lookahead_days()
        if (horizon_days is None or native is None or native <= 0
                or int(horizon_days) == native):
            return np.clip(vals, -self.er_clip_bound, self.er_clip_bound)
        scaled = vals * (float(horizon_days) / float(native))
        return np.clip(scaled, -self.er_clip_bound, self.er_clip_bound)


# ------------------------------------------------------------------- bars
@dataclass
class Bar:
    run_id: str
    date: str
    regime: str
    era: str
    tickers: list[str]
    raw: np.ndarray
    mu_stored: np.ndarray          # NaN where prod stored no mu
    eligible: np.ndarray           # bool: not vetoed upstream of the floor
    mu_horizon_days: int | None
    counters: dict = field(default_factory=dict)
    # filled by replay:
    center: float = float("nan")
    mu_rec: np.ndarray | None = None
    mad: float = float("nan")
    fidelity: float | None = None  # max |ER(raw)@horizon - mu_stored|
    is_current_pairing: bool = False
    excess: dict = field(default_factory=dict)   # horizon -> np.ndarray (NaN)


def classify_era(active_scorer: str | None, model_type: str | None) -> str:
    """Retired-scorer vs panel-era cut (design §4). Same coarse rule as M3."""
    label = active_scorer or model_type
    if label is None or label == "":
        return "pre_tournament_null"
    if label in _LEGACY_TOURNAMENT_TYPES:
        return "legacy_tournament"
    return str(label)


def is_upstream_vetoed(blocked_by: str | None) -> bool:
    if not blocked_by:
        return False
    return any(blocked_by.startswith(p) for p in UPSTREAM_VETO_PREFIXES)


def open_ro(path: str) -> sqlite3.Connection:
    """Read-only connection — the harness must never mutate the trade DB."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def canonical_runs(con: sqlite3.Connection,
                   min_candidates: int = MIN_FULL_RUN_CANDIDATES) -> list[dict]:
    """One canonical live run per date -- forwards to the shared
    ``expkit.replay.canonical_runs`` (the M3/#234 dedup discipline).

    Kept as a thin local wrapper (rather than switching every call site to
    the expkit import directly) so this script's own default
    (``MIN_FULL_RUN_CANDIDATES``, an M4b-specific threshold) stays local
    while the dedup SQL itself has exactly one implementation, shared with
    every other arm-vs-arm replay experiment via ``expkit.replay``."""
    return _expkit_canonical_runs(con, min_candidates)


def load_bars(con: sqlite3.Connection, runs: list[dict]) -> list[Bar]:
    bars: list[Bar] = []
    for r in runs:
        rows = con.execute(
            """
            SELECT ticker, raw_panel, mu, blocked_by, active_scorer,
                   model_type, mu_horizon_days
            FROM score_distribution
            WHERE run_id=? AND is_holding=0 AND raw_panel IS NOT NULL
            ORDER BY ticker
            """,
            (r["run_id"],),
        ).fetchall()
        tickers, raws, mus, elig = [], [], [], []
        eras: Counter = Counter()
        horizons: Counter = Counter()
        for t, raw, mu, blocked_by, scorer, mtype, mu_h in rows:
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(v):
                continue
            tickers.append(str(t))
            raws.append(v)
            mus.append(float(mu) if mu is not None else float("nan"))
            elig.append(not is_upstream_vetoed(blocked_by))
            eras[classify_era(scorer, mtype)] += 1
            if mu_h is not None:
                horizons[int(mu_h)] += 1
        if not tickers:
            continue
        bars.append(Bar(
            run_id=r["run_id"], date=r["run_date"], regime=r["regime"],
            era=eras.most_common(1)[0][0],
            tickers=tickers,
            raw=np.asarray(raws, dtype=float),
            mu_stored=np.asarray(mus, dtype=float),
            eligible=np.asarray(elig, dtype=bool),
            mu_horizon_days=(horizons.most_common(1)[0][0]
                             if horizons else None),
            counters=r.get("counters", {}),
        ))
    return bars


def replay_bars(bars: list[Bar], cal: Calibrator,
                deviations: list[str]) -> None:
    """Fill mu_rec (recentered replay), MAD, fidelity + pairing flags."""
    anchor = cal.neutral_raw
    if anchor is None:
        raise SystemExit(
            "calibrator ER head never crosses zero — recentering has no "
            "anchor; replay is meaningless for this artifact (design §2)."
        )
    for b in bars:
        b.center = float(np.median(b.raw))            # per-bar stats on the
        b.mu_rec = cal.mu_at_horizon(                 # FULL cross-section
            b.raw - b.center + anchor, b.mu_horizon_days)
        b.mad = float(np.median(np.abs(b.mu_rec - np.median(b.mu_rec))))
        replayed = cal.mu_at_horizon(b.raw, b.mu_horizon_days)
        stored_ok = np.isfinite(b.mu_stored)
        if stored_ok.any():
            b.fidelity = float(
                np.max(np.abs(replayed[stored_ok] - b.mu_stored[stored_ok])))
            b.is_current_pairing = b.fidelity <= PAIRING_FIDELITY_TOL
        else:
            b.fidelity = None
            b.is_current_pairing = False
            deviations.append(
                f"{b.date}: no stored mu — pairing undeterminable; bar "
                "treated as NOT current-pairing")


# ---------------------------------------------------------------- outcomes
def attach_outcomes(con: sqlite3.Connection, bars: list[Bar]) -> dict:
    """Excess over SPY per horizon, both legs from the same effective
    as_of_date (weekend mapping within MAX_EFFDATE_LAG_DAYS — exactly M3)."""
    eff_cache: dict[str, str | None] = {}
    row_cache: dict[tuple, tuple | None] = {}

    def eff_date(run_date: str) -> str | None:
        if run_date not in eff_cache:
            row = con.execute(
                "SELECT MAX(as_of_date) FROM ticker_forward_returns "
                "WHERE as_of_date <= ?", (run_date,)).fetchone()
            eff = row[0]
            if eff is not None:
                d0 = _dt.date.fromisoformat(run_date)
                d1 = _dt.date.fromisoformat(eff)
                if (d0 - d1).days > MAX_EFFDATE_LAG_DAYS:
                    eff = None
            eff_cache[run_date] = eff
        return eff_cache[run_date]

    def fwd_row(ticker: str, eff: str):
        key = (ticker, eff)
        if key not in row_cache:
            row_cache[key] = con.execute(
                "SELECT fwd_20d, fwd_60d, fwd_10d, fwd_5d "
                "FROM ticker_forward_returns WHERE ticker=? AND as_of_date=?",
                (ticker, eff)).fetchone()
        return row_cache[key]

    coverage = {h: {"resolved": 0, "unresolved": 0} for h in HORIZONS}
    for b in bars:
        eff = eff_date(b.date)
        for h in HORIZONS:
            b.excess[h] = np.full(len(b.tickers), np.nan)
        if eff is None:
            for h in HORIZONS:
                coverage[h]["unresolved"] += len(b.tickers)
            continue
        spy = fwd_row("SPY", eff)
        for i, t in enumerate(b.tickers):
            tr = fwd_row(t, eff)
            for idx, h in enumerate(HORIZONS):
                tv = tr[idx] if tr else None
                sv = spy[idx] if spy else None
                if tv is not None and sv is not None:
                    b.excess[h][i] = float(tv) - float(sv)
                    coverage[h]["resolved"] += 1
                else:
                    coverage[h]["unresolved"] += 1
    return coverage


# ------------------------------------------------------------------- arms
def floor_clearing(bar: Bar, arm: str, param: float | None) -> np.ndarray:
    """Boolean floor-clearing mask for an arm on one bar (design §2 rules).

    Per-bar statistics (quantile, MAD) are computed over the FULL scored
    cross-section (pre-veto, #147 lesson); eligibility (upstream vetoes) then
    masks the ADMITTED set identically across arms.
    """
    if arm == "baseline":
        with np.errstate(invalid="ignore"):
            return bar.eligible & (bar.mu_stored >= FLOOR)
    mu = bar.mu_rec
    if arm == "quantile":          # (a) top-K% AND mu>0
        thr = float(np.quantile(mu, 1.0 - float(param)))
        return bar.eligible & (mu >= thr) & (mu > 0.0)
    if arm == "dispersion":        # (b) mu >= k*MAD AND mu>0
        return bar.eligible & (mu >= float(param) * bar.mad) & (mu > 0.0)
    if arm == "absolute":          # (c) re-anchored absolute
        return bar.eligible & (mu >= float(param))
    raise ValueError(f"unknown arm {arm!r}")


def bl4_mask(bar: Bar, arm: str, basis: str) -> np.ndarray:
    """Signal-direction (BL-4) mask, applied at the outcome stage.

    ``prod-raw`` (default): raw>0 for EVERY arm — the literal reading of the
    design §4 "BL-4 ... applied identically to all arms" and today's prod
    semantics. ``arm``: each arm's own deployed world — baseline tests the
    production raw sign (raw>0); recentered arms test the recentered sign
    (raw>center), i.e. BL-4 as it would run post-M4. ``off``: no mask.
    """
    if basis == "off":
        return np.ones(len(bar.tickers), dtype=bool)
    if basis == "prod-raw" or arm == "baseline":
        return bar.raw > 0.0
    return bar.raw > bar.center


def mean_count(bars: list[Bar], arm: str, param: float | None) -> float:
    return float(np.mean([floor_clearing(b, arm, param).sum() for b in bars]))


def solve_matched_param(bars: list[Bar], arm: str, target: float,
                        lo: float, hi: float, increasing: bool,
                        tol: float = BREADTH_TOL, iters: int = 200) -> dict:
    """Set the arm's single parameter ONCE so its mean floor-clearing count
    matches the baseline's within +/-tol (design §4). Bisection on the
    monotone (step) map param -> mean count; no per-bar retuning ever."""
    f_lo, f_hi = mean_count(bars, arm, lo), mean_count(bars, arm, hi)
    best = None
    for cand, cnt in ((lo, f_lo), (hi, f_hi)):
        if best is None or abs(cnt - target) < abs(best[1] - target):
            best = (cand, cnt)
    a, b = lo, hi
    for _ in range(iters):
        mid = 0.5 * (a + b)
        f_mid = mean_count(bars, arm, mid)
        if abs(f_mid - target) < abs(best[1] - target):
            best = (mid, f_mid)
        if abs(f_mid - target) <= 1e-12:
            break
        under = f_mid < target
        if increasing:
            a, b = (mid, b) if under else (a, mid)
        else:
            a, b = (a, mid) if under else (mid, b)
    param, achieved = best
    return {
        "arm": arm, "param": float(param), "achieved_mean": float(achieved),
        "target": float(target), "matched": abs(achieved - target) <= tol,
        "bounds_mean": [float(f_lo), float(f_hi)],
    }


# ------------------------------------------------- admission distribution
def max_zero_streak(counts: list[int]) -> int:
    best = cur = 0
    for c in counts:
        cur = cur + 1 if c == 0 else 0
        best = max(best, cur)
    return best


def admission_metrics(bars: list[Bar], arm: str, param: float | None) -> dict:
    counts = [int(floor_clearing(b, arm, param).sum()) for b in bars]
    arr = np.asarray(counts, dtype=float)
    spill = arr > TOP_N
    return {
        "arm": arm, "param": param,
        "counts_by_date": {b.date: c for b, c in zip(bars, counts)},
        "mean": float(arr.mean()),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "topn_saturation_freq": float(np.mean(arr >= TOP_N)),
        "qp_spill_freq": float(np.mean(spill)),
        "qp_spill_excess_p90": float(
            np.percentile(np.maximum(arr - TOP_N, 0.0), 90)),
        "zero_admission_freq": float(np.mean(arr == 0)),
        "max_zero_streak": max_zero_streak(counts),
        "spill_proxy_note": SPILL_PROXY_NOTE,
    }


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation (average ranks for ties; no scipy)."""
    if len(x) < 3 or len(x) != len(y):
        return None

    def ranks(v):
        arr = np.asarray(v, dtype=float)
        order = np.argsort(arr, kind="mergesort")
        rk = np.empty(len(arr))
        i = 0
        while i < len(arr):
            j = i
            while j + 1 < len(arr) and arr[order[j + 1]] == arr[order[i]]:
                j += 1
            rk[order[i:j + 1]] = 0.5 * (i + j) + 1.0
            i = j + 1
        return rk

    rx, ry = ranks(x), ranks(y)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return None
    return float(np.mean((rx - rx.mean()) * (ry - ry.mean())) / (sx * sy))


# --------------------------------------------------------------- statistics
def per_date_agg(bars: list[Bar], horizon: str, base_masks: dict,
                 cand_masks: dict) -> tuple[list[str], np.ndarray]:
    """Per-date [sum_base, n_base, sum_cand, n_cand] over resolved outcomes."""
    agg: dict[str, list[float]] = {}
    for b in bars:
        ex = b.excess.get(horizon)
        if ex is None:
            continue
        ok = np.isfinite(ex)
        mb = base_masks[b.date] & ok
        mc = cand_masks[b.date] & ok
        if not (mb.any() or mc.any()):
            continue
        a = agg.setdefault(b.date, [0.0, 0.0, 0.0, 0.0])
        a[0] += float(ex[mb].sum()); a[1] += float(mb.sum())
        a[2] += float(ex[mc].sum()); a[3] += float(mc.sum())
    dates = sorted(agg)
    return dates, np.asarray([agg[d] for d in dates], dtype=float)


def _delta(sumA: float, nA: float, sumK: float, nK: float) -> float | None:
    if nA == 0 or nK == 0:
        return None
    return sumK / nK - sumA / nA


def exact_block_bootstrap(dates: list[str], A: np.ndarray,
                          block_len: int) -> dict:
    """V3 small-n branch: the circular block bootstrap sample is fully
    determined by the tuple of block starts; when n^n_blocks is enumerable
    the distribution is EXACT and significance reduces to exact tail masses
    P(delta>=0)/P(delta<=0). No seed, no MC noise."""
    n = len(dates)
    if n == 0:
        return {"exact": False, "n_dates": 0, "n_tuples": 0}
    n_blocks = math.ceil(n / block_len)
    n_tuples = n ** n_blocks
    if n_tuples > EXACT_ENUM_LIMIT:
        return {"exact": False, "n_dates": n, "n_tuples": n_tuples}
    lens = [block_len] * n_blocks
    lens[-1] = n - block_len * (n_blocks - 1)
    deltas, skipped = [], 0
    for starts in itertools.product(range(n), repeat=n_blocks):
        sumA = nA = sumK = nK = 0.0
        for bi, s in enumerate(starts):
            for off in range(lens[bi]):
                r = A[(s + off) % n]
                sumA += r[0]; nA += r[1]; sumK += r[2]; nK += r[3]
        d = _delta(sumA, nA, sumK, nK)
        if d is None:
            skipped += 1
        else:
            deltas.append(d)
    if not deltas:
        return {"exact": False, "n_dates": n, "n_tuples": n_tuples,
                "n_skipped_empty": skipped}
    ds = np.sort(np.asarray(deltas))
    m = len(ds)
    p_ge0 = float(np.sum(ds >= 0)) / m
    p_le0 = float(np.sum(ds <= 0)) / m
    # DEGENERACY GUARD (M3's block-13 lesson, exact-branch form): when the
    # block covers the whole sample (block_len >= n) every start tuple is a
    # rotation of the full window and all atoms equal the observed delta — a
    # point mass whose "CI" excludes 0 whenever delta != 0. Such a
    # distribution carries NO resampling information; criterion 1 must not
    # fire on it.
    degenerate = bool(block_len >= n or ds[0] == ds[-1])
    return {
        "exact": True, "n_dates": n, "block_len": block_len,
        "n_tuples": n_tuples, "n_skipped_empty": skipped,
        "delta_min": float(ds[0]), "delta_max": float(ds[-1]),
        "ci95_interp": [float(np.percentile(ds, 2.5)),
                        float(np.percentile(ds, 97.5))],
        "p_ge_0": p_ge0, "p_le_0": p_le0,
        "two_sided_p": min(1.0, 2 * min(p_ge0, p_le0)),
        "n_atoms": m,
        "degenerate": degenerate,
    }


def mc_block_bootstrap(dates: list[str], A: np.ndarray, block_len: int,
                       seed: int = SEED, n_boot: int = N_BOOT) -> dict:
    n = len(dates)
    if n == 0:
        return {"exact": False, "mc": False, "n_dates": 0}
    rng = np.random.default_rng(seed + block_len)
    n_blocks = math.ceil(n / block_len)
    lens = [block_len] * n_blocks
    lens[-1] = n - block_len * (n_blocks - 1)
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    deltas = []
    for row in starts:
        sumA = nA = sumK = nK = 0.0
        for bi, s in enumerate(row):
            for off in range(lens[bi]):
                r = A[(s + off) % n]
                sumA += r[0]; nA += r[1]; sumK += r[2]; nK += r[3]
        d = _delta(sumA, nA, sumK, nK)
        if d is not None:
            deltas.append(d)
    if not deltas:
        return {"exact": False, "mc": True, "n_dates": n, "degenerate": True}
    ds = np.sort(np.asarray(deltas))
    return {
        "exact": False, "mc": True, "seed": seed + block_len,
        "block_len": block_len, "n_dates": n,
        "n_boot_effective": len(ds),
        "ci95": [float(np.percentile(ds, 2.5)),
                 float(np.percentile(ds, 97.5))],
        "p_ge_0": float(np.mean(ds >= 0)),
        "p_le_0": float(np.mean(ds <= 0)),
        "degenerate": bool(block_len >= n or ds[0] == ds[-1]),
    }


def delta_significance(dates: list[str], A: np.ndarray, block_len: int,
                       deviations: list[str] | None = None,
                       primary: bool = True) -> dict:
    """Small-n dispatch (V3): < SMALL_N_DATES resolved dates => exact tail
    masses required; an MC fallback on the PRIMARY block length there is a
    recorded deviation (block-1 sensitivity: n^n tuples are enumerable only
    for tiny n, so its MC fallback is expected and only branch-labelled)."""
    n = len(dates)
    if n < SMALL_N_DATES:
        res = exact_block_bootstrap(dates, A, block_len)
        if res.get("exact"):
            res["branch"] = "exact_small_n"
            return res
        if deviations is not None and primary:
            deviations.append(
                f"block-{block_len}: n_dates={n} < {SMALL_N_DATES} but exact "
                f"enumeration infeasible (n_tuples={res.get('n_tuples')}); "
                "MC fallback used — recorded deviation (V3 method note)")
        res = mc_block_bootstrap(dates, A, block_len)
        res["branch"] = "mc_fallback_small_n"
        return res
    res = mc_block_bootstrap(dates, A, block_len)
    res["branch"] = "mc"
    exact = exact_block_bootstrap(dates, A, block_len)
    if exact.get("exact"):
        res["exact_alongside"] = exact
    return res


def criterion1_pass(sig: dict, point_delta: float | None) -> bool:
    """Frozen criterion 1: delta > 0 with the block-5 95% CI excluding 0
    (exact branch: P(delta<=0) <= 0.025). A DEGENERATE resampling
    distribution (block covers the whole sample / point mass) can never
    fire — the M3 block-13 pathology, guarded here."""
    if point_delta is None or point_delta <= 0:
        return False
    if sig.get("degenerate"):
        return False
    if sig.get("exact"):
        return sig["p_le_0"] <= 0.025
    ci = sig.get("ci95")
    return bool(ci and ci[0] > 0)


# ------------------------------------------------------------- evaluation
def set_stats(ex: np.ndarray) -> dict:
    ex = ex[np.isfinite(ex)]
    n = int(ex.size)
    if n == 0:
        return {"n": 0, "mean_excess": None, "n_winners": 0, "n_losers": 0}
    winners = int(np.sum(ex > COST_PROXY))
    return {"n": n, "mean_excess": float(ex.mean()),
            "n_winners": winners, "n_losers": n - winners}


def evaluate_candidate(bars: list[Bar], arm: str, param: float | None,
                       horizon: str, bl4_basis: str,
                       deviations: list[str] | None = None) -> dict:
    """Full frozen-criteria evaluation of one candidate arm vs baseline."""
    base_fc = {b.date: floor_clearing(b, "baseline", None) for b in bars}
    cand_fc = {b.date: floor_clearing(b, arm, param) for b in bars}
    base_adm = {b.date: base_fc[b.date] & bl4_mask(b, "baseline", bl4_basis)
                for b in bars}
    cand_adm = {b.date: cand_fc[b.date] & bl4_mask(b, arm, bl4_basis)
                for b in bars}

    # pooled expectancy + removed-relative-to-baseline (criterion 3)
    base_ex, cand_ex, removed_ex = [], [], []
    for b in bars:
        ex = b.excess.get(horizon)
        if ex is None:
            continue
        ok = np.isfinite(ex)
        base_ex.append(ex[base_adm[b.date] & ok])
        cand_ex.append(ex[cand_adm[b.date] & ok])
        removed_ex.append(ex[base_adm[b.date] & ~cand_adm[b.date] & ok])
    base_ex = np.concatenate(base_ex) if base_ex else np.array([])
    cand_ex = np.concatenate(cand_ex) if cand_ex else np.array([])
    removed_ex = np.concatenate(removed_ex) if removed_ex else np.array([])
    base_stats, cand_stats, removed_stats = (
        set_stats(base_ex), set_stats(cand_ex), set_stats(removed_ex))
    point_delta = (
        cand_stats["mean_excess"] - base_stats["mean_excess"]
        if cand_stats["mean_excess"] is not None
        and base_stats["mean_excess"] is not None else None)

    dates, A = per_date_agg(bars, horizon, base_adm, cand_adm)
    sig5 = delta_significance(dates, A, BLOCK_PRIMARY, deviations,
                              primary=True)
    sig1 = delta_significance(dates, A, BLOCK_SENS, deviations,
                              primary=False)

    # criterion 2: per-regime / per-era point-estimate not-worse
    cuts: dict[str, dict] = {}
    crit2 = True
    for kind, key in (("regime", lambda b: b.regime),
                      ("era", lambda b: b.era)):
        for val in sorted({key(b) for b in bars}):
            sub = [b for b in bars if key(b) == val]
            sub_dates = {
                b.date for b in sub
                if b.excess.get(horizon) is not None
                and np.isfinite(b.excess[horizon]).any()}
            b_ex, c_ex = [], []
            for b in sub:
                ex = b.excess.get(horizon)
                if ex is None:
                    continue
                ok = np.isfinite(ex)
                b_ex.append(ex[base_adm[b.date] & ok])
                c_ex.append(ex[cand_adm[b.date] & ok])
            b_ex = np.concatenate(b_ex) if b_ex else np.array([])
            c_ex = np.concatenate(c_ex) if c_ex else np.array([])
            bs, cs = set_stats(b_ex), set_stats(c_ex)
            d = (cs["mean_excess"] - bs["mean_excess"]
                 if cs["mean_excess"] is not None
                 and bs["mean_excess"] is not None else None)
            counted = len(sub_dates) >= MIN_CUT_DATES
            entry = {"n_resolved_dates": len(sub_dates), "counted": counted,
                     "baseline": bs, "candidate": cs, "delta": d}
            cuts[f"{kind}:{val}"] = entry
            if counted:
                if d is None:
                    entry["note"] = ("delta undefined (an arm admits no "
                                     "resolved name in this cut) — reported, "
                                     "treated as not-cleared")
                    crit2 = False
                elif d < 0:
                    crit2 = False

    # criterion 3 (matched-breadth winners/losers-removed axis)
    crit3 = removed_stats["n_winners"] <= removed_stats["n_losers"]

    # criteria 4 + 5 on floor-clearing admission distributions
    base_m = admission_metrics(bars, "baseline", None)
    cand_m = admission_metrics(bars, arm, param)
    crit4 = cand_m["zero_admission_freq"] <= base_m["zero_admission_freq"]
    monotone_rho = None
    if arm == "dispersion":
        crit4 = crit4 and (cand_m["max_zero_streak"]
                           <= base_m["max_zero_streak"])
        mads = [b.mad for b in bars]
        counts = [cand_m["counts_by_date"][b.date] for b in bars]
        monotone_rho = spearman(mads, counts)
        crit4 = crit4 and (monotone_rho is not None and monotone_rho > 0)

    c5 = {
        "topn_saturation": abs(cand_m["topn_saturation_freq"]
                               - base_m["topn_saturation_freq"])
        <= TOL_SATURATION_FREQ,
        "p90": abs(cand_m["p90"] - base_m["p90"]) <= TOL_P90_COUNT,
        "p95": abs(cand_m["p95"] - base_m["p95"]) <= TOL_P95_COUNT,
        "qp_spill": abs(cand_m["qp_spill_freq"] - base_m["qp_spill_freq"])
        <= TOL_SPILL_FREQ,
        "zero_streak": cand_m["max_zero_streak"]
        <= base_m["max_zero_streak"] + TOL_ZERO_STREAK_EXTRA,
    }
    crit1 = criterion1_pass(sig5, point_delta)
    crit5 = all(c5.values())
    return {
        "arm": arm, "param": param, "horizon": horizon,
        "bl4_basis": bl4_basis,
        "baseline": base_stats, "candidate": cand_stats,
        "removed_vs_baseline": removed_stats,
        "expectancy_delta": point_delta,
        "block5": sig5, "block1_sensitivity": sig1,
        "cuts": cuts,
        "admission": {"baseline": base_m, "candidate": cand_m},
        "monotone_in_dispersion_rho": monotone_rho,
        "criteria": {
            "1_delta_ci_excludes_0": crit1,
            "2_not_worse_all_cuts": crit2,
            "3_winners_removed_le_losers_removed": crit3,
            "4_zero_admission_le_baseline": crit4,
            "5_admission_distribution_match": crit5,
            "5_detail": c5,
        },
        "stage1_all_criteria_pass": all(
            [crit1, crit2, crit3, crit4, crit5]),
    }


# ---------------------------------------------------------------- controls
def _noise_sigma(bars: list[Bar], horizon: str) -> float:
    pool = []
    for b in bars:
        ex = b.excess.get(horizon)
        if ex is not None:
            pool.append(ex[np.isfinite(ex)])
    pool = np.concatenate(pool) if pool else np.array([])
    if pool.size >= 30:
        return float(pool.std())
    return 0.06  # realistic 20d cross-sectional excess sigma fallback


def run_controls(bars: list[Bar], arms: dict[str, float | None],
                 horizon: str, bl4_basis: str, n_reps: int = 200,
                 gaps: tuple = (0.02, 0.04, 0.08), seed: int = SEED) -> dict:
    """Positive (S-REL planted effect) + true-null controls.

    Parameters were already solved on ADMISSION data only (no outcome
    leakage), so they are held fixed across control reps. Each rep swaps in
    synthetic outcomes and re-evaluates frozen criterion 1 end-to-end
    (per-date aggregation -> small-n exact tail masses / MC — the SAME
    dispatch the verdict path uses, so the measured false-fire rate
    calibrates the actual machinery, the V3 lesson).

    Two true-nulls:
      * iid-noise null: outcomes are pure N(0, sigma) noise, independent of
        admission;
      * within-date permutation null (when real resolved outcomes exist):
        the bar's REAL excess values are permuted across its names, breaking
        the admission->outcome link while preserving each date's marginal
        outcome distribution and cross-sectional scale.
    """
    sigma = _noise_sigma(bars, horizon)
    masks = {}
    for arm, param in arms.items():
        base_adm = {b.date: floor_clearing(b, "baseline", None)
                    & bl4_mask(b, "baseline", bl4_basis) for b in bars}
        cand_adm = {b.date: floor_clearing(b, arm, param)
                    & bl4_mask(b, arm, bl4_basis) for b in bars}
        masks[arm] = (base_adm, cand_adm)
    branch_seen: set[str] = set()

    def criterion1_from_excess(arm: str, excess_by_bar: dict) -> bool:
        base_adm, cand_adm = masks[arm]
        agg: dict[str, list[float]] = {}
        for b in bars:
            ex = excess_by_bar.get(b.date)
            if ex is None:
                continue
            ok = np.isfinite(ex)
            mb, mc = base_adm[b.date] & ok, cand_adm[b.date] & ok
            if not (mb.any() or mc.any()):
                continue
            a = agg.setdefault(b.date, [0.0, 0.0, 0.0, 0.0])
            a[0] += float(ex[mb].sum()); a[1] += float(mb.sum())
            a[2] += float(ex[mc].sum()); a[3] += float(mc.sum())
        dates = sorted(agg)
        if not dates:
            return False
        A = np.asarray([agg[d] for d in dates], dtype=float)
        pd_ = _delta(*A.sum(axis=0))
        sig = delta_significance(dates, A, BLOCK_PRIMARY)
        branch_seen.add(sig.get("branch", "?")
                        + ("+degenerate" if sig.get("degenerate") else ""))
        return criterion1_pass(sig, pd_)

    def iid_rep(rng, arm, gap: float | None) -> bool:
        base_adm, cand_adm = masks[arm]
        exs = {}
        for b in bars:
            ex = rng.normal(0.0, sigma, size=len(b.tickers))
            if gap is not None:
                only_cand = cand_adm[b.date] & ~base_adm[b.date]
                only_base = base_adm[b.date] & ~cand_adm[b.date]
                ex = ex + gap / 2.0 * only_cand - gap / 2.0 * only_base
            exs[b.date] = ex
        return criterion1_from_excess(arm, exs)

    def perm_rep(rng, arm) -> bool | None:
        exs, any_real = {}, False
        for b in bars:
            real = b.excess.get(horizon)
            if real is None or not np.isfinite(real).any():
                continue
            any_real = True
            ex = np.array(real, dtype=float)
            idx = np.flatnonzero(np.isfinite(ex))
            ex[idx] = ex[idx][rng.permutation(len(idx))]
            exs[b.date] = ex
        if not any_real:
            return None
        return criterion1_from_excess(arm, exs)

    out: dict = {"noise_sigma": sigma, "n_reps": n_reps, "arms": {},
                 "nominal": 0.025}
    for arm in arms:
        rng = np.random.default_rng(seed)
        null_fires = sum(iid_rep(rng, arm, None) for _ in range(n_reps))
        rng = np.random.default_rng(seed + 500)
        perm_results = [perm_rep(rng, arm) for _ in range(n_reps)]
        perm_valid = [r for r in perm_results if r is not None]
        power = {}
        for gi, gap in enumerate(gaps):
            rng = np.random.default_rng(seed + 1000 + gi)
            det = sum(iid_rep(rng, arm, gap) for _ in range(n_reps))
            power[f"gap_{gap:g}"] = det / n_reps
        out["arms"][arm] = {
            "true_null_false_fire_rate_iid": null_fires / n_reps,
            "true_null_false_fire_rate_perm": (
                sum(perm_valid) / len(perm_valid) if perm_valid else None),
            "positive_control_power": power,
        }
    out["sig_branch_used"] = sorted(branch_seen)
    return out


# ---------------------------------------------------------------- run gate
def gate_status(bars: list[Bar], horizon: str) -> dict:
    paired = [b for b in bars if b.is_current_pairing]
    resolved = [
        b for b in paired
        if b.excess.get(horizon) is not None
        and np.isfinite(b.excess[horizon]).any()]
    met = len(resolved) >= MIN_STAGE1_SESSIONS
    return {
        "required_sessions": MIN_STAGE1_SESSIONS,
        "primary_horizon": horizon,
        "current_pairing_sessions": len(paired),
        "current_pairing_sessions_with_resolved_outcomes": len(resolved),
        "gate_met": met,
        "verdict_eligibility": (
            "STAGE-1 ELIGIBLE" if met else "PRE-GATE EXPLORATORY"),
        "note": (
            "Stage 1 nomination may only be recorded from a gate-met run; a "
            "Stage 1 winner authorizes SHADOW deployment only (design §3/§6) "
            "— never a live enable. Stage 2 prospective confirmation gates "
            "the strategy-104 config PR."),
    }


# --------------------------------------------------------- baseline report
def baseline_report(con: sqlite3.Connection, cal: Calibrator,
                    n_runs: int, min_candidates: int) -> dict:
    """P1 A/B reader: per-run intercept / laundering / admission stats.

    Reads the last N full runs and reports, per run: the STORED production
    numbers (mu center, sign_laundered as prod counted it, floor-clearing
    count) plus the CURRENT calibrator artifact's replay of the same raws
    (fidelity <= PAIRING_FIDELITY_TOL marks a current-pairing run). Re-run
    after each session to compare run-to-run — this is the reader for the
    #280 registered prediction (sign_laundered collapses to single digits
    under the restored pairing).
    """
    runs = canonical_runs(con, min_candidates)[-n_runs:]
    bars = load_bars(con, runs)
    deviations: list[str] = []
    replay_bars(bars, cal, deviations)
    rows = []
    for b in bars:
        stored_ok = np.isfinite(b.mu_stored)
        mu_safe = np.where(stored_ok, b.mu_stored, 0.0)
        # BL-2 counter semantics (V5-verified 100% one-directional):
        # laundered = raw<0 AND mu>0; the reverse direction is reported
        # separately and should stay 0.
        laundered_stored = int(np.sum((b.raw < 0.0) & (mu_safe > 0.0)))
        laundered_reverse = int(np.sum((b.raw > 0.0) & (mu_safe < 0.0)))
        replayed = cal.mu_at_horizon(b.raw, b.mu_horizon_days)
        rows.append({
            "date": b.date, "run_id": b.run_id, "n_candidates": len(b.tickers),
            "regime": b.regime, "era": b.era,
            "raw_center_median": float(np.median(b.raw)),
            "mu_stored_mean": float(np.nanmean(b.mu_stored))
            if stored_ok.any() else None,
            "mu_stored_median": float(np.nanmedian(b.mu_stored))
            if stored_ok.any() else None,
            "sign_laundered_stored": laundered_stored,
            "sign_laundered_reverse_stored": laundered_reverse,
            "sign_laundered_prod_counter": b.counters.get(
                "calibrator_sign_laundered"),
            "floor_clearing_stored_all": int(np.sum(
                np.where(stored_ok, b.mu_stored, -np.inf) >= FLOOR)),
            "floor_clearing_stored_eligible": int(np.sum(
                b.eligible & (np.where(stored_ok, b.mu_stored, -np.inf)
                              >= FLOOR))),
            "current_cal_fidelity_max_abs_diff": b.fidelity,
            "is_current_pairing": b.is_current_pairing,
            "current_cal_mu_mean": float(np.mean(replayed)),
            "current_cal_mu_median": float(np.median(replayed)),
            "current_cal_sign_laundered": int(
                np.sum((b.raw < 0.0) & (replayed > 0.0))),
            "current_cal_floor_clearing": int(np.sum(replayed >= FLOOR)),
        })
    return {
        "mode": "baseline-report",
        "calibrator": calibrator_stamp(cal),
        "registered_prediction_ref": (
            "orchestrator #280: under the restored scorer/calibrator pairing "
            "sign_laundered collapses from ~45 to single digits WITHOUT M4's "
            "flag; watch sign_laundered_stored on is_current_pairing runs"),
        "runs": rows,
        "deviations": deviations,
    }


def calibrator_stamp(cal: Calibrator) -> dict:
    native = cal.native_lookahead_days()
    return {
        "path": cal.path, "file_sha256": cal.sha256,
        "trained_date": cal.trained_date,
        "neutral_raw": cal.neutral_raw,
        "native_lookahead_days": native,
        "er_clip_bound": cal.er_clip_bound,
        "horizon_scaling_note": (
            "mu replayed at each run's stored mu_horizon_days; when it "
            "differs from the artifact's native lookahead the pipeline "
            "scales linearly and re-clips (job_panel_scoring R2 audit) — "
            "reproduced here"),
    }


# ------------------------------------------------------------------ replay
def baseline_premeasure(bars: list[Bar]) -> dict:
    """Re-measure the CURRENT pairing's baseline BEFORE replaying (P1-restore
    requirement): per-bar floor-clearing counts, laundering, mu center of the
    window the candidate arms will be matched against."""
    rows = []
    for b in bars:
        stored_ok = np.isfinite(b.mu_stored)
        mu_safe = np.where(stored_ok, b.mu_stored, 0.0)
        rows.append({
            "date": b.date,
            "is_current_pairing": b.is_current_pairing,
            "floor_clearing": int(floor_clearing(b, "baseline", None).sum()),
            "sign_laundered": int(np.sum((b.raw < 0.0) & (mu_safe > 0.0))),
            "raw_center_median": float(b.center),
            "mu_stored_median": (float(np.nanmedian(b.mu_stored))
                                 if stored_ok.any() else None),
        })
    counts = [r["floor_clearing"] for r in rows]
    return {
        "note": ("current-pairing baseline re-measured before replay "
                 "(post-P1-restore pairing: scorer restored to 06-21, "
                 "calibrator refit 2026-07-03)"),
        "per_bar": rows,
        "mean_floor_clearing_B": (float(np.mean(counts)) if counts else None),
        "mean_sign_laundered": (
            float(np.mean([r["sign_laundered"] for r in rows]))
            if rows else None),
    }


def run_replay(con: sqlite3.Connection, cal: Calibrator, bl4_basis: str,
               primary_horizon: str, min_candidates: int,
               window: str = "pairing", control_reps: int = 0) -> dict:
    deviations: list[str] = []
    runs = canonical_runs(con, min_candidates)
    all_bars = load_bars(con, runs)
    if not all_bars:
        raise SystemExit("no full canonical runs with raw_panel in the DB")
    replay_bars(all_bars, cal, deviations)
    coverage = attach_outcomes(con, all_bars)

    # Stage-1 window selection: the run gate is ALWAYS computed over the
    # current-pairing bars; the evaluation window defaults to those same bars
    # (design §3 + P1-restore context: B must be the CURRENT pairing's
    # baseline). --window all is a cross-era exploratory widening.
    gate = gate_status(all_bars, primary_horizon)
    if window == "pairing":
        bars = [b for b in all_bars if b.is_current_pairing]
    else:
        bars = list(all_bars)
        deviations.append(
            "--window all: replay window includes non-current-pairing bars "
            "(retired scorer/calibrator pairings) — cross-era EXPLORATORY "
            "read, never a Stage-1 verdict input (recorded deviation)")
    if not bars:
        return {
            "mode": "replay",
            "generated_at": _dt.datetime.now(
                _dt.timezone.utc).isoformat(timespec="seconds"),
            "design": ("doc/design/2026-07-03-m4b-relative-conviction-floor"
                       ".md §4"),
            "calibrator": calibrator_stamp(cal),
            "window": window,
            "run_gate": gate,
            "verdict_eligibility": gate["verdict_eligibility"],
            "note": ("no bars in the current-pairing window yet — the "
                     "P1-restore pairing has produced no full canonical run; "
                     "re-run after sessions accrue, or use --window all for "
                     "a cross-era exploratory read"),
            "deviations": deviations,
        }

    structural_empty = [b.date for b in bars if not b.eligible.any()]
    if structural_empty:
        deviations.append(
            f"{len(structural_empty)} bar(s) with zero floor-eligible names "
            f"(wholesale upstream veto) excluded from all arms identically: "
            f"{structural_empty}")
        bars = [b for b in bars if b.eligible.any()]

    premeasure = baseline_premeasure(bars)

    # matched breadth (design §4): B = baseline mean floor-clearing count
    B = mean_count(bars, "baseline", None)
    max_pos = float(np.mean([
        int((b.eligible & (b.mu_rec > 0)).sum()) for b in bars]))
    solves = {
        "quantile": solve_matched_param(
            bars, "quantile", B, lo=1e-6, hi=1.0, increasing=True),
        "dispersion": solve_matched_param(
            bars, "dispersion", B, lo=0.0, hi=50.0, increasing=False),
        "absolute": solve_matched_param(
            bars, "absolute", B,
            lo=-0.05, hi=float(cal.er_clip_bound), increasing=False),
    }
    for arm, s in solves.items():
        if not s["matched"]:
            cap_note = (
                f"; mu>0 side-condition caps mean positive-mu breadth at "
                f"{max_pos:.2f}" if arm in ("quantile", "dispersion")
                and B > max_pos else "")
            deviations.append(
                f"{arm}: matched breadth UNACHIEVABLE within +/-{BREADTH_TOL} "
                f"(target B={B:.2f}, nearest achievable "
                f"{s['achieved_mean']:.2f}{cap_note}) — arm evaluated at "
                "nearest achievable breadth, flagged per §4")

    evaluations = {}
    for arm, s in solves.items():
        evaluations[arm] = evaluate_candidate(
            bars, arm, s["param"], primary_horizon, bl4_basis, deviations)
        # sensitivity horizons: point deltas only
        sens = {}
        for h in HORIZONS:
            if h == primary_horizon:
                continue
            ev = evaluate_candidate(bars, arm, s["param"], h, bl4_basis)
            sens[h] = {
                "expectancy_delta": ev["expectancy_delta"],
                "n_candidate": ev["candidate"]["n"],
                "n_baseline": ev["baseline"]["n"],
                "block5": {k: ev["block5"].get(k) for k in
                           ("branch", "exact", "p_le_0", "ci95",
                            "ci95_interp", "n_dates")},
            }
        evaluations[arm]["sensitivity_horizons"] = sens

    controls = None
    if control_reps > 0:
        controls = run_controls(
            bars, {arm: s["param"] for arm, s in solves.items()},
            primary_horizon, bl4_basis, n_reps=control_reps)

    fwd60 = coverage.get("fwd_60d", {})
    fwd60_note = (
        "fwd_60d has resolved rows — consider --primary-horizon fwd_60d "
        "(the horizon mu actually targets)"
        if fwd60.get("resolved", 0) > 0 else
        "fwd_60d unresolved on this window (expected until ~Aug 2026); "
        "fwd_20d primary is the stated compromise (design §4/§7)")

    return {
        "mode": "replay",
        "generated_at": _dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds"),
        "design": "doc/design/2026-07-03-m4b-relative-conviction-floor.md §4",
        "calibrator": calibrator_stamp(cal),
        "window": window,
        "substrate": {
            "n_bars": len(bars),
            "dates": [b.date for b in bars],
            "n_structural_empty_excluded": len(structural_empty),
            "outcome_coverage": coverage,
            "fwd_60d_note": fwd60_note,
            "current_pairing_bars": [
                b.date for b in bars if b.is_current_pairing],
        },
        "run_gate": gate,
        "verdict_eligibility": gate["verdict_eligibility"],
        "baseline_premeasure": premeasure,
        "matched_breadth": {"target_B": B, "solves": solves,
                            "mean_positive_mu_breadth_cap": max_pos},
        "bl4_basis": bl4_basis,
        "primary_horizon": primary_horizon,
        "ngboost_sigma_band": {"status": "SKIPPED", "note": NGBOOST_SKIP_NOTE},
        "evaluations": evaluations,
        "controls": controls,
        "pre_registered": {
            "floor": FLOOR, "cost_proxy": COST_PROXY, "top_n": TOP_N,
            "block_primary": BLOCK_PRIMARY, "block_sensitivity": BLOCK_SENS,
            "breadth_tol": BREADTH_TOL, "small_n_dates": SMALL_N_DATES,
            "min_cut_dates": MIN_CUT_DATES,
            "min_stage1_sessions": MIN_STAGE1_SESSIONS,
            "criterion5_tolerances": {
                "topn_saturation_freq": TOL_SATURATION_FREQ,
                "p90_count": TOL_P90_COUNT, "p95_count": TOL_P95_COUNT,
                "qp_spill_freq": TOL_SPILL_FREQ,
                "zero_streak_extra": TOL_ZERO_STREAK_EXTRA,
            },
        },
        "deviations": deviations,
    }


# --------------------------------------------------------------- reporting
def print_replay_table(res: dict) -> None:
    print(f"M4-b floor replay — {res['verdict_eligibility']} "
          f"(window={res.get('window')})")
    g = res["run_gate"]
    print(f"run gate: {g['current_pairing_sessions_with_resolved_outcomes']}"
          f"/{g['required_sessions']} current-pairing sessions with resolved "
          f"{g['primary_horizon']} outcomes  "
          f"(pairing sessions in DB: {g['current_pairing_sessions']})")
    c = res["calibrator"]
    print(f"calibrator: trained {c['trained_date']}  neutral_raw="
          f"{c['neutral_raw']:+.4f}  native={c['native_lookahead_days']}d  "
          f"sha={c['file_sha256'][:12]}")
    if "evaluations" not in res:
        print(f"\n{res.get('note', 'no evaluable window')}")
        return
    mb = res["matched_breadth"]
    pm = res["baseline_premeasure"]
    print(f"substrate: {res['substrate']['n_bars']} bars "
          f"{res['substrate']['dates'][0]}..{res['substrate']['dates'][-1]}  "
          f"target B={mb['target_B']:.2f}")
    print(f"baseline premeasure: mean floor-clearing B="
          f"{pm['mean_floor_clearing_B']:.2f}  mean sign-laundered="
          f"{pm['mean_sign_laundered']:.1f}")
    hdr = (f"{'arm':<12}{'param':>10}{'meanN':>7}{'delta':>10}"
           f"{'sig':>18}{'C1':>4}{'C2':>4}{'C3':>4}{'C4':>4}{'C5':>4}"
           f"{'ALL':>5}")
    print(hdr)
    print("-" * len(hdr))
    for arm, ev in res["evaluations"].items():
        s = res["matched_breadth"]["solves"][arm]
        cr = ev["criteria"]
        sig = ev["block5"]
        if sig.get("exact"):
            sigtxt = f"p_le0={sig['p_le_0']:.4f}"
        elif sig.get("ci95"):
            sigtxt = f"ci[{sig['ci95'][0]:+.4f},{sig['ci95'][1]:+.4f}]"
        else:
            sigtxt = "n/a"
        d = ev["expectancy_delta"]
        print(f"{arm:<12}{s['param']:>10.5f}{s['achieved_mean']:>7.2f}"
              f"{(f'{d:+.5f}' if d is not None else 'n/a'):>10}"
              f"{sigtxt:>18}"
              f"{str(cr['1_delta_ci_excludes_0'])[0]:>4}"
              f"{str(cr['2_not_worse_all_cuts'])[0]:>4}"
              f"{str(cr['3_winners_removed_le_losers_removed'])[0]:>4}"
              f"{str(cr['4_zero_admission_le_baseline'])[0]:>4}"
              f"{str(cr['5_admission_distribution_match'])[0]:>4}"
              f"{str(ev['stage1_all_criteria_pass'])[0]:>5}")
    print(f"\nNGBoost sigma-band: SKIPPED (see evidence JSON for the "
          f"deferral note)")
    if res.get("controls"):
        print("\ncontrols:")
        _print_controls(res["controls"])
    if res["deviations"]:
        print("\ndeviations (criterion 6 ledger):")
        for d in res["deviations"]:
            print(f"  - {d}")


def _print_controls(ctl_all: dict) -> None:
    for arm, ctl in ctl_all["arms"].items():
        pw = ", ".join(f"{k}={v:.2f}"
                       for k, v in ctl["positive_control_power"].items())
        perm = ctl["true_null_false_fire_rate_perm"]
        print(f"  {arm:<12} null false-fire iid="
              f"{ctl['true_null_false_fire_rate_iid']:.4f} perm="
              f"{(f'{perm:.4f}' if perm is not None else 'n/a')} "
              f"(nominal {ctl_all['nominal']})  power: {pw}")
    print(f"  significance branch(es) exercised: "
          f"{', '.join(ctl_all.get('sig_branch_used', []))}")


def print_baseline_report(rep: dict) -> None:
    c = rep["calibrator"]
    print("M4-b baseline report — P1 A/B reader (registered prediction: "
          "#280)")
    print(f"calibrator: trained {c['trained_date']}  neutral_raw="
          f"{c['neutral_raw']:+.4f}  native={c['native_lookahead_days']}d  "
          f"sha={c['file_sha256'][:12]}")
    hdr = (f"{'date':<11}{'n':>4}{'rawC':>8}{'muC':>8}{'laund':>7}"
           f"{'ctr':>5}{'floor':>7}{'fid':>10}{'pair':>6}{'cal_lnd':>8}"
           f"{'cal_flr':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rep["runs"]:
        fid = r["current_cal_fidelity_max_abs_diff"]
        print(f"{r['date']:<11}{r['n_candidates']:>4}"
              f"{r['raw_center_median']:>8.3f}"
              f"{(r['mu_stored_median'] if r['mu_stored_median'] is not None else float('nan')):>8.4f}"
              f"{r['sign_laundered_stored']:>7}"
              f"{str(r['sign_laundered_prod_counter'] if r['sign_laundered_prod_counter'] is not None else '-'):>5}"
              f"{r['floor_clearing_stored_eligible']:>7}"
              f"{(f'{fid:.1e}' if fid is not None else 'n/a'):>10}"
              f"{('YES' if r['is_current_pairing'] else 'no'):>6}"
              f"{r['current_cal_sign_laundered']:>8}"
              f"{r['current_cal_floor_clearing']:>8}")
    print("\ncolumns: rawC=median raw; muC=median stored mu; laund=stored "
          "sign-laundered (raw<0 & mu>0, BL-2 semantics); ctr=prod BL-2 "
          "counter; floor=stored floor-clearing (eligible, mu>=0.03); "
          "fid=max|replay-stored| vs CURRENT calibrator; pair=YES marks "
          "current-pairing runs; cal_lnd/cal_flr=current calibrator "
          "projected onto stored raws (diagnostic only on non-pairing runs "
          "— raws are the old scorer's).")


# --------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--replay", action="store_true",
                      help="full frozen-protocol replay (default)")
    mode.add_argument("--baseline-report", action="store_true",
                      help="P1 A/B reader: per-run pairing baseline stats")
    mode.add_argument("--controls", action="store_true",
                      help="positive + true-null controls only")
    mode.add_argument("--gate-check", action="store_true",
                      help="report the Stage-1 run-gate status and exit")
    ap.add_argument("--db", default=DEFAULT_DB, help="runs DB (READ-ONLY)")
    ap.add_argument("--calibrator", default=DEFAULT_CALIBRATOR,
                    help="live global panel calibration JSON")
    ap.add_argument("--runs", type=int, default=10,
                    help="baseline-report: number of most-recent full runs")
    ap.add_argument("--min-candidates", type=int,
                    default=MIN_FULL_RUN_CANDIDATES)
    ap.add_argument("--primary-horizon", default=PRIMARY_HORIZON,
                    choices=HORIZONS,
                    help="fwd_20d until fwd_60d resolves (~Aug 2026)")
    ap.add_argument("--window", default="pairing",
                    choices=("pairing", "all"),
                    help="replay window: current-pairing bars only "
                         "(default, Stage-1) or all canonical bars "
                         "(cross-era exploratory; recorded deviation)")
    ap.add_argument("--bl4-basis", default="prod-raw",
                    choices=("prod-raw", "arm", "off"),
                    help="BL-4 signal-direction basis (default prod-raw: "
                         "identical raw>0 mask across arms, design §4)")
    ap.add_argument("--control-reps", type=int, default=0,
                    help="replay mode: also run controls with N reps; "
                         "controls mode default 200")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    cal = Calibrator.load(args.calibrator)
    con = open_ro(args.db)
    try:
        if args.baseline_report:
            out = baseline_report(con, cal, args.runs, args.min_candidates)
            print_baseline_report(out)
        elif args.gate_check:
            deviations: list[str] = []
            bars = load_bars(con, canonical_runs(con, args.min_candidates))
            replay_bars(bars, cal, deviations)
            attach_outcomes(con, bars)
            out = {"mode": "gate-check",
                   "calibrator": calibrator_stamp(cal),
                   "run_gate": gate_status(bars, args.primary_horizon)}
            g = out["run_gate"]
            print(f"run gate: {g['verdict_eligibility']} — "
                  f"{g['current_pairing_sessions_with_resolved_outcomes']}"
                  f"/{g['required_sessions']} current-pairing sessions with "
                  f"resolved {args.primary_horizon}; pairing sessions in "
                  f"DB: {g['current_pairing_sessions']}")
        elif args.controls:
            reps = args.control_reps or 200
            out = run_replay(con, cal, args.bl4_basis, args.primary_horizon,
                             args.min_candidates, window=args.window,
                             control_reps=reps)
            if "controls" not in out:
                print(out.get("note", "no evaluable window for controls"))
                return 1
            out = {"mode": "controls", "controls": out["controls"],
                   "matched_breadth": out["matched_breadth"],
                   "run_gate": out["run_gate"],
                   "window": out["window"],
                   "calibrator": out["calibrator"],
                   "deviations": out["deviations"]}
            _print_controls(out["controls"])
        else:
            out = run_replay(con, cal, args.bl4_basis, args.primary_horizon,
                             args.min_candidates, window=args.window,
                             control_reps=args.control_reps)
            print_replay_table(out)
    finally:
        con.close()

    if args.json_out:
        p = Path(args.json_out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2, sort_keys=True,
                                default=_json_default) + "\n",
                     encoding="utf-8")
        print(f"\nevidence JSON -> {p}")
    return 0


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


if __name__ == "__main__":
    raise SystemExit(main())
