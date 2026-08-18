#!/usr/bin/env python
"""Vol-state deployment window — the ONE confirmatory run (frozen runner).

Governing contract: doc/research/2026-08-18-vol-switch-confirmatory-prereg.md
(orch#1001, MERGED — frozen BEFORE any scoring). This script is the §6
execution-contract runner: committed AND REVIEWED before the run. THIS PR
ships the runner un-run; the single run happens only after the runner PR
merges (V2 enforces exactly that: the runner refuses to execute unless its
bytes match origin/main). ONE execution — re-running after seeing results is
FORBIDDEN (V1).

Hypothesis (prereg §1, one-sided): the panel's top-decile tail skill is
positive when trailing market volatility is elevated ("ON"). The confirmatory
runs on data the hypothesis NEVER saw: PRIMARY corpus 2017-01-03..2023-09-29,
strictly pre-exploration (the formation bundle is committed at
doc/research/data/2026-08-18-tail-switch-exploratory/).

Scoring (prereg §4): the production recipe VERBATIM — served artifact
`artifacts/prod/panel-ltr.alpha158_fund.json`, config fingerprint
sha256:f8fb2259b2bf1537, objective left AT PRODUCTION (rank:pairwise; ZERO
delta), 172 features + norms + params + fwd_60d_excess, best_iter=100.
Quarterly expanding refits, cutoffs 2016-Q2..2023-Q3 for the primary corpus
(extended ..2025-Q4 for the secondary) = 39 cutoffs on one ladder; the
60-trading-day embargo C + 60td <= d asserted per date. Machinery = the
tail_q90 runner's reviewed refit engine
(doc/research/data/2026-08-18-gi-tailq90-derivation.py, #996/#999 lineage):
the reused defs are copied VERBATIM and a committed test
(tests/test_vol_switch_runner.py) enforces byte-identity against that file,
so the reuse cannot silently drift into a rewrite.

State (prereg §2): ON at date d <=> SPY 20-trading-day realized vol
(close-to-close, sample std ddof=1, annualized sqrt(252)) > 13.5% — strict
inequality, so exactly 0.135 is OFF. Sensitivity variant (reported, never
decisive): expanding upper-tercile (66.7th pct of all vol20 history <= d),
504-observation warmup from the series start 2016-01-04 (threshold first
defined 2018-01-31; earlier days OFF, fail-closed).

Estimand (prereg §3): weekly (every 5th trading day) cross-sections over the
production panel dataset (292 tickers, survivor caveat DECLARED in the
prereg); h=60 labels = the panel's own fwd_60d_excess (per-date z-scored
fwd-60td excess vs SPY — SD units, matching the prereg's formation numbers);
per-date top-decile (by score, N = round(n/10)) DGTW-adjusted spread — the
capacity-memo instrument (renquant-model doc/research/evidence/
2026-07-24-capacity-memo/structural_decomposition.py): per-date vol x mom x
beta (STD60 x ROC60 x BETA60) terciles via qcut on rank(method="first"), 27
cells, self-excluded cell mean as benchmark, spread = top-decile mean minus
cross-section mean — plus the prereg's >=15/cell floor: a name whose cell has
fewer than 15 members keeps its label UNADJUSTED and is flagged (the flagged
fraction is reported per date and overall).

Block unit (prereg §3, canon §1.2 unit (ii)): consecutive NON-OVERLAPPING
60-trading-day blocks from the corpus start; primary = 28 complete blocks
(1,697 // 60, trailing 17-td remainder dropped from block inference);
ON-eligible = >=15 ON days, ON-dominant = >=45. A block's outcome = the mean
spread over its ON-state weekly cross-section dates.

Decision rule (prereg §5, verbatim — one shot, no re-runs, no threshold
search), applied to the PRIMARY corpus / FIXED definition only:
  positive control  unconditional primary spread > 0 — checked BEFORE any
                    conditional read; failure => INVALID_INSTRUMENT, the
                    conditional statistics are not computed.
  P1 (primary)      ON-state mean spread > 0 over the 19 fixed-definition
                    ON-eligible primary blocks, by the canon's
                    dependence-robust CONJUNCTION: (a) Newey-West (lag 1) SE
                    on the block series, small-sample t with df = N_on - 1,
                    one-sided 95% CI excludes 0; AND (b) stationary block
                    bootstrap (expected block length 2, 10,000 resamples,
                    fixed seed 0), one-sided 95% CI [q05, +inf) excludes 0.
                    BOTH must pass; if they disagree the result is reported
                    as DISAGREEMENT and P1 FAILS (conservative, pre-frozen).
                    The winsorized +-50% ON-spread >= 0 guard (anti-lottery)
                    is a further P1 conjunct: a raw pass with a negative
                    winsorized mean is a lottery pass and FAILS.
  P2 (secondary)    ON-state minus OFF-state block-mean difference > 0 with
                    block-t >= 1.0 (annotation grade, declared underpowered).
  guards            >=15 ON-eligible blocks AND realized ESS >= 6 on the ON
                    block series (ESS = N(1-rho1)/(1+rho1), rho1 = lag-1
                    autocorrelation clipped below at 0) else UNMEASURABLE
                    (fail-closed).
  verdicts          P1 AND P2 -> CONFIRMED; P1 only -> PARTIAL; P1 fails ->
                    REFUTED — each echoed with its §5 consequence string.

FROZEN RUNNER GUARDS (prereg §6 — written down here, before the run):

V1   One-shot marker: the runner REFUSES to run if any output file already
     exists. Outputs land ONLY next to this script (doc/research/data/).
V2   Byte-identity vs origin/main at execution: freeze-then-review-then-run,
     mechanically enforced (not merged -> fail closed).
V3   Served-artifact identity: config_fingerprint sha256:f8fb2259b2bf1537,
     kind panel_ltr_xgboost, label fwd_60d_excess, lookahead 60, 172
     feature_cols + 172 norm kinds, best_iter 100.
V4   Objective AT PRODUCTION: params are the artifact's dict VERBATIM with
     objective rank:pairwise and a pinned seed — asserted; ANY delta fails
     closed (this is the no-delta complement of tail_q90's single-delta).
V5   Refit calendar: exactly 39 cutoffs, each the last trading day (SPY
     calendar) of its quarter, 2016-Q2..2025-Q4, strictly increasing; primary
     corpus dates must resolve to the primary sub-ladder 2016-Q2..2023-Q3
     (asserted per date).
V6   Embargo per scoring date: the chosen refit is the NEWEST with
     C + 60td <= d, both conditions asserted per date; EVERY grid date must
     be scoreable (first scoreable date precedes the corpus start — no
     placebo leg exists in this design, so no exception class either).
V7   Training window per refit: expanding from 2016-01-04, realized labels
     only — max train-row date t satisfies t + 60td <= C, asserted per refit.
V8   Production-preprocessing parity: panel frame, panel-space transform,
     per-cutoff robust-z recompute and the sentiment trained_zeroing gate run
     via the production trainer's OWN helpers (read-only import); recomputed
     norm kinds == artifact feature_norm_kind and the replayed sentiment gate
     contract == the artifact's stored contract, per refit / per run.
V9   Frozen-geometry recompute (prereg §2/§3, CORRECTIONS #1/#3/#4 — the
     prereg COUNTED these; tolerance EXACT, mismatch = environment drift,
     fail closed): primary corpus 1,697 td; ON days 821 (fixed) / 808
     (expanding); expanding threshold first defined 2018-01-31; 28 complete
     blocks; ON-eligible 19 (fixed) / 19 (expanding) / 18 (both); ON-dominant
     8 / 8; weekly grid 340 dates; every ON-eligible block carries >=1
     ON-state weekly cross-section (else the frozen N=19 series is
     unconstructible).
V10  Paired weekly-grid identity: the ON/OFF classification is evaluated at
     EXACTLY the scoring dates — positional lookup (corpus day index) and
     label lookup (.loc[date]) must agree on every grid date.
V11  Snapshot edge: the last secondary grid date + 60td lies within the SPY
     calendar, and the panel's realized-label coverage reaches the last grid
     date — labels end within available data, never beyond it.
V12  Estimand floor: every weekly cross-section carries >= 100 usable names
     (finite score + label + all three DGTW characteristics). This is an
     ASSERT, not a filter — the formation corpus rule made binding.
V13  Ordering: the positive control is computed and checked BEFORE any
     conditional (ON/OFF) statistic; on failure the conditional read never
     happens and the outputs record INVALID_INSTRUMENT.
V14  Zero writes outside doc/research/data/: outputs are absolute paths next
     to this script; the chdir into the umbrella exists ONLY because the
     production helpers read data/ paths relative to it — nothing is written
     there.

INTERPRETATION LEDGER (constructions the prereg names but does not pin to
code — frozen HERE, in the reviewed runner, before the run):
 i.   P2 pairing: per-block PAIRED difference (ON-mean minus OFF-mean within
      the same block), over complete primary blocks with >=15 ON days AND
      >=15 OFF days (the formation DEFINITIONS.md rule — "a block contributes
      to a cell iff >= 15 days in that cell" — applied to both cells) and
      >=1 weekly cross-section in each state; block-t = mean/SE over those
      paired differences. Chosen because §5 prescribes ONE block-t for the
      difference (a one-sample statistic) and calls P2 less level-sensitive
      because the level "differences out" — which is the paired construction.
 ii.  DGTW cells: the capacity-memo script pools dates through a groupby;
      this runner applies the identical arithmetic per date (the memo's
      transform is per-date anyway). The >=15/cell floor is the prereg's
      addition; flagged-unadjusted rows keep the raw label.
 iii. Winsorized guard: per the capacity-memo construction the +-50% clip is
      applied to the per-name adjusted outcome BEFORE the spread; the label
      is in SD units, so the clip is +-0.50 SD.
 iv.  Bootstrap CI convention: one-sided 95% CI = [5th percentile of the
      resample means, +inf); "excludes 0" <=> q05 > 0. Stationary bootstrap
      is Politis-Romano with circular wrap, geometric blocks p = 1/2.
 v.   Top decile: N = int(round(n/10)) names by score, ties broken by stable
      sort on the deterministic panel row order (the formation's
      construction; the memo's fixed TOP_N=10 is superseded by the prereg's
      "top-decile").

Deterministic by construction: fixed seed (the artifact's for xgboost, 0 for
the bootstrap), fixed calendar, no early stopping, no search, stable row
ordering before the DMatrix build. All inputs are read-only local stores
whose sha256 digests are recorded.

Usage:  python 2026-08-18-vol-switch-derivation.py
Env:    RQ_UMBRELLA_ROOT overrides the default umbrella checkout path.
Output: results JSON + weekly-series CSV + block-table CSV + refit-ledger
        JSON next to this script.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

# ---------------------------------------------------------------- frozen IO
HERE = Path(__file__).resolve().parent
UMBRELLA = Path(os.environ.get("RQ_UMBRELLA_ROOT", "/Users/renhao/git/github/RenQuant"))

OHLCV = UMBRELLA / "data" / "ohlcv"
PANEL_PARQUET = UMBRELLA / "data" / "alpha158_291_fundamental_dataset.parquet"
SERVED_ARTIFACT = (UMBRELLA / "backtesting" / "renquant_104" / "artifacts"
                   / "prod" / "panel-ltr.alpha158_fund.json")
TRAINER_SCRIPT = UMBRELLA / "scripts" / "train_production_model.py"

OUT_JSON = HERE / "2026-08-18-vol-switch-results.json"
OUT_SERIES = HERE / "2026-08-18-vol-switch-series.csv"
OUT_BLOCKS = HERE / "2026-08-18-vol-switch-blocks.csv"
OUT_LEDGER = HERE / "2026-08-18-vol-switch-refit-ledger.json"
OUTPUTS = (OUT_JSON, OUT_SERIES, OUT_BLOCKS, OUT_LEDGER)

TAILQ90_RUNNER = HERE / "2026-08-18-gi-tailq90-derivation.py"

# ---------------------------------------------------------- frozen constants
# Corpora / grid / blocks — prereg §3 (post-CORRECTIONS numbers).
PRIMARY_START = "2017-01-03"
PRIMARY_END = "2023-09-29"
SECONDARY_END = "2026-03-31"         # secondary window end (calendar); the
                                     # last trading day <= this bound governs
SAMPLE_STEP = 5                      # weekly = every 5th trading day
BLOCK_TD = 60                        # non-overlapping 60-TRADING-day blocks
ELIGIBLE_MIN_ON_DAYS = 15            # ON-eligible block floor (prereg §3)
DOMINANT_MIN_ON_DAYS = 45            # ON-dominant (descriptive)
MIN_NAMES_PER_DATE = 100             # V12 estimand floor (formation rule)

# State — prereg §2.
VOL_WINDOW = 20                      # trading days
FIXED_ON_THRESHOLD = 0.135           # frozen rounded exploratory T3 edge
EXPANDING_WARMUP_OBS = 504           # sensitivity variant warmup
EXPANDING_QUANTILE = 2 / 3           # upper tercile

# Frozen primary-corpus geometry — prereg §2/§3 + CORRECTIONS #1/#3/#4,
# re-measured by the committed geometry_check.py (exploratory bundle README
# §3). Tolerance EXACT (V9).
FROZEN_PRIMARY_GEOMETRY = {
    "corpus_td": 1697,
    "on_days_fixed": 821,
    "on_days_expanding": 808,
    "expanding_threshold_first": "2018-01-31",
    "complete_blocks": 28,
    "eligible_fixed": 19,
    "eligible_expanding": 19,
    "eligible_both": 18,
    "dominant_fixed": 8,
    "dominant_expanding": 8,
    "weekly_grid_n": 340,            # derived: ceil(1697 / 5)
}

# Scoring — prereg §4 (production recipe VERBATIM, objective AT PRODUCTION).
FROZEN_CONFIG_FINGERPRINT = "sha256:f8fb2259b2bf1537"
PRODUCTION_OBJECTIVE = "rank:pairwise"
N_FEATURES = 172
LABEL = "fwd_60d_excess"
LABEL_HORIZON_TDAYS = 60             # h = 60 (training label AND estimand)
EMBARGO_TDAYS = 60                   # C + 60 trading days <= d
EXPECTED_BEST_ITER = 100
TRAIN_DATA_START = "2016-01-04"
REFIT_FIRST_QUARTER = (2016, 2)      # 2016-Q2 (prereg §4)
REFIT_LAST_QUARTER = (2025, 4)       # 2025-Q4 (secondary extension)
PRIMARY_LAST_QUARTER = (2023, 3)     # primary sub-ladder end (prereg §4)
EXPECTED_REFITS = 39
EXPECTED_PRIMARY_REFITS = 30         # 2016-Q2..2023-Q3
PANEL_N_TICKERS = 292                # prereg §3 universe

# Estimand — prereg §3 (capacity-memo instrument + the prereg's cell floor).
DGTW_CHARS = ("STD60", "ROC60", "BETA60")   # vol x mom x beta
DGTW_MIN_CELL = 15                   # >=15/cell else flagged-unadjusted
TOPDEC_DIV = 10                      # top decile: N = round(n/10)
WINSOR_CLIP = 0.5                    # +-50% (SD units — z label)

# Decision rule — prereg §5.
NW_LAG = 1
ONE_SIDED_ALPHA = 0.05
BOOT_RESAMPLES = 10_000
BOOT_EXPECTED_BLOCK = 2.0
BOOT_SEED = 0
P2_BLOCK_T_MIN = 1.0
MIN_ON_ELIGIBLE_BLOCKS = 15
MIN_ESS = 6.0

# §5 consequence strings, echoed verbatim into the output with the verdict.
CONSEQUENCE = {
    "CONFIRMED": (
        "authorizes ONLY a design PR for a vol-gated bull deployment window "
        "(shadow/sizing-first, operator-gated; no direct production change; "
        "survivor-clean confirmation happens at the PIT-universe / "
        "live-shadow stage, not in this corpus)"),
    "PARTIAL": (
        "shadow-forward path: the deployment-window design may proceed but "
        "its activation burden doubles (pre-committed: >=40 live shadow "
        "sessions in ON-state with positive realized spread before any "
        "operator ask)"),
    "REFUTED": (
        "the vol-switch line closes; the near-term bull discovery arm is "
        "exhausted (recorded as such; remaining leads are the #213 asset "
        "(2027 clock) and G-B policy)"),
    "UNMEASURABLE": (
        "fail-closed: guard floor not met (>=15 ON-eligible blocks AND "
        "realized ESS >= 6 on the ON block series); no verdict is issued and "
        "nothing deployment-shaped is authorized"),
    "INVALID_INSTRUMENT": (
        "positive control failed (unconditional primary spread <= 0): the "
        "instrument fails sanity; no conditional read was performed and no "
        "verdict is issued"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"FROZEN-GUARD FAILURE — STOP, do not adjust the spec: {msg}")


# --------------------------------------------------------------------------
# REUSED MACHINERY — copied VERBATIM from the reviewed tail_q90 runner
# doc/research/data/2026-08-18-gi-tailq90-derivation.py (#996/#999 lineage;
# prereg §4: "cite-and-reuse, not rewrite"). tests/test_vol_switch_runner.py
# enforces byte-identity of these definitions against that file.
# --------------------------------------------------------------------------
def build_refit_calendar(cal: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """T6: the 31 refit cutoffs — last trading day of each calendar quarter,
    2018-Q2 .. 2025-Q4, taken from the SPY trading calendar (spec §3)."""
    out: list[pd.Timestamp] = []
    for year in range(REFIT_FIRST_QUARTER[0], REFIT_LAST_QUARTER[0] + 1):
        for q in (1, 2, 3, 4):
            if (year, q) < REFIT_FIRST_QUARTER or (year, q) > REFIT_LAST_QUARTER:
                continue
            q_start = pd.Timestamp(year=year, month=3 * q - 2, day=1)
            q_end = q_start + pd.offsets.QuarterEnd(0)
            in_q = cal[(cal >= q_start) & (cal <= q_end)]
            _assert(len(in_q) > 0,
                    f"no trading days in {year}Q{q} — calendar too short for the refit ladder")
            out.append(in_q[-1])
    _assert(len(out) == EXPECTED_REFITS,
            f"refit calendar has {len(out)} cutoffs, frozen count is {EXPECTED_REFITS}")
    _assert(all(a < b for a, b in zip(out, out[1:])),
            "refit cutoffs are not strictly increasing")
    return out


def refit_index_for_date(cutoff_positions, date_pos: int,
                         embargo_tdays: int = EMBARGO_TDAYS):
    """T7: index of the NEWEST refit whose cutoff position p satisfies
    p + embargo <= date_pos (spec §3: C + 60 trading days <= d).
    Returns None when no refit is admissible (no gap-filling with newer
    models, no exceptions). Boundary: p + embargo == date_pos IS admissible;
    p + embargo == date_pos + 1 is not."""
    best = None
    for i, p in enumerate(cutoff_positions):
        if p + embargo_tdays <= date_pos:
            best = i
    return best


def latest_realized_label_pos(cutoff_pos: int,
                              horizon_tdays: int = LABEL_HORIZON_TDAYS) -> int:
    """T8: latest calendar position whose forward label is realized by the
    cutoff — a row at position t needs data through t + horizon, so
    t <= cutoff_pos - horizon. The boundary row (t + horizon == cutoff_pos,
    label window ending exactly AT the cutoff) IS usable; one later is not."""
    return cutoff_pos - horizon_tdays


class ReadersLite:
    """Close/volume reader over the read-only OHLCV store, digest-recording.

    Adapted from the moe runner's ScreenReaders (G2) with the quality_gp
    fundamentals machinery removed — this family reads no emitter inputs
    (T15). Provides the `.close()` surface `close_panel` expects and the
    `._frame()` surface the verbatim MomReaders copy expects.
    """

    def __init__(self) -> None:
        self._close: dict[str, pd.Series | None] = {}
        self._frames: dict[str, pd.DataFrame | None] = {}
        self._digests: dict[str, str] = {}

    def _frame(self, ticker: str) -> pd.DataFrame | None:
        if ticker not in self._frames:
            p = OHLCV / ticker / "1d.parquet"
            if not p.is_file():
                self._frames[ticker] = None
            else:
                self._digests[f"ohlcv/{ticker}/1d.parquet"] = _sha256(p)
                self._frames[ticker] = pd.read_parquet(p)
        return self._frames[ticker]

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

    def read_digests(self) -> dict[str, str]:
        return dict(self._digests)


def assert_one_shot(outputs=OUTPUTS) -> None:
    """T1: refuse to run when any output already exists — one shot, ever."""
    existing = [str(p) for p in outputs if Path(p).exists()]
    _assert(not existing,
            "one-shot marker: output(s) already exist, this screen has been "
            f"run — re-running is FORBIDDEN: {existing}")


def assert_runner_matches_main() -> dict:
    """T2: the executing runner's bytes must equal origin/main's copy."""
    me = Path(__file__).resolve()
    top = subprocess.run(["git", "-C", str(me.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    rel = me.relative_to(Path(top))
    blob = subprocess.run(["git", "-C", top, "show", f"origin/main:{rel.as_posix()}"],
                          capture_output=True)
    _assert(blob.returncode == 0,
            "runner is not on origin/main — freeze-then-review-then-run: "
            "merge the runner PR first, then execute the merged copy")
    _assert(blob.stdout == me.read_bytes(),
            "runner bytes differ from origin/main — execute the merged copy only")
    main_sha = subprocess.run(["git", "-C", top, "rev-parse", "origin/main"],
                              capture_output=True, text=True, check=True).stdout.strip()
    return {"origin_main_sha": main_sha,
            "runner_sha256": hashlib.sha256(me.read_bytes()).hexdigest()}


def load_trainer_module():
    """T9: read-only import of the production trainer (its helpers ARE the
    'everything else verbatim' surface: panel slice semantics, panel-space
    transform, per-cutoff robust-z recompute, sentiment trained_zeroing)."""
    spec = importlib.util.spec_from_file_location("rq_train_production_model",
                                                  TRAINER_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_served_artifact() -> dict:
    """T4: the frozen base recipe, identity-asserted."""
    art = json.loads(SERVED_ARTIFACT.read_text())
    _assert(art.get("config_fingerprint") == FROZEN_CONFIG_FINGERPRINT,
            f"served artifact fingerprint {art.get('config_fingerprint')!r} != "
            f"frozen {FROZEN_CONFIG_FINGERPRINT}")
    _assert(art.get("kind") == "panel_ltr_xgboost", "unexpected artifact kind")
    _assert(art.get("label_col") == LABEL, "artifact label_col != fwd_60d_excess")
    _assert(int(art.get("lookahead_days", -1)) == LABEL_HORIZON_TDAYS,
            "artifact lookahead_days != 60")
    _assert(len(art.get("feature_cols") or []) == N_FEATURES,
            "artifact does not carry exactly 172 feature_cols")
    _assert(len(art.get("feature_norm_kind") or []) == N_FEATURES,
            "artifact does not carry exactly 172 feature_norm_kind entries")
    _assert(int(art.get("best_iter", -1)) == EXPECTED_BEST_ITER,
            "artifact best_iter != 100 — boosting-round count unpinned")
    return art


def fit_booster(xgb_mod, tpm, train_df: pd.DataFrame, feat_cols: list[str],
                mu: np.ndarray, sd: np.ndarray, kinds: list[str],
                params: dict, n_rounds: int):
    """One refit. Mirrors the production train_xgb matrix construction
    (panel-space transform, y clip ±5, date-sorted rows, per-date groups)
    with the params supplied by the caller — the objective is the ONLY thing
    that differs between the candidate and the rho reference. Stable sort
    pins row order for byte-reproducibility (see module docstring)."""
    Xdf = tpm.panel_training_matrix(train_df, feat_cols, mu, sd, kinds)
    Xtr = Xdf.values.astype(np.float64)
    ytr = train_df[LABEL].clip(-5, 5).values.astype(np.float64)
    order = np.argsort(train_df["date"].values, kind="stable")
    Xs, ys, ds = Xtr[order], ytr[order], train_df["date"].values[order]
    _, gsz = np.unique(ds, return_counts=True)
    dtr = xgb_mod.DMatrix(Xs, label=ys)
    dtr.set_group(gsz)
    booster = xgb_mod.train(params, dtr, num_boost_round=n_rounds)
    digest = hashlib.sha256(bytes(booster.save_raw(raw_format="json"))).hexdigest()
    return booster, digest


def score_frame(xgb_mod, tpm, booster, frame: pd.DataFrame, feat_cols: list[str],
                mu: np.ndarray, sd: np.ndarray, kinds: list[str]) -> pd.Series:
    """RAW scores for one date's cross-section (spec §2: emitted RAW)."""
    _assert(frame["ticker"].is_unique, "duplicate tickers in a scoring cross-section")
    Xdf = tpm.panel_training_matrix(frame, feat_cols, mu, sd, kinds)
    pred = booster.predict(xgb_mod.DMatrix(Xdf.values.astype(np.float64)))
    s = pd.Series(pred, index=[str(t) for t in frame["ticker"]], dtype=float)
    return s[np.isfinite(s)]


