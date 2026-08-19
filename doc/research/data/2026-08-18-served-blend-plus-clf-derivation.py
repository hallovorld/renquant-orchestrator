#!/usr/bin/env python
"""Does the top-decile clf leg beat the SERVED blend? — paired backtest runner.

QUESTION (the one that gates deployment): on the SERVED construction, does
adding the top-decile classifier leg beat what production serves today?

STATUS / SEMANTICS. This is a BACKTEST, executed under the operator's
2026-08-18 policy ("用backtest代替所有数据积累" — backtests replace
evidence-accumulation waits). It is NOT a preregistered one-shot
confirmatory: no prereg document governs it, and the freeze-then-review-
then-run protocol of the vol-switch runner (its V2 byte-identity-vs-
origin/main guard) deliberately does NOT apply here, because the runner,
its outputs and its memo land in ONE PR. What IS frozen — written down
here, in code, before any number was read — is the estimand, the corpus,
the arms, the primary statistic and the decision bar (§ FROZEN STATISTIC).
Nothing here changes production; the output authorizes a decision
discussion, not a deploy.

ARMS (per-date cross-sectional z-sum, UNWEIGHTED — the served blend
contract, renquant-pipeline kernel/panel_pipeline/blend_scorer.py
`BlendPanelScorer.score`: z per leg over that leg's finite universe with
ddof=0, plain sum, NaN propagates so the composite scores the
INTERSECTION; no weights — weighting is the MoE stage's own change):

  A_prod   z(panel-xgb) + z(momentum_residual)          <- served TODAY
  B_3leg   z(panel-xgb) + z(momentum_residual) + z(clf) <- the candidate
  C_2leg   z(panel-xgb) + z(clf)                        <- model#76's arm
  D_solo   z(panel-xgb)                                 <- model#76's base

A_prod is EXACTLY today's served blend: the pinned production config
`renquant-strategy-104/configs/strategy_config.json`
(`ranking.panel_scoring.kind == "blend"`) carries components
[0] artifacts/prod/panel-ltr.alpha158_fund.json (fp sha256:f8fb2259b2bf1537)
[1] kind=momentum_residual, artifacts/momentum/momentum_artifact_ledger.jsonl
    (fp momentum-v0-fd65161a20b29314).
The clf leg is artifacts/shadow/panel-clf.top-decile.fwd60.json — today
shadow-only.

LEG RECONSTRUCTION (all three legs are refit/recomputed STRICTLY PIT):

 xgb  The production recipe VERBATIM — served artifact's 172 feature_cols,
      feature_norm_kind, params (rank:pairwise, seed pinned), best_iter
      100; quarterly expanding refits with the 60-trading-day embargo
      C + 60td <= d. Machinery copied VERBATIM from the reviewed
      vol-switch runner (2026-08-18-vol-switch-derivation.py, orch#1002/
      #1003), whose own lineage is the tail_q90 runner (#996/#999);
      tests/test_served_blend_clf_runner.py enforces byte-identity so the
      reuse cannot silently drift into a rewrite.

 clf  The shadow artifact's recipe VERBATIM — same 172 feature_cols and
      same feature_norm_kind as the prod artifact (asserted equal), params
      {objective binary:logistic, eta 0.05, max_depth 5, min_child_weight
      50, subsample 0.7, colsample_bytree 0.7, eval_metric logloss, seed
      42}, 100 rounds, label = per-date TOP-DECILE MEMBERSHIP of
      fwd_60d_excess (groupby(date).rank(pct=True) >= 0.9), no set_group.
      The construction mirrors renquant-model
      scripts/train_topdecile_clf_shadow.py (`top_decile_label`,
      `CLF_PARAMS`, `N_ROUNDS`) — which is itself the frozen construction
      model#76 certified. Refit on the SAME cutoff ladder and the SAME
      training frame as the xgb leg.

 mom  momentum_residual_v0, recomputed per scoring date by the OWNING
      library, `renquant_model_momentum.train_momentum_artifact` — pure
      over injected readers, no fitted state, no disk. Params
      `params_v0()` (window 252, skip 21, min_obs 200, min_features 3,
      min_side_obs 30) — the fingerprint the served config pins. Readers =
      the `MomReaders` copy from the reviewed tail_q90 runner (byte-
      identity enforced), over the read-only OHLCV store + the umbrella
      sector map. PIT by construction: the artifact's formation window is
      (d - 273bd, d - 21bd], so the newest bar that can touch a score is
      21 business days before the scoring date, and NO forward label ever
      enters it.

      COVERAGE FINDING (the question this runner was told to answer
      first): the momentum ARTIFACT LEDGER begins at genesis cutoff
      2026-08-02 and holds 3 rows — there is NO historical ledger. That is
      a fact about the SERVING surface, not about computability: the
      scorer is a deterministic function of OHLCV + a sector map, so the
      historical series is RECONSTRUCTIBLE and is reconstructed here.
      Nothing is fabricated and no ledger row is extrapolated.

CORPUS / ESTIMAND / INFERENCE — the vol-switch runner's, reused:
  corpus    PRIMARY 2017-01-03..2023-09-29, weekly (every 5th trading day)
            cross-sections over the production panel (292 tickers,
            survivor caveat DECLARED), 1,697 trading days, 340 weekly
            dates, 28 complete non-overlapping 60-trading-day blocks.
  estimand  per-date DGTW-adjusted top-decile spread at h=60 — label =
            the panel's own fwd_60d_excess (per-date z-scored fwd-60td
            excess vs SPY, SD units); per-date vol x mom x beta
            (STD60 x ROC60 x BETA60) terciles, 27 cells, self-excluded
            cell mean as benchmark, >=15/cell floor else flagged-
            unadjusted; spread = top-decile mean minus cross-section mean,
            N = round(n/10).
  PAIRING   ALL FOUR ARMS ARE SCORED ON ONE COMMON PER-DATE UNIVERSE — the
            intersection of every leg's finite scores with a finite label
            and finite DGTW characteristics. Same names, same adjusted
            labels, same benchmark cells; the ONLY thing that varies
            across arms is the ranking. This is what makes the per-date
            differences paired. The per-leg z is therefore taken over that
            common universe (the served scorer takes each leg's z over its
            own finite universe; for A and B those coincide, since the
            momentum leg is the binding one and the clf leg is finite
            wherever the xgb leg is — ASSERTED per date). The coverage
            cost of the momentum leg is recorded per date
            (`n_panel_usable` vs `n_common`), never hidden.

FROZEN STATISTIC (frozen here, before any number was read; no threshold
search, no alternative statistic is computed):
  PRIMARY   the PAIRED per-date difference B_3leg - A_prod, aggregated to
            the 28 complete non-overlapping 60-trading-day blocks (block
            outcome = mean of the per-date differences in that block).
            Inference on that block series: Newey-West (lag 1) SE with
            small-sample t (df = N-1), and the Politis-Romano stationary
            block bootstrap (E[block] = 2, 10,000 resamples, seed 0).
  BAR       INHERITED VERBATIM from the standing certification's frozen
            rule (model#75 §"Decision rule", the rule model#76 passed):
            **CI90 lower bound > 0**. It is not invented here and not
            tuned here. Mapping:
              BEATS               one-sided-95% (= CI90) lower bound > 0
                                  on BOTH inference legs
              NOT DISTINGUISHABLE point estimate > 0, CI includes 0
              WORSE               point estimate <= 0
            reported with an explicit DISAGREEMENT flag if the two
            inference legs split (conservative: a split is not a pass).
  GUARDS    n_blocks >= 15 AND realized ESS >= 6 on the block series
            (ESS = N(1-rho1)/(1+rho1), rho1 clipped below at 0) else
            UNMEASURABLE, fail-closed. Counted and printed BEFORE any
            verdict language is emitted.
  CONTROL   C_2leg - D_solo by the identical machinery — the arm pair
            model#76 certified at +0.0687/60d, CI90 [+0.0156, +0.1269].
            It is a DIRECTIONAL control, NOT a numeric identity check:
            model#76's harness differs (5 purged folds vs this expanding
            quarterly ladder; 10-seed averaged placebo-differenced "clean"
            spread vs this single-recipe DGTW spread; top-10 names vs
            top-decile; its own corpus). A sign/rough-magnitude agreement
            supports the harness; a numeric mismatch does NOT by itself
            impeach it, and this runner says so rather than claiming a
            positive control it cannot own.
  SUB-READ  the ON-state slice (SPY 20td realized vol > 0.135 — the fixed
            definition frozen in orch#1001 and CONFIRMED in orch#1003),
            reported because the vol-window lane is live. Reported, never
            decisive.

RUNNER GUARDS (fail-closed; a guard failure produces NO statistics):
 G1  One-shot marker: refuses to run if any output file already exists.
     Outputs land ONLY next to this script.
 G2  Served-artifact identity: prod config_fingerprint
     sha256:f8fb2259b2bf1537, kind panel_ltr_xgboost, label
     fwd_60d_excess, lookahead 60, 172 feature_cols + 172 norm kinds,
     best_iter 100; objective AT PRODUCTION (rank:pairwise) with a pinned
     seed, params taken from the artifact VERBATIM.
 G3  Clf-artifact identity: config_fingerprint pinned, kind
     panel_ltr_xgboost, label fwd_60d_excess, lookahead 60, best_iter 100,
     objective binary:logistic with a pinned seed, and
     metadata.classifier_label_spec == top_decile_membership /
     fwd_60d_excess / 0.9 — the label this runner reconstructs is read
     FROM the artifact's own spec, never assumed.
 G4  Leg-recipe parity: clf feature_cols and feature_norm_kind are
     EQUAL to the prod artifact's (asserted list-wise) — one normalization
     per cutoff serves both legs, so the arms differ by model, not by
     preprocessing.
 G5  Refit calendar: exactly 30 cutoffs, each the last trading day (SPY
     calendar) of its quarter, 2016-Q2..2023-Q3, strictly increasing.
 G6  Embargo per scoring date: the chosen refit is the NEWEST with
     C + 60td <= d, and it is the newest (the next cutoff violates it) —
     both asserted per date. Every grid date must be scoreable.
 G7  Training window per refit: expanding from 2016-01-04, realized labels
     only — max train-row date t satisfies t + 60td <= C, asserted.
 G8  Production-preprocessing parity: panel frame, panel-space transform,
     per-cutoff norm recompute and the sentiment trained_zeroing gate run
     through the production trainer's OWN helpers (read-only import);
     recomputed norm kinds == the artifact's feature_norm_kind, and the
     replayed sentiment-gate contract == the prod artifact's stored
     contract.
 G9  Frozen corpus geometry, tolerance EXACT (a mismatch is environment
     drift, not something to adjust): 1,697 corpus trading days, 340
     weekly dates, 28 complete blocks, 821 fixed-definition ON days.
     These are the numbers orch#1001 counted and orch#1003 re-measured.
 G10 Momentum PIT: the artifact's MEASURED effective_train_cutoff_date is
     strictly BEFORE the scoring date, and its formation window's upper
     bound is <= that cutoff — asserted per date. Its universe is resolved
     the production way (the panel tickers on the latest panel date <= d).
 G11 Estimand floor: every weekly cross-section carries >= 100 names in
     the COMMON universe (assert, not a filter).
 G12 Arm-universe identity: all four arms score exactly the same names on
     every date, and every leg is finite on all of them.
 G13 Zero writes outside doc/research/data/: outputs are absolute paths
     next to this script; the chdir into the umbrella exists ONLY because
     the production helpers read data/ paths relative to it.

DECLARED FIDELITY GAPS (stated because they cut against the candidate or
the reader's confidence, and a backtest that hides them is worthless):
 (a) SURVIVORSHIP. The panel is the 292-name survivor universe and the
     OHLCV store holds today's names; LEVELS are inflated for every arm.
     The paired contrast is the robust object, which is why it is the
     primary statistic.
 (b) SERVING FRESHNESS. Production publishes the momentum artifact WEEKLY
     and serves that cross-section until the next publish, so the served
     momentum leg is up to ~7 calendar days staler than what this runner
     computes at each weekly grid date. This makes the momentum leg here
     marginally FRESHER than served — it flatters A and B, i.e. it works
     against B-A only insofar as the two share the leg (they do), and it
     flatters A_prod's level. The 21-business-day input embargo dominates
     either way. No lookahead is introduced.
 (c) SENTIMENT GATE. The deployed clf shadow artifact carries no
     sentiment trained_zeroing stamp; this runner trains BOTH legs on the
     production-gated frame so the arms differ by model only. That is a
     deliberate parity choice and a declared deviation from the deployed
     clf artifact's own preprocessing.
 (d) SECTOR MAP. The momentum leg's f3 (industry momentum) reads the
     CURRENT umbrella sector map for historical dates — a small,
     unavoidable point-in-time impurity in one of five equal-weight
     features, declared, not corrected.
 (e) This is a BACKTEST standing in for forward accumulation per the
     operator's policy. It is not a live shadow readout, and the corpus
     ends 2023-09-29.

Deterministic by construction: pinned seeds (the artifacts' own for
xgboost, 0 for the bootstrap), fixed calendar, no early stopping, no
search, stable row ordering before every DMatrix build.

Usage:  python 2026-08-18-served-blend-plus-clf-derivation.py
Env:    RQ_UMBRELLA_ROOT / RQ_MODEL_SRC override the checkout paths.
Output: results JSON + weekly-series CSV + block-table CSV + refit-ledger
        JSON next to this script.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

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
CLF_ARTIFACT = (UMBRELLA / "backtesting" / "renquant_104" / "artifacts"
                / "shadow" / "panel-clf.top-decile.fwd60.json")
MOM_LEDGER = (UMBRELLA / "backtesting" / "renquant_104" / "artifacts"
              / "momentum" / "momentum_artifact_ledger.jsonl")
TRAINER_SCRIPT = UMBRELLA / "scripts" / "train_production_model.py"
SERVED_CONFIG = STRAT104 / "configs" / "strategy_config.json"

OUT_JSON = HERE / "2026-08-18-served-blend-plus-clf-results.json"
OUT_SERIES = HERE / "2026-08-18-served-blend-plus-clf-series.csv"
OUT_BLOCKS = HERE / "2026-08-18-served-blend-plus-clf-blocks.csv"
OUT_LEDGER = HERE / "2026-08-18-served-blend-plus-clf-refit-ledger.json"
OUTPUTS = (OUT_JSON, OUT_SERIES, OUT_BLOCKS, OUT_LEDGER)

VOL_SWITCH_RUNNER = HERE / "2026-08-18-vol-switch-derivation.py"
TAILQ90_RUNNER = HERE / "2026-08-18-gi-tailq90-derivation.py"

# Late-bound at run time (main): renquant_model_common total-return helper.
# Module-level placeholder keeps the verbatim MomReaders copy import-light for
# the unit tests (which never execute the rho section).
total_return_close = None

# ---------------------------------------------------------- frozen constants
# Corpus / grid / blocks — the vol-switch primary corpus (orch#1001 §3).
PRIMARY_START = "2017-01-03"
PRIMARY_END = "2023-09-29"
SAMPLE_STEP = 5                      # weekly = every 5th trading day
BLOCK_TD = 60                        # non-overlapping 60-TRADING-day blocks
ELIGIBLE_MIN_ON_DAYS = 15            # ON-eligible block floor (sub-read only)
MIN_NAMES_PER_DATE = 100             # G11 estimand floor

# State — the fixed definition frozen in orch#1001 and CONFIRMED in orch#1003.
VOL_WINDOW = 20                      # trading days
FIXED_ON_THRESHOLD = 0.135

# Frozen primary-corpus geometry (G9) — orch#1001 §2/§3 as re-measured by the
# committed orch#1003 run. Tolerance EXACT.
FROZEN_PRIMARY_GEOMETRY = {
    "corpus_td": 1697,
    "on_days_fixed": 821,
    "complete_blocks": 28,
    "weekly_grid_n": 340,            # derived: ceil(1697 / 5)
}

# Scoring — the production recipe VERBATIM (G2), objective AT PRODUCTION.
FROZEN_CONFIG_FINGERPRINT = "sha256:f8fb2259b2bf1537"
PRODUCTION_OBJECTIVE = "rank:pairwise"
N_FEATURES = 172
LABEL = "fwd_60d_excess"
LABEL_HORIZON_TDAYS = 60             # h = 60 (training label AND estimand)
EMBARGO_TDAYS = 60                   # C + 60 trading days <= d
EXPECTED_BEST_ITER = 100
TRAIN_DATA_START = "2016-01-04"
REFIT_FIRST_QUARTER = (2016, 2)      # 2016-Q2
REFIT_LAST_QUARTER = (2023, 3)       # 2023-Q3 — the primary corpus's ladder
EXPECTED_REFITS = 30
PANEL_N_TICKERS = 292

# Clf leg — the shadow artifact's frozen recipe (G3).
FROZEN_CLF_FINGERPRINT = (
    "sha256:1d8f167fed18cd8cb1e0760251fdd5398724e630462d92b41561d2e19973e41b")
CLF_OBJECTIVE = "binary:logistic"
CLF_TOP_DECILE = 0.9                 # label threshold, re-read from the artifact
CLF_LABEL_KIND = "top_decile_membership"

# Momentum leg — the fingerprint the served config pins.
FROZEN_MOMENTUM_FINGERPRINT = "momentum-v0-fd65161a20b29314"
MOMENTUM_SKIP_BDAYS = 21             # the leg's own declared input embargo

# Served-blend contract (blend_scorer.BlendPanelScorer.score).
Z_DDOF = 0

# Estimand — the capacity-memo instrument + the orch#1001 cell floor.
DGTW_CHARS = ("STD60", "ROC60", "BETA60")   # vol x mom x beta
DGTW_MIN_CELL = 15
TOPDEC_DIV = 10
WINSOR_CLIP = 0.5                    # +-50% (SD units — z label)

# Arms — order is identity-bearing for the served blend's fingerprint.
ARMS = ("A_prod", "B_3leg", "C_2leg_certified", "D_solo_xgb")
ARM_LEGS = {
    "A_prod": ("xgb", "mom"),
    "B_3leg": ("xgb", "mom", "clf"),
    "C_2leg_certified": ("xgb", "clf"),
    "D_solo_xgb": ("xgb",),
}
PRIMARY_CONTRAST = ("B_3leg", "A_prod")
CONTROL_CONTRAST = ("C_2leg_certified", "D_solo_xgb")
# The standing certification this runner cross-checks against.
MODEL76_CERTIFIED = {"diff": 0.0687, "ci90": [0.0156, 0.1269],
                     "source": "renquant-model doc/research/"
                               "2026-07-26-blend-confirmatory-v2-results.md"}

# Inference — the vol-switch runner's frozen machinery.
NW_LAG = 1
ONE_SIDED_ALPHA = 0.05
BOOT_RESAMPLES = 10_000
BOOT_EXPECTED_BLOCK = 2.0
BOOT_SEED = 0
MIN_BLOCKS = 15
MIN_ESS = 6.0


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"FROZEN-GUARD FAILURE — STOP, do not adjust the spec: {msg}")


# --------------------------------------------------------------------------
# REUSED MACHINERY — copied VERBATIM from the reviewed vol-switch runner
# doc/research/data/2026-08-18-vol-switch-derivation.py (orch#1002/#1003),
# itself a verbatim reuse of the tail_q90 runner (#996/#999).
# tests/test_served_blend_clf_runner.py enforces byte-identity of these
# definitions, so the reuse cannot silently drift into a rewrite.
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


def block_on_day_counts(on_corpus: pd.Series, n_blocks: int) -> list[int]:
    """ON-day count per complete non-overlapping 60-td block (positional —
    the corpus series must be exactly the corpus trading days, in order)."""
    return [int(on_corpus.iloc[i * BLOCK_TD:(i + 1) * BLOCK_TD].sum())
            for i in range(n_blocks)]


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


# ------------------------------------------- NEW: this runner's own frozen logic
def load_clf_artifact(prod_art: dict) -> dict:
    """G3/G4: the shadow clf recipe, identity-asserted, and pinned to the
    prod artifact's preprocessing (same feature_cols AND same norm kinds) so
    one normalization per cutoff serves both legs and the arms differ by
    MODEL, never by preprocessing. The top-decile threshold is read FROM the
    artifact's own `classifier_label_spec`, never assumed."""
    art = json.loads(CLF_ARTIFACT.read_text())
    _assert(art.get("config_fingerprint") == FROZEN_CLF_FINGERPRINT,
            f"clf artifact fingerprint {art.get('config_fingerprint')!r} != "
            f"frozen {FROZEN_CLF_FINGERPRINT}")
    _assert(art.get("kind") == "panel_ltr_xgboost",
            "clf artifact kind drifted (it is deliberately stamped "
            "panel_ltr_xgboost so PanelScorer.load serves it unchanged)")
    _assert(art.get("label_col") == LABEL, "clf label_col != fwd_60d_excess")
    _assert(int(art.get("lookahead_days", -1)) == LABEL_HORIZON_TDAYS,
            "clf lookahead_days != 60")
    _assert(int(art.get("best_iter", -1)) == EXPECTED_BEST_ITER,
            "clf best_iter != 100 — boosting-round count unpinned")
    params = dict(art.get("params") or {})
    _assert(params.get("objective") == CLF_OBJECTIVE,
            f"clf objective {params.get('objective')!r} != {CLF_OBJECTIVE!r}")
    _assert("seed" in params, "clf params carry no seed — determinism unpinned")
    spec = (art.get("metadata") or {}).get("classifier_label_spec") or {}
    _assert(spec.get("kind") == CLF_LABEL_KIND,
            f"clf label spec kind {spec.get('kind')!r} != {CLF_LABEL_KIND!r}")
    _assert(spec.get("base_label") == LABEL, "clf label spec base_label != the panel label")
    _assert(float(spec.get("threshold_pct", -1)) == CLF_TOP_DECILE,
            f"clf label threshold {spec.get('threshold_pct')!r} != {CLF_TOP_DECILE}")
    _assert(list(art.get("feature_cols") or []) == list(prod_art["feature_cols"]),
            "clf feature_cols != prod feature_cols — the legs do not share a frame")
    _assert(list(art.get("feature_norm_kind") or []) == list(prod_art["feature_norm_kind"]),
            "clf feature_norm_kind != prod feature_norm_kind — the legs do not "
            "share a normalization")
    return art


