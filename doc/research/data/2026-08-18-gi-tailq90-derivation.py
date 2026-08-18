#!/usr/bin/env python
"""G-I candidate `tail_q90_60d` — the ONE authorized screen run (frozen runner).

Governing contract: doc/research/2026-08-18-gi-tailq90-screen-spec.md
(orch#994, MERGED). This script is the execution-contract runner required by
that spec's §6: committed AND REVIEWED before the run — the
freeze-then-review-then-run sequencing. THIS PR ships the runner un-run; the
single run happens only after the runner PR merges (T2 enforces exactly that:
the runner refuses to execute unless its bytes match origin/main).

The screen TRIAGES (FLAGGED / NOT FLAGGED); it neither kills nor admits
(spec §4: survivorship direction UNKNOWN — a formal kill additionally requires
a point-in-time-universe rerun; admission always needs the full #984 §5b
confirmatory path). ONE execution on this corpus — re-running with different
parameters after seeing results is FORBIDDEN (T1).

Candidate (spec §2, everything verbatim from the served production artifact
`artifacts/prod/panel-ltr.alpha158_fund.json`, config fingerprint
sha256:f8fb2259b2bf1537, EXACTLY ONE delta):
    objective: rank:pairwise -> reg:quantileerror, quantile_alpha 0.90.
Features (172 cols + per-col norm kinds), label (fwd_60d_excess), params
(eta/max_depth/min_child_weight/subsample/colsample_bytree/seed/verbosity),
and boosting rounds (best_iter=100) are pinned by the artifact and asserted.

PIT calendar (spec §3): 31 quarterly refit cutoffs (last trading day of each
quarter, 2018-Q2..2025-Q4), expanding train window from 2016-01-04, rows with
realized labels only; at scoring date d use the NEWEST refit whose cutoff C
satisfies C + 60 trading days <= d — asserted per date, no gap-filling.

Estimand + triage rule (spec §4 — REVISED under codex review 2026-08-18,
h=60 PRIMARY): paired-cross-section weekly Spearman IC of the RAW score vs
h-day forward excess over SPY; placebo = same scores lagged 2h trading days;
Delta = mean(genuine) - mean(placebo). NOT FLAGGED iff Delta>0 AND
block-t >= 1.0 over the 29 non-overlapping 60d blocks AND >50% of
blocks-with-data positive, AT h=60 — else FLAGGED. h=20 (89 blocks) is
informational and decisive in neither direction. The paired-cross-section /
block-t / placebo machinery is REUSED from the merged corrected runner
doc/research/data/2026-08-17-gi-moe-screen-derivation.py (the #990 pairing
correction): the pure functions are copied VERBATIM and a committed test
(tests/test_tailq90_runner.py) enforces byte-identity against that file, so
the reuse cannot silently drift into a rewrite.

FROZEN RUNNER GUARDS (spec §6 — written down here, before the run):

T1  One-shot marker: the runner REFUSES to run if any of its output files
    already exist. No silent re-runs; outputs land ONLY next to this script
    (doc/research/data/) at run time. THIS PR emits none of them.
T2  Byte-identity vs main at execution: the executing file's bytes must equal
    origin/main's copy (git show). Not yet merged -> fail closed -> the
    freeze-then-review-then-run order is mechanically enforced.
T3  xgboost reg:quantileerror support is HARD-asserted by a behavioral probe
    (a 1-round micro-fit), not a version-string parse. Fail closed otherwise.
T4  Served-artifact identity: config_fingerprint == sha256:f8fb2259b2bf1537,
    kind == panel_ltr_xgboost, label_col == fwd_60d_excess, lookahead 60,
    172 feature_cols, 172 feature_norm_kind entries, best_iter == 100.
T5  Single-delta params: the training params dict equals the artifact's dict
    VERBATIM except objective -> reg:quantileerror plus quantile_alpha=0.90.
    Asserted key-by-key; any other difference fails closed.
T6  Refit calendar: exactly 31 cutoffs, each the last trading day (SPY
    calendar) of its quarter, 2018-Q2..2025-Q4, strictly increasing.
T7  Embargo per scoring date: the chosen refit is the NEWEST with
    C + 60 trading days <= d, asserted per date (both conditions). Every
    CORPUS grid date must be scoreable; only pre-corpus placebo-lag dates may
    lack an admissible refit — those are dropped WITH a counted reason and
    the count is asserted equal to its deterministic calendar expectation.
T8  Training window per refit: expanding from 2016-01-04; rows with realized
    labels only — the max train-row date t must satisfy t + 60 trading days
    <= C on the SPY calendar, asserted per refit. No exceptions.
T9  Production-preprocessing parity ("everything else verbatim"): the panel
    frame, panel-space feature transform, per-cutoff fund robust-z recompute,
    and the sentiment trained_zeroing gate are executed via the production
    trainer's OWN helpers (scripts/train_production_model.py, imported
    read-only) — not re-implemented. The recomputed per-col norm kinds are
    asserted equal to the artifact's feature_norm_kind, and the replayed
    sentiment gate contract (feature cols + disabled regimes) is asserted
    equal to the artifact's stored contract — config drift fails closed.
T10 Corpus (verbatim #987/moe G1/G2): SPY-calendar weekly grid
    2019-01-14..2026-03-02 step 5, |n - 358| <= 1 asserted and reported;
    universe = the golden-config watchlist, n == 145 asserted (names absent
    from the panel are RECORDED, never silently dropped);
    NAMES_PER_DATE_FLOOR == 50.
T11 Paired cross-section (verbatim moe G7, the #990 correction): both legs
    on ONE shared cross-section; ticker identity asserted, not trusted;
    per-leg counts kept as telemetry; every dropped date counted with reason.
T12 Blocks (verbatim moe G9/G10): exactly 89 complete blocks at h=20 and 29
    at h=60 asserted; block-t over blocks-with-data; a strict-majority
    minimum-blocks floor per horizon (15 of 29 at h=60, 45 of 89 at h=20) —
    below it the verdict is FLAGGED with reason insufficient_blocks
    (fail-closed), never computed on a sliver.
T13 Verdict at h == 60 ONLY (spec §4 REVISED): NOT FLAGGED iff Delta > 0 AND
    block-t >= 1.0 AND >50% of blocks-with-data positive. h=20 carries NO
    verdict field — a horizon the model was not trained for can neither flag
    nor rescue it.
T14 rho section (spec §5, informational, |rho|<0.7 roster gate applied at
    prereg, not here): tail_q90_60d vs mom_slow_12m / mom_fast via the
    momentum machinery on common dates (>=50 common names per date), and vs
    the DECLARED core reference — a same-recipe rank:pairwise refit at the
    SAME frozen cutoffs, trained purely as the rho reference (spec §5: the
    #992 named gap makes core-score history unreachable without heavy
    compute). Its scores are used for rho ONLY, never screened.
T15 Emitter-independence (spec §6): this family touches no
    renquant_model_factors code — asserted (module absent from sys.modules)
    after all imports and again before writing outputs.

Deterministic by construction: fixed seed (the artifact's), fixed calendar,
no early stopping, no hyperparameter search, stable row ordering before the
DMatrix build (production's np.argsort default is an unstable quicksort; row
order within a date is loss-invariant but feeds the subsample RNG, so the
runner pins kind="stable" for byte-reproducibility). Wall-clock stamps land
in metadata only. All inputs are read-only local stores whose sha256 digests
are recorded; the runner chdir()s into the umbrella ONLY because the
production helpers read data/ paths relative to it — it writes nothing there.

Usage:  python 2026-08-18-gi-tailq90-derivation.py
Env:    RQ_UMBRELLA_ROOT / RQ_MODEL_SRC / RQ_STRAT104_ROOT override the
        default local checkout paths (read-only inputs, same contract).
Output: results JSON + IC-series CSV + refit-ledger JSON next to this script.
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
from scipy.stats import spearmanr

# ---------------------------------------------------------------- frozen IO
HERE = Path(__file__).resolve().parent
UMBRELLA = Path(os.environ.get("RQ_UMBRELLA_ROOT", "/Users/renhao/git/github/RenQuant"))
MODEL_SRC = Path(os.environ.get("RQ_MODEL_SRC", "/Users/renhao/git/github/renquant-model/src"))
STRAT104 = Path(os.environ.get("RQ_STRAT104_ROOT", "/Users/renhao/git/github/renquant-strategy-104"))

OHLCV = UMBRELLA / "data" / "ohlcv"
SECTORS = UMBRELLA / "data" / "ticker_sectors.json"
PANEL_PARQUET = UMBRELLA / "data" / "alpha158_291_fundamental_dataset.parquet"
SERVED_ARTIFACT = (UMBRELLA / "backtesting" / "renquant_104" / "artifacts"
                   / "prod" / "panel-ltr.alpha158_fund.json")
TRAINER_SCRIPT = UMBRELLA / "scripts" / "train_production_model.py"
WATCHLIST_CFG = STRAT104 / "configs" / "strategy_config.golden.json"

OUT_JSON = HERE / "2026-08-18-gi-tailq90-screen-results.json"
OUT_CSV = HERE / "2026-08-18-gi-tailq90-ic-series.csv"
OUT_LEDGER = HERE / "2026-08-18-gi-tailq90-refit-ledger.json"
OUTPUTS = (OUT_JSON, OUT_CSV, OUT_LEDGER)

MOE_RUNNER = HERE / "2026-08-17-gi-moe-screen-derivation.py"

# ---------------------------------------------------------- frozen constants
# Corpus / estimand block — verbatim #987 with the #990 pairing correction
# (same names and values as the moe runner; the byte-identity test relies on
# these globals resolving identically).
CORPUS_START = "2019-01-14"          # spec §4 / #987 §2
CORPUS_END = "2026-03-02"            # spec §4 / #987 §2
SAMPLE_STEP = 5                      # every 5th trading day
HORIZONS = (20, 60)                  # h=60 primary, h=20 informational (§4)
PRIMARY_H = 60                       # spec §4 REVISED: the trained horizon
PLACEBO_LAG_MULT = 2                 # placebo lag = 2h trading days
NAMES_PER_DATE_FLOOR = 50            # frozen floor (#987 §2)
BLOCK_T_MIN = 1.0                    # spec §4 criterion 2
POS_BLOCK_FRAC_MIN = 0.5             # spec §4 criterion 3 (strictly greater)
EXPECTED_BLOCKS = {20: 89, 60: 29}   # asserted exactly (T12)
MIN_BLOCKS_WITH_DATA = {60: 15, 20: 45}  # strict majority per horizon (T12)
EXPECTED_WEEKLY_N = 358              # #987 §2 derived count (|n-358|<=1)
WATCHLIST_N = 145                    # the 145-name live universe (T10)

# Candidate block — spec §2/§3
CANDIDATE = "tail_q90_60d"
RHO_REFERENCE = "core_rank_ref"      # spec §5: rho ONLY, never screened
FROZEN_CONFIG_FINGERPRINT = "sha256:f8fb2259b2bf1537"
N_FEATURES = 172
LABEL = "fwd_60d_excess"
LABEL_HORIZON_TDAYS = 60             # training-label horizon (trading days)
EMBARGO_TDAYS = 60                   # C + 60 trading days <= d (spec §3)
QUANTILE_ALPHA = 0.90
EXPECTED_BEST_ITER = 100             # the artifact's boosting rounds
TRAIN_DATA_START = "2016-01-04"      # spec §3 data start
REFIT_FIRST_QUARTER = (2018, 2)      # 2018-Q2
REFIT_LAST_QUARTER = (2025, 4)       # 2025-Q4
EXPECTED_REFITS = 31

# Late-bound at run time (main): renquant_model_common total-return helper.
# Module-level placeholder keeps the verbatim MomReaders copy import-light for
# the unit tests (which never execute the rho section).
total_return_close = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"FROZEN-GUARD FAILURE — STOP, do not adjust the spec: {msg}")


# ------------------------------------------------------- pure frozen helpers
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


def single_delta_params(artifact_params: dict) -> dict:
    """T5: the frozen single-delta construction (spec §2). The returned dict
    equals the artifact's params VERBATIM except objective ->
    reg:quantileerror plus quantile_alpha — asserted key-by-key."""
    _assert(isinstance(artifact_params, dict) and len(artifact_params) > 0,
            "artifact params dict missing or empty")
    _assert(artifact_params.get("objective") == "rank:pairwise",
            f"artifact objective is {artifact_params.get('objective')!r}, "
            "expected rank:pairwise — wrong base artifact")
    _assert("quantile_alpha" not in artifact_params,
            "artifact params already carry quantile_alpha — single-delta undefined")
    _assert("seed" in artifact_params, "artifact params carry no seed — determinism unpinned")
    out = dict(artifact_params)
    out["objective"] = "reg:quantileerror"
    out["quantile_alpha"] = QUANTILE_ALPHA
    for k, v in artifact_params.items():
        if k != "objective":
            _assert(out[k] == v, f"param {k!r} drifted from the artifact value")
    _assert(set(out) == set(artifact_params) | {"quantile_alpha"},
            "single-delta params introduced or dropped keys beyond the declared delta")
    return out


def triage_verdict(delta: float, block_t: float, pos_frac: float,
                   n_blocks_with_data: int, min_blocks: int) -> tuple[str, str]:
    """T12/T13: the frozen triage rule (spec §4). Fail-closed on thin blocks."""
    if n_blocks_with_data < min_blocks:
        return "FLAGGED", "insufficient_blocks"
    ok = (delta > 0 and block_t >= BLOCK_T_MIN and pos_frac > POS_BLOCK_FRAC_MIN)
    if ok:
        return "NOT FLAGGED", "all three criteria met"
    why = "; ".join(c for c, bad in [
        (f"delta={delta:+.5f} <= 0", not delta > 0),
        (f"block_t={block_t:.3f} < {BLOCK_T_MIN}", not block_t >= BLOCK_T_MIN),
        (f"pos_block_frac={pos_frac:.3f} <= {POS_BLOCK_FRAC_MIN}",
         not pos_frac > POS_BLOCK_FRAC_MIN)] if bad)
    return "FLAGGED", why


# --------------------------------------------------------------------------
# REUSED MACHINERY — copied VERBATIM from the merged corrected runner
# doc/research/data/2026-08-17-gi-moe-screen-derivation.py (orch#987 spec,
# #990 pairing correction). tests/test_tailq90_runner.py enforces
# byte-identity of these definitions against that file — reuse, not rewrite.
# --------------------------------------------------------------------------
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


# ----------------------------------------------------------------- readers
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


# ---------------------------------------------------------------- run guards
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


def assert_quantileerror_support() -> str:
    """T3: behavioral probe — a 1-round reg:quantileerror micro-fit must
    succeed on the installed xgboost. Fail closed otherwise."""
    import xgboost as xgb  # noqa: PLC0415
    X = np.arange(40, dtype=float).reshape(20, 2)
    y = np.arange(20, dtype=float)
    try:
        xgb.train({"objective": "reg:quantileerror",
                   "quantile_alpha": QUANTILE_ALPHA, "seed": 0, "verbosity": 0},
                  xgb.DMatrix(X, label=y), num_boost_round=1)
    except Exception as exc:  # noqa: BLE001 — any failure means unsupported
        raise AssertionError(
            "FROZEN-GUARD FAILURE — STOP: installed xgboost "
            f"{xgb.__version__} cannot train reg:quantileerror: {exc}") from exc
    return str(xgb.__version__)


def assert_emitter_independence() -> None:
    """T15: this family touches no renquant_model_factors code."""
    offenders = [m for m in sys.modules if "renquant_model_factors" in m]
    _assert(not offenders,
            f"emitter code imported — emitter-independence violated: {offenders}")


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


# ----------------------------------------------------------------------- main
def main() -> None:
    t_start = time.time()
    assert_one_shot()
    main_identity = assert_runner_matches_main()
    xgb_version = assert_quantileerror_support()
    import xgboost as xgb  # noqa: PLC0415 — post-probe

    # The production helpers read data/ paths relative to the umbrella root;
    # the runner reads there and writes ONLY next to itself (absolute paths).
    os.chdir(UMBRELLA)

    if str(MODEL_SRC) not in sys.path:
        sys.path.insert(0, str(MODEL_SRC))
    from renquant_model_momentum.train import (  # noqa: PLC0415
        params_v0 as mom_params_v0, params_v1_fast as mom_params_v1_fast,
        train_momentum_artifact)
    global total_return_close
    from renquant_model_common.total_return import (  # noqa: PLC0415
        total_return_close as _trc)
    total_return_close = _trc

    tpm = load_trainer_module()
    assert_emitter_independence()

    art = load_served_artifact()
    feat_cols = [str(c) for c in art["feature_cols"]]
    params_q90 = single_delta_params(art["params"])
    params_rho_ref = dict(art["params"])  # VERBATIM, no delta — rho ONLY (T14)
    n_rounds = int(art["best_iter"])

    wl_raw = json.loads(WATCHLIST_CFG.read_text())
    universe = sorted(dict.fromkeys(str(t) for t in wl_raw["watchlist"]))
    _assert(len(universe) == WATCHLIST_N,
            f"watchlist n={len(universe)} != frozen {WATCHLIST_N}")

    readers = ReadersLite()
    spy_close = readers.market_close()
    g = build_grid(spy_close.index)
    cal, grid, n_grid, i0 = g["cal"], g["grid"], g["n"], g["i0"]

    refit_cutoffs = build_refit_calendar(cal)
    cutoff_pos = [int(cal.get_loc(c)) for c in refit_cutoffs]
    first_scoreable_pos = cutoff_pos[0] + EMBARGO_TDAYS

    # ---- panel (read-only; the production training frame) -----------------
    print(f"[1/6] loading panel {PANEL_PARQUET.name} ...", flush=True)
    panel_digest = _sha256(PANEL_PARQUET)
    panel = pd.read_parquet(PANEL_PARQUET)
    panel["date"] = pd.to_datetime(panel["date"])
    _assert(LABEL in panel.columns, "panel lacks the fwd_60d_excess label")
    _assert(all(c in panel.columns for c in feat_cols),
            "panel lacks artifact feature columns")
    # Cross-check: the production feat-col derivation over THIS panel must
    # reproduce the artifact's 172 columns exactly (T9).
    excl = {"ticker", "date", "split_label",
            "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess"}
    derived = [c for c in panel.columns
               if c not in excl and c not in set(tpm.TRACK_B_FEATURES)]
    _assert(set(derived) == set(feat_cols),
            "production feat-col derivation != artifact feature_cols")

    panel = panel[panel["ticker"].isin(universe)].copy()
    absent_from_panel = sorted(set(universe) - set(panel["ticker"].unique()))
    _assert(len(panel) > 0, "panel empty after watchlist filter")
    _assert(str(panel["date"].min().date()) == TRAIN_DATA_START,
            f"panel data start {panel['date'].min().date()} != frozen {TRAIN_DATA_START}")
    _assert(not panel.duplicated(["date", "ticker"]).any(),
            "duplicate (date, ticker) rows in the panel")
    panel_dates = pd.DatetimeIndex(sorted(panel["date"].unique()))
    _assert(panel_dates.isin(cal).all(),
            "panel dates off the SPY trading calendar")
    _assert(grid.isin(panel_dates).all(),
            "corpus grid dates missing from the panel — features unavailable")

    # ---- sentiment trained_zeroing replay (T9, production helpers) --------
    print("[2/6] sentiment trained_zeroing replay (production regime chain) ...",
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

    # ---- 31 refits: candidate + rho reference (T5/T6/T8/T9) ---------------
    print(f"[3/6] {EXPECTED_REFITS} expanding refits x 2 objectives ...", flush=True)
    boosters_q90, boosters_ref, norms, ledger = [], [], [], []
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
        b_q90, dig_q90 = fit_booster(xgb, tpm, tr, feat_cols, mu, sd, kinds,
                                     params_q90, n_rounds)
        b_ref, dig_ref = fit_booster(xgb, tpm, tr, feat_cols, mu, sd, kinds,
                                     params_rho_ref, n_rounds)
        boosters_q90.append(b_q90)
        boosters_ref.append(b_ref)
        norms.append((mu, sd, kinds))
        ledger.append({
            "refit_index": i,
            "cutoff": str(cutoff.date()),
            "first_scoreable_date": str(cal[cpos + EMBARGO_TDAYS].date())
                if cpos + EMBARGO_TDAYS < len(cal) else None,
            "n_train_rows": int(len(tr)),
            "n_train_dates": int(tr["date"].nunique()),
            "train_min_date": str(tr["date"].min().date()),
            "train_max_date": str(tr["date"].max().date()),
            "booster_sha256_tail_q90_60d": dig_q90,
            "booster_sha256_core_rank_ref": dig_ref,
            "fit_seconds": round(time.time() - t0, 1),
        })
        print(f"    {cutoff.date()}: rows={len(tr):>7d} "
              f"max_train={tr['date'].max().date()} "
              f"({ledger[-1]['fit_seconds']}s)", flush=True)

    # ---- scores on the extended grid (T7) ---------------------------------
    print("[4/6] scoring the extended weekly grid ...", flush=True)
    scores_q90: dict[pd.Timestamp, pd.Series] = {}
    scores_ref: dict[pd.Timestamp, pd.Series] = {}
    refit_used: dict[str, str] = {}
    n_unscoreable = 0
    for d in g["ext_dates"]:
        dpos = int(cal.get_loc(d))
        ri = refit_index_for_date(cutoff_pos, dpos)
        if ri is None:
            _assert(d < grid[0],
                    f"corpus grid date {d.date()} has no admissible refit")
            n_unscoreable += 1
            continue
        _assert(cutoff_pos[ri] + EMBARGO_TDAYS <= dpos,
                f"embargo violated at {d.date()}")
        if ri + 1 < len(cutoff_pos):
            _assert(cutoff_pos[ri + 1] + EMBARGO_TDAYS > dpos,
                    f"not the newest admissible refit at {d.date()}")
        frame = by_date.get(d)
        if frame is None or frame.empty:
            scores_q90[d] = pd.Series(dtype=float)
            scores_ref[d] = pd.Series(dtype=float)
            continue
        mu, sd, kinds = norms[ri]
        scores_q90[d] = score_frame(xgb, tpm, boosters_q90[ri], frame,
                                    feat_cols, mu, sd, kinds)
        scores_ref[d] = score_frame(xgb, tpm, boosters_ref[ri], frame,
                                    feat_cols, mu, sd, kinds)
        refit_used[str(d.date())] = str(refit_cutoffs[ri].date())
    expected_unscoreable = sum(
        1 for d in g["ext_dates"] if int(cal.get_loc(d)) < first_scoreable_pos)
    _assert(n_unscoreable == expected_unscoreable,
            f"unscoreable ext dates {n_unscoreable} != deterministic "
            f"expectation {expected_unscoreable}")
    _assert(all(d in scores_q90 for d in grid),
            "a corpus grid date was left unscored")

    # ---- labels: forward h-day excess over SPY (moe G5, raw close) --------
    print("[5/6] labels + paired IC series + frozen triage rule ...", flush=True)
    closes = close_panel(readers, universe, cal)
    spy_on_cal = spy_close.reindex(cal)
    labels: dict[int, dict[pd.Timestamp, pd.Series]] = {}
    for h in HORIZONS:
        fwd = closes.shift(-h) / closes - 1.0
        spy_fwd = spy_on_cal.shift(-h) / spy_on_cal - 1.0
        ex = fwd.sub(spy_fwd, axis=0)
        labels[h] = {d: ex.loc[d].dropna() for d in grid}

    # ---- IC series, blocks, verdict (moe [3/4] machinery; T11/T12/T13) ----
    rows = []
    horizons_out: dict[str, dict] = {}
    for h in HORIZONS:
        _assert(PLACEBO_LAG_MULT * h % SAMPLE_STEP == 0,
                "placebo lag not aligned to the sampling step")
        blocks_per = h // SAMPLE_STEP  # 4 at h=20, 12 at h=60
        n_complete = n_grid // blocks_per
        over = EXPECTED_BLOCKS[h]
        _assert(n_complete >= over, f"fewer than {over} complete blocks at h={h}")
        n_complete = over  # frozen count: exactly the spec's blocks (G9)

        dropped = {"floor_paired": 0, "degenerate": 0, "no_refit_placebo": 0}
        series = []
        for k, d in enumerate(grid):
            lab = labels[h][d]
            gen_s = scores_q90[d]
            lag_pos = i0 + SAMPLE_STEP * k - PLACEBO_LAG_MULT * h
            lag_date = cal[lag_pos]
            pla_s = scores_q90.get(lag_date)
            block = k // blocks_per
            complete = block < n_complete
            if pla_s is None:
                # T7: placebo score date precedes the first admissible refit.
                _assert(lag_pos < first_scoreable_pos,
                        f"missing placebo scores at {lag_date.date()} despite "
                        "an admissible refit")
                dropped["no_refit_placebo"] += 1
                rows.append({"candidate": CANDIDATE, "h": h,
                             "date": str(d.date()), "obs_index": k,
                             "block": block, "block_complete": complete,
                             "kept": False, "drop_reason": "no_refit_placebo",
                             "placebo_score_date": str(lag_date.date()),
                             "n_pairs_shared": 0,
                             "n_pairs_genuine_leg_only": 0,
                             "n_pairs_placebo_leg_only": 0,
                             "coverage_gap_genuine_minus_placebo": 0,
                             "ic_genuine": float("nan"),
                             "ic_placebo": float("nan")})
                continue
            # G7 (corrected, codex on orch#990): ONE shared cross-section
            # for both legs; per-leg counts kept as telemetry because their
            # DIFFERENCE is the confound the correction removes.
            ic_g, ic_p, n_pair, pair_names = paired_spearman_ic(gen_s, pla_s, lab)
            _, n_g = spearman_ic(gen_s, lab)
            _, n_p = spearman_ic(pla_s, lab)
            keep, reason = True, ""
            if n_pair < NAMES_PER_DATE_FLOOR:
                keep, reason = False, "floor_paired"
            elif not (np.isfinite(ic_g) and np.isfinite(ic_p)):
                keep, reason = False, "degenerate"
            if not keep:
                dropped[reason] += 1
            else:
                series.append((k, d, ic_g, ic_p, block, complete, pair_names))
            rows.append({"candidate": CANDIDATE, "h": h, "date": str(d.date()),
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
        # T7: the placebo-gap drop count is deterministic from the calendar.
        expected_gap = sum(
            1 for k in range(n_grid)
            if i0 + SAMPLE_STEP * k - PLACEBO_LAG_MULT * h < first_scoreable_pos)
        _assert(dropped["no_refit_placebo"] == expected_gap,
                f"h={h}: no_refit_placebo drops {dropped['no_refit_placebo']} "
                f"!= deterministic expectation {expected_gap}")

        gen = np.array([s[2] for s in series])
        pla = np.array([s[3] for s in series])
        # G7 (corrected): assert IDENTITY, not just cardinality (see moe).
        _assert(len(gen) == len(pla), "genuine/placebo date sets differ")
        for _k, _d, _ig, _ip, _b, _c, _names in series:
            _assert(len(_names) >= NAMES_PER_DATE_FLOOR,
                    f"kept date {_d.date()} below the paired floor")
            _assert(len(set(_names)) == len(_names),
                    f"duplicate tickers in the paired set at {_d.date()}")
        delta = float(gen.mean() - pla.mean()) if len(gen) else float("nan")

        block_vals: dict[int, list[float]] = {}
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
            "role": "PRIMARY (decisive)" if h == PRIMARY_H
                    else "informational (never decisive, spec §4)",
        }
        if h == PRIMARY_H:
            verdict, why = triage_verdict(delta, bt, pos_frac, n_bd,
                                          MIN_BLOCKS_WITH_DATA[h])
            hres["verdict"] = verdict
            hres["verdict_reason"] = why
        horizons_out[str(h)] = hres

    # ---- rho section (T14, informational) ---------------------------------
    print("[6/6] rho section: momentum lanes + core rank reference ...", flush=True)
    mom_readers = MomReaders(readers)
    mom_params = {"mom_slow_12m": mom_params_v0(), "mom_fast": mom_params_v1_fast()}
    mom_scores: dict[str, dict[pd.Timestamp, pd.Series]] = {
        "mom_slow_12m": {}, "mom_fast": {}}
    for d in grid:
        for ref, prm in mom_params.items():
            art_m = train_momentum_artifact(d, universe, prm, readers=mom_readers)
            s = pd.Series(art_m["scores"], dtype=float)
            mom_scores[ref][d] = s[np.isfinite(s)]

    def _mean_rho(a_by_date: dict, b_by_date: dict) -> dict:
        # moe G12 aggregation: per-date Spearman over >=50 common finite
        # names; unweighted mean over qualifying dates (n_dates + sd reported).
        per_date = []
        for d in grid:
            a, b = a_by_date.get(d), b_by_date.get(d)
            if a is None or b is None:
                continue
            both = pd.concat([a, b], axis=1, join="inner").dropna()
            if len(both) >= NAMES_PER_DATE_FLOOR:
                r = spearmanr(both.iloc[:, 0], both.iloc[:, 1]).statistic
                if np.isfinite(r):
                    per_date.append(float(r))
        arr = np.array(per_date)
        return {"mean_rho": float(arr.mean()) if len(arr) else None,
                "sd_rho": float(arr.std(ddof=1)) if len(arr) > 1 else None,
                "n_dates": len(arr)}

    rho_matrix = {CANDIDATE: {
        "mom_slow_12m": _mean_rho(scores_q90, mom_scores["mom_slow_12m"]),
        "mom_fast": _mean_rho(scores_q90, mom_scores["mom_fast"]),
        RHO_REFERENCE: {
            **_mean_rho(scores_q90, scores_ref),
            "note": ("same-recipe rank:pairwise refit at the SAME frozen "
                     "cutoffs, trained purely as the spec §5 rho reference "
                     "(core-score history unreachable — the #992 named gap); "
                     "scores used for rho ONLY, never screened"),
        },
    }}

    # ---- outputs (T1: only next to this script) ---------------------------
    assert_emitter_independence()
    csv_df = pd.DataFrame(rows)
    csv_df.to_csv(OUT_CSV, index=False)
    OUT_LEDGER.write_text(json.dumps({
        "spec": "doc/research/2026-08-18-gi-tailq90-screen-spec.md (orch#994)",
        "refits": ledger,
        "refit_used_by_score_date": refit_used,
        "n_unscoreable_ext_dates": n_unscoreable,
    }, indent=2, sort_keys=True) + "\n")

    out = {
        "spec": "doc/research/2026-08-18-gi-tailq90-screen-spec.md (orch#994)",
        "semantics": ("TRIAGE — FLAGGED / NOT FLAGGED; neither kill nor admit "
                      "(spec §4: kill needs a PIT-universe rerun; admission "
                      "needs the #984 §5b confirmatory path)"),
        "candidate": CANDIDATE,
        "verdict_primary_h60": horizons_out[str(PRIMARY_H)].get("verdict"),
        "verdict_reason": horizons_out[str(PRIMARY_H)].get("verdict_reason"),
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": round(time.time() - t_start, 1),
        "pins": {
            "runner_identity": main_identity,
            "xgboost_version": xgb_version,
            "served_artifact": str(SERVED_ARTIFACT),
            "served_artifact_sha256": _sha256(SERVED_ARTIFACT),
            "served_config_fingerprint": art["config_fingerprint"],
            "panel_parquet": str(PANEL_PARQUET),
            "panel_parquet_sha256": panel_digest,
            "trainer_script_sha256": _sha256(TRAINER_SCRIPT),
            "watchlist_config": str(WATCHLIST_CFG),
            "watchlist_sha256": _sha256(WATCHLIST_CFG),
            "watchlist_n": len(universe),
            "watchlist_absent_from_panel": absent_from_panel,
            "renquant_model_head": subprocess.run(
                ["git", "-C", str(MODEL_SRC.parent), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True).stdout.strip(),
            "spy_1d_sha256": readers.read_digests()["ohlcv/SPY/1d.parquet"],
            "ohlcv_digest_of_digests": hashlib.sha256(json.dumps(
                {k: v for k, v in sorted(readers.read_digests().items())
                 if k.startswith("ohlcv/")}, sort_keys=True).encode()).hexdigest(),
        },
        "corpus": {
            "start": CORPUS_START, "end": CORPUS_END,
            "sample_step": SAMPLE_STEP,
            "n_cross_sections": n_grid,
            "first_grid_date": str(grid[0].date()),
            "last_grid_date": str(grid[-1].date()),
        },
        "frozen_rule": {
            "horizon_primary": PRIMARY_H,
            "horizon_informational": 20,
            "names_per_date_floor": NAMES_PER_DATE_FLOOR,
            "placebo_lag_trading_days": {str(h): PLACEBO_LAG_MULT * h
                                         for h in HORIZONS},
            "block_t_min": BLOCK_T_MIN,
            "pos_block_frac_min_exclusive": POS_BLOCK_FRAC_MIN,
            "min_blocks_with_data": {str(h): MIN_BLOCKS_WITH_DATA[h]
                                     for h in HORIZONS},
            "expected_blocks": {str(h): EXPECTED_BLOCKS[h] for h in HORIZONS},
            "embargo_trading_days": EMBARGO_TDAYS,
            "n_refits": EXPECTED_REFITS,
            "quantile_alpha": QUANTILE_ALPHA,
        },
        "params": {CANDIDATE: params_q90, RHO_REFERENCE: params_rho_ref},
        "momentum_params": mom_params,
        "sentiment_gate_replay": gate_meta,
        "horizons": horizons_out,
        "rho_matrix": rho_matrix,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    r = horizons_out[str(PRIMARY_H)]
    print("\n===== VERDICT (h=60 PRIMARY, frozen triage rule — spec §4) =====")
    print(f"  {CANDIDATE}: delta={r['delta']:+.5f} block_t={r['block_t']:+.3f} "
          f"pos%={r['pos_block_frac']:.3f} kept={r['n_kept']}/{n_grid} "
          f"-> {r['verdict']} ({r['verdict_reason']})")
    r20 = horizons_out["20"]
    print(f"  [informational h=20] delta={r20['delta']:+.5f} "
          f"block_t={r20['block_t']:+.3f} pos%={r20['pos_block_frac']:.3f} "
          f"kept={r20['n_kept']}/{n_grid} (no verdict — spec §4)")
    print(f"\nwrote {OUT_JSON.name}, {OUT_CSV.name}, {OUT_LEDGER.name} "
          f"({out['runtime_sec']}s)")


if __name__ == "__main__":
    main()