# --------------------------------------------------- pure frozen state logic
def realized_vol20(close: pd.Series) -> pd.Series:
    """Prereg §2: SPY 20-td realized vol — close-to-close simple returns,
    rolling sample std (ddof=1, pandas default), annualized sqrt(252).
    Byte-matches the committed geometry_check.py construction."""
    return close.pct_change().rolling(VOL_WINDOW).std() * np.sqrt(252)


def on_state_fixed(vol20: pd.Series) -> pd.Series:
    """ON <=> vol20 > 0.135, STRICT (exactly 0.135 is OFF). NaN vol20
    (warmup days) compares False -> OFF, fail-closed."""
    return vol20 > FIXED_ON_THRESHOLD


def expanding_threshold(vol20: pd.Series) -> pd.Series:
    """Sensitivity variant threshold: expanding 66.7th percentile of all
    vol20 history <= d, defined once >= 504 observations exist (series start
    2016-01-04 -> first defined 2018-01-31). NaN before warmup."""
    return vol20.dropna().expanding(min_periods=EXPANDING_WARMUP_OBS).quantile(
        EXPANDING_QUANTILE)


def on_state_expanding(vol20: pd.Series) -> pd.Series:
    """ON <=> vol20 > expanding threshold; days before the threshold exists
    are OFF by fail-closed convention (prereg CORRECTIONS #4)."""
    thr = expanding_threshold(vol20).reindex(vol20.index)
    return vol20 > thr  # NaN threshold (or NaN vol20) compares False -> OFF