def top_decile_label(train: pd.DataFrame, label: str = LABEL) -> pd.Series:
    """1{row's label is in its date's top decile} — the frozen construction.

    Semantically identical to renquant-model
    scripts/train_topdecile_clf_shadow.py::top_decile_label (the construction
    model#76 certified); the threshold is supplied by the artifact's own
    `classifier_label_spec` at the call site."""
    return (train.groupby("date")[label].rank(pct=True) >= CLF_TOP_DECILE).astype(float)


def fit_clf_booster(xgb_mod, tpm, train_df: pd.DataFrame, feat_cols: list[str],
                    mu: np.ndarray, sd: np.ndarray, kinds: list[str],
                    params: dict, n_rounds: int):
    """One clf refit. Mirrors renquant-model
    scripts/train_topdecile_clf_shadow.py::main VERBATIM in construction:
    binary top-decile-membership label, the SAME production normalization and
    panel-space transform as the LTR leg, stable date-sorted rows, and
    deliberately NO `set_group` (ranking groups are meaningless under
    binary:logistic) and NO y clip (the label is already 0/1)."""
    y = top_decile_label(train_df)
    Xdf = tpm.panel_training_matrix(train_df, feat_cols, mu, sd, kinds)
    order = np.argsort(train_df["date"].values, kind="stable")
    dtr = xgb_mod.DMatrix(Xdf.values[order].astype(np.float64),
                          label=y.values[order])
    booster = xgb_mod.train(params, dtr, num_boost_round=n_rounds)
    digest = hashlib.sha256(bytes(booster.save_raw(raw_format="json"))).hexdigest()
    return booster, digest, float(y.mean())


