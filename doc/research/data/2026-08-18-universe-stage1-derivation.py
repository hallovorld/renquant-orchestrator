#!/usr/bin/env python
"""Universe-extension Stage 1 — the ONE triage run (frozen runner; ships REVIEWED, runs LATER).

Governing contract: doc/research/2026-08-18-universe-stage1-triage-spec.md
(orch#995, MERGED). This script is the execution-contract runner required by
that spec's §6 (the #990 freeze-then-review-then-run sequencing): every guard
below is prereg content, committed and REVIEWED before the run — MECHANICALLY
ENFORCED by U11, which refuses to execute unless this file's bytes equal the
freshly FETCHED origin/main copy. Stage 1 TRIAGES (PASS (triage) /
DEPRIORITIZED); it neither kills nor admits (spec §1). One shot per corpus —
re-running with different parameters after seeing results is FORBIDDEN —
MECHANICALLY ENFORCED by U10, which refuses when any output already exists.

Deterministic by construction: no randomness anywhere (no seeds needed), no
clock enters any computed number (wall-clock stamps land in metadata only),
inputs are read-only local stores whose sha256 digests are recorded.

The paired-cross-section, grid, and block machinery is ADAPTED from the
reviewed doc/research/data/2026-08-17-gi-moe-screen-derivation.py (guards
G1/G5/G6/G7/G9 there — incl. the codex orch#990 shared-cross-section
correction), extended from an IC estimand to the spread estimand.

════════════════════════ FROZEN RUNNER GUARDS (spec §6) ════════════════════

U1  SERVED-PIN BYTE-IDENTITY. The served production scorer is the config's
    ``ranking.panel_scoring`` block (kind=blend, 2 components). The spec's
    instrument (the capacity-memo DGTW tail statistic, measured on panel-xgb
    scores) is the PANEL leg, so Arms A/W score with the SERVED PANEL MODEL
    PIN = ``components[0]`` (artifacts/prod/panel-ltr.alpha158_fund.json,
    role "PRODUCTION panel scorer"), resolved under the live strategy dir
    ``<umbrella>/backtesting/renquant_104/`` exactly as production resolves
    it. Byte identity is asserted the way production asserts it
    (blend_scorer.load_blend_scorer): sha256 of the artifact FILE BYTES must
    prefix-match ``expected_content_sha256`` (>=8 hex, sha256: stripped) AND
    the artifact's stored ``config_fingerprint`` must equal
    ``expected_config_fingerprint`` verbatim. Also asserted: kind ==
    panel_ltr_xgboost, exactly 172 feature_cols, label fwd_60d_excess,
    lookahead 60. The blend's component[1] (momentum_residual, ledger-served,
    genesis 2026-08 — NO historical coverage on this corpus) is recorded as
    context, never scored. DEVIATION NOTE (report, don't paper over): the
    spec's phrase "served production model pin" is implemented as the served
    blend's PANEL component pin — the #987/capacity-memo instrument lineage.

U2  UNIVERSE-COUNT RECOMPUTE. The §3 cascades are recomputed from the raw
    stores with the 2026-08-18 feasibility memo's measured conventions
    (session evidence universe-feasibility/universe_screen.py, whose staged
    counts 2,058/1,758/627/609/1,955 the spec's §3 quotes):
      * inventory: every data/ohlcv/<T>/1d.parquet with >= 60 rows;
      * px  = median(close of the LAST 63 rows)   [snapshot-edge convention]
      * adv = median(close*volume of LAST 63 rows) [63d-ADV, snapshot edge]
      * listing >= 3y  == nrows >= 756
      * "OHLCV >= 5y"  == first bar on/before CORPUS_START (2021-07-01).
        The snapshot's standard fetch depth is ~5y (typical extension file:
        1,256 rows, 2021-05-03..2026-05-08), so the memo's ">=5y" and
        "history reaches the corpus start" are the same 609 names — verified
        against the memo evidence before freezing (609 exactly, both ways of
        reading it were re-derived from universe_screen.csv).
      * SEC-fundamentals-covered == ticker present in
        data/sec_fundamentals_daily.parquet (the file the full recipe
        consumes; sec_fundamentals_extended has DIFFERENT columns and cannot
        feed the recipe).
    Arm A = non-watchlist & px in [5,400] & adv >= $5M & nrows >= 756 &
            fund-covered & first bar <= 2021-07-01          (~609)
    Arm B = non-watchlist & px in [5,400] & adv >= $1M & nrows >= 756 &
            first bar <= 2021-07-01                          (~1,955)
    Arm W = the golden config watchlist                      (145 EXACT)
    TOLERANCE: |n_A - 609| <= 18 and |n_B - 1955| <= 59 (±3%: the spec says
    "~"; the stores drift daily and a silent universe drift is exactly what
    this guard must catch), n_W == 145 exact. EXACT counts are RECORDED in
    the output at every cascade stage.

U3  POSITIVE CONTROL BEFORE ARM A. Arm W's h=60 genuine top-decile
    DGTW-adjusted spread is computed IN THE REFERENCE INSTRUMENT'S UNITS and
    hard-asserted BEFORE any Arm A cross-section is scored. The committed
    reference number is renquant-model
    doc/research/evidence/2026-07-24-capacity-memo/
    structural_decomposition_result.json ["dgtw"]["dgtw"] =
    +0.24038304426130444 (the memo §7.1 table prints +0.243). UNITS: the
    memo's f60 is the production panel's fwd_60d_excess, which is per-date
    cross-sectionally z-scored (verified on the committed panel: per-date
    mean 0, std 1) — the reference is in per-date CS-sigma units, NOT raw
    return units. The control therefore z-scores the raw h=60 excess labels
    per date across the arm (ddof=1, +1e-12 = the panel builder's EPS) and
    runs the identical DGTW/decile machinery on them.
    TOLERANCE (frozen): mean control spread >= REF/3 = +0.080128 sigma
    (sign-preserving lower bound only). Rationale: the reference was a
    single run on the ~292-name panel with OOS CV-fold scores, daily
    cross-sections, top-10, n=35 blocks; Arm W is 145 names, weekly, 19
    blocks, top-decile(14), scored by the 2026-08-02 served pin whose
    training window CONTAINS most of this corpus — in-sample INFLATION is
    expected and is therefore not a failure mode this control can police
    (recorded as telemetry when spread > 3x REF); COLLAPSE or SIGN FLIP is
    instrument failure and voids the run. On failure the runner STOPS
    (RunVoidError) and Arm A is never computed.

U4  CROSS-SECTION / BLOCK COUNTS. Corpus = SPY trading days in
    [2021-07-01, 2026-02-13] (both endpoints asserted to be trading days),
    sampled every 5th day from the first. The window holds 1,161 trading
    days (the spec's "~1,155" was approximate) so the RULE yields 233
    cross-sections vs the spec's derived 231 — the rule is the more
    primitive frozen object (the #992 G1 precedent), so the rule governs,
    |n - 231| <= 2 is asserted, and the exact n is REPORTED, never papered
    over. Complete blocks are asserted EXACTLY at the spec's counts: 19 at
    h=60 (obs 0..227), 58 at h=20 (obs 0..231); trailing obs are excluded
    from block inference but remain in the mean-level Δ (G9 semantics).

U5  PAIRED-PLACEBO IDENTITY. Placebo = the SAME arm's score cross-section
    computed 2h trading days EARLIER, evaluated against the SAME forward
    label at the grid date (G6). Per kept date, ONE shared cross-section:
    finite genuine score ∩ finite placebo score ∩ finite label ∩ finite
    STD60/ROC60/BETA60 (the memo's own dropna set), names-floor 50 (=the
    #987 harness floor, identical for all arms) applied to THAT shared set;
    both legs' deciles are selected over exactly those names (G7,
    corrected). Ticker IDENTITY is asserted per kept date (no dups, floor
    met); per-leg-only coverage counts survive as telemetry.

U6  SNAPSHOT-EDGE. No label may extend past 2026-05-08 (the OHLCV snapshot
    edge). ENFORCED BY TRIMMING: a grid obs whose h-day label endpoint
    (SPY calendar) falls after 2026-05-08 is dropped from that horizon and
    counted under dropped_label_edge. DISCOVERED SPEC DISCREPANCY (reported,
    not papered over): the last grid date 2026-02-13 has its h=60 label
    endpoint on 2026-05-12 — the spec's premise "h=60 labels mature inside
    the 2026-05-08 edge" is 2 trading days off for that one obs. The guard
    governs (label validity is the primitive), dropping exactly obs 232 at
    h=60 (asserted <= 1 obs, and asserted to lie OUTSIDE every complete
    block, so U4's 19/58 are untouched). h=20 loses nothing (asserted 0).

U7  ZERO WRITES OUTSIDE SCRATCH. Every write goes through _write_guard():
    allowed targets are (a) this script's own directory (doc/research/data/
    of the ISOLATED WORKTREE the run happens in — results land there for
    the results PR) and (b) the scratch dir (env RQ_STAGE1_SCRATCH, default
    ~/.cache/renquant-universe-stage1). Both are asserted NOT to lie inside
    the umbrella repo; the umbrella (and its data/) is never a write
    target. Corpus-build intermediates (per-ticker feature caches keyed by
    the source file's sha256) live in scratch only.

U8  MINIMUM BLOCKS (fail-closed floor, the #992 G10 analog — a runner guard
    frozen here as prereg content per the house rule): the h=60 Arm-A
    verdict is UNMEASURABLE unless >= 10 of the 19 complete blocks have
    data (a strict majority). Early extension history (typical first bar
    2021-05-03 => no placebo scores until the lag window clears) is
    expected to empty the first ~2 blocks; that is reported, not hidden.

U9  PIT FUNDAMENTALS. For every served fundamental value, the filing's
    *_source_available_at must be <= the row date (asserted on the raw
    daily rows restricted to the arm's tickers, for each of the 5 recipe
    columns that carries an available_at column) — the #992 G4 check,
    widened to all five columns.

U10 ONE-SHOT MARKER. The runner REFUSES to run when any of its outputs
    (results JSON / obs CSV) already exists next to this script — one shot
    per corpus, as a precondition rather than a convention (the #996 T1
    shape). A VOIDED run also spends the shot: its VOID payload is an
    output, so the U3 "voids the run" semantics are mechanical too.

U11 BYTE-IDENTITY VS FETCHED origin/main. Before any other work, the
    executing file's bytes must equal origin/main's copy of itself, with a
    mandatory `git fetch origin main` FIRST so the comparison authority is
    the remote, never a stale local ref (the orch#997 correction to the
    #996 T2 guard; a fetch failure fails CLOSED — an offline box refuses
    rather than validating against yesterday's cache). Not merged yet ->
    refuses: freeze-then-review-then-run is enforced, not promised. The
    post-fetch origin/main sha + this file's sha256 are recorded in the
    output pins as the run's lineage.

════════════════ FROZEN OPERATIONALIZATIONS (spec §4/§5 → code) ═══════════

ESTIMAND (spec §4, the capacity-memo instrument's own construction —
structural_decomposition.py in the committed evidence dir):
  * cells: per date, terciles of raw STD60 x ROC60 x BETA60 via
    qcut(rank(method='first'), 3) — tercile assignment is monotone-invariant
    so raw columns and the memo's train-normalized columns give identical
    cells;
  * DGTW benchmark: self-excluded cell mean of the h=60 raw excess label;
    a cell with < 15 names is UNADJUSTED-AND-FLAGGED (adjusted value = the
    raw label; the flag count is reported per date/arm). NOTE the floor
    binds mostly Arm W (145 names / 27 cells): its DGTW adjustment will be
    largely vacuous by the spec's own frozen floor — reported, not hidden;
  * spread: mean(adjusted over the top decile by score) − mean(adjusted
    over ALL shared names); n_top = max(1, floor(n/10));
  * Δ (decision quantity): per date, spread_genuine − spread_placebo;
    each leg's decile is selected by its own scores over the SAME names.
COSTS (RS-5 frozen buckets, RT): >=$25M ADV: 25bps; $10-25M: 40bps;
  $5-10M: 60bps; $1-5M: UNCOSTABLE (excluded from all verdict arms).
  Bucket membership is per NAME, from the SAME snapshot 63d-ADV the
  universe filter used (frozen; a per-date ADV would be more PIT-correct
  but is a different instrument than the one the spec's counts froze).
  Charging: per kept obs t, drag_t = (h / 5) * sum(RT cost of names
  ENTERING the genuine decile at t) / n_top(t); consecutive kept obs define
  turnover (the first kept obs is a full entry). The h/5 factor scales the
  weekly-cadence turnover cost to the h-day spread window (12x at h=60).
  Costs are charged against the GENUINE leg only (the placebo is a null
  instrument, not a traded book): net Δ_t = Δ_t − drag_t. Conservative by
  construction.
TRIAGE BARS (spec §5, h=60, Arm A) — operationalized:
  1. net-of-cost Δspread > 0: mean over kept obs of (Δ_t − drag_t) > 0,
     Arm A pooled over its costable names ($1-5M names never enter Arm A);
  2. block-t >= 1.0 over the 19 complete blocks of the GROSS Δ series
     (spec §4 defines Δ pre-cost; costs enter bar 1). Net block-t is also
     reported, informationally;
  3. > 50% of blocks-with-data positive (gross block deltas);
  4. transfer: EXISTS a costable ADV bucket b with Δspread_A,b >=
     Δspread_W, where Δspread_A,b re-selects deciles WITHIN the bucket's
     names (DGTW cells stay ARM-level per the spec's "terciles within-arm")
     and both sides are GROSS (Arm W is uncosted mega-cap; comparing A-net
     to W-gross would double-count bar 1's cost test).
  All four AND U8 measurable => PASS (triage); else DEPRIORITIZED (or
  UNMEASURABLE(insufficient_blocks), fail-closed). Arm B can neither pass
  nor fail anything: reported per ADV bucket (incl. the uncostable $1-5M
  bucket, labeled), never pooled with Arm A. h=20 secondary: same
  machinery, reported, NEVER decisive.

KNOWN SERVE-VS-HARNESS DIFFERENCES (declared, not discretionary): the 14
non-alpha158 features are built with the committed TRAIN recipe
(renquant_base_data.alpha158_fund_panel: exact-date fund merge + PEAD/SUE
from earnings_surprise/ + sentiment from news_sentiment_alpaca/, each with
the recipe's per-date median-then-0.0 fill), i.e. the recipe the pin was
trained on; the artifact's sentiment RUNTIME regime gate (a serve-time
zeroing by regime state) is NOT simulated — no regime series is in this
spec's scope; affected: 3/172 features, extension coverage 0.6%. Arm B is
the spec's own NaN-variant: the 14 columns are absent => the serve
transform's fillna(0.0) applies. Score rows require the bar to EXIST at the
grid date (no most-recent-row fallback): the corpus analog of G5's no-fill
label rule.

Usage:  caffeinate -i python 2026-08-18-universe-stage1-derivation.py
Env:    RQ_UMBRELLA_ROOT / RQ_STRAT104_ROOT / RQ_BASEDATA_SRC /
        RQ_PIPELINE_SRC / RQ_COMMON_SRC / RQ_STAGE1_SCRATCH override the
        default local paths (read-only inputs, same contract).
Output: results JSON + per-obs CSV next to this script. THIS PR SHIPS THE
        RUNNER UN-RUN; the run is a later, separately-authorized execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- frozen IO
HERE = Path(__file__).resolve().parent
UMBRELLA = Path(os.environ.get("RQ_UMBRELLA_ROOT", "/Users/renhao/git/github/RenQuant"))
STRAT104 = Path(os.environ.get("RQ_STRAT104_ROOT", "/Users/renhao/git/github/renquant-strategy-104"))
BASEDATA_SRC = Path(os.environ.get("RQ_BASEDATA_SRC", "/Users/renhao/git/github/renquant-base-data/src"))
PIPELINE_SRC = Path(os.environ.get("RQ_PIPELINE_SRC", "/Users/renhao/git/github/renquant-pipeline/src"))
COMMON_SRC = Path(os.environ.get("RQ_COMMON_SRC", "/Users/renhao/git/github/renquant-common/src"))
SCRATCH = Path(os.environ.get("RQ_STAGE1_SCRATCH",
                              str(Path.home() / ".cache" / "renquant-universe-stage1")))

DATA = UMBRELLA / "data"
OHLCV = DATA / "ohlcv"
SEC_DAILY = DATA / "sec_fundamentals_daily.parquet"
STRATEGY_DIR = UMBRELLA / "backtesting" / "renquant_104"   # live-deploy-mechanism-104
WATCHLIST_CFG = STRAT104 / "configs" / "strategy_config.golden.json"

OUT_JSON = HERE / "2026-08-18-universe-stage1-results.json"
OUT_CSV = HERE / "2026-08-18-universe-stage1-obs.csv"

# ---------------------------------------------------------- frozen constants
CORPUS_START = "2021-07-01"            # spec §3
CORPUS_END = "2026-02-13"              # spec §3
SNAPSHOT_EDGE = "2026-05-08"           # spec §3/§6 — no label past this date
SAMPLE_STEP = 5                        # every 5th trading day (spec §3)
HORIZONS = (20, 60)                    # secondary, primary (spec §4)
PRIMARY_H = 60                         # verdict at h=60 ONLY (spec §5)
PLACEBO_LAG_MULT = 2                   # placebo lag = 2h trading days (spec §4)
NAMES_PER_DATE_FLOOR = 50              # the #987 harness floor (U5)
MIN_CELL_N = 15                        # spec §4 DGTW cell floor
DECILE_FRAC = 0.10                     # top decile by score (spec §4)
BLOCK_T_MIN = 1.0                      # spec §5 bar 2
POS_BLOCK_FRAC_MIN = 0.5              # spec §5 bar 3 (strictly greater)
EXPECTED_BLOCKS = {20: 58, 60: 19}     # spec §5 — asserted exactly (U4)
EXPECTED_WEEKLY_N = 231                # spec §5 derived count (U4: |n-231|<=2)
WEEKLY_N_TOL = 2
MIN_BLOCKS_WITH_DATA_H60 = 10          # U8 fail-closed floor (majority of 19)
BUCKET_NAMES_FLOOR = 10                # per-date floor for a bucket sub-decile
WATCHLIST_N = 145                      # spec §3 (exact)
EXPECTED_ARM_A_N = 609                 # spec §3 (~; U2 tolerance ±3%)
EXPECTED_ARM_B_N = 1955                # spec §3 (~; U2 tolerance ±3%)
ARM_COUNT_TOL_FRAC = 0.03
PX_MIN, PX_MAX = 5.0, 400.0            # spec §3
ADV_MIN_A, ADV_MIN_B = 5e6, 1e6        # spec §3
MIN_LISTING_ROWS = 756                 # 3y (U2 convention)
ADV_WINDOW_ROWS = 63                   # 63d-ADV (spec §3)
MIN_INVENTORY_ROWS = 60                # feasibility-memo scan floor
# RS-5 frozen RT costs by 63d-ADV bucket (spec §4), decimal per round trip.
BUCKETS = (("adv_ge_25M", 25e6, float("inf"), 0.0025),
           ("adv_10_25M", 10e6, 25e6, 0.0040),
           ("adv_5_10M", 5e6, 10e6, 0.0060),
           ("adv_1_5M", 1e6, 5e6, None))      # uncostable — never in verdicts
COSTABLE_BUCKETS = ("adv_ge_25M", "adv_10_25M", "adv_5_10M")
# U3 positive control (units: per-date CS-sigma — see header).
POSITIVE_CONTROL_REF = 0.24038304426130444
POSITIVE_CONTROL_MIN = POSITIVE_CONTROL_REF / 3.0
CONTROL_Z_EPS = 1e-12                  # the panel builder's EPS
# U1 pins (copied from the golden config's components[0] on 2026-08-18;
# re-read + re-asserted against the live config at run time).
EXPECTED_ARTIFACT_RELPATH = "artifacts/prod/panel-ltr.alpha158_fund.json"
EXPECTED_FEATURE_N = 172
EXPECTED_KIND = "panel_ltr_xgboost"
EXPECTED_LABEL = "fwd_60d_excess"
EXPECTED_LOOKAHEAD = 60
MIN_CONTENT_PIN_HEX = 8                # blend_scorer.MIN_CONTENT_PIN_HEX
CHAR_COLS = ("STD60", "ROC60", "BETA60")   # the memo's DGTW characteristics
FUND_COLS = ("earnings_yield", "book_to_price", "gross_profitability",
             "roe", "asset_growth")


class RunVoidError(RuntimeError):
    """Instrument failure (U3) — the run is VOID, not evidence."""


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(f"FROZEN-GUARD FAILURE — STOP, do not adjust the spec: {msg}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ══════════════════════ pure functions (unit-tested) ═══════════════════════

def tercile_labels(s: pd.Series) -> pd.Series:
    """Memo-verbatim tercile assignment: qcut over rank(method='first')."""
    return pd.qcut(s.rank(method="first"), 3, labels=False)


def assign_cells(chars: pd.DataFrame) -> pd.Series:
    """vol x mom x beta tercile cell id per name (0..26), memo-verbatim."""
    t = {c: tercile_labels(chars[c]).astype(int) for c in CHAR_COLS}
    return t["STD60"] * 9 + t["ROC60"] * 3 + t["BETA60"]


def dgtw_adjust(labels: pd.Series, cells: pd.Series,
                min_cell: int = MIN_CELL_N) -> tuple[pd.Series, int]:
    """Self-excluded cell-mean adjustment; small cells UNADJUSTED-AND-FLAGGED.

    For a name in a cell with n >= min_cell: adjusted = label − (cell sum −
    own label)/(n−1). For a name in a smaller cell: adjusted = raw label,
    and the name counts toward the returned flag total (spec §4).
    """
    lab = labels.astype(float)
    cell_sum = lab.groupby(cells).transform("sum")
    cell_n = lab.groupby(cells).transform("count")
    bench = (cell_sum - lab) / (cell_n - 1).replace(0, np.nan)
    big = cell_n >= min_cell
    adjusted = lab.where(~big, lab - bench)
    n_flagged = int((~big).sum())
    return adjusted, n_flagged


def top_decile_n(n: int, frac: float = DECILE_FRAC) -> int:
    return max(1, int(math.floor(n * frac)))


def decile_spread_pair(adjusted: pd.Series, gen: pd.Series, pla: pd.Series,
                       frac: float = DECILE_FRAC
                       ) -> tuple[float, float, tuple[str, ...]]:
    """Both legs' top-decile spreads over ONE shared cross-section.

    spread = mean(adjusted over the leg's top decile by score) − mean(adjusted
    over ALL names) — the memo's daily_top_spread construction. Each leg
    selects its own decile BY ITS OWN SCORES over identical names. Returns
    (spread_genuine, spread_placebo, genuine_decile_names).
    """
    n = len(adjusted)
    k = top_decile_n(n, frac)
    base = float(adjusted.mean())
    top_g = gen.nlargest(k).index
    top_p = pla.nlargest(k).index
    sp_g = float(adjusted.loc[top_g].mean()) - base
    sp_p = float(adjusted.loc[top_p].mean()) - base
    return sp_g, sp_p, tuple(str(x) for x in top_g)


def paired_spread_cross_section(
    gen: pd.Series, pla: pd.Series, labels: pd.Series, chars: pd.DataFrame,
    *, names_floor: int = NAMES_PER_DATE_FLOOR, min_cell: int = MIN_CELL_N,
    frac: float = DECILE_FRAC,
) -> dict | None:
    """ONE shared cross-section for both legs (U5; G7-corrected lineage).

    Intersect finite genuine score, finite placebo score, finite label AND
    finite STD60/ROC60/BETA60 FIRST (the memo's own dropna set); apply the
    names floor to that shared set; build cells + DGTW adjustment once; both
    deciles select over exactly those names. Returns None when the shared
    set misses the floor. The returned dict carries the shared names so the
    caller ASSERTS identity rather than trusting it, plus the adjusted
    series for bucket-restricted re-selection.
    """
    df = pd.concat({"gen": gen, "pla": pla, "lab": labels}, axis=1, join="inner")
    df = df.join(chars, how="inner").dropna()
    df = df[np.isfinite(df).all(axis=1)]
    n = len(df)
    if n < names_floor:
        return None
    cells = assign_cells(df[list(CHAR_COLS)])
    adjusted, n_flagged = dgtw_adjust(df["lab"], cells, min_cell)
    sp_g, sp_p, top_g = decile_spread_pair(adjusted, df["gen"], df["pla"], frac)
    return {
        "names": tuple(str(x) for x in df.index),
        "n": n,
        "spread_gen": sp_g,
        "spread_pla": sp_p,
        "delta": sp_g - sp_p,
        "top_gen": top_g,
        "n_flagged_unadjusted": n_flagged,
        "adjusted": adjusted,
        "gen": df["gen"],
        "pla": df["pla"],
    }


def block_of_obs(k: int, blocks_per: int) -> int:
    """Weekly grid obs k belongs to block floor(k/blocks_per) (G9)."""
    return k // blocks_per


def complete_blocks(n_obs: int, blocks_per: int) -> int:
    """Number of COMPLETE blocks on an n_obs weekly grid (G9)."""
    return n_obs // blocks_per


def block_t_stats(obs_deltas: list[tuple[int, float]], blocks_per: int,
                  n_complete: int) -> dict:
    """Block means over kept obs in COMPLETE blocks; block-t; positive frac.

    obs_deltas: [(obs_index, delta), ...] for KEPT obs only. A block with
    zero kept obs has no data. block-t = mean / (sd(ddof=1)/sqrt(n)) —
    df = n_blocks_with_data − 1 Student-t context, never 1.96 (spec §5).
    """
    block_vals: dict[int, list[float]] = {}
    for k, d in obs_deltas:
        b = block_of_obs(k, blocks_per)
        if b < n_complete:
            block_vals.setdefault(b, []).append(float(d))
    bdel = np.array([float(np.mean(v)) for _, v in sorted(block_vals.items())])
    n_bd = len(bdel)
    if n_bd >= 2 and float(bdel.std(ddof=1)) > 0:
        bt = float(bdel.mean() / (bdel.std(ddof=1) / np.sqrt(n_bd)))
        pos = float((bdel > 0).mean())
    else:
        bt, pos = float("nan"), float("nan")
    return {"n_blocks_with_data": n_bd, "block_t": bt, "pos_block_frac": pos,
            "block_deltas": [float(x) for x in bdel]}


def adv_bucket(adv_usd: float) -> str | None:
    """RS-5 bucket for a 63d-ADV dollar value; None below $1M."""
    for name, lo, hi, _cost in BUCKETS:
        if lo <= adv_usd < hi:
            return name
    return None


def bucket_rt_cost(bucket: str | None) -> float | None:
    """Round-trip cost (decimal) for a bucket; None = uncostable."""
    for name, _lo, _hi, cost in BUCKETS:
        if name == bucket:
            return cost
    return None


def cost_drag_series(top_sets: list[tuple[int, tuple[str, ...]]],
                     cost_by_name: dict[str, float], h: int,
                     step: int = SAMPLE_STEP) -> dict[int, float]:
    """Per-obs cost drag on the genuine decile (frozen formula, header).

    drag_t = (h/step) * sum(RT cost of names ENTERING the decile at t)
             / n_top(t).
    Consecutive KEPT obs define turnover; the first kept obs is a full
    entry. Every decile name must be costable (verdict arms exclude the
    $1-5M band by construction) — a missing cost raises, fail-closed.
    """
    factor = h / step
    drags: dict[int, float] = {}
    prev: frozenset[str] = frozenset()
    for k, top in top_sets:
        cur = frozenset(top)
        entering = cur - prev
        total = 0.0
        for name in entering:
            c = cost_by_name.get(name)
            if c is None:
                raise AssertionError(
                    f"FROZEN-GUARD FAILURE — uncostable name {name!r} in a "
                    "costed decile (the $1-5M band must never reach a "
                    "verdict arm)")
            total += float(c)
        drags[k] = factor * total / max(1, len(cur))
        prev = cur
    return drags


def triage_verdict(*, net_delta: float, block_t: float, pos_frac: float,
                   n_blocks_with_data: int, transfer_ok: bool,
                   min_blocks: int = MIN_BLOCKS_WITH_DATA_H60) -> tuple[str, str]:
    """The §5 four-condition triage rule + the U8 fail-closed floor.

    Returns (verdict, reason): PASS (triage) | DEPRIORITIZED |
    UNMEASURABLE(insufficient_blocks).
    """
    if n_blocks_with_data < min_blocks:
        return ("UNMEASURABLE", f"insufficient_blocks: {n_blocks_with_data} < {min_blocks}")
    conds = [
        (f"net_delta={net_delta:+.6f} <= 0", bool(net_delta > 0)),
        (f"block_t={block_t:.3f} < {BLOCK_T_MIN}", bool(block_t >= BLOCK_T_MIN)),
        (f"pos_block_frac={pos_frac:.3f} <= {POS_BLOCK_FRAC_MIN}",
         bool(pos_frac > POS_BLOCK_FRAC_MIN)),
        ("transfer: no costable bucket with ArmA >= ArmW", bool(transfer_ok)),
    ]
    failed = [msg for msg, ok in conds if not ok]
    if not failed:
        return ("PASS (triage)", "all four §5 conditions met")
    return ("DEPRIORITIZED", "; ".join(failed))


def positive_control_ok(mean_spread_z: float) -> tuple[bool, str]:
    """U3: sign-preserving lower bound vs the committed reference (header)."""
    if not np.isfinite(mean_spread_z):
        return False, "control spread is not finite"
    if mean_spread_z < POSITIVE_CONTROL_MIN:
        return False, (f"ArmW control spread {mean_spread_z:+.5f} sigma < "
                       f"frozen floor {POSITIVE_CONTROL_MIN:+.5f} "
                       f"(= ref {POSITIVE_CONTROL_REF:+.5f} / 3)")
    note = ""
    if mean_spread_z > 3 * POSITIVE_CONTROL_REF:
        note = (" [telemetry: > 3x ref — in-sample inflation, expected; "
                "see header U3]")
    return True, f"ArmW control spread {mean_spread_z:+.5f} sigma >= floor{note}"


def content_pin_matches(expected: str, observed_hex: str) -> bool:
    """Production's abbrev-tolerant content-pin compare (blend_scorer)."""
    e = str(expected or "").strip().lower().removeprefix("sha256:")
    o = str(observed_hex or "").strip().lower().removeprefix("sha256:")
    if not e or not o or min(len(e), len(o)) < MIN_CONTENT_PIN_HEX:
        return False
    shorter, longer = (e, o) if len(e) <= len(o) else (o, e)
    return longer.startswith(shorter)


def config_fp_pin_matches(expected: str, observed: str) -> bool:
    """Production's verbatim config-fp compare (sha256: tolerant, no abbrev)."""
    if not expected or not observed:
        return False
    e = str(expected).strip().split(":", 1)[-1]
    o = str(observed).strip().split(":", 1)[-1]
    return bool(e) and e == o


# ═══════════════════════ IO / guards (run-time only) ═══════════════════════

def _write_guard(path: Path) -> Path:
    """U7: every write target must be under HERE or SCRATCH, never umbrella."""
    p = path.resolve()
    allowed = any(str(p).startswith(str(root.resolve()) + os.sep) or p == root.resolve()
                  for root in (HERE, SCRATCH))
    _assert(allowed, f"write target {p} outside HERE/SCRATCH (U7)")
    _assert(not str(p).startswith(str(UMBRELLA.resolve()) + os.sep),
            f"write target {p} inside the umbrella tree (U7)")
    return p


def assert_one_shot(outputs=(OUT_JSON, OUT_CSV)) -> None:
    """U10: refuse to run when any output already exists — one shot, ever."""
    existing = [str(p) for p in outputs if Path(p).exists()]
    _assert(not existing,
            "one-shot marker: output(s) already exist, this triage has been "
            f"run — re-running is FORBIDDEN (U10): {existing}")


def assert_runner_matches_main() -> dict:
    """U11: the executing runner's bytes must equal origin/main's copy,
    compared AFTER a mandatory fetch (orch#997: without the fetch the
    guard's authority is a local cache). Fetch failure fails CLOSED."""
    me = Path(__file__).resolve()
    top = subprocess.run(["git", "-C", str(me.parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True).stdout.strip()
    rel = me.relative_to(Path(top))
    fetch = subprocess.run(["git", "-C", top, "fetch", "--quiet", "origin", "main"],
                           capture_output=True, text=True)
    _assert(fetch.returncode == 0,
            "cannot fetch origin/main — refusing to validate against a stale "
            f"local ref (orch#997, fail closed): {fetch.stderr.strip()}")
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


def _git_head(repo: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return "unavailable"


def verify_served_pin() -> dict:
    """U1: load + byte-verify the served PANEL component pin (header)."""
    cfg = json.loads(WATCHLIST_CFG.read_text())
    ps = cfg["ranking"]["panel_scoring"]
    _assert(ps.get("kind") == "blend",
            f"served scorer kind is {ps.get('kind')!r}, expected 'blend' — "
            "the serving config changed; re-freeze before running")
    comps = ps.get("components") or []
    _assert(len(comps) >= 1, "served blend has no components")
    c0 = comps[0]
    _assert(str(c0.get("artifact_path")) == EXPECTED_ARTIFACT_RELPATH,
            f"components[0].artifact_path={c0.get('artifact_path')!r} != "
            f"frozen {EXPECTED_ARTIFACT_RELPATH!r}")
    art_path = STRATEGY_DIR / EXPECTED_ARTIFACT_RELPATH
    _assert(art_path.is_file(), f"served artifact missing: {art_path}")
    file_sha = _sha256(art_path)
    _assert(content_pin_matches(str(c0.get("expected_content_sha256")), file_sha),
            f"served-pin BYTE-IDENTITY mismatch: config pins "
            f"{c0.get('expected_content_sha256')!r}, file is sha256:{file_sha}")
    art = json.loads(art_path.read_text())
    _assert(config_fp_pin_matches(str(c0.get("expected_config_fingerprint")),
                                  str(art.get("config_fingerprint"))),
            f"config_fingerprint mismatch: pinned "
            f"{c0.get('expected_config_fingerprint')!r} vs artifact "
            f"{art.get('config_fingerprint')!r}")
    _assert(art.get("kind") == EXPECTED_KIND, f"artifact kind {art.get('kind')!r}")
    feats = [str(c) for c in art.get("feature_cols") or []]
    _assert(len(feats) == EXPECTED_FEATURE_N,
            f"artifact has {len(feats)} feature_cols, expected {EXPECTED_FEATURE_N}")
    _assert(art.get("label_col") == EXPECTED_LABEL and
            int(art.get("lookahead_days", -1)) == EXPECTED_LOOKAHEAD,
            "artifact label/lookahead not the frozen fwd_60d_excess/60")
    wl = sorted(dict.fromkeys(str(t) for t in cfg["watchlist"]))
    _assert(len(wl) == WATCHLIST_N, f"watchlist n={len(wl)} != {WATCHLIST_N} (U2)")
    return {
        "artifact": art, "artifact_path": str(art_path),
        "artifact_file_sha256": file_sha,
        "config_sha256": _sha256(WATCHLIST_CFG),
        "watchlist": wl,
        "component1_context": {k: v for k, v in (comps[1] if len(comps) > 1 else {}).items()
                               if not k.startswith("_")},
        "trained_date": art.get("trained_date"),
    }


def load_booster(art: dict):
    import xgboost as xgb  # noqa: PLC0415
    booster = xgb.Booster()
    booster.load_model(bytearray(str(art["booster_raw_json"]).encode("utf-8")))
    return booster


def build_grid(cal: pd.DatetimeIndex) -> dict:
    """U4/U6: corpus grid + per-horizon label-edge trims (adapted G1)."""
    corpus = cal[(cal >= CORPUS_START) & (cal <= CORPUS_END)]
    _assert(str(corpus[0].date()) == CORPUS_START and
            str(corpus[-1].date()) == CORPUS_END,
            "corpus endpoints are not trading days of the SPY calendar")
    grid = corpus[::SAMPLE_STEP]
    n = len(grid)
    _assert(abs(n - EXPECTED_WEEKLY_N) <= WEEKLY_N_TOL,
            f"weekly grid n={n} deviates from the frozen {EXPECTED_WEEKLY_N} "
            f"by more than {WEEKLY_N_TOL}")
    i0 = cal.get_loc(corpus[0])
    max_lag = PLACEBO_LAG_MULT * max(HORIZONS)
    _assert(i0 >= max_lag, "not enough pre-corpus calendar for the placebo lag")
    ext_idx = list(range(i0 - max_lag, i0 + SAMPLE_STEP * (n - 1) + 1, SAMPLE_STEP))
    _assert(cal[ext_idx[-1]] == grid[-1], "extended grid misaligned with grid end")
    edge = pd.Timestamp(SNAPSHOT_EDGE)
    kept_obs: dict[int, list[int]] = {}
    dropped_label_edge: dict[int, list[str]] = {}
    for h in HORIZONS:
        _assert(PLACEBO_LAG_MULT * h % SAMPLE_STEP == 0,
                "placebo lag not aligned to the sampling step")
        keep, drop = [], []
        for k in range(n):
            j = i0 + SAMPLE_STEP * k
            _assert(j + h < len(cal), f"SPY calendar too short for h={h} labels")
            if cal[j + h] <= edge:
                keep.append(k)
            else:
                drop.append(str(cal[j].date()))
        kept_obs[h] = keep
        dropped_label_edge[h] = drop
        n_complete = complete_blocks(n, h // SAMPLE_STEP)
        _assert(n_complete >= EXPECTED_BLOCKS[h],
                f"fewer than {EXPECTED_BLOCKS[h]} complete blocks at h={h}")
        if drop:
            first_dropped = n - len(drop)
            _assert(first_dropped >= EXPECTED_BLOCKS[h] * (h // SAMPLE_STEP),
                    f"label-edge trim reaches into a complete block at h={h}")
    _assert(len(dropped_label_edge[60]) <= 1,
            f"h=60 label-edge trim dropped {len(dropped_label_edge[60])} obs, "
            "expected <= 1 (the known 2026-02-13 -> 2026-05-12 overshoot)")
    _assert(len(dropped_label_edge[20]) == 0,
            "h=20 labels must all mature inside the snapshot edge")
    return {"cal": cal, "corpus": corpus, "grid": grid, "n": n, "i0": i0,
            "ext_dates": [cal[i] for i in ext_idx], "kept_obs": kept_obs,
            "dropped_label_edge": dropped_label_edge}


def scan_inventory() -> pd.DataFrame:
    """U2: snapshot-convention screen stats per on-disk OHLCV name."""
    tickers = sorted(p.name for p in OHLCV.iterdir()
                     if (p / "1d.parquet").is_file())
    rows = []
    for t in tickers:
        p = OHLCV / t / "1d.parquet"
        try:
            df = pd.read_parquet(p, columns=["close", "volume"])
        except Exception:  # noqa: BLE001
            continue
        if len(df) < MIN_INVENTORY_ROWS:
            continue
        tail = df.tail(ADV_WINDOW_ROWS)
        idx = pd.to_datetime(df.index)
        rows.append({
            "ticker": t,
            "px": float(tail["close"].median()),
            "adv_usd": float((tail["close"] * tail["volume"]).median()),
            "nrows": int(len(df)),
            "dmin": idx.min(), "dmax": idx.max(),
        })
    return pd.DataFrame(rows).set_index("ticker")


def construct_universes(inv: pd.DataFrame, watchlist: list[str],
                        fund_tickers: set[str]) -> dict:
    """U2: recompute the §3 cascades; assert counts; record every stage."""
    start = pd.Timestamp(CORPUS_START)
    nonwl = inv[~inv.index.isin(set(watchlist))]
    px_ok = nonwl[(nonwl.px >= PX_MIN) & (nonwl.px <= PX_MAX)]
    age_ok = px_ok[px_ok.nrows >= MIN_LISTING_ROWS]
    hist_ok = age_ok[age_ok.dmin <= start]
    a_adv = hist_ok[hist_ok.adv_usd >= ADV_MIN_A]
    arm_a = a_adv[a_adv.index.isin(fund_tickers)]
    arm_b = hist_ok[hist_ok.adv_usd >= ADV_MIN_B]
    counts = {
        "inventory": int(len(inv)),
        "non_watchlist": int(len(nonwl)),
        "px_5_400": int(len(px_ok)),
        "listing_ge_3y": int(len(age_ok)),
        "history_reaches_corpus_start": int(len(hist_ok)),
        "arm_a_adv_ge_5M": int(len(a_adv)),
        "arm_a_final": int(len(arm_a)),
        "arm_b_final": int(len(arm_b)),
    }
    tol_a = int(round(EXPECTED_ARM_A_N * ARM_COUNT_TOL_FRAC))
    tol_b = int(round(EXPECTED_ARM_B_N * ARM_COUNT_TOL_FRAC))
    _assert(abs(len(arm_a) - EXPECTED_ARM_A_N) <= tol_a,
            f"Arm A n={len(arm_a)} outside {EXPECTED_ARM_A_N}±{tol_a} (U2)")
    _assert(abs(len(arm_b) - EXPECTED_ARM_B_N) <= tol_b,
            f"Arm B n={len(arm_b)} outside {EXPECTED_ARM_B_N}±{tol_b} (U2)")
    return {"arm_a": sorted(arm_a.index), "arm_b": sorted(arm_b.index),
            "counts": counts,
            "adv_by_name": inv["adv_usd"].to_dict()}


def _ticker_features(ticker: str, ext_dates: list[pd.Timestamp],
                     compute_frame) -> pd.DataFrame | None:
    """Raw alpha158 rows at extended-grid dates (bar-exists-only; cached)."""
    p = OHLCV / ticker / "1d.parquet"
    if not p.is_file():
        return None
    sha = _sha256(p)
    cache = SCRATCH / "features" / f"{ticker}.parquet"
    if cache.is_file():
        cached = pd.read_parquet(cache)
        if len(cached) and "_src_sha" in cached.columns and \
                str(cached["_src_sha"].iloc[0]) == sha:
            return cached.drop(columns=["_src_sha"])
    try:
        raw = pd.read_parquet(p)[["open", "high", "low", "close", "volume"]]
    except Exception:  # noqa: BLE001
        return None
    raw.index = pd.to_datetime(raw.index)
    raw = raw.sort_index()
    frame = compute_frame(raw)
    have = [d for d in ext_dates if d in raw.index and d in frame.index]
    if not have:
        return None
    out = frame.loc[have].copy()
    out["_src_sha"] = sha
    _write_guard(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out.drop(columns=["_src_sha"])


def build_arm_corpus(arm: str, tickers: list[str], grid_info: dict,
                     full_recipe: bool) -> dict:
    """Score/char/close panels for one arm over the extended grid.

    full_recipe=True (Arms A/W): the 14 extras via the committed TRAIN
    recipe (renquant_base_data.alpha158_fund_panel builders — header).
    full_recipe=False (Arm B): extras absent -> the serve transform's
    fillna(0.0) is the spec's NaN-variant.
    """
    from renquant_base_data.alpha158_ops import compute_alpha158_frame  # noqa: PLC0415
    ext_dates = grid_info["ext_dates"]
    blocks = []
    closes = {}
    for i, t in enumerate(tickers):
        feats = _ticker_features(t, ext_dates, compute_alpha158_frame)
        if feats is None or feats.empty:
            continue
        f = feats.reset_index().rename(columns={"index": "date", "Date": "date"})
        f.insert(0, "ticker", t)
        blocks.append(f)
        closes[t] = pd.read_parquet(OHLCV / t / "1d.parquet",
                                    columns=["close"])["close"]
        if (i + 1) % 200 == 0:
            print(f"    [{arm}] features {i + 1}/{len(tickers)}", flush=True)
    panel = pd.concat(blocks, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])

    if full_recipe:
        from renquant_base_data.alpha158_fund_panel import (  # noqa: PLC0415
            _add_pead_features, _add_sue_features, _add_sentiment_features,
            _merge_fundamentals)
        cols = ["date", "ticker", *FUND_COLS,
                *[f"{c}_source_available_at" for c in FUND_COLS]]
        fund_raw = pd.read_parquet(SEC_DAILY)
        fund_raw = fund_raw[[c for c in cols if c in fund_raw.columns]]
        fund_raw["date"] = pd.to_datetime(fund_raw["date"])
        fund_raw = fund_raw[fund_raw["ticker"].isin(set(panel["ticker"]))]
        # U9 PIT: no value visible before its filing is, for every column
        # that declares an availability date.
        for c in FUND_COLS:
            ac = f"{c}_source_available_at"
            if ac in fund_raw.columns:
                served = fund_raw.dropna(subset=[c, ac])
                _assert(bool((pd.to_datetime(served[ac]) <= served["date"]).all()),
                        f"sec_fundamentals_daily rows visible before "
                        f"available_at for {c} (U9)")
        fund = fund_raw[["ticker", "date", *[c for c in FUND_COLS
                                             if c in fund_raw.columns]]]
        panel = _merge_fundamentals(panel, fund)
        panel = _add_pead_features(panel, data_dir=DATA)
        panel = _add_sue_features(panel, data_dir=DATA)
        panel = _add_sentiment_features(panel, data_dir=DATA)
    return {"panel": panel, "closes": closes}


def score_arm(arm: str, corpus: dict, art: dict, booster, grid_info: dict) -> dict:
    """Served-pin scoring per extended-grid date (serve-verbatim transform)."""
    from renquant_pipeline.kernel.panel_pipeline.feature_transform import (  # noqa: PLC0415
        transform_feature_frame)
    import xgboost as xgb  # noqa: PLC0415
    feats = [str(c) for c in art["feature_cols"]]
    panel = corpus["panel"]
    scores: dict[pd.Timestamp, pd.Series] = {}
    chars: dict[pd.Timestamp, pd.DataFrame] = {}
    for d, grp in panel.groupby("date"):
        g = grp.set_index("ticker")
        chars[d] = g[list(CHAR_COLS)].astype(float)
        X = g.reindex(columns=feats, fill_value=float("nan"))
        Xt = transform_feature_frame(X, feats, art, source_space="raw")
        pred = booster.predict(xgb.DMatrix(Xt.values.astype(float)))
        s = pd.Series(pred, index=Xt.index.astype(str), dtype=float)
        scores[d] = s[np.isfinite(s)]
    for d in grid_info["ext_dates"]:
        scores.setdefault(d, pd.Series(dtype=float))
        chars.setdefault(d, pd.DataFrame(columns=list(CHAR_COLS)))
    return {"scores": scores, "chars": chars}


def build_labels(corpus: dict, grid_info: dict) -> dict[int, dict]:
    """G5-verbatim raw h-day forward excess-over-SPY labels per grid date."""
    cal = grid_info["cal"]
    spy = pd.read_parquet(OHLCV / "SPY" / "1d.parquet", columns=["close"])["close"]
    spy = spy.reindex(cal)
    cl = pd.DataFrame({t: s.reindex(cal) for t, s in corpus["closes"].items()},
                      index=cal)
    out: dict[int, dict] = {}
    edge = pd.Timestamp(SNAPSHOT_EDGE)
    for h in HORIZONS:
        fwd = cl.shift(-h) / cl - 1.0
        spy_fwd = spy.shift(-h) / spy - 1.0
        ex = fwd.sub(spy_fwd, axis=0)
        per_date = {}
        for k in grid_info["kept_obs"][h]:
            j = grid_info["i0"] + SAMPLE_STEP * k
            d = cal[j]
            _assert(cal[j + h] <= edge, f"label past snapshot edge at {d} (U6)")
            per_date[k] = ex.loc[d].dropna()
        out[h] = per_date
    return out


def analyze_arm(arm: str, scored: dict, labels: dict, grid_info: dict, h: int,
                *, cost_by_name: dict[str, float] | None = None,
                bucket_by_name: dict[str, str] | None = None,
                z_labels: bool = False) -> dict:
    """Paired per-obs spreads, Δ series, blocks, costs, buckets for one arm."""
    from scipy.stats import spearmanr  # noqa: PLC0415
    cal, i0 = grid_info["cal"], grid_info["i0"]
    obs_rows, kept, top_sets = [], [], []
    dropped = {"floor_paired": 0}
    bucket_obs: dict[str, list] = {b: [] for b in
                                   set((bucket_by_name or {}).values()) - {None}}
    for k in grid_info["kept_obs"][h]:
        d = cal[i0 + SAMPLE_STEP * k]
        lag_date = cal[i0 + SAMPLE_STEP * k - PLACEBO_LAG_MULT * h]
        gen = scored["scores"][d]
        pla = scored["scores"][lag_date]
        lab = labels[h][k]
        if z_labels and len(lab) > 1:
            lab = (lab - lab.mean()) / (lab.std(ddof=1) + CONTROL_Z_EPS)
        res = paired_spread_cross_section(gen, pla, lab, scored["chars"][d])
        row = {"arm": arm, "h": h, "obs_index": k, "date": str(d.date()),
               "placebo_score_date": str(lag_date.date()),
               "block": block_of_obs(k, h // SAMPLE_STEP),
               "units": "cs_sigma" if z_labels else "raw_excess",
               "n_pairs_genuine_leg_only": int(np.isfinite(gen).sum()),
               "n_pairs_placebo_leg_only": int(np.isfinite(pla).sum())}
        if res is None:
            dropped["floor_paired"] += 1
            row.update({"kept": False, "n_pairs_shared": 0})
            obs_rows.append(row)
            continue
        # U5: identity asserted, never trusted.
        _assert(len(set(res["names"])) == len(res["names"]) and
                len(res["names"]) >= NAMES_PER_DATE_FLOOR,
                f"paired-identity violation at {d.date()} (U5)")
        ic_g = ic_p = float("nan")
        if not z_labels:
            lab_shared = lab.loc[list(res["names"])]
            ic_g = float(spearmanr(res["gen"], lab_shared).statistic)
            ic_p = float(spearmanr(res["pla"], lab_shared).statistic)
        row.update({"kept": True, "n_pairs_shared": res["n"],
                    "spread_gen": res["spread_gen"],
                    "spread_pla": res["spread_pla"], "delta": res["delta"],
                    "n_flagged_unadjusted": res["n_flagged_unadjusted"],
                    "ic_genuine": ic_g, "ic_placebo": ic_p})
        obs_rows.append(row)
        kept.append((k, res))
        top_sets.append((k, res["top_gen"]))
        if bucket_by_name:
            for b in bucket_obs:
                names_b = [t for t in res["names"] if bucket_by_name.get(t) == b]
                if len(names_b) < BUCKET_NAMES_FLOOR:
                    continue
                sp_g, sp_p, top_b = decile_spread_pair(
                    res["adjusted"].loc[names_b], res["gen"].loc[names_b],
                    res["pla"].loc[names_b])
                bucket_obs[b].append((k, sp_g - sp_p, top_b, len(names_b)))

    blocks_per = h // SAMPLE_STEP
    n_complete = EXPECTED_BLOCKS[h]
    deltas = [(k, r["delta"]) for k, r in kept]
    bstats = block_t_stats(deltas, blocks_per, n_complete)
    gross_delta = float(np.mean([d for _, d in deltas])) if deltas else float("nan")
    out = {
        "n_obs_in_horizon": len(grid_info["kept_obs"][h]),
        "n_kept": len(kept), "dropped": dropped,
        "mean_spread_gen": float(np.mean([r["spread_gen"] for _, r in kept]))
        if kept else float("nan"),
        "mean_spread_pla": float(np.mean([r["spread_pla"] for _, r in kept]))
        if kept else float("nan"),
        "delta_gross": gross_delta,
        "mean_ic_genuine": float(np.nanmean([r2.get("ic_genuine", float("nan"))
                                             for r2 in obs_rows if r2.get("kept")]))
        if kept and not z_labels else None,
        **bstats,
    }
    if cost_by_name is not None and kept:
        drags = cost_drag_series(top_sets, cost_by_name, h)
        net = [(k, r["delta"] - drags[k]) for k, r in kept]
        out["mean_cost_drag"] = float(np.mean(list(drags.values())))
        out["delta_net"] = float(np.mean([d for _, d in net]))
        out["net_block"] = block_t_stats(net, blocks_per, n_complete)
        for row in obs_rows:
            if row.get("kept"):
                row["cost_drag"] = drags[row["obs_index"]]
                row["delta_net"] = row["delta"] - drags[row["obs_index"]]
    if bucket_by_name:
        per_bucket = {}
        for b, obs in bucket_obs.items():
            if not obs:
                per_bucket[b] = {"n_kept": 0}
                continue
            bd = [(k, d) for k, d, _t, _n in obs]
            entry = {"n_kept": len(obs),
                     "delta_gross": float(np.mean([d for _, d in bd])),
                     "mean_names": float(np.mean([n for _, _d, _t, n in obs])),
                     **block_t_stats(bd, blocks_per, n_complete)}
            cost = bucket_rt_cost(b)
            if cost is not None:
                drags_b = cost_drag_series(
                    [(k, t) for k, _d, t, _n in obs],
                    {t: cost for _, _d, tt, _n in obs for t in tt}, h)
                entry["delta_net"] = float(np.mean(
                    [d - drags_b[k] for k, d in bd]))
                entry["costable"] = True
            else:
                entry["costable"] = False
                entry["note"] = "uncostable ($1-5M) — exploratory only, never a verdict input"
            per_bucket[b] = entry
        out["per_bucket"] = per_bucket
    return {"summary": out, "obs_rows": obs_rows}


def main() -> None:
    t_start = time.time()
    assert_one_shot()                          # U10 — one shot per corpus
    runner_id = assert_runner_matches_main()   # U11 — reviewed-before-run, fetch-first
    SCRATCH.mkdir(parents=True, exist_ok=True)
    _write_guard(OUT_JSON)
    _write_guard(OUT_CSV)
    for p in (BASEDATA_SRC, PIPELINE_SRC, COMMON_SRC):
        sys.path.insert(0, str(p))

    print("[1/8] U1 served-pin byte-identity ...", flush=True)
    pin = verify_served_pin()
    art = pin["artifact"]
    booster = load_booster(art)

    print("[2/8] U4/U6 grid + label-edge trims ...", flush=True)
    spy_close = pd.read_parquet(OHLCV / "SPY" / "1d.parquet",
                                columns=["close"])["close"]
    g = build_grid(pd.DatetimeIndex(pd.to_datetime(spy_close.index)))

    print("[3/8] U2 universe recompute ...", flush=True)
    inv = scan_inventory()
    fund_tickers = set(pd.read_parquet(SEC_DAILY, columns=["ticker"])
                       ["ticker"].unique())
    uni = construct_universes(inv, pin["watchlist"], fund_tickers)
    print(f"    counts: {uni['counts']}", flush=True)

    bucket_by_name = {t: adv_bucket(uni["adv_by_name"].get(t, float("nan")))
                      for t in uni["arm_a"] + uni["arm_b"]}
    cost_by_name_a = {t: bucket_rt_cost(bucket_by_name[t])
                      for t in uni["arm_a"]}
    _assert(all(c is not None for c in cost_by_name_a.values()),
            "an Arm-A name has no costable bucket — the $1-5M exclusion leaked")

    print("[4/8] Arm W corpus + scoring (positive control FIRST, U3) ...", flush=True)
    corpus_w = build_arm_corpus("W", pin["watchlist"], g, full_recipe=True)
    scored_w = score_arm("W", corpus_w, art, booster, g)
    labels_w = build_labels(corpus_w, g)
    control = analyze_arm("W", scored_w, labels_w, g, PRIMARY_H, z_labels=True)
    ok, reason = positive_control_ok(control["summary"]["mean_spread_gen"])
    print(f"    U3 positive control: {reason}", flush=True)
    if not ok:
        payload = {
            "verdict": "VOID (instrument failure — U3 positive control)",
            "reason": reason, "arm_w_control": control["summary"],
            "pins": {"artifact_file_sha256": pin["artifact_file_sha256"],
                     "runner_identity": runner_id},
        }
        OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        raise RunVoidError(reason)
    arm_w = {h: analyze_arm("W", scored_w, labels_w, g, h) for h in HORIZONS}

    print("[5/8] Arm A corpus + scoring (only after the control held) ...", flush=True)
    corpus_a = build_arm_corpus("A", uni["arm_a"], g, full_recipe=True)
    scored_a = score_arm("A", corpus_a, art, booster, g)
    labels_a = build_labels(corpus_a, g)
    arm_a = {h: analyze_arm("A", scored_a, labels_a, g, h,
                            cost_by_name=cost_by_name_a,
                            bucket_by_name={t: bucket_by_name[t]
                                            for t in uni["arm_a"]})
             for h in HORIZONS}

    print("[6/8] Arm B corpus + scoring (exploratory, labeled) ...", flush=True)
    corpus_b = build_arm_corpus("B", uni["arm_b"], g, full_recipe=False)
    scored_b = score_arm("B", corpus_b, art, booster, g)
    labels_b = build_labels(corpus_b, g)
    arm_b = {h: analyze_arm("B", scored_b, labels_b, g, h,
                            bucket_by_name={t: bucket_by_name[t]
                                            for t in uni["arm_b"]})
             for h in HORIZONS}

    print("[7/8] §5 triage verdict (h=60, Arm A) ...", flush=True)
    a60 = arm_a[PRIMARY_H]["summary"]
    w60 = arm_w[PRIMARY_H]["summary"]
    per_bucket = a60.get("per_bucket", {})
    transfer_ok = any(
        b in per_bucket and per_bucket[b].get("n_kept", 0) > 0 and
        np.isfinite(per_bucket[b].get("delta_gross", float("nan"))) and
        per_bucket[b]["delta_gross"] >= w60["delta_gross"]
        for b in COSTABLE_BUCKETS)
    verdict, why = triage_verdict(
        net_delta=a60.get("delta_net", float("nan")),
        block_t=a60.get("block_t", float("nan")),
        pos_frac=a60.get("pos_block_frac", float("nan")),
        n_blocks_with_data=a60.get("n_blocks_with_data", 0),
        transfer_ok=transfer_ok)

    print("[8/8] outputs ...", flush=True)
    all_rows = []
    for arm_res in (arm_w, arm_a, arm_b):
        for h in HORIZONS:
            all_rows.extend(arm_res[h]["obs_rows"])
    all_rows.extend(control["obs_rows"])
    pd.DataFrame(all_rows).to_csv(OUT_CSV, index=False)

    out = {
        "spec": "doc/research/2026-08-18-universe-stage1-triage-spec.md (orch#995)",
        "semantics": ("TRIAGE — PASS (triage) authorizes ONLY the Stage-2 PIT "
                      "program; anything else DEPRIORITIZED (spec §1/§5); "
                      "survivor-only snapshot, decides no serving/capital change"),
        "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_sec": round(time.time() - t_start, 1),
        "verdict": {"arm_a_h60": verdict, "reason": why,
                    "transfer_condition_met": bool(transfer_ok)},
        "pins": {
            "runner_identity": runner_id,
            "served_artifact_path": pin["artifact_path"],
            "served_artifact_file_sha256": pin["artifact_file_sha256"],
            "served_artifact_config_fingerprint": art.get("config_fingerprint"),
            "served_artifact_trained_date": pin["trained_date"],
            "strategy_config_path": str(WATCHLIST_CFG),
            "strategy_config_sha256": pin["config_sha256"],
            "sec_fundamentals_daily_sha256": _sha256(SEC_DAILY),
            "blend_component1_context_not_scored": pin["component1_context"],
            "repo_heads": {name: _git_head(root) for name, root in
                           (("umbrella", UMBRELLA), ("strategy-104", STRAT104),
                            ("base-data", BASEDATA_SRC.parent),
                            ("pipeline", PIPELINE_SRC.parent),
                            ("common", COMMON_SRC.parent))},
        },
        "corpus": {
            "start": CORPUS_START, "end": CORPUS_END,
            "snapshot_edge": SNAPSHOT_EDGE,
            "trading_days": int(len(g["corpus"])),
            "n_cross_sections": g["n"],
            "n_cross_sections_note": (
                "the frozen every-5th-trading-day RULE yields this count on "
                "the 1,161-day window; the spec's derived 231 was approximate "
                "— the rule governs (U4), discrepancy reported"),
            "dropped_label_edge": {str(h): g["dropped_label_edge"][h]
                                   for h in HORIZONS},
            "first_grid_date": str(g["grid"][0].date()),
            "last_grid_date": str(g["grid"][-1].date()),
        },
        "universe_counts": uni["counts"],
        "frozen_rule": {
            "primary_h": PRIMARY_H,
            "names_per_date_floor": NAMES_PER_DATE_FLOOR,
            "min_cell_n": MIN_CELL_N,
            "decile_frac": DECILE_FRAC,
            "placebo_lag_trading_days": {str(h): PLACEBO_LAG_MULT * h
                                         for h in HORIZONS},
            "block_t_min": BLOCK_T_MIN,
            "pos_block_frac_min_exclusive": POS_BLOCK_FRAC_MIN,
            "expected_blocks": {str(h): EXPECTED_BLOCKS[h] for h in HORIZONS},
            "min_blocks_with_data_h60": MIN_BLOCKS_WITH_DATA_H60,
            "bucket_rt_costs_bps": {"adv_ge_25M": 25, "adv_10_25M": 40,
                                    "adv_5_10M": 60, "adv_1_5M": "UNCOSTABLE"},
            "positive_control": {"reference": POSITIVE_CONTROL_REF,
                                 "floor": POSITIVE_CONTROL_MIN,
                                 "units": "per-date CS sigma (header U3)"},
        },
        "arm_w_positive_control": control["summary"],
        "arm_w": {str(h): arm_w[h]["summary"] for h in HORIZONS},
        "arm_a": {str(h): arm_a[h]["summary"] for h in HORIZONS},
        "arm_b_exploratory_never_pooled": {str(h): arm_b[h]["summary"]
                                           for h in HORIZONS},
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n")

    print("\n===== VERDICT (h=60, Arm A — spec §5 frozen bars) =====")
    print(f"  {verdict}: {why}")
    print(f"  ArmA gross Δ={a60['delta_gross']:+.6f} net Δ="
          f"{a60.get('delta_net', float('nan')):+.6f} "
          f"block_t={a60['block_t']:+.3f} pos%={a60['pos_block_frac']:.3f} "
          f"blocks={a60['n_blocks_with_data']}/{EXPECTED_BLOCKS[60]}")
    print(f"  ArmW gross Δ={w60['delta_gross']:+.6f} (control "
          f"{control['summary']['mean_spread_gen']:+.5f} sigma)")
    print(f"\nwrote {OUT_JSON.name}, {OUT_CSV.name} ({out['runtime_sec']}s)")


if __name__ == "__main__":
    main()