def block_on_day_counts(on_corpus: pd.Series, n_blocks: int) -> list[int]:
    """ON-day count per complete non-overlapping 60-td block (positional —
    the corpus series must be exactly the corpus trading days, in order)."""
    return [int(on_corpus.iloc[i * BLOCK_TD:(i + 1) * BLOCK_TD].sum())
            for i in range(n_blocks)]


def assert_frozen_primary_geometry(measured: dict) -> None:
    """V9: EXACT match against the prereg's counted geometry — a mismatch
    means environment drift; fail closed, never adjust."""
    for key, frozen in FROZEN_PRIMARY_GEOMETRY.items():
        _assert(key in measured, f"geometry recompute is missing {key!r}")
        _assert(measured[key] == frozen,
                f"frozen geometry mismatch on {key!r}: measured "
                f"{measured[key]!r} != frozen {frozen!r} (prereg §2/§3)")


# ------------------------------------------------- pure frozen estimand logic
def dgtw_adjust(df: pd.DataFrame, min_cell: int = DGTW_MIN_CELL) -> pd.DataFrame:
    """The capacity-memo DGTW construction, per date, + the prereg's cell
    floor. `df` carries STD60/ROC60/BETA60 and `label`; rows with any of the
    four missing are dropped (the caller counts them). Terciles per
    characteristic via qcut on rank(method='first') (the memo's tie-break),
    27 cells, benchmark = self-excluded cell mean of the label. Rows in cells
    with < min_cell members keep the label UNADJUSTED and are flagged
    (`adjusted == False`) — prereg §3 '>=15/cell else flagged-unadjusted'."""
    d = df.dropna(subset=[*DGTW_CHARS, "label"]).copy()
    for c in DGTW_CHARS:
        d[c + "_t"] = pd.qcut(d[c].rank(method="first"), 3, labels=False)
    d["cell"] = (d["STD60_t"].astype(int) * 9 + d["ROC60_t"].astype(int) * 3
                 + d["BETA60_t"].astype(int))
    g = d.groupby("cell")["label"]
    d["cell_n"] = g.transform("count")
    bench = (g.transform("sum") - d["label"]) / (d["cell_n"] - 1).replace(0, np.nan)
    d["adjusted"] = d["cell_n"] >= min_cell
    d["dgtw"] = np.where(d["adjusted"], d["label"] - bench, d["label"])
    return d