def zscore_leg(vals: pd.Series) -> pd.Series:
    """The served blend's per-leg normalization, verbatim in semantics
    (blend_scorer.BlendPanelScorer.score): z over the leg's FINITE values
    with ddof=0. A degenerate leg (n_finite < 2 or sd <= 0) contributes 0,
    exactly as the served scorer does (fail-soft, recorded by the caller)."""
    v = pd.Series(vals, dtype=float)
    finite = np.isfinite(v.to_numpy())
    if int(finite.sum()) < 2:
        return pd.Series(0.0, index=v.index, dtype=float)
    mu = float(v[finite].mean())
    sd = float(v[finite].std(ddof=Z_DDOF))
    if not np.isfinite(sd) or sd <= 0.0:
        return pd.Series(0.0, index=v.index, dtype=float)
    return (v - mu) / sd


def blend_scores(legs: dict[str, pd.Series], names: tuple[str, ...]) -> pd.Series:
    """The served combination rule: UNWEIGHTED sum of per-leg cross-sectional
    z-scores over a single common index (blend_scorer §"GOAL-9 orch#794 AC3":
    per-component weights are deliberately NOT introduced). NaN propagates
    through the sum, so a name missing from any leg is unscored."""
    _assert(len(names) >= 1, "blend needs at least one leg")
    total = None
    for name in names:
        z = zscore_leg(legs[name])
        total = z if total is None else total + z
    return total


