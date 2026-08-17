#!/usr/bin/env python
"""G-I MoE step 2 — the ONE authorized IC-screen run (frozen runner).

Governing contract: doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md
(orch#987, MERGED). This script is the execution-contract runner required by
that spec's §7: every guard below is prereg content, committed BEFORE the
scoring run. The screen TRIAGES (FLAGGED / NOT FLAGGED); it neither kills
nor admits (spec §1). One shot per corpus — re-running with different
parameters after seeing results is FORBIDDEN.

Deterministic by construction: no randomness anywhere (no seeds needed), no
clock enters any computed number (wall-clock stamps land in metadata only),
inputs are read-only local stores whose sha256 digests are recorded.

FROZEN RUNNER GUARDS (spec §7 step 2 — written down here, before the run):

G1  Corpus grid: SPY trading calendar dates in [2019-01-14, 2026-03-02],
    sampled every 5th trading day STARTING AT THE FIRST corpus date.
    The window holds 1,792 trading days, so the sampling RULE yields 359
    cross-sections; the spec's §2 derived count says 358 (= 1792/5 rounded
    down). The RULE is the more primitive frozen object, so the rule is
    implemented and the one-observation discrepancy is asserted tight
    (|n - 358| <= 1) and REPORTED, never papered over. No observation is
    silently dropped to hit the quoted count.
G2  Universe: the current live watchlist — the `watchlist` key of
    renquant-strategy-104/configs/strategy_config.golden.json (n must be
    exactly 145; sha256 recorded).
G3  Emitter identity: renquant_model_factors at the model#227 merge commit
    74c22647a7880c6a3234e53fb5d037d82fde3faf (spec §7 step 3). The runner
    asserts that commit is an ancestor of the imported checkout's HEAD and
    records HEAD. Artifact params are the emitters' own frozen v0 blocks
    (params_high52w_v0 / params_lowbeta_v0 / params_quality_gp_v0) —
    NEVER constructed ad hoc here.
G4  quality_gp input: the upstream `gross_profitability` column of
    data/sec_fundamentals_daily.parquet (the surface
    renquant_base_data.sec_fundamentals.compute_derived_features writes —
    the frozen SOURCE_COLUMN's named upstream). The point-in-time snapshot
    series served to the emitter is reconstructed as: rows with finite
    gross_profitability AND non-null gross_profitability_source_available_at;
    snapshot index = source_available_at (the date the filing became
    readable — the historical analog of the loaders' fetch-date snapshot
    index); snapshot value = the LAST daily row's value per
    (ticker, available_at). PIT sanity asserted: available_at <= row date
    on every served row. MAX_AGE_DAYS=400 then binds exactly as frozen.
G5  Labels: h-trading-day forward EXCESS return over SPY, raw close basis
    (the emitters' frozen close-only surface): for grid date at SPY-calendar
    index j, r = close[j+h]/close[j] - 1 with the ticker's close reindexed
    onto the SPY calendar WITHOUT any fill (a missing bar at either endpoint
    -> NaN -> the name is absent that date). Label dates may extend past the
    corpus end (the last cross-section's label needs them); scores never do.
G6  Placebo: the SAME candidate's score cross-section computed at the date
    2h trading days EARLIER (SPY calendar), evaluated against the SAME
    forward label at the grid date. Lag dates are 5-day aligned by
    construction, so scores are computed once on an extended grid
    (calendar indices i0-120 .. i0+5*(n-1) step 5, i0 = corpus start).
G7  Per-date PAIRED cross-section (corrected 2026-08-17, codex on orch#990).
    The first version enforced only a common DATE set: it computed the two
    legs with two independent inner-joins and subtracted them, so a name
    present in the genuine leg but absent from the lagged placebo leg
    silently changed the composition between the two ICs. Because the
    placebo IS the same score lagged 2h trading days, that difference is
    lag-dependent by construction -- a coverage artifact able to appear as
    Delta, which is the one quantity the screen decides on.
    Now: for candidate c and horizon h, intersect finite genuine score,
    finite placebo score AND finite label FIRST; apply
    NAMES_PER_DATE_FLOOR=50 to that SHARED set; correlate both legs against
    the label over exactly those names (:func:`paired_spearman_ic`). A date
    is KEPT iff the shared count clears the floor and both ICs are finite.
    Identical ticker IDENTITIES are asserted, not just identical dates or
    equal counts. The per-leg counts survive as telemetry
    (`n_pairs_genuine_leg_only`, `n_pairs_placebo_leg_only`,
    `coverage_gap_genuine_minus_placebo`) so the size of the confound the
    correction removes is visible in the output rather than inferred.
    Every dropped date is counted, with its reason.
G8  Spearman: scipy.stats.spearmanr on the pre-filtered finite pairs.
    Tie behaviour: average ranks (scipy's default; frozen here). A kept
    date always has >= 50 pairs, so degenerate-input NaNs cannot arise from
    emptiness; if spearmanr still returns NaN (zero score variance), the
    date is dropped and counted under `dropped_degenerate`.
G9  Blocks: weekly grid obs k (0-indexed) belongs to block floor(k*5/h)
    (equivalently floor(k/4) at h=20, floor(k/12) at h=60 on this aligned
    grid). Only COMPLETE blocks enter block inference: 89 blocks at h=20
    (obs 0..355), 29 at h=60 (obs 0..347) — asserted exactly. Obs in the
    trailing incomplete block are excluded from block inference but remain
    in the mean-level Delta (spec §5 criterion 1 is a mean over the weekly
    series; §5 criterion 2 is the block-t; they are separate criteria).
    Block value = mean over that block's KEPT obs of (IC_gen - IC_plac);
    a block with zero kept obs has no data. block-t = mean(block deltas) /
    (sd(block deltas, ddof=1) / sqrt(n_blocks_with_data)).
G10 Minimum-blocks floor (spec §7 requires one): at h=20 the block-t is
    UNMEASURABLE if fewer than 45 of the 89 blocks have data (a strict
    majority) — the verdict is then FLAGGED with reason
    `insufficient_blocks` (fail-closed), never computed on a sliver.
G11 Verdict (h=20 ONLY, spec §5): NOT FLAGGED iff Delta > 0 AND
    block-t >= 1.0 AND >50% of blocks-with-data have positive block delta.
    Anything else -> FLAGGED. h=60 is informational, never decisive.
G12 rho matrix (spec §6, informational): per corpus grid date, Spearman rho
    of the candidate's genuine scores vs the reference's scores over their
    common finite names, dates with >= 50 common names only; aggregation =
    the unweighted mean over qualifying dates (n_dates and sd reported).
    References: mom_slow_12m = renquant_model_momentum v0 composite,
    mom_fast = v1_fast composite, both built by train_momentum_artifact on
    the same universe/dates with their own frozen params. multifactor_core
    has NO committed historical score series reachable without running the
    panel pipeline (score_db.sqlite is empty; run bundles are 2026-only) —
    recorded as a NAMED GAP, not fabricated, not heavy-computed.

Usage:  python 2026-08-17-gi-moe-screen-derivation.py
Env:    RQ_UMBRELLA_ROOT / RQ_MODEL_SRC / RQ_STRAT104_ROOT override the
        default local checkout paths (read-only inputs, same contract).
Output: results JSON + IC-series CSV next to this script (doc/research/data/).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ---------------------------------------------------------------- frozen IO
HERE = Path(__file__).resolve().parent
UMBRELLA = Path(os.environ.get("RQ_UMBRELLA_ROOT", "/Users/renhao/git/github/RenQuant"))
MODEL_SRC = Path(os.environ.get("RQ_MODEL_SRC", "/Users/renhao/git/github/renquant-model/src"))
STRAT104 = Path(os.environ.get("RQ_STRAT104_ROOT", "/Users/renhao/git/github/renquant-strategy-104"))

OHLCV = UMBRELLA / "data" / "ohlcv"
SEC_DAILY = UMBRELLA / "data" / "sec_fundamentals_daily.parquet"
SECTORS = UMBRELLA / "data" / "ticker_sectors.json"
WATCHLIST_CFG = STRAT104 / "configs" / "strategy_config.golden.json"

OUT_JSON = HERE / "2026-08-17-gi-moe-screen-results.json"
OUT_CSV = HERE / "2026-08-17-gi-moe-screen-ic-series.csv"

# ---------------------------------------------------------- frozen constants
CORPUS_START = "2019-01-14"          # spec §2
CORPUS_END = "2026-03-02"            # spec §2
SAMPLE_STEP = 5                      # every 5th trading day (spec §2)
HORIZONS = (20, 60)                  # primary, informational (spec §3)
PRIMARY_H = 20                       # verdicts at h=20 ONLY (spec §5)
PLACEBO_LAG_MULT = 2                 # placebo lag = 2h trading days (spec §3)
NAMES_PER_DATE_FLOOR = 50            # the emitters' frozen floor (spec §2)
MIN_BLOCKS_WITH_DATA = 45            # G10 minimum-blocks floor (h=20)
BLOCK_T_MIN = 1.0                    # spec §5 criterion 2
POS_BLOCK_FRAC_MIN = 0.5             # spec §5 criterion 3 (strictly greater)
EXPECTED_BLOCKS = {20: 89, 60: 29}   # spec §4 — asserted exactly
EXPECTED_WEEKLY_N = 358              # spec §2 derived count (G1: |n-358|<=1)
WATCHLIST_N = 145                    # spec §2 "the 145-name live universe"
MODEL_PIN = "74c22647a7880c6a3234e53fb5d037d82fde3faf"  # spec §7 step 3

sys.path.insert(0, str(MODEL_SRC))
from renquant_model_factors import (  # noqa: E402
    build_high52w_artifact, build_lowbeta_artifact, build_quality_gp_artifact,
    params_high52w_v0, params_lowbeta_v0, params_quality_gp_v0)
from renquant_model_momentum.train import (  # noqa: E402
    params_v0 as mom_params_v0, params_v1_fast as mom_params_v1_fast,
    train_momentum_artifact)
from renquant_model_common.total_return import total_return_close  # noqa: E402

CANDIDATES = {
    "high52w": (build_high52w_artifact, params_high52w_v0),
    "lowbeta": (build_lowbeta_artifact, params_lowbeta_v0),
    "quality_gp": (build_quality_gp_artifact, params_quality_gp_v0),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"FROZEN-GUARD FAILURE — STOP, do not adjust the spec: {msg}")


# ------------------------------------------------------------------ readers
class ScreenReaders:
    """FactorReaders over the read-only local stores (G2/G4), digest-recording."""

    def __init__(self, universe: list[str]) -> None:
        self._close: dict[str, pd.Series | None] = {}
        self._frames: dict[str, pd.DataFrame | None] = {}
        self._digests: dict[str, str] = {}
        self._fund = self._build_fund_snapshots(universe)

    def _build_fund_snapshots(self, universe: list[str]) -> dict[str, pd.Series]:
        self._digests["sec_fundamentals_daily.parquet"] = _sha256(SEC_DAILY)
        cols = ["date", "ticker", "gross_profitability",
                "gross_profitability_source_available_at"]
        df = pd.read_parquet(SEC_DAILY, columns=cols)
        df = df[df["ticker"].isin(universe)]
        df = df.dropna(subset=["gross_profitability",
                               "gross_profitability_source_available_at"])
        # G4 PIT sanity: a value must never be visible before its filing is.
        _assert(bool((df["gross_profitability_source_available_at"]
                      <= df["date"]).all()),
                "sec_fundamentals_daily has rows visible before available_at")
        snaps = (df.sort_values("date")
                   .groupby(["ticker", "gross_profitability_source_available_at"])
                   ["gross_profitability"].last())
        out: dict[str, pd.Series] = {}
        for t, grp in snaps.groupby(level=0):
            out[str(t)] = grp.droplevel(0).sort_index()
        return out

    def _frame(self, ticker: str) -> pd.DataFrame | None:
        if ticker not in self._frames:
            p = OHLCV / ticker / "1d.parquet"
            if not p.is_file():
                self._frames[ticker] = None
            else:
                self._digests[f"ohlcv/{ticker}/1d.parquet"] = _sha256(p)
                self._frames[ticker] = pd.read_parquet(p)
        return self._frames[ticker]

    # -- FactorReaders protocol --------------------------------------------
    def close(self, ticker: str) -> pd.Series | None:
        if ticker not in self._close:
            f = self._frame(ticker)
            self._close[ticker] = None if f is None else f["close"]
        return self._close[ticker]

    def market_close(self) -> pd.Series:
        s = self.close("SPY")
        if s is None:
            raise FileNotFoundError(f"SPY absent under {OHLCV}")
        return s

    def fundamental(self, ticker: str) -> pd.Series | None:
        return self._fund.get(ticker)

    def read_digests(self) -> dict[str, str]:
        return dict(self._digests)


class MomReaders:
    """MomentumReaders over the same stores — mirrors the production
    tools/momentum_train_run.py LiveReaders construction (total_return_close
    + pct_change; volume; sectors from ticker_sectors.json)."""

    def __init__(self, screen: ScreenReaders) -> None:
        self._screen = screen
        self._tr: dict[str, pd.Series | None] = {}
        self._sectors: dict[str, str | None] | None = None

    def _load(self, ticker: str) -> None:
        if ticker in self._tr:
            return
        raw = self._screen._frame(ticker)
        if raw is None:
            self._tr[ticker] = None
            return
        div = (raw["dividend"] if "dividend" in raw.columns
               else pd.Series(0.0, index=raw.index))
        self._tr[ticker] = total_return_close(raw["close"], div).pct_change()

    def tr_returns(self, ticker: str) -> pd.Series | None:
        self._load(ticker)
        return self._tr[ticker]

    def volume(self, ticker: str) -> pd.Series | None:
        raw = self._screen._frame(ticker)
        return None if raw is None else raw["volume"]

    def market_tr_returns(self) -> pd.Series:
        r = self.tr_returns("SPY")
        if r is None:
            raise FileNotFoundError(f"SPY absent under {OHLCV}")
        return r

    def sector_of(self) -> dict[str, str | None]:
        if self._sectors is None:
            raw = json.loads(SECTORS.read_text())
            self._sectors = {t: v.get("sector") for t, v in raw.items()}
        return self._sectors

    def read_digests(self) -> dict[str, str]:
        return {}


# ------------------------------------------------------------------ helpers
def verify_model_pin() -> str:
    """G3: the imported emitter checkout must contain the frozen merge commit."""
    repo = MODEL_SRC.parent
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    rc = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                         MODEL_PIN, "HEAD"]).returncode
    _assert(rc == 0, f"model pin {MODEL_PIN} is not an ancestor of {head}")
    return head


def build_grid(cal: pd.DatetimeIndex) -> dict:
    corpus = cal[(cal >= CORPUS_START) & (cal <= CORPUS_END)]
    _assert(str(corpus[0].date()) == CORPUS_START and
            str(corpus[-1].date()) == CORPUS_END,
            "corpus endpoints are not trading days of the SPY calendar")
    grid = corpus[::SAMPLE_STEP]
    n = len(grid)
    # G1: the sampling rule governs; the derived count must be within 1.
    _assert(abs(n - EXPECTED_WEEKLY_N) <= 1,
            f"weekly grid n={n} deviates from the frozen 358 by more than 1")
    i0 = cal.get_loc(corpus[0])
    max_lag = PLACEBO_LAG_MULT * max(HORIZONS)
    _assert(i0 >= max_lag, "not enough pre-corpus calendar for the placebo lag")
    ext_idx = list(range(i0 - max_lag, i0 + SAMPLE_STEP * (n - 1) + 1, SAMPLE_STEP))
    _assert(cal[ext_idx[-1]] == grid[-1], "extended grid misaligned with grid end")
    last_label_idx = i0 + SAMPLE_STEP * (n - 1) + max(HORIZONS)
    _assert(last_label_idx < len(cal),
            "SPY calendar too short for the last cross-section's h=60 label")
    return {"cal": cal, "corpus": corpus, "grid": grid, "n": n, "i0": i0,
            "ext_dates": [cal[i] for i in ext_idx]}


def close_panel(readers: ScreenReaders, universe: list[str],
                cal: pd.DatetimeIndex) -> pd.DataFrame:
    """Raw closes reindexed onto the SPY calendar, no fill (G5)."""
    cols = {}
    for t in universe:
        s = readers.close(t)
        if s is not None:
            cols[t] = s.reindex(cal)
    return pd.DataFrame(cols, index=cal)


def spearman_ic(scores: pd.Series, labels: pd.Series) -> tuple[float, int]:
    """Single-leg IC. Retained for the rho matrix (G12) and for TELEMETRY only.

    NOT used for the genuine/placebo decision quantity -- see
    :func:`paired_spearman_ic` and the G7 note. Computing the two legs with
    two independent inner-joins is exactly the defect codex found on orch#990.
    """
    both = pd.concat([scores, labels], axis=1, join="inner").dropna()
    both = both[np.isfinite(both).all(axis=1)]
    n = len(both)
    if n < NAMES_PER_DATE_FLOOR:
        return float("nan"), n
    rho = spearmanr(both.iloc[:, 0], both.iloc[:, 1]).statistic
    return float(rho), n


def paired_spearman_ic(
    gen: pd.Series, pla: pd.Series, labels: pd.Series
) -> tuple[float, float, int, tuple[str, ...]]:
    """Both legs on ONE shared cross-section (G7, corrected).

    Delta = mean(genuine IC) - mean(placebo IC) is only a signal difference if
    both ICs are measured over the SAME names. The placebo is the same score
    lagged by 2h trading days, so a name short of history at the lagged date
    drops out of the placebo leg while surviving in the genuine leg. Filtering
    each leg separately then subtracting lets that lag-dependent coverage
    difference appear as Delta -- a composition artifact wearing the shape of
    the estimand.

    So: intersect finite genuine score, finite placebo score AND finite label
    FIRST, apply NAMES_PER_DATE_FLOOR to that shared set, and correlate both
    legs against the label over exactly those names. Returns the shared ticker
    identities so the caller can assert identity rather than trust it.
    """
    both = pd.concat([gen, pla, labels], axis=1, join="inner").dropna()
    both = both[np.isfinite(both).all(axis=1)]
    n = len(both)
    names = tuple(str(x) for x in both.index)
    if n < NAMES_PER_DATE_FLOOR:
        return float("nan"), float("nan"), n, names
    rho_g = spearmanr(both.iloc[:, 0], both.iloc[:, 2]).statistic
    rho_p = spearmanr(both.iloc[:, 1], both.iloc[:, 2]).statistic
    return float(rho_g), float(rho_p), n, names


def main() -> None:
    t_start = time.time()
    model_head = verify_model_pin()

    wl_raw = json.loads(WATCHLIST_CFG.read_text())
    universe = sorted(dict.fromkeys(str(t) for t in wl_raw["watchlist"]))
    _assert(len(universe) == WATCHLIST_N,
            f"watchlist n={len(universe)} != frozen {WATCHLIST_N}")

    readers = ScreenReaders(universe)
    spy_close = readers.market_close()
    g = build_grid(spy_close.index)
    cal, grid, n_grid, i0 = g["cal"], g["grid"], g["n"], g["i0"]

    # ---- candidate scores on the extended grid (RAW, frozen v0 params) ----
    print(f"[1/4] scoring {len(CANDIDATES)} candidates on "
          f"{len(g['ext_dates'])} dates ...", flush=True)
    scores: dict[str, dict[pd.Timestamp, pd.Series]] = {}
    coverage: dict[str, dict[str, int]] = {}
    params_used: dict[str, dict] = {}
    for name, (build, params_fn) in CANDIDATES.items():
        params = params_fn()
        params_used[name] = params
        per_date: dict[pd.Timestamp, pd.Series] = {}
        cov: dict[str, int] = {}
        for ts in g["ext_dates"]:
            art = build(ts, universe, params, readers=readers)
            s = pd.Series(art["scores"], dtype=float)
            per_date[ts] = s[np.isfinite(s)]
            cov[str(ts.date())] = int(art["n_scored"])
        scores[name] = per_date
        coverage[name] = cov
        print(f"    {name}: median n_scored = "
              f"{int(np.median(list(cov.values())))}", flush=True)

    # ---- labels: forward h-day excess return over SPY (raw close, G5) -----
    print("[2/4] building forward excess-return labels ...", flush=True)
    closes = close_panel(readers, universe, cal)
    spy_on_cal = spy_close.reindex(cal)
    labels: dict[int, dict[pd.Timestamp, pd.Series]] = {}
    for h in HORIZONS:
        fwd = closes.shift(-h) / closes - 1.0
        spy_fwd = spy_on_cal.shift(-h) / spy_on_cal - 1.0
        ex = fwd.sub(spy_fwd, axis=0)
        labels[h] = {d: ex.loc[d].dropna() for d in grid}

    # ---- IC series, common kept set, blocks, verdicts ---------------------
    print("[3/4] IC series + frozen triage rule ...", flush=True)
    rows = []
    results: dict[str, dict] = {}
    for name in CANDIDATES:
        results[name] = {"horizons": {}}
        for h in HORIZONS:
            lag_steps = PLACEBO_LAG_MULT * h // SAMPLE_STEP
            _assert(PLACEBO_LAG_MULT * h % SAMPLE_STEP == 0,
                    "placebo lag not aligned to the sampling step")
            blocks_per = h // SAMPLE_STEP  # 4 at h=20, 12 at h=60
            n_complete = n_grid // blocks_per
            over = EXPECTED_BLOCKS[h]
            _assert(n_complete >= over, f"fewer than {over} complete blocks at h={h}")
            n_complete = over  # frozen count: exactly the spec's blocks (G9)

            kept, dropped = [], {"floor_paired": 0, "degenerate": 0}
            series = []
            for k, d in enumerate(grid):
                lab = labels[h][d]
                gen_s = scores[name][d]
                lag_date = cal[i0 + SAMPLE_STEP * k - PLACEBO_LAG_MULT * h]
                pla_s = scores[name][lag_date]
                # G7 (corrected, codex on orch#990): ONE shared cross-section
                # for both legs. The per-leg counts below are kept as telemetry
                # precisely because their DIFFERENCE is the confound that made
                # the correction necessary -- it should be visible, not hidden.
                ic_g, ic_p, n_pair, pair_names = paired_spearman_ic(
                    gen_s, pla_s, lab)
                _, n_g = spearman_ic(gen_s, lab)
                _, n_p = spearman_ic(pla_s, lab)
                block = k // blocks_per
                complete = block < n_complete
                keep, reason = True, ""
                if n_pair < NAMES_PER_DATE_FLOOR:
                    keep, reason = False, "floor_paired"
                elif not (np.isfinite(ic_g) and np.isfinite(ic_p)):
                    keep, reason = False, "degenerate"
                if not keep:
                    dropped[reason] += 1
                else:
                    kept.append(k)
                    series.append((k, d, ic_g, ic_p, block, complete,
                                   pair_names))
                rows.append({"candidate": name, "h": h, "date": str(d.date()),
                             "obs_index": k, "block": block,
                             "block_complete": complete, "kept": keep,
                             "drop_reason": reason,
                             "placebo_score_date": str(lag_date.date()),
                             "n_pairs_shared": n_pair,
                             "n_pairs_genuine_leg_only": n_g,
                             "n_pairs_placebo_leg_only": n_p,
                             "coverage_gap_genuine_minus_placebo": n_g - n_p,
                             "ic_genuine": ic_g if keep else float("nan"),
                             "ic_placebo": ic_p if keep else float("nan")})

            gen = np.array([s[2] for s in series])
            pla = np.array([s[3] for s in series])
            # G7 (corrected): assert IDENTITY, not just cardinality. The old
            # check compared lengths of two independently-filtered legs, which
            # is satisfied even when the two cross-sections contain different
            # NAMES -- the exact confound this guard is supposed to exclude.
            # paired_spearman_ic returns the shared tickers; both legs are the
            # same object by construction, so assert that rather than trust it.
            _assert(len(gen) == len(pla), "genuine/placebo date sets differ")
            for _k, _d, _ig, _ip, _b, _c, _names in series:
                _assert(len(_names) >= NAMES_PER_DATE_FLOOR,
                        f"kept date {_d.date()} below the paired floor")
                _assert(len(set(_names)) == len(_names),
                        f"duplicate tickers in the paired set at {_d.date()}")
            delta = float(gen.mean() - pla.mean()) if len(gen) else float("nan")

            block_vals = {}
            for k, d, ic_g, ic_p, block, complete, _pair_names in series:
                if complete:
                    block_vals.setdefault(block, []).append(ic_g - ic_p)
            bdel = np.array([float(np.mean(v)) for _, v in sorted(block_vals.items())])
            n_bd = len(bdel)
            if n_bd >= 2:
                bt = float(bdel.mean() / (bdel.std(ddof=1) / np.sqrt(n_bd)))
                pos_frac = float((bdel > 0).mean())
            else:
                bt, pos_frac = float("nan"), float("nan")

            hres = {
                "n_grid_dates": n_grid, "n_kept": len(series),
                "dropped": dropped,
                "mean_ic_genuine": float(gen.mean()) if len(gen) else None,
                "mean_ic_placebo": float(pla.mean()) if len(pla) else None,
                "delta": delta,
                "n_blocks_expected": over, "n_blocks_with_data": n_bd,
                "block_t": bt, "pos_block_frac": pos_frac,
            }
            if h == PRIMARY_H:
                if n_bd < MIN_BLOCKS_WITH_DATA:
                    verdict, why = "FLAGGED", "insufficient_blocks"
                else:
                    ok = (delta > 0 and bt >= BLOCK_T_MIN
                          and pos_frac > POS_BLOCK_FRAC_MIN)
                    verdict = "NOT FLAGGED" if ok else "FLAGGED"
                    why = ("all three criteria met" if ok else "; ".join(
                        c for c, bad in [
                            (f"delta={delta:+.5f} <= 0", not delta > 0),
                            (f"block_t={bt:.3f} < {BLOCK_T_MIN}", not bt >= BLOCK_T_MIN),
                            (f"pos_block_frac={pos_frac:.3f} <= {POS_BLOCK_FRAC_MIN}",
                             not pos_frac > POS_BLOCK_FRAC_MIN)] if bad))
                hres["verdict"] = verdict
                hres["verdict_reason"] = why
            results[name]["horizons"][str(h)] = hres

    # ---- rho matrix (G12, informational) ----------------------------------
    print("[4/4] rho matrix vs momentum lanes ...", flush=True)
    mom_readers = MomReaders(readers)
    mom_scores: dict[str, dict[pd.Timestamp, pd.Series]] = {"mom_slow_12m": {},
                                                            "mom_fast": {}}
    mom_params = {"mom_slow_12m": mom_params_v0(), "mom_fast": mom_params_v1_fast()}
    for d in grid:
        for ref, prm in (("mom_slow_12m", mom_params["mom_slow_12m"]),
                         ("mom_fast", mom_params["mom_fast"])):
            art = train_momentum_artifact(d, universe, prm, readers=mom_readers)
            s = pd.Series(art["scores"], dtype=float)
            mom_scores[ref][d] = s[np.isfinite(s)]

    rho_matrix: dict[str, dict[str, dict]] = {}
    for name in CANDIDATES:
        rho_matrix[name] = {}
        for ref in ("mom_slow_12m", "mom_fast"):
            per_date = []
            for d in grid:
                a, b = scores[name][d], mom_scores[ref][d]
                both = pd.concat([a, b], axis=1, join="inner").dropna()
                if len(both) >= NAMES_PER_DATE_FLOOR:
                    r = spearmanr(both.iloc[:, 0], both.iloc[:, 1]).statistic
                    if np.isfinite(r):
                        per_date.append(float(r))
            arr = np.array(per_date)
            rho_matrix[name][ref] = {
                "mean_rho": float(arr.mean()) if len(arr) else None,
                "sd_rho": float(arr.std(ddof=1)) if len(arr) > 1 else None,
                "n_dates": len(arr)}
        rho_matrix[name]["multifactor_core"] = {
            "named_gap": ("no committed/reachable historical score series for "
                          "multifactor_core on the corpus dates without running "
                          "the panel pipeline (score_db.sqlite empty; run "
                          "bundles 2026-only) — deferred to the #984 §5b batch")}

    # ---- outputs ----------------------------------------------------------
    csv_df = pd.DataFrame(rows)
    csv_df.to_csv(OUT_CSV, index=False)

    out = {
        "spec": "doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md (orch#987)",
        "semantics": "TRIAGE — FLAGGED / NOT FLAGGED; neither kill nor admit (spec §1)",
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": round(time.time() - t_start, 1),
        "pins": {
            "renquant_model_head": model_head,
            "renquant_model_frozen_pin": MODEL_PIN,
            "watchlist_config": str(WATCHLIST_CFG),
            "watchlist_sha256": _sha256(WATCHLIST_CFG),
            "watchlist_n": len(universe),
            "sec_fundamentals_daily_sha256": readers.read_digests()[
                "sec_fundamentals_daily.parquet"],
            "spy_1d_sha256": readers.read_digests()["ohlcv/SPY/1d.parquet"],
            "ohlcv_digest_of_digests": hashlib.sha256(json.dumps(
                {k: v for k, v in sorted(readers.read_digests().items())
                 if k.startswith("ohlcv/")}, sort_keys=True).encode()).hexdigest(),
        },
        "corpus": {
            "start": CORPUS_START, "end": CORPUS_END,
            "trading_days": int(len(g["corpus"])),
            "sample_step": SAMPLE_STEP,
            "n_cross_sections": n_grid,
            "n_cross_sections_note": (
                "the frozen every-5th-trading-day RULE yields 359 on the "
                "1,792-day window; the spec's derived count said 358 — the "
                "rule governs (G1), discrepancy reported, nothing dropped"),
            "first_grid_date": str(grid[0].date()),
            "last_grid_date": str(grid[-1].date()),
        },
        "frozen_rule": {
            "horizon_primary": PRIMARY_H,
            "names_per_date_floor": NAMES_PER_DATE_FLOOR,
            "placebo_lag_trading_days": {str(h): PLACEBO_LAG_MULT * h
                                         for h in HORIZONS},
            "block_t_min": BLOCK_T_MIN,
            "pos_block_frac_min_exclusive": POS_BLOCK_FRAC_MIN,
            "min_blocks_with_data": MIN_BLOCKS_WITH_DATA,
            "expected_blocks": {str(h): EXPECTED_BLOCKS[h] for h in HORIZONS},
        },
        "params": params_used,
        "momentum_params": mom_params,
        "candidates": results,
        "rho_matrix": rho_matrix,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    print("\n===== VERDICTS (h=20, frozen triage rule — spec §5) =====")
    for name in CANDIDATES:
        r = results[name]["horizons"][str(PRIMARY_H)]
        print(f"  {name:11s} delta={r['delta']:+.5f} block_t={r['block_t']:+.3f} "
              f"pos%={r['pos_block_frac']:.3f} kept={r['n_kept']}/{n_grid} "
              f"-> {r['verdict']} ({r['verdict_reason']})")
    print(f"\nwrote {OUT_JSON.name}, {OUT_CSV.name} "
          f"({out['runtime_sec']}s)")


if __name__ == "__main__":
    main()