def top_decile_spread(df: pd.DataFrame, col: str) -> tuple[float, int, int]:
    """Per-date top-decile spread: N = int(round(n/10)) names by score
    (stable sort — deterministic tie-break on the panel row order), spread =
    top-decile mean of `col` minus the full-cross-section mean of `col`
    (the capacity-memo daily_top_spread, top-N generalized to top-decile)."""
    n = len(df)
    ndec = int(round(n / TOPDEC_DIV))
    _assert(ndec >= 1, f"cross-section too small for a top decile (n={n})")
    top = df.sort_values("score", ascending=False, kind="stable").head(ndec)
    return float(top[col].mean() - df[col].mean()), n, ndec


def vol_matched_topdec(df: pd.DataFrame) -> float:
    """Tilt control (prereg §6, reported only): STD60-tercile cohort-matched
    top-decile outcome — per-date STD60 terciles, self-excluded cohort mean
    benchmark, value = top-decile mean of (label - benchmark). Mirrors the
    formation vol_matched_check.py with top-decile N."""
    d = df.dropna(subset=["STD60", "label"])
    terc = pd.qcut(d["STD60"].rank(method="first"), 3, labels=False)
    g = d.groupby(terc)["label"]
    bench = (g.transform("sum") - d["label"]) / (g.transform("count") - 1)
    adj = d["label"] - bench
    ndec = int(round(len(d) / TOPDEC_DIV))
    top_idx = d.sort_values("score", ascending=False, kind="stable").head(ndec).index
    return float(adj.loc[top_idx].mean())