def block_series(weekly: pd.DataFrame, value_col: str, n_blocks: int,
                 mask: pd.Series | None = None) -> tuple[np.ndarray, list[dict]]:
    """Per-block mean of a per-date value over complete non-overlapping
    60-trading-day blocks. `mask` (optional) restricts which weekly dates
    contribute — the ON-state sub-read's only degree of freedom. Blocks with
    no contributing date are dropped and counted by the caller."""
    rows, vals = [], []
    sub_all = weekly if mask is None else weekly[mask.to_numpy()]
    for b in range(n_blocks):
        sub = sub_all[sub_all["block"] == b]
        if not len(sub):
            rows.append({"block": b, "n_dates": 0, "value": None})
            continue
        v = float(sub[value_col].mean())
        rows.append({"block": b, "n_dates": int(len(sub)), "value": v})
        vals.append(v)
    return np.asarray(vals, dtype=float), rows


def infer(x: np.ndarray) -> dict:
    """The frozen inference on a block series: Newey-West(1) small-sample t
    AND the stationary block bootstrap, one-sided alpha = 0.05 (= the CI90
    lower bound the standing certification's rule uses). Both legs are
    reported; a split is flagged as DISAGREEMENT and is NOT a pass."""
    nw = nw_lag1(x)
    boot_means = stationary_bootstrap_means(x)
    q05 = float(np.percentile(boot_means, 100.0 * ONE_SIDED_ALPHA))
    q95 = float(np.percentile(boot_means, 100.0 * (1.0 - ONE_SIDED_ALPHA)))
    boot = {"q05": q05, "q95": q95, "n_resamples": int(len(boot_means)),
            "expected_block_length": BOOT_EXPECTED_BLOCK, "seed": BOOT_SEED,
            "passes": bool(q05 > 0)}
    rho1, ess = ess_lag1(x)
    n = int(len(x))
    disagreement = bool(nw["passes"]) != bool(boot["passes"])
    return {
        "n_blocks": n,
        "mean": float(x.mean()),
        "sd_blocks": float(x.std(ddof=1)) if n > 1 else None,
        "pos_block_frac": float((x > 0).mean()),
        "rho1": rho1, "ess": ess,
        "measurable": bool(n >= MIN_BLOCKS and ess >= MIN_ESS),
        "nw": nw, "bootstrap": boot,
        "disagreement": disagreement,
        "both_legs_pass": bool(nw["passes"] and boot["passes"]),
    }