# ------------------------------------------------- pure frozen block logic
def aggregate_blocks(weekly: pd.DataFrame, on_col: str,
                     on_day_counts: list[int]) -> pd.DataFrame:
    """Per-block ON/OFF aggregation over the weekly cross-section rows.
    `weekly` carries `block` (complete blocks only; remainder rows excluded
    by the caller), the ON flag column, and the spread columns. A block's
    ON (OFF) outcome = mean spread over its ON- (OFF-) state weekly dates
    (prereg §3)."""
    rows = []
    for b, on_days in enumerate(on_day_counts):
        sub = weekly[weekly["block"] == b]
        on = sub[sub[on_col].astype(bool)]
        off = sub[~sub[on_col].astype(bool)]
        on_mean = float(on["spread_dgtw"].mean()) if len(on) else np.nan
        off_mean = float(off["spread_dgtw"].mean()) if len(off) else np.nan
        rows.append({
            "block": b,
            "on_days": on_days,
            "off_days": BLOCK_TD - on_days,
            "eligible": on_days >= ELIGIBLE_MIN_ON_DAYS,
            "dominant": on_days >= DOMINANT_MIN_ON_DAYS,
            "n_weekly": int(len(sub)),
            "n_on_weekly": int(len(on)),
            "n_off_weekly": int(len(off)),
            "on_mean": on_mean,
            "off_mean": off_mean,
            "on_mean_w50": float(on["spread_dgtw_w50"].mean()) if len(on) else np.nan,
            "on_minus_off": (on_mean - off_mean
                             if len(on) and len(off) else np.nan),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------- pure frozen decision rule
def nw_lag1(x: np.ndarray) -> dict:
    """P1(a): Newey-West (lag 1, Bartlett weight 1/2) SE of the mean computed
    ON THE BLOCK SERIES; small-sample t with df = N - 1; one-sided 95% CI
    [mean - t_crit * se, +inf) excludes 0 <=> t >= t_crit."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    _assert(n >= 2, "NW inference needs at least 2 blocks")
    m = float(x.mean())
    dev = x - m
    gamma0 = float((dev * dev).sum() / n)
    gamma1 = float((dev[1:] * dev[:-1]).sum() / n)
    var_mean = (gamma0 + 2.0 * (1.0 - 1.0 / (NW_LAG + 1)) * gamma1) / n
    _assert(var_mean > 0, "NW variance of the mean is not positive")
    se = float(np.sqrt(var_mean))
    tstat = m / se
    crit = float(student_t.ppf(1.0 - ONE_SIDED_ALPHA, n - 1))
    return {"mean": m, "se": se, "t": float(tstat), "df": n - 1,
            "t_crit_one_sided_95": crit,
            "ci_lower_one_sided_95": m - crit * se,
            "passes": bool(m - crit * se > 0)}


def stationary_bootstrap_means(x: np.ndarray,
                               n_resamples: int = BOOT_RESAMPLES,
                               expected_block: float = BOOT_EXPECTED_BLOCK,
                               seed: int = BOOT_SEED) -> np.ndarray:
    """P1(b): Politis-Romano stationary block bootstrap of the mean —
    circular wrap, geometric block lengths with p = 1/expected_block,
    fixed seed. Returns the resample means (deterministic given the seed)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    _assert(n >= 2, "bootstrap needs at least 2 blocks")
    p = 1.0 / expected_block
    rng = np.random.default_rng(seed)
    means = np.empty(n_resamples, dtype=float)
    for b in range(n_resamples):
        idx = np.empty(n, dtype=np.int64)
        i = int(rng.integers(n))
        idx[0] = i
        for k in range(1, n):
            if rng.random() < p:
                i = int(rng.integers(n))
            else:
                i = (i + 1) % n
            idx[k] = i
        means[b] = x[idx].mean()
    return means


def ess_lag1(x: np.ndarray) -> tuple[float, float]:
    """Guard: ESS = N * (1 - rho1) / (1 + rho1), rho1 = lag-1 autocorrelation
    of the block series clipped below at 0 (canon §1.2 minima)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    dev = x - x.mean()
    gamma0 = float((dev * dev).sum() / n)
    _assert(gamma0 > 0, "degenerate (constant) block series — ESS undefined")
    rho1 = float((dev[1:] * dev[:-1]).sum() / n / gamma0)
    rho1_clipped = max(rho1, 0.0)
    ess = n * (1.0 - rho1_clipped) / (1.0 + rho1_clipped)
    return rho1, float(ess)


def p1_conjunction(nw_passes: bool, boot_passes: bool,
                   wins_passes: bool) -> tuple[bool, bool]:
    """The §5 conjunction: BOTH inference legs must pass AND the winsorized
    anti-lottery guard must hold; a split between the two legs is reported as
    DISAGREEMENT and FAILS P1 (conservative, pre-frozen). Returns
    (p1_pass, disagreement)."""
    disagreement = bool(nw_passes) != bool(boot_passes)
    return bool(nw_passes and boot_passes and wins_passes), disagreement


def p1_decision(on_vals: np.ndarray, on_wins_vals: np.ndarray) -> dict:
    """P1 (prereg §5): the dependence-robust CONJUNCTION — NW-on-blocks AND
    stationary bootstrap, one-sided alpha = 0.05; a split decision is
    reported as DISAGREEMENT and FAILS (conservative, pre-frozen). The
    winsorized +-50% ON-spread >= 0 anti-lottery guard is a further conjunct."""
    nw = nw_lag1(on_vals)
    boot_means = stationary_bootstrap_means(on_vals)
    q05 = float(np.percentile(boot_means, 100.0 * ONE_SIDED_ALPHA))
    boot = {"q05": q05, "n_resamples": int(len(boot_means)),
            "expected_block_length": BOOT_EXPECTED_BLOCK, "seed": BOOT_SEED,
            "passes": bool(q05 > 0)}
    wins_mean = float(np.asarray(on_wins_vals, dtype=float).mean())
    wins_pass = wins_mean >= 0
    p1_pass, disagreement = p1_conjunction(nw["passes"], boot["passes"], wins_pass)
    return {"nw": nw, "bootstrap": boot, "disagreement": disagreement,
            "winsorized_on_mean": wins_mean,
            "winsorized_guard_passes": bool(wins_pass),
            "p1_pass": p1_pass}


def p2_decision(blocks: pd.DataFrame) -> dict:
    """P2 (prereg §5 + interpretation ledger i): per-block PAIRED ON-minus-
    OFF difference over complete blocks with >=15 days in EACH state and >=1
    weekly cross-section in each state; block-t = mean/SE; pass <=>
    difference > 0 AND block-t >= 1.0."""
    ok = blocks[(blocks["on_days"] >= ELIGIBLE_MIN_ON_DAYS)
                & (blocks["off_days"] >= ELIGIBLE_MIN_ON_DAYS)
                & (blocks["n_on_weekly"] >= 1)
                & (blocks["n_off_weekly"] >= 1)]
    d = ok["on_minus_off"].to_numpy(dtype=float)
    n = len(d)
    if n < 2:
        return {"n_blocks": n, "mean_diff": float(d.mean()) if n else None,
                "block_t": None, "passes": False,
                "reason": "fewer than 2 paired ON/OFF blocks"}
    m = float(d.mean())
    tstat = float(m / (d.std(ddof=1) / np.sqrt(n)))
    return {"n_blocks": n, "mean_diff": m, "block_t": tstat,
            "passes": bool(m > 0 and tstat >= P2_BLOCK_T_MIN),
            "contributing_blocks": [int(b) for b in ok["block"]]}


def final_verdict(positive_control_pass: bool, measurable: bool,
                  p1_pass: bool, p2_pass: bool) -> tuple[str, str]:
    """Prereg §5 verdict mapping with the pre-frozen consequence strings.
    Precedence: instrument sanity, then the measurability guards, then P1/P2."""
    if not positive_control_pass:
        v = "INVALID_INSTRUMENT"
    elif not measurable:
        v = "UNMEASURABLE"
    elif p1_pass and p2_pass:
        v = "CONFIRMED"
    elif p1_pass:
        v = "PARTIAL"
    else:
        v = "REFUTED"
    return v, CONSEQUENCE[v]


# ----------------------------------------------------------------------- main
def main() -> None:
    t_start = time.time()
    assert_one_shot()
    main_identity = assert_runner_matches_main()
    import xgboost as xgb  # noqa: PLC0415 — heavyweight, main-only

    # The production helpers read data/ paths relative to the umbrella root;
    # the runner reads there and writes ONLY next to itself (V14).
    os.chdir(UMBRELLA)
    tpm = load_trainer_module()

    art = load_served_artifact()
    feat_cols = [str(c) for c in art["feature_cols"]]
    # V4: objective AT PRODUCTION — the artifact's params VERBATIM, no delta.
    params = dict(art["params"])
    _assert(params.get("objective") == PRODUCTION_OBJECTIVE,
            f"artifact objective {params.get('objective')!r} != "
            f"{PRODUCTION_OBJECTIVE!r} — wrong base artifact")
    _assert("seed" in params, "artifact params carry no seed — determinism unpinned")
    n_rounds = int(art["best_iter"])

    # ---- SPY calendar + frozen state geometry (V9/V10) --------------------
    print("[1/6] SPY state series + frozen-geometry recompute ...", flush=True)
    readers = ReadersLite()
    spy_close = readers.market_close()
    _assert(spy_close.index.is_monotonic_increasing and spy_close.index.is_unique,
            "SPY calendar is not a clean trading-day index")
    cal = spy_close.index
    vol20 = realized_vol20(spy_close)
    on_fixed_all = on_state_fixed(vol20)
    on_exp_all = on_state_expanding(vol20)
    thr = expanding_threshold(vol20)

    corpus = vol20.loc[PRIMARY_START:PRIMARY_END]
    _assert(str(corpus.index[0].date()) == PRIMARY_START
            and str(corpus.index[-1].date()) == PRIMARY_END,
            "primary corpus endpoints are not trading days of the SPY calendar")
    _assert(corpus.notna().all(), "vol20 undefined on a primary-corpus day")
    sec_index = cal[(cal >= PRIMARY_START) & (cal <= SECONDARY_END)]
    _assert(sec_index[0] == corpus.index[0], "secondary corpus start drifted")

    on_fixed_prim = on_fixed_all.loc[corpus.index]
    on_exp_prim = on_exp_all.loc[corpus.index]
    n_blocks_prim = len(corpus) // BLOCK_TD
    counts_fixed = block_on_day_counts(on_fixed_prim, n_blocks_prim)
    counts_exp = block_on_day_counts(on_exp_prim, n_blocks_prim)
    elig_fixed = [c >= ELIGIBLE_MIN_ON_DAYS for c in counts_fixed]
    elig_exp = [c >= ELIGIBLE_MIN_ON_DAYS for c in counts_exp]
    grid_prim = corpus.index[::SAMPLE_STEP]
    measured_geometry = {
        "corpus_td": len(corpus),
        "on_days_fixed": int(on_fixed_prim.sum()),
        "on_days_expanding": int(on_exp_prim.sum()),
        "expanding_threshold_first": str(thr.dropna().index[0].date()),
        "complete_blocks": n_blocks_prim,
        "eligible_fixed": sum(elig_fixed),
        "eligible_expanding": sum(elig_exp),
        "eligible_both": sum(f and e for f, e in zip(elig_fixed, elig_exp)),
        "dominant_fixed": sum(c >= DOMINANT_MIN_ON_DAYS for c in counts_fixed),
        "dominant_expanding": sum(c >= DOMINANT_MIN_ON_DAYS for c in counts_exp),
        "weekly_grid_n": len(grid_prim),
    }
    assert_frozen_primary_geometry(measured_geometry)

    grid_sec = sec_index[::SAMPLE_STEP]
    n_blocks_sec = len(sec_index) // BLOCK_TD
    on_fixed_sec = on_fixed_all.loc[sec_index]
    on_exp_sec = on_exp_all.loc[sec_index]
    counts_fixed_sec = block_on_day_counts(on_fixed_sec, n_blocks_sec)
    counts_exp_sec = block_on_day_counts(on_exp_sec, n_blocks_sec)
    _assert(counts_fixed_sec[:n_blocks_prim] == counts_fixed,
            "secondary blocks do not extend the primary blocks in place")

    # V11 snapshot edge (calendar leg): the last grid date's label window
    # must end within the committed SPY calendar.
    last_pos = int(cal.get_loc(grid_sec[-1]))
    _assert(last_pos + LABEL_HORIZON_TDAYS < len(cal),
            "snapshot edge: the last grid date's h=60 label window leaves the calendar")

    # ---- refit ladder (V5) ------------------------------------------------
    refit_cutoffs = build_refit_calendar(cal)
    cutoff_pos = [int(cal.get_loc(c)) for c in refit_cutoffs]
    primary_ladder_end = pd.Timestamp(
        year=PRIMARY_LAST_QUARTER[0], month=3 * PRIMARY_LAST_QUARTER[1] - 2,
        day=1) + pd.offsets.QuarterEnd(0)
    n_primary_ladder = sum(1 for c in refit_cutoffs if c <= primary_ladder_end)
    _assert(n_primary_ladder == EXPECTED_PRIMARY_REFITS,
            f"primary sub-ladder has {n_primary_ladder} cutoffs, frozen "
            f"{EXPECTED_PRIMARY_REFITS} (2016-Q2..2023-Q3)")
    first_scoreable_pos = cutoff_pos[0] + EMBARGO_TDAYS
    _assert(cal[first_scoreable_pos] <= grid_prim[0],
            "first scoreable date falls after the primary corpus start — "
            "the frozen ladder cannot score the corpus")

    # ---- panel (read-only; the production training frame) -----------------
    print(f"[2/6] loading panel {PANEL_PARQUET.name} ...", flush=True)
    panel_digest = _sha256(PANEL_PARQUET)
    panel = pd.read_parquet(PANEL_PARQUET)
    panel["date"] = pd.to_datetime(panel["date"])
    _assert(LABEL in panel.columns, "panel lacks the fwd_60d_excess label")
    _assert(all(c in panel.columns for c in feat_cols),
            "panel lacks artifact feature columns")
    _assert(all(c in panel.columns for c in DGTW_CHARS),
            "panel lacks the DGTW characteristic columns")
    # V8 cross-check: the production feat-col derivation over THIS panel must
    # reproduce the artifact's 172 columns exactly.
    excl = {"ticker", "date", "split_label",
            "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess"}
    derived = [c for c in panel.columns
               if c not in excl and c not in set(tpm.TRACK_B_FEATURES)]
    _assert(set(derived) == set(feat_cols),
            "production feat-col derivation != artifact feature_cols")
    _assert(panel["ticker"].nunique() == PANEL_N_TICKERS,
            f"panel universe {panel['ticker'].nunique()} != frozen {PANEL_N_TICKERS}")
    _assert(str(panel["date"].min().date()) == TRAIN_DATA_START,
            f"panel data start {panel['date'].min().date()} != frozen {TRAIN_DATA_START}")
    _assert(not panel.duplicated(["date", "ticker"]).any(),
            "duplicate (date, ticker) rows in the panel")
    panel_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    _assert(panel_dates.isin(cal).all(), "panel dates off the SPY trading calendar")
    _assert(grid_sec.isin(panel_dates).all(),
            "grid dates missing from the panel — features unavailable")
    # V11 snapshot edge (label leg): realized labels reach the last grid date.
    last_labeled = panel.dropna(subset=[LABEL])["date"].max()
    _assert(last_labeled >= grid_sec[-1],
            f"panel realized labels end {last_labeled.date()} before the last "
            f"grid date {grid_sec[-1].date()} — labels do not cover the corpus")

    # ---- sentiment trained_zeroing replay (V8, production helpers) --------
    print("[3/6] sentiment trained_zeroing replay (production regime chain) ...",
          flush=True)
    fingerprint_cfg = tpm.build_fingerprint_config(
        fingerprint_config_path=None, watchlist_file=None,
        label_used=LABEL, feat_cols=feat_cols)
    regime_map = tpm.build_sentiment_training_regime_map(
        panel["date"].unique(), fingerprint_cfg)
    panel, gate_meta = tpm.apply_sentiment_training_gate(
        panel, feat_cols, fingerprint_cfg, regime_map)
    _assert(bool(gate_meta), "sentiment gate not required — contract drifted "
            "from the artifact's trained_zeroing recipe")
    _assert(list(gate_meta["sentiment_runtime_gate_feature_cols"]) ==
            list(art["sentiment_runtime_gate_feature_cols"]),
            "replayed sentiment gate cols != artifact's stored contract")
    _assert(sorted(gate_meta["sentiment_runtime_gate_disabled_regimes"]) ==
            sorted(art["sentiment_runtime_gate_disabled_regimes"]),
            "replayed disabled regimes != artifact's stored contract")

    by_date = {d: sub for d, sub in panel.groupby("date")}

    # ---- 39 expanding refits, objective AT PRODUCTION (V4/V5/V7/V8) -------
    print(f"[4/6] {EXPECTED_REFITS} expanding refits (rank:pairwise verbatim) ...",
          flush=True)
    boosters, norms, ledger = [], [], []
    for i, cutoff in enumerate(refit_cutoffs):
        cpos = cutoff_pos[i]
        latest_pos = latest_realized_label_pos(cpos)
        _assert(latest_pos > 0, f"cutoff {cutoff.date()} precedes the data start")
        latest_date = cal[latest_pos]
        tr = panel[(panel["date"] >= pd.Timestamp(TRAIN_DATA_START))
                   & (panel["date"] <= latest_date)].dropna(subset=[LABEL])
        _assert(len(tr) > 0, f"no realized-label rows at cutoff {cutoff.date()}")
        max_pos = int(cal.get_loc(tr["date"].max()))
        _assert(max_pos + LABEL_HORIZON_TDAYS <= cpos,
                f"training rows at cutoff {cutoff.date()} carry unrealized labels")
        mu, sd, kinds, _, _ = tpm.build_normalization(tr, feat_cols)
        _assert(list(kinds) == list(art["feature_norm_kind"]),
                f"norm kinds at cutoff {cutoff.date()} != artifact feature_norm_kind")
        t0 = time.time()
        booster, digest = fit_booster(xgb, tpm, tr, feat_cols, mu, sd, kinds,
                                      params, n_rounds)
        boosters.append(booster)
        norms.append((mu, sd, kinds))
        ledger.append({
            "refit_index": i,
            "cutoff": str(cutoff.date()),
            "in_primary_ladder": bool(cutoff <= primary_ladder_end),
            "first_scoreable_date": str(cal[cpos + EMBARGO_TDAYS].date())
                if cpos + EMBARGO_TDAYS < len(cal) else None,
            "n_train_rows": int(len(tr)),
            "n_train_dates": int(tr["date"].nunique()),
            "train_min_date": str(tr["date"].min().date()),
            "train_max_date": str(tr["date"].max().date()),
            "booster_sha256": digest,
            "fit_seconds": round(time.time() - t0, 1),
        })
        print(f"    {cutoff.date()}: rows={len(tr):>7d} "
              f"max_train={tr['date'].max().date()} "
              f"({ledger[-1]['fit_seconds']}s)", flush=True)

    # ---- weekly cross-sections: score + estimand (V6/V10/V12) -------------
    print("[5/6] scoring the weekly grid + DGTW estimand ...", flush=True)
    sec_pos = {d: i for i, d in enumerate(sec_index)}
    refit_used: dict[str, str] = {}
    weekly_rows = []
    for d in grid_sec:
        dpos = int(cal.get_loc(d))
        ri = refit_index_for_date(cutoff_pos, dpos)
        _assert(ri is not None, f"grid date {d.date()} has no admissible refit")
        _assert(cutoff_pos[ri] + EMBARGO_TDAYS <= dpos,
                f"embargo violated at {d.date()}")
        if ri + 1 < len(cutoff_pos):
            _assert(cutoff_pos[ri + 1] + EMBARGO_TDAYS > dpos,
                    f"not the newest admissible refit at {d.date()}")
        in_primary = d <= corpus.index[-1]
        if in_primary:
            # V5: primary dates must resolve within the primary sub-ladder.
            _assert(refit_cutoffs[ri] <= primary_ladder_end,
                    f"primary date {d.date()} selected a post-2023-Q3 refit")
        frame = by_date.get(d)
        _assert(frame is not None and not frame.empty,
                f"no panel cross-section at grid date {d.date()}")
        mu, sd, kinds = norms[ri]
        scores = score_frame(xgb, tpm, boosters[ri], frame, feat_cols, mu, sd, kinds)
        refit_used[str(d.date())] = str(refit_cutoffs[ri].date())

        est = frame.set_index("ticker")[[LABEL, *DGTW_CHARS]].rename(
            columns={LABEL: "label"})
        est.index = [str(t) for t in est.index]
        est = est.join(scores.rename("score"), how="inner")
        est = est.dropna(subset=["score", "label", *DGTW_CHARS])
        _assert(len(est) >= MIN_NAMES_PER_DATE,
                f"{d.date()}: {len(est)} usable names < floor {MIN_NAMES_PER_DATE}")

        dg = dgtw_adjust(est)
        dg["dgtw_w50"] = dg["dgtw"].clip(-WINSOR_CLIP, WINSOR_CLIP)
        spread, n_used, ndec = top_decile_spread(dg, "dgtw")
        spread_w50, _, _ = top_decile_spread(dg, "dgtw_w50")
        spread_raw, _, _ = top_decile_spread(dg, "label")

        # V10: paired weekly-grid identity — positional and label lookups of
        # the state classification must agree at the scoring date.
        p = sec_pos[d]
        onf_pos, one_pos = bool(on_fixed_sec.iloc[p]), bool(on_exp_sec.iloc[p])
        _assert(onf_pos == bool(on_fixed_all.loc[d])
                and one_pos == bool(on_exp_all.loc[d]),
                f"state classification misaligned with the scoring date {d.date()}")

        block = p // BLOCK_TD
        weekly_rows.append({
            "date": str(d.date()),
            "day_pos": p,
            "block": block if block < n_blocks_sec else -1,
            "in_primary": bool(in_primary),
            "in_primary_block": bool(p < n_blocks_prim * BLOCK_TD),
            "on_fixed": onf_pos,
            "on_expanding": one_pos,
            "spy_vol20": float(vol20.loc[d]),
            "n_usable": n_used,
            "n_topdec": ndec,
            "frac_flagged_unadjusted": float(1.0 - dg["adjusted"].mean()),
            "spread_dgtw": spread,
            "spread_dgtw_w50": spread_w50,
            "spread_raw": spread_raw,
            "volmatched_topdec": vol_matched_topdec(est),
            "refit_cutoff": refit_used[str(d.date())],
        })
    weekly = pd.DataFrame(weekly_rows)
    weekly_dt = pd.to_datetime(weekly["date"])
    _assert(len(weekly) == len(grid_sec) and (weekly_dt.values == grid_sec.values).all(),
            "weekly table does not cover exactly the frozen grid")

    # ---- decision (V13: positive control BEFORE any conditional read) -----
    print("[6/6] frozen decision rule ...", flush=True)
    prim_weekly = weekly[weekly["in_primary"]].copy()
    _assert(len(prim_weekly) == FROZEN_PRIMARY_GEOMETRY["weekly_grid_n"],
            "primary weekly cross-section count drifted")
    positive_control_mean = float(prim_weekly["spread_dgtw"].mean())
    positive_control_pass = positive_control_mean > 0

    out: dict = {}
    blocks_tables: dict[str, pd.DataFrame] = {}
    if positive_control_pass:
        # Conditional read — computed only after the instrument sanity check.
        prim_block_weekly = weekly[weekly["in_primary_block"]]
        blocks_tables["primary_fixed"] = aggregate_blocks(
            prim_block_weekly, "on_fixed", counts_fixed)
        blocks_tables["primary_expanding"] = aggregate_blocks(
            prim_block_weekly, "on_expanding", counts_exp)
        sec_block_weekly = weekly[weekly["block"] >= 0]
        blocks_tables["secondary_fixed"] = aggregate_blocks(
            sec_block_weekly, "on_fixed", counts_fixed_sec)
        blocks_tables["secondary_expanding"] = aggregate_blocks(
            sec_block_weekly, "on_expanding", counts_exp_sec)

        bf = blocks_tables["primary_fixed"]
        elig = bf[bf["eligible"]]
        # V9 (series leg): the decisive series must be exactly the frozen 19.
        _assert(int((elig["n_on_weekly"] >= 1).sum()) == len(elig)
                == FROZEN_PRIMARY_GEOMETRY["eligible_fixed"],
                "an ON-eligible primary block lacks ON-state weekly "
                "cross-sections — the frozen N=19 series is unconstructible")
        on_vals = elig["on_mean"].to_numpy(dtype=float)
        on_wins_vals = elig["on_mean_w50"].to_numpy(dtype=float)
        _assert(np.isfinite(on_vals).all() and np.isfinite(on_wins_vals).all(),
                "non-finite ON block outcome in the decisive series")

        rho1, ess = ess_lag1(on_vals)
        measurable = (len(on_vals) >= MIN_ON_ELIGIBLE_BLOCKS) and (ess >= MIN_ESS)
        p1 = p1_decision(on_vals, on_wins_vals)
        p2 = p2_decision(bf)
        verdict, consequence = final_verdict(
            positive_control_pass, measurable, p1["p1_pass"], p2["passes"])

        # Sensitivity variant (reported, never decisive): same P1 machinery
        # on the expanding-definition eligible blocks.
        be = blocks_tables["primary_expanding"]
        elig_e = be[be["eligible"] & (be["n_on_weekly"] >= 1)]
        on_vals_e = elig_e["on_mean"].to_numpy(dtype=float)
        rho1_e, ess_e = ess_lag1(on_vals_e)
        sensitivity = {
            "state_definition": "expanding upper-tercile (prereg §2 variant)",
            "decisive": False,
            "n_eligible_blocks": int(len(elig_e)),
            "rho1": rho1_e, "ess": ess_e,
            "p1_style": p1_decision(on_vals_e,
                                    elig_e["on_mean_w50"].to_numpy(dtype=float)),
            "p2_style": p2_decision(be),
        }
        # Secondary corpus (reported, never decisive — formation-contaminated).
        sf = blocks_tables["secondary_fixed"]
        elig_s = sf[sf["eligible"] & (sf["n_on_weekly"] >= 1)]
        on_vals_s = elig_s["on_mean"].to_numpy(dtype=float)
        rho1_s, ess_s = ess_lag1(on_vals_s)
        secondary = {
            "corpus": f"{PRIMARY_START}..{str(sec_index[-1].date())} "
                      "(contains the formation window — cannot decide)",
            "decisive": False,
            "n_blocks": n_blocks_sec,
            "n_eligible_blocks_fixed": int(len(elig_s)),
            "rho1": rho1_s, "ess": ess_s,
            "p1_style_fixed": p1_decision(
                on_vals_s, elig_s["on_mean_w50"].to_numpy(dtype=float)),
            "p2_style_fixed": p2_decision(sf),
        }
        conditional = {
            "decisive_series": {
                "corpus": "primary", "state_definition": "fixed > 0.135",
                "n_on_eligible_blocks": int(len(on_vals)),
                "on_block_means": [float(v) for v in on_vals],
                "rho1": rho1, "ess": ess,
                "measurable": bool(measurable),
            },
            "p1": p1,
            "p2": p2,
            "sensitivity_variant": sensitivity,
            "secondary_corpus": secondary,
            "tilt_control_volmatched": {
                "note": "STD60-cohort-matched top-decile outcome (reported)",
                "primary_on_mean_fixed": float(
                    prim_weekly[prim_weekly["on_fixed"]]["volmatched_topdec"].mean()),
                "primary_off_mean_fixed": float(
                    prim_weekly[~prim_weekly["on_fixed"]]["volmatched_topdec"].mean()),
                "primary_uncond_mean": float(prim_weekly["volmatched_topdec"].mean()),
            },
        }
    else:
        verdict, consequence = final_verdict(False, False, False, False)
        conditional = {
            "note": "positive control failed — the conditional read was NOT "
                    "performed (prereg §5, V13)"}

    # ---- outputs (V1/V14: only next to this script) -----------------------
    weekly.to_csv(OUT_SERIES, index=False)
    if blocks_tables:
        all_blocks = pd.concat(
            [t.assign(table=k) for k, t in blocks_tables.items()],
            ignore_index=True)
        all_blocks.to_csv(OUT_BLOCKS, index=False)
    else:
        pd.DataFrame({"note": ["positive control failed — no conditional "
                               "block tables were computed"]}).to_csv(
            OUT_BLOCKS, index=False)
    OUT_LEDGER.write_text(json.dumps({
        "prereg": "doc/research/2026-08-18-vol-switch-confirmatory-prereg.md (orch#1001)",
        "refits": ledger,
        "refit_used_by_score_date": refit_used,
    }, indent=2, sort_keys=True) + "\n")

    out = {
        "verdict": verdict,
        "consequence": consequence,
        "positive_control": {
            "unconditional_primary_mean_spread": positive_control_mean,
            "passes": bool(positive_control_pass),
            "rule": "unconditional primary spread > 0 BEFORE any conditional read",
        },
        "prereg": "doc/research/2026-08-18-vol-switch-confirmatory-prereg.md (orch#1001)",
        "semantics": ("CONFIRMATORY — one shot; CONFIRMED authorizes ONLY a "
                      "design PR (§5); nothing here changes production"),
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": round(time.time() - t_start, 1),
        "conditional": conditional,
        "frozen_geometry_measured": measured_geometry,
        "corpus": {
            "primary": {"start": PRIMARY_START, "end": PRIMARY_END,
                        "n_td": len(corpus), "n_weekly": int(len(prim_weekly)),
                        "n_blocks": n_blocks_prim},
            "secondary": {"start": PRIMARY_START,
                          "end": str(sec_index[-1].date()),
                          "n_td": int(len(sec_index)),
                          "n_weekly": int(len(weekly)),
                          "n_blocks": n_blocks_sec},
        },
        "frozen_rule": {
            "fixed_on_threshold": FIXED_ON_THRESHOLD,
            "vol_window_td": VOL_WINDOW,
            "expanding_warmup_obs": EXPANDING_WARMUP_OBS,
            "block_td": BLOCK_TD,
            "eligible_min_on_days": ELIGIBLE_MIN_ON_DAYS,
            "sample_step": SAMPLE_STEP,
            "dgtw_min_cell": DGTW_MIN_CELL,
            "winsor_clip": WINSOR_CLIP,
            "nw_lag": NW_LAG,
            "one_sided_alpha": ONE_SIDED_ALPHA,
            "bootstrap": {"resamples": BOOT_RESAMPLES,
                          "expected_block_length": BOOT_EXPECTED_BLOCK,
                          "seed": BOOT_SEED},
            "p2_block_t_min": P2_BLOCK_T_MIN,
            "min_on_eligible_blocks": MIN_ON_ELIGIBLE_BLOCKS,
            "min_ess": MIN_ESS,
            "embargo_trading_days": EMBARGO_TDAYS,
            "n_refits": EXPECTED_REFITS,
            "objective": PRODUCTION_OBJECTIVE,
        },
        "params": params,
        "sentiment_gate_replay": gate_meta,
        "pins": {
            "runner_identity": main_identity,
            "xgboost_version": str(xgb.__version__),
            "served_artifact": str(SERVED_ARTIFACT),
            "served_artifact_sha256": _sha256(SERVED_ARTIFACT),
            "served_config_fingerprint": art["config_fingerprint"],
            "panel_parquet": str(PANEL_PARQUET),
            "panel_parquet_sha256": panel_digest,
            "trainer_script_sha256": _sha256(TRAINER_SCRIPT),
            "spy_1d_sha256": readers.read_digests()["ohlcv/SPY/1d.parquet"],
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    print("\n===== VERDICT (prereg §5, frozen decision rule) =====")
    print(f"  {verdict}: {consequence}")
    print(f"  positive control: mean={positive_control_mean:+.5f} "
          f"({'PASS' if positive_control_pass else 'FAIL'})")
    if positive_control_pass:
        print(f"  P1: NW t={p1['nw']['t']:+.3f} (crit {p1['nw']['t_crit_one_sided_95']:.3f}) "
              f"boot q05={p1['bootstrap']['q05']:+.5f} "
              f"wins mean={p1['winsorized_on_mean']:+.5f} "
              f"disagreement={p1['disagreement']} -> "
              f"{'PASS' if p1['p1_pass'] else 'FAIL'}")
        diff_s = ("n/a" if p2["mean_diff"] is None
                  else f"{p2['mean_diff']:+.5f}")
        bt_s = ("n/a" if p2["block_t"] is None
                else f"{p2['block_t']:+.3f}")
        print(f"  P2: diff={diff_s} block_t={bt_s} n={p2['n_blocks']} "
              f"-> {'PASS' if p2['passes'] else 'FAIL'}")
        print(f"  guards: N_eligible={len(on_vals)} rho1={rho1:+.3f} ess={ess:.2f} "
              f"measurable={measurable}")
    print(f"\nwrote {OUT_JSON.name}, {OUT_SERIES.name}, {OUT_BLOCKS.name}, "
          f"{OUT_LEDGER.name} ({out['runtime_sec']}s)")


if __name__ == "__main__":
    main()