def verdict_of(res: dict) -> tuple[str, str]:
    """The frozen bar, INHERITED from model#75's decision rule (the rule
    model#76 passed): CI90 lower bound > 0. Guards precede the verdict."""
    if not res["measurable"]:
        return ("UNMEASURABLE",
                f"guard floor not met (n_blocks {res['n_blocks']} >= {MIN_BLOCKS} "
                f"AND ESS {res['ess']:.2f} >= {MIN_ESS}); no verdict is issued")
    if res["mean"] <= 0:
        return ("WORSE", "point estimate <= 0 on the paired block series")
    if res["disagreement"]:
        return ("NOT DISTINGUISHABLE",
                "the two inference legs SPLIT — conservative, a split is not a pass")
    if res["both_legs_pass"]:
        return ("BEATS",
                "one-sided-95% (CI90) lower bound > 0 on BOTH inference legs")
    return ("NOT DISTINGUISHABLE",
            "point estimate > 0 but the CI90 lower bound includes 0")


# ----------------------------------------------------------------------- main
def main() -> None:
    t_start = time.time()
    assert_one_shot()
    import xgboost as xgb  # noqa: PLC0415 — heavyweight, main-only

    # The production helpers read data/ paths relative to the umbrella root;
    # the runner reads there and writes ONLY next to itself (G13).
    os.chdir(UMBRELLA)
    if str(MODEL_SRC) not in sys.path:
        sys.path.insert(0, str(MODEL_SRC))
    from renquant_model_momentum.train import (  # noqa: PLC0415
        params_v0 as mom_params_v0, train_momentum_artifact)
    global total_return_close
    from renquant_model_common.total_return import (  # noqa: PLC0415
        total_return_close as _trc)
    total_return_close = _trc

    tpm = load_trainer_module()

    art = load_served_artifact()
    art_clf = load_clf_artifact(art)
    feat_cols = [str(c) for c in art["feature_cols"]]
    # G2: objective AT PRODUCTION — the artifact's params VERBATIM, no delta.
    params = dict(art["params"])
    _assert(params.get("objective") == PRODUCTION_OBJECTIVE,
            f"artifact objective {params.get('objective')!r} != "
            f"{PRODUCTION_OBJECTIVE!r} — wrong base artifact")
    _assert("seed" in params, "artifact params carry no seed — determinism unpinned")
    n_rounds = int(art["best_iter"])
    params_clf = dict(art_clf["params"])
    n_rounds_clf = int(art_clf["best_iter"])

    # ---- the SERVED contract, read from the pinned config (never assumed) --
    served_cfg = json.loads(SERVED_CONFIG.read_text())
    ps = served_cfg["ranking"]["panel_scoring"]
    _assert(ps.get("kind") == "blend",
            f"pinned config panel_scoring.kind is {ps.get('kind')!r}, not 'blend' — "
            "A_prod would not be the served construction")
    comps = ps.get("components") or []
    _assert(len(comps) == 2, f"served blend has {len(comps)} components, expected 2")
    _assert(comps[0].get("artifact_path") == "artifacts/prod/panel-ltr.alpha158_fund.json"
            and comps[0].get("expected_config_fingerprint") == FROZEN_CONFIG_FINGERPRINT,
            "served component 0 is not the prod panel artifact this runner refits")
    _assert(comps[1].get("kind") == "momentum_residual"
            and comps[1].get("artifact_path") == "artifacts/momentum/momentum_artifact_ledger.jsonl"
            and comps[1].get("expected_config_fingerprint") == FROZEN_MOMENTUM_FINGERPRINT,
            "served component 1 is not the momentum_residual ledger leg this runner recomputes")

    # ---- momentum ledger coverage (the computability finding, MEASURED) ----
    ledger_rows = [json.loads(ln) for ln in MOM_LEDGER.read_text().splitlines() if ln.strip()]
    ledger_cutoffs = sorted(str(r.get("cutoff_date")) for r in ledger_rows)
    mom_params = mom_params_v0()
    _assert(int(mom_params["skip"]) == MOMENTUM_SKIP_BDAYS,
            f"momentum params skip {mom_params['skip']} != frozen {MOMENTUM_SKIP_BDAYS}")
    ledger_coverage = {
        "path": str(MOM_LEDGER),
        "n_rows": len(ledger_rows),
        "cutoffs": ledger_cutoffs,
        "genesis_cutoff": ledger_cutoffs[0] if ledger_cutoffs else None,
        "covers_primary_corpus": bool(
            ledger_cutoffs and ledger_cutoffs[0] <= PRIMARY_START),
        "finding": ("the served momentum ledger begins at its genesis cutoff and "
                    "holds NO row inside the primary corpus; the historical series "
                    "is RECONSTRUCTED here by the owning library "
                    "(renquant_model_momentum.train_momentum_artifact, pure over "
                    "readers, no fitted state), NOT extrapolated from ledger rows"),
        "params_v0": {k: v for k, v in mom_params.items() if k != "params_source"},
    }
    _assert(not ledger_coverage["covers_primary_corpus"],
            "the momentum ledger now covers the primary corpus — this runner's "
            "reconstruction rationale is stale, re-derive before trusting it")

    # ---- SPY calendar + frozen corpus geometry (G9) ------------------------
    print("[1/6] SPY state series + frozen-geometry recompute ...", flush=True)
    readers = ReadersLite()
    spy_close = readers.market_close()
    _assert(spy_close.index.is_monotonic_increasing and spy_close.index.is_unique,
            "SPY calendar is not a clean trading-day index")
    cal = spy_close.index
    vol20 = realized_vol20(spy_close)
    on_fixed_all = on_state_fixed(vol20)

    corpus = vol20.loc[PRIMARY_START:PRIMARY_END]
    _assert(str(corpus.index[0].date()) == PRIMARY_START
            and str(corpus.index[-1].date()) == PRIMARY_END,
            "primary corpus endpoints are not trading days of the SPY calendar")
    _assert(corpus.notna().all(), "vol20 undefined on a primary-corpus day")
    on_fixed_prim = on_fixed_all.loc[corpus.index]
    n_blocks = len(corpus) // BLOCK_TD
    counts_fixed = block_on_day_counts(on_fixed_prim, n_blocks)
    grid = corpus.index[::SAMPLE_STEP]
    measured_geometry = {
        "corpus_td": len(corpus),
        "on_days_fixed": int(on_fixed_prim.sum()),
        "complete_blocks": n_blocks,
        "weekly_grid_n": len(grid),
    }
    for key, frozen in FROZEN_PRIMARY_GEOMETRY.items():
        _assert(measured_geometry.get(key) == frozen,
                f"frozen geometry mismatch on {key!r}: measured "
                f"{measured_geometry.get(key)!r} != frozen {frozen!r}")

    # ---- refit ladder (G5/G6) ---------------------------------------------
    refit_cutoffs = build_refit_calendar(cal)
    cutoff_pos = [int(cal.get_loc(c)) for c in refit_cutoffs]
    _assert(cal[cutoff_pos[0] + EMBARGO_TDAYS] <= grid[0],
            "first scoreable date falls after the corpus start — the frozen "
            "ladder cannot score the corpus")

    # ---- panel (read-only; the production training frame) ------------------
    print(f"[2/6] loading panel {PANEL_PARQUET.name} ...", flush=True)
    panel_digest = _sha256(PANEL_PARQUET)
    panel = pd.read_parquet(PANEL_PARQUET)
    panel["date"] = pd.to_datetime(panel["date"])
    _assert(LABEL in panel.columns, "panel lacks the fwd_60d_excess label")
    _assert(all(c in panel.columns for c in feat_cols),
            "panel lacks artifact feature columns")
    _assert(all(c in panel.columns for c in DGTW_CHARS),
            "panel lacks the DGTW characteristic columns")
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
    _assert(grid.isin(panel_dates).all(),
            "grid dates missing from the panel — features unavailable")
    last_labeled = panel.dropna(subset=[LABEL])["date"].max()
    _assert(last_labeled >= grid[-1],
            f"panel realized labels end {last_labeled.date()} before the last "
            f"grid date {grid[-1].date()} — labels do not cover the corpus")

    # ---- sentiment trained_zeroing replay (G8, production helpers) ---------
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

    # ---- 30 expanding refits x 2 legs (G5/G7/G8) ---------------------------
    print(f"[4/6] {EXPECTED_REFITS} expanding refits x 2 legs "
          f"(rank:pairwise + binary:logistic) ...", flush=True)
    boosters, boosters_clf, norms, ledger = [], [], [], []
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
        t1 = time.time()
        booster_clf, digest_clf, pos_rate = fit_clf_booster(
            xgb, tpm, tr, feat_cols, mu, sd, kinds, params_clf, n_rounds_clf)
        boosters.append(booster)
        boosters_clf.append(booster_clf)
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
            "booster_xgb_sha256": digest,
            "booster_clf_sha256": digest_clf,
            "clf_positive_rate": pos_rate,
            "fit_seconds_xgb": round(t1 - t0, 1),
            "fit_seconds_clf": round(time.time() - t1, 1),
        })
        print(f"    {cutoff.date()}: rows={len(tr):>7d} "
              f"max_train={tr['date'].max().date()} pos_rate={pos_rate:.3f} "
              f"({ledger[-1]['fit_seconds_xgb']}s + {ledger[-1]['fit_seconds_clf']}s)",
              flush=True)

    # ---- weekly cross-sections: 3 legs -> 4 arms -> estimand ---------------
    print("[5/6] scoring the weekly grid (3 legs, 4 arms) + DGTW estimand ...",
          flush=True)
    mom_readers = MomReaders(readers)
    corpus_pos = {d: i for i, d in enumerate(corpus.index)}
    refit_used: dict[str, str] = {}
    mom_meta: dict[str, dict] = {}
    weekly_rows = []
    for d in grid:
        dpos = int(cal.get_loc(d))
        ri = refit_index_for_date(cutoff_pos, dpos)
        _assert(ri is not None, f"grid date {d.date()} has no admissible refit")
        _assert(cutoff_pos[ri] + EMBARGO_TDAYS <= dpos,
                f"embargo violated at {d.date()}")
        if ri + 1 < len(cutoff_pos):
            _assert(cutoff_pos[ri + 1] + EMBARGO_TDAYS > dpos,
                    f"not the newest admissible refit at {d.date()}")
        frame = by_date.get(d)
        _assert(frame is not None and not frame.empty,
                f"no panel cross-section at grid date {d.date()}")
        mu, sd, kinds = norms[ri]
        s_xgb = score_frame(xgb, tpm, boosters[ri], frame, feat_cols, mu, sd, kinds)
        s_clf = score_frame(xgb, tpm, boosters_clf[ri], frame, feat_cols, mu, sd, kinds)
        refit_used[str(d.date())] = str(refit_cutoffs[ri].date())

        # momentum leg — recomputed PIT by the owning library (G10). Universe
        # resolved the production way: the panel tickers on this date.
        mom_universe = sorted({str(t) for t in frame["ticker"]})
        art_m = train_momentum_artifact(d, mom_universe, mom_params,
                                        readers=mom_readers)
        _assert(art_m["kind"] == "momentum_residual_v0",
                f"momentum artifact kind drifted at {d.date()}")
        # G10: PIT chain, in the direction the artifact's own contract defines.
        # `formation_window.hi_inclusive` is the NOMINAL bound (cutoff - 21
        # business days); `effective_train_cutoff_date` is the MEASURED max
        # index date actually consumed, which lands on or BEFORE the nominal
        # bound whenever that bound is a market holiday (e.g. scoring date
        # 2018-01-23 -> nominal 2017-12-25 Christmas -> measured 2017-12-22).
        # The chain that must hold is measured <= nominal < scoring date.
        eff_cut = pd.Timestamp(art_m["effective_train_cutoff_date"])
        nominal_hi = pd.Timestamp(art_m["formation_window"]["hi_inclusive"])
        _assert(eff_cut < d,
                f"momentum PIT violation at {d.date()}: measured effective train "
                f"cutoff {eff_cut.date()} is not strictly before the scoring date")
        _assert(eff_cut <= nominal_hi,
                f"momentum measured cutoff {eff_cut.date()} at {d.date()} exceeds "
                f"its own nominal formation-window bound {nominal_hi.date()}")
        _assert(nominal_hi < d,
                f"momentum formation window at {d.date()} extends to or past the "
                f"scoring date (nominal bound {nominal_hi.date()})")
        s_mom = pd.Series(art_m["scores"], dtype=float)
        s_mom = s_mom[np.isfinite(s_mom)]
        mom_meta[str(d.date())] = {
            "n_scored": int(art_m["n_scored"]),
            "n_names": int(art_m["n_names"]),
            "names_floor_ok": bool(art_m["names_floor_ok"]),
            "effective_train_cutoff_date": str(eff_cut.date()),
            "formation_window": art_m["formation_window"],
        }

        # ---- the COMMON per-date universe (the pairing) --------------------
        est = frame.set_index("ticker")[[LABEL, *DGTW_CHARS]].rename(
            columns={LABEL: "label"})
        est.index = [str(t) for t in est.index]
        panel_usable = est.dropna(subset=["label", *DGTW_CHARS]).join(
            s_xgb.rename("xgb"), how="inner").dropna(subset=["xgb"])
        # G12: the clf leg is finite wherever the xgb leg is (same matrix).
        _assert(set(panel_usable.index) <= set(s_clf.index),
                f"{d.date()}: the clf leg is not finite on every xgb-scored name")
        common = panel_usable.join(s_mom.rename("mom"), how="inner")
        common["clf"] = s_clf.reindex(common.index)
        _assert(np.isfinite(common[["xgb", "mom", "clf"]].to_numpy()).all(),
                f"{d.date()}: a leg is non-finite on the common universe")
        _assert(len(common) >= MIN_NAMES_PER_DATE,
                f"{d.date()}: {len(common)} common names < floor {MIN_NAMES_PER_DATE}")

        dg = dgtw_adjust(common)
        _assert(len(dg) == len(common),
                f"{d.date()}: DGTW adjustment dropped rows the common universe kept")
        dg["dgtw_w50"] = dg["dgtw"].clip(-WINSOR_CLIP, WINSOR_CLIP)

        legs = {k: dg[k] for k in ("xgb", "mom", "clf")}
        row = {
            "date": str(d.date()),
            "day_pos": corpus_pos[d],
            "block": corpus_pos[d] // BLOCK_TD if corpus_pos[d] < n_blocks * BLOCK_TD else -1,
            "on_fixed": bool(on_fixed_all.loc[d]),
            "spy_vol20": float(vol20.loc[d]),
            "n_panel_usable": int(len(panel_usable)),
            "n_mom_scored": int(len(s_mom)),
            "n_common": int(len(common)),
            "n_topdec": int(round(len(dg) / TOPDEC_DIV)),
            "frac_flagged_unadjusted": float(1.0 - dg["adjusted"].mean()),
            "refit_cutoff": refit_used[str(d.date())],
        }
        for arm in ARMS:
            dg["score"] = blend_scores(legs, ARM_LEGS[arm])
            sp, _, _ = top_decile_spread(dg, "dgtw")
            spw, _, _ = top_decile_spread(dg, "dgtw_w50")
            row[f"spread_{arm}"] = sp
            row[f"spread_w50_{arm}"] = spw
        row["diff_primary"] = row[f"spread_{PRIMARY_CONTRAST[0]}"] - row[f"spread_{PRIMARY_CONTRAST[1]}"]
        row["diff_control"] = row[f"spread_{CONTROL_CONTRAST[0]}"] - row[f"spread_{CONTROL_CONTRAST[1]}"]
        row["diff_primary_w50"] = (row[f"spread_w50_{PRIMARY_CONTRAST[0]}"]
                                   - row[f"spread_w50_{PRIMARY_CONTRAST[1]}"])
        weekly_rows.append(row)

    weekly = pd.DataFrame(weekly_rows)
    _assert(len(weekly) == FROZEN_PRIMARY_GEOMETRY["weekly_grid_n"],
            "weekly table does not cover exactly the frozen grid")
    _assert((pd.to_datetime(weekly["date"]).values == grid.values).all(),
            "weekly table dates drifted from the frozen grid")

    # ---- the frozen statistic (G-guards counted BEFORE any verdict) --------
    print("[6/6] frozen statistic: paired block inference ...", flush=True)
    in_blocks = weekly["block"] >= 0
    wb = weekly[in_blocks].copy()

    block_tables: dict[str, list[dict]] = {}
    results: dict[str, dict] = {}

    prim_vals, prim_rows = block_series(wb, "diff_primary", n_blocks)
    block_tables["primary_B_minus_A"] = prim_rows
    primary = infer(prim_vals)
    primary["contrast"] = f"{PRIMARY_CONTRAST[0]} - {PRIMARY_CONTRAST[1]}"
    primary["per_date_mean"] = float(weekly["diff_primary"].mean())
    primary["n_dates"] = int(len(weekly))
    primary["winsorized_w50_per_date_mean"] = float(weekly["diff_primary_w50"].mean())
    v, r = verdict_of(primary)
    primary["verdict"], primary["verdict_reason"] = v, r
    results["primary"] = primary

    ctrl_vals, ctrl_rows = block_series(wb, "diff_control", n_blocks)
    block_tables["control_C_minus_D"] = ctrl_rows
    control = infer(ctrl_vals)
    control["contrast"] = f"{CONTROL_CONTRAST[0]} - {CONTROL_CONTRAST[1]}"
    control["per_date_mean"] = float(weekly["diff_control"].mean())
    cv, cr = verdict_of(control)
    control["verdict"], control["verdict_reason"] = cv, cr
    control["certified_reference"] = MODEL76_CERTIFIED
    control["comparability"] = (
        "DIRECTIONAL control, not a numeric identity check: model#76 measured "
        "the seed-averaged placebo-differenced clean TOP-10 spread over 5 purged "
        "folds on its own corpus; this runner measures the DGTW-adjusted "
        "top-decile spread on an expanding quarterly ladder over "
        f"{PRIMARY_START}..{PRIMARY_END}. Agreement in SIGN and rough magnitude "
        "supports the harness; a numeric gap does not by itself impeach it.")
    results["control"] = control

    # per-arm levels (same common universe on every date — directly comparable)
    levels = {}
    for arm in ARMS:
        vals, rows = block_series(wb, f"spread_{arm}", n_blocks)
        block_tables[f"level_{arm}"] = rows
        levels[arm] = {
            "legs": list(ARM_LEGS[arm]),
            "per_date_mean_spread": float(weekly[f"spread_{arm}"].mean()),
            "per_date_mean_spread_w50": float(weekly[f"spread_w50_{arm}"].mean()),
            "block_mean": float(vals.mean()),
            "n_blocks": int(len(vals)),
        }
    results["per_arm_levels"] = levels

    # ON-state sub-read (reported, never decisive)
    on_mask = wb["on_fixed"].astype(bool)
    on_vals, on_rows = block_series(wb, "diff_primary", n_blocks, mask=on_mask)
    block_tables["on_state_B_minus_A"] = on_rows
    eligible = [b for b, c in enumerate(counts_fixed) if c >= ELIGIBLE_MIN_ON_DAYS]
    on_elig_vals = np.asarray(
        [r["value"] for r in on_rows
         if r["value"] is not None and r["block"] in eligible], dtype=float)
    on_read = {
        "definition": f"SPY vol20 > {FIXED_ON_THRESHOLD} (fixed, orch#1001/#1003)",
        "decisive": False,
        "n_on_weekly_dates": int(on_mask.sum()),
        "n_on_eligible_blocks_in_corpus": len(eligible),
        "n_blocks_with_on_dates": int(len(on_elig_vals)),
        "per_date_mean": float(wb[on_mask.to_numpy()]["diff_primary"].mean()),
    }
    if len(on_elig_vals) >= 2:
        on_read.update(infer(on_elig_vals))
        ov, orr = verdict_of(on_read)
        on_read["verdict_if_this_were_decisive"] = ov
        on_read["verdict_reason"] = orr
    results["on_state_sub_read"] = on_read

    # OFF-state counterpart, for symmetry (reported, never decisive)
    off_mask = ~wb["on_fixed"].astype(bool)
    off_vals, off_rows = block_series(wb, "diff_primary", n_blocks, mask=off_mask)
    block_tables["off_state_B_minus_A"] = off_rows
    results["off_state_sub_read"] = {
        "decisive": False,
        "n_off_weekly_dates": int(off_mask.sum()),
        "n_blocks_with_off_dates": int(len(off_vals)),
        "per_date_mean": float(wb[off_mask.to_numpy()]["diff_primary"].mean()),
        "block_mean": float(off_vals.mean()) if len(off_vals) else None,
    }

    # ---- outputs (G1/G13: only next to this script) ------------------------
    weekly.to_csv(OUT_SERIES, index=False)
    pd.concat([pd.DataFrame(rows).assign(table=k) for k, rows in block_tables.items()],
              ignore_index=True).to_csv(OUT_BLOCKS, index=False)
    OUT_LEDGER.write_text(json.dumps({
        "runner": Path(__file__).name,
        "refits": ledger,
        "refit_used_by_score_date": refit_used,
        "momentum_artifact_by_score_date": mom_meta,
    }, indent=2, sort_keys=True) + "\n")

    out = {
        "question": ("on the SERVED construction, does adding the top-decile "
                     "classifier leg beat what production serves today?"),
        "semantics": ("BACKTEST under the operator's 2026-08-18 policy "
                      "(backtests replace evidence-accumulation waits). NOT a "
                      "preregistered confirmatory; nothing here changes production."),
        "verdict": primary["verdict"],
        "verdict_reason": primary["verdict_reason"],
        "frozen_bar": ("CI90 lower bound > 0 on BOTH inference legs — inherited "
                       "verbatim from model#75's decision rule (the rule model#76 "
                       "passed); not invented or tuned here"),
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": round(time.time() - t_start, 1),
        "results": results,
        "served_blend_contract": {
            "config": str(SERVED_CONFIG),
            "kind": ps.get("kind"),
            "components": [{k: v for k, v in c.items() if not k.startswith("_")}
                           for c in comps],
            "combination_rule": ("unweighted sum of per-leg cross-sectional "
                                 f"z-scores, ddof={Z_DDOF}, NaN-propagating "
                                 "(blend_scorer.BlendPanelScorer.score)"),
        },
        "arms": {a: list(ARM_LEGS[a]) for a in ARMS},
        "momentum_ledger_coverage": ledger_coverage,
        "corpus": {"start": PRIMARY_START, "end": PRIMARY_END,
                   "n_td": len(corpus), "n_weekly": int(len(weekly)),
                   "n_blocks": n_blocks},
        "frozen_geometry_measured": measured_geometry,
        "coverage": {
            "n_panel_usable_mean": float(weekly["n_panel_usable"].mean()),
            "n_panel_usable_min": int(weekly["n_panel_usable"].min()),
            "n_common_mean": float(weekly["n_common"].mean()),
            "n_common_min": int(weekly["n_common"].min()),
            "n_common_max": int(weekly["n_common"].max()),
            "frac_flagged_unadjusted_mean": float(weekly["frac_flagged_unadjusted"].mean()),
        },
        "frozen_rule": {
            "block_td": BLOCK_TD, "sample_step": SAMPLE_STEP,
            "dgtw_min_cell": DGTW_MIN_CELL, "winsor_clip": WINSOR_CLIP,
            "nw_lag": NW_LAG, "one_sided_alpha": ONE_SIDED_ALPHA,
            "bootstrap": {"resamples": BOOT_RESAMPLES,
                          "expected_block_length": BOOT_EXPECTED_BLOCK,
                          "seed": BOOT_SEED},
            "min_blocks": MIN_BLOCKS, "min_ess": MIN_ESS,
            "embargo_trading_days": EMBARGO_TDAYS, "n_refits": EXPECTED_REFITS,
            "xgb_objective": PRODUCTION_OBJECTIVE, "clf_objective": CLF_OBJECTIVE,
            "clf_top_decile": CLF_TOP_DECILE,
        },
        "params": {"xgb": params, "clf": params_clf},
        "sentiment_gate_replay": gate_meta,
        "declared_fidelity_gaps": [
            "survivorship: 292-name survivor panel + today's OHLCV store — LEVELS "
            "inflated for every arm; the paired contrast is the robust object",
            "serving freshness: production publishes momentum WEEKLY and serves it "
            "until the next publish, so the served leg is up to ~7 calendar days "
            "staler than what this runner computes at each weekly grid date",
            "sentiment gate: both legs are trained on the production-gated frame; "
            "the deployed clf shadow artifact carries no such stamp",
            "sector map: the momentum f3 leg reads the CURRENT umbrella sector map "
            "for historical dates (1 of 5 equal-weight features)",
            "this is a BACKTEST standing in for forward accumulation; the corpus "
            "ends 2023-09-29 and it is not a live shadow readout",
        ],
        "pins": {
            "xgboost_version": str(xgb.__version__),
            "served_artifact": str(SERVED_ARTIFACT),
            "served_artifact_sha256": _sha256(SERVED_ARTIFACT),
            "served_config_fingerprint": art["config_fingerprint"],
            "clf_artifact": str(CLF_ARTIFACT),
            "clf_artifact_sha256": _sha256(CLF_ARTIFACT),
            "clf_config_fingerprint": art_clf["config_fingerprint"],
            "served_config_sha256": _sha256(SERVED_CONFIG),
            "momentum_ledger_sha256": _sha256(MOM_LEDGER),
            "panel_parquet": str(PANEL_PARQUET),
            "panel_parquet_sha256": panel_digest,
            "trainer_script_sha256": _sha256(TRAINER_SCRIPT),
            "sector_map_sha256": _sha256(SECTORS),
            "spy_1d_sha256": readers.read_digests()["ohlcv/SPY/1d.parquet"],
            "vol_switch_runner_sha256": _sha256(VOL_SWITCH_RUNNER),
            "tailq90_runner_sha256": _sha256(TAILQ90_RUNNER),
        },
    }
    OUT_JSON.write_text(json.dumps(out, indent=2) + "\n")

    print("\n===== VERDICT (frozen bar: CI90 lower bound > 0, both legs) =====")
    print(f"  PRIMARY  {primary['contrast']}: {primary['verdict']} — {primary['verdict_reason']}")
    print(f"    block mean {primary['mean']:+.5f}  n_blocks={primary['n_blocks']} "
          f"rho1={primary['rho1']:+.3f} ESS={primary['ess']:.2f} "
          f"pos_blocks={primary['pos_block_frac']:.2f}")
    print(f"    NW t={primary['nw']['t']:+.3f} (crit {primary['nw']['t_crit_one_sided_95']:.3f}) "
          f"CI90_lo={primary['nw']['ci_lower_one_sided_95']:+.5f}")
    print(f"    boot q05={primary['bootstrap']['q05']:+.5f} q95={primary['bootstrap']['q95']:+.5f} "
          f"disagreement={primary['disagreement']}")
    print(f"  CONTROL  {control['contrast']}: {control['verdict']}")
    print(f"    block mean {control['mean']:+.5f}  NW t={control['nw']['t']:+.3f} "
          f"boot [{control['bootstrap']['q05']:+.5f}, {control['bootstrap']['q95']:+.5f}] "
          f"(model#76 certified {MODEL76_CERTIFIED['diff']:+.4f} "
          f"CI90 {MODEL76_CERTIFIED['ci90']})")
    print("  LEVELS (common universe, per-date mean DGTW top-decile spread):")
    for arm in ARMS:
        print(f"    {arm:<18} {levels[arm]['per_date_mean_spread']:+.5f}  "
              f"legs={'+'.join(levels[arm]['legs'])}")
    print(f"  ON-state sub-read (not decisive): per-date mean "
          f"{on_read['per_date_mean']:+.5f} over {on_read['n_on_weekly_dates']} ON dates, "
          f"{on_read['n_blocks_with_on_dates']} blocks")
    print(f"\nwrote {OUT_JSON.name}, {OUT_SERIES.name}, {OUT_BLOCKS.name}, "
          f"{OUT_LEDGER.name} ({out['runtime_sec']}s)")


if __name__ == "__main__":
    main()
