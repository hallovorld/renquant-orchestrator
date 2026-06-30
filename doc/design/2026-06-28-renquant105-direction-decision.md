# renquant105 — DIRECTION DECISION

Status: **SCOPED DIRECTION HYPOTHESIS (for Codex + operator discussion)** —
2026-06-28. Author: Ren Hao (with Claude Opus 4.8). The operator delegated this
call to me; this PR is the discussion vehicle. It is the single durable record of
the proposed pivot — framed as a scoped hypothesis with cited artifacts (§4(b)),
not a definitive exhaustion decision.

This is a **scoped decision hypothesis, not a research framework and not a
proof.** It transcribes the evidence this session established and states the
resulting direction. It does **not** stand up a CPCV/FWER validation cathedral —
the per-signal scans that produced the *durable* evidence below already shipped
(`scripts/sighunt.py`, `scripts/robustness.py`, `scripts/regimemom.py`,
`scripts/fundamentals_scan.py`) and are documented in §5. The A1 / A2 / BEAR
audits that anchor the strongest model-side claims are **temporary `/tmp`
scratch outputs from unmerged, uncommitted scripts** (full provenance in §4(b))
and are therefore **discussion evidence, NOT a decision keystone.** The decision
below stands as a scoped hypothesis, not a theorem.

---

## §1 The finding (scoped hypothesis, not a keystone proof)

**No robust directional edge has surfaced under the current diagnostic suite on
the current large-cap inputs** (~134 liquid US large-caps + current
price/fundamental data) — across every regime / signal / combination / 盘中·盘后
we tested this session, read-only, with OOS / CI / placebo injection. We state
this as a **scoped hypothesis**, NOT as an exhaustion theorem and NOT as a proven
causal "binding constraint = DATA + UNIVERSE." Stated honestly: these are
read-only diagnostics on a *current-watchlist, survivorship-biased* panel; they
**cannot** prove the universal absence of edge. Every direct test we ran points
the same way, and the null is *consistent with* what the literature reports for
large-cap cross-sectional anomalies — but "consistent with" is not "caused by,"
and the A1 / A2 / BEAR numbers below come from un-durable `/tmp` scratch (§4(b)).
Under this diagnostic suite, on these inputs, no usable directional edge
surfaced.

The evidence, with numbers:

- **A1 — the existing model's directional skill looks like a thin slice, not a
  book.** [Discussion evidence — temporary `/tmp` scratch, see §4(b).]
  Read-only audit of the live model's per-name scores: genuine (leak-controlled)
  IC has a **CI that includes 0**, and it is **not leak-free** — predictor-side
  persistence balloons the naive IC. The apparent skill is **entirely a ~10%
  BEAR-slice artifact**; in BULL_CALM, which is **~79% of live time**, the
  genuine IC is **≈ −0.003 (a coin flip)**. Tradable net Sharpe ≈ 0. (Consistent
  with the ledger diagnostic `doc/research/2026-06-27-renquant105-trend-signal-baseline.md`,
  whose own faithful-cohort verdict is **UNDETERMINED** on ≈1 overlap-ratio of
  live data — i.e. the live ledger cannot yet *prove* skill either; the
  read-only model audit and the ledger both fail to surface a usable directional
  edge.)

- **A2 — ML combination buys nothing (Gu–Kelly–Xiu style).** [Discussion
  evidence — temporary `/tmp` scratch, see §4(b).] Sector+beta neutralized,
  walk-forward, **1002 OOS dates**: every multi-factor combination
  is **dominated by a single momentum factor**, and that momentum is itself a
  **recent-bull regime artifact** (null on the full sample). **No multi-factor
  synergy** — combining the available factors does not manufacture an edge that
  the best single factor lacks.

- **Single factors — null, negative, or net-negative under faithful costs.**
  - Price-trend (`sighunt.py` / `robustness.py`, 8y 2018→2026, 134 names,
    11 bps round-trip): five canonical factors show **no robust unconditional
    20/60d edge**. mom_12_1 clears the placebo floor **only at h=5** (un-deflated
    t≈1.9); at the h=20 target it has positive net L/S (+87 bps) but an **IC that
    does not clear the floor (0.74×)**. The 5-year momentum "signal" is a
    **bull-regime artifact** — IC fell from 1.24× to 0.74× the moment the panel
    extended to the full 8 years.
  - Regime-conditioned momentum (`regimemom.py`): **NO.** The yearly sign-flip
    **survives inside UP-trend** (2021 was 100% UP yet momentum IC = −0.065,
    the worst year), so a trend gate cannot isolate the momentum-paying state.
  - Fundamentals (`fundamentals_scan.py`, value/quality/growth): **nothing is a
    usable long edge.** Value is the strongest signal and points the **wrong way
    (negative)** and is only **soft** once overlap is respected (EY-252d
    non-overlapping t ≈ −2.4, down from an overlap-inflated −7.9); quality/growth
    are **null**. Regime-conditional, large-cap-weak.
  - PEAD / minute: null or net-negative under faithful costs.

- **BEAR / short audit — not a short edge either.** [Discussion evidence —
  temporary `/tmp` scratch, see §4(b).] The BEAR-slice skill is a
  **V-recovery LONG-ranking** (config-forbidden to act on as a short), the short
  leg is **net-negative**, effective **N ≈ 6**, the bootstrap **CI includes 0**,
  and 盘中 (intraday) adds nothing. There is no harvestable directional edge on
  the short side.

**Conclusion of §1 (scoped).** Under this diagnostic suite, on these inputs, no
robust directional edge surfaced. The **working hypothesis** — not a proven
binding constraint — is that the **inputs** (~134 liquid US large-caps + current
price/fundamental data) are the limiting factor: cross-sectional anomalies are
documented to be *weak* in large-caps, and our null is *consistent with* that
literature. This is a hypothesis to act on, not a theorem: we did not (and on a
survivorship-biased current-watchlist panel cannot) prove that more rigorous
validation or a different model architecture could not surface an edge. The
honest read is that none surfaced here, and the cheapest next move treats the
inputs as the suspected bottleneck while keeping that claim falsifiable.

---

## §2 The decision — two tracks

### Track A (immediate, NO new inputs) — non-directional improvement of the EXISTING book

Test a **meta-label entry filter** (López de Prado): a secondary model that
predicts **P(a given primary model pick is profitable)** and only takes the
high-confidence subset, to improve the existing book's **EXPECTANCY** — *not* to
create new alpha.

**Honest caveat, stated plainly:** meta-labeling improves the **precision of
acting on a primary signal**; it **cannot manufacture edge from a coin-flip
primary.** Given §1 (BULL_CALM genuine IC ≈ −0.003), the **first step is to
confirm there is a *conditional* signal worth filtering** — i.e. that the model is
measurably better in some identifiable state (regime, surprise window, liquidity,
dispersion). That first step is a **candidate-quality test** on the model's
top-decile candidates (NOT a reconstruction of the live acted-on book — §4), and
it **is not runnable today**: it depends on a durable OOS pick table that does not
yet exist as a committed artifact, so Track A's literal first move is a small
**regeneration PR** (§4). **If, once that table exists, no conditional state shows
materially higher pick quality, Track A is also null, and we say so.** No
over-claim.

Secondary non-directional levers (note, do not start): **vol / risk-timing**
(minute data is verified to improve volatility estimation — sizing, not
direction) and **execution / cost** reduction. These "lose less / size better /
enter better" levers improve realized expectancy without any directional edge.

### Track B (the real directional path — OPERATOR-level decision; FLAG, don't start)

A genuine directional 105 requires **changing an input.** Two candidates:

- **Broaden / down-cap the universe.** Cross-sectional anomalies are **strong in
  small/mid-cap, weak in large-cap**. This is the most literature-supported path
  to real directional edge — but it **conflicts with the large-cap liquidity
  design** of renquant-104 and is a structural change.
- **Acquire new data.** The estimate-revision snapshotter (#205) is **proposed /
  blocked — pending base-data ownership + a scheduler.** It is **NOT merged**
  (CI-red as of 2026-06-28) and is **NOT accruing any point-in-time revision
  history yet**; no PIT history exists today. Alt-data is a further option. New
  orthogonal, PIT-clean inputs are the other documented large-cap path, but every
  one of them is a future build, not an existing asset.

Both are **bigger decisions that take months and conflict with the current
design** — explicitly **the operator's call**, not something I start under this
PR.

---

## §3 Why this decision (honest)

The original 105 goal — **"catch more / more-accurate trends"** — requires a
**directional edge**, which **did not surface under this session's diagnostic
suite on the current inputs** (§1, scoped hypothesis). On that read, a real,
directional 105 most plausibly needs **Track B (an input change)** — stated as
the leading hypothesis, not a proven necessity.

**Track A is the immediate, low-cost thing that can help the LIVE book NOW
without new inputs — but it is "lose less / size better / enter better", NOT
"new alpha."** This distinction is the crux of the decision and must not be
blurred: **do not mistake Track A for solving the directional problem.** Track A
raises the expectancy of acting on whatever conditional edge already exists (if
any); Track B is the only path that creates directional edge that isn't there
today.

---

## §4 Proposed first concrete step — Track A conditional-pick-quality TEST SPEC

This is a **test spec**, defined **before** any meta-label filter is built. We do
NOT build a filter first. We first answer one falsifiable question: **is the
existing model's pick quality conditionally predictable — measurably higher in
some identifiable, ex-ante-observable state?** If not, Track A is null and we say
so.

**This is a CANDIDATE-QUALITY test, not a live-book expectancy test.** The label
below is defined on the model's **top-decile long-side candidates**, NOT on the
portfolio the live book actually held. The live book does not act on every
top-decile candidate — cash, risk caps, held-name constraints, regime gates, and
execution filters intervene — so a conditional improvement in candidate quality is
an **upper bound on**, not a measurement of, the lift to the live book. Track A's
first deliverable is therefore a candidate-quality verdict; reconstructing the
actual acted-on portfolio path (same constraints) is a **separate, larger step**
and is explicitly out of scope for this first test.

**Prerequisite — this step is NOT ready to run; it needs a regeneration PR
first.** The OOS prediction table the A1 audit used is **temporary `/tmp` scratch
from unmerged scripts** (§4(b)); it is **not committed, not durable, and will be
deleted**, so the test below cannot depend on it. There is **no committed
generator for this table in this repo** — `model_sanity_compare.py` only collates
`analyze_manifest_sanity_placebo` JSON; the per-(date,name) OOS prediction parquet
is produced by the gate's sanity-panel scoring, which is not exposed as a
committed, re-runnable command here. So **Track A's first step is to land a small
regeneration PR**, not to run anything today. That PR must commit:
- **Generator:** a committed script/module (proposed home
  `scripts/regen_oos_pick_table.py` in this repo, or the equivalent in the gate
  repo if scoring must live there) that re-scores the prod manifest read-only.
- **Inputs (durable, in the umbrella RenQuant tree — read-only, NOT this repo):**
  manifest `walkforward_manifest_gbdt_prod_recipe_v2.json` (37 PIT artifacts);
  feature panel `data/alpha158_291_fundamental_dataset.parquet`; label panel
  `data/alpha158_291_fundamental_dataset_rawlabel.parquet`; label
  `fwd_60d_excess`; val cut `2024-02-01`.
- **Output (durable, committed):** an OOS pick table parquet (proposed path
  `data/exp/oos_pick_table_recipe_v2.parquet`, an **experiment path, never a
  canonical prod path**) with schema `{date, name, score, decile_rank,
  fwd_60d_excess, regime}` over the 508 OOS dates (2024-02 → 2026-02).

Until that regeneration PR lands, the rest of §4 is the **spec the regenerated
table will be tested against**, not a command that can run on current artifacts.

**Target / label (defined against the regenerated, durable table above).** Define
a **binary candidate-success label** per (date, name) among the model's top-decile
long-side candidates: `y = 1` if the realized `fwd_60d_excess` is `> 0` net of the
11 bps round-trip cost proxy, else `0`. The conditioning question is "given the
model ranked it top-decile, did it pay?" — the meta-label framing, scoped to
candidate quality (not the acted-on book).

**Candidate conditioning variables (ex-ante only, no look-ahead).** Each must be
computable strictly from information available at the decision date. **All sources
below are existing umbrella-tree files (read-only, NOT this repo, NOT new
inputs)** — so this stays Track A. Where a variable's PIT-safety or full-OOS-window
coverage is **not yet verified from here** (this session did not re-run scans to
confirm), it is flagged; any variable that turns out to need #205 or another
unmerged source is **Track B, not Track A**, and is dropped from the Track A test.
1. **Regime** — the live regime label at pick date (BEAR / BULL_CALM / CHOPPY /
   BULL_VOLATILE). Source: the same regime classifier the live book uses (umbrella
   tree). As-of: computed from data through the pick date. PIT status:
   **[VERIFIED available]** — already attached per-date in the A1 scratch
   (`regime_sharpe.json` cut), so it will be a column on the regenerated table.
2. **Cross-sectional dispersion** — std of model scores on that date. Source:
   derived directly from the regenerated OOS pick table's `score` column. As-of:
   same-date scores only. PIT status: **[VERIFIED]** — pure function of the table.
3. **Score margin** — the picked name's `score` minus the date's decile cutoff.
   Source/PIT: same as (2), **[VERIFIED]**.
4. **Earnings-surprise window** — days-since-last-earnings + in-PEAD-window flag.
   Source: `data/fmp_harvest/earnings_291.parquet` (umbrella tree), PIT via SEC
   `acceptedDate`. As-of: last earnings on/before pick date. PIT status:
   **[GUESS — needs check]** — `acceptedDate` is the right PIT key, but full
   coverage of all 134 names across the whole 2024-02 → 2026-02 OOS window is **not
   verified from here**. If coverage is incomplete or not PIT-clean, drop this
   variable (do NOT substitute an unmerged feed — that would be Track B).
5. **Liquidity / volatility state** — name-level 60d realized vol + ADV bucket.
   Source: the price/bars panel used by the scans (umbrella tree). As-of: trailing
   60 sessions ending at the pick date (no forward window). PIT status: **[GUESS —
   needs check]** — trailing-window vol/ADV are PIT-safe by construction, but the
   committed home of a durable bars panel must be confirmed (the A2 bars were `/tmp`
   scratch). If no durable bars source exists, this variable is regenerated by the
   same Track-A regeneration PR or dropped.

If, after the availability check, only the **[VERIFIED]** variables (1–3) survive,
the Track A test runs on those alone and the doc says so — it does not wait on, or
quietly reach for, any unmerged data.

**Sample split / OOS window.** Chronological only. **Train/fit** the conditional
estimator on the **first 60%** of the 508 OOS dates (≈ 2024-02 → 2025-05),
**embargo 60 trading days** (= the label horizon, to kill overlap leakage),
**test** on the **remaining ~40%** (≈ 2025-08 → 2026-02). No shuffling, no
k-fold across time. Report per-regime cell counts so thin slices (BEAR ≈ 50
dates, BULL_VOLATILE ≈ 19) are visible and not over-read.

**Baseline.** The **unconditional** top-decile candidate set over the same test
window — i.e. every top-decile candidate with no conditioning. Track A only earns
its keep if conditioning **beats this baseline out-of-sample**, net of the
turnover it removes, **and the lift is large enough to matter at the portfolio
level** (next paragraph).

**Metrics (all on the held-out test window).**
- **Hit-rate** of conditioned candidates vs baseline hit-rate (with bootstrap 95%
  CI, date-block bootstrap, block = 13 as in A1).
- **Per-pick expectancy net of turnover/cost** — mean `fwd_60d_excess` of the
  conditioned candidate set minus the 11 bps round-trip proxy, vs the same for
  baseline.
- **Portfolio-level / capital-weighted lift** — the per-pick expectancy lift
  **annualized** (×≈4 60d-periods/yr, holding overlap acknowledged) and scaled by
  the **fraction of book capital it can actually touch** (active days × names
  filtered ÷ baseline names), so the gate is read in **annualized book-return
  terms**, not per-pick bps. A +5 bps/60d per-pick lift on a sliver of capital is
  near-zero at the book level and must NOT pass.
- **Turnover / opportunity cost** — incremental turnover the filter adds vs
  baseline (each removed-then-re-added name is a round trip), and the **count of
  baseline winners the filter drops** (missed-winner / opportunity cost). A filter
  that buys a small hit-rate gain by dropping many eventual winners is not a win.
- **Active-day exposure** — fraction of test dates on which the conditioned
  filter is in-market at all (a filter that acts on only a few percent of days is
  not a usable book lever even if its conditional hit-rate is high).

**Stop / go threshold (explicit, pre-registered — calibrated to PORTFOLIO impact,
not per-pick statistical nonzero).**
- **GO** (build the meta-label filter on the winning conditioning) only if, on the
  held-out test window, **all of** the following hold:
  (a) **Annualized, capital-weighted book-return lift over baseline ≥ +50 bps/yr**
      (i.e. economically material to the actual book, not just statistically
      nonzero per pick) AND its bootstrap 95% CI lower bound is **> 0**;
  (b) per-pick net-of-cost expectancy lift **≥ +5 bps per 60d** with bootstrap 95%
      CI lower bound **> 0** (statistical-significance floor, necessary but **not
      sufficient** — (a) is the binding economic gate);
  (c) hit-rate lift **≥ +3 pp** with CI excluding 0;
  (d) active-day exposure **≥ 25%** of test dates;
  (e) the filter does **not** drop **> 1/3** of baseline winners (missed-winner /
      opportunity-cost cap) and adds no more than a **doubling** of baseline
      turnover.
  The numeric levels in (a) and (e) are **first-pass proposals for operator/Codex
  calibration**, deliberately set so a statistically-nonzero-but-untradeable result
  cannot pass; they are open to tightening, not loosening.
- **STOP / NULL** otherwise: if no conditioning clears all of (a)–(e), declare
  **Track A null** and record that **Track B (an input change) is the only
  remaining path** to a directional 105. We do not then go fishing for a filter.

Same rigor as A1 / A2: chronological OOS, embargo, bootstrap CI, net-of-cost, and
a pre-registered threshold so the test cannot be talked into a pass.

---

## §4(b) Evidence contract — provenance, status, scope per source

Per the §4(b) evidence-block convention. The strongest model-side claims (A1,
A2, BEAR) come from **temporary `/tmp` scratch from unmerged scripts**, so they
are **discussion evidence, NOT a decision keystone** — the decision stands as a
scoped hypothesis (§1), not a proof. These outputs are **not committed, not
durable, and will be deleted**; a reviewer cannot re-fetch them from git.

### A1 — live-model per-name skill audit
- **Scripts (NOT committed, temporary):** `/tmp/a1_modeledge/01_get_oos_predictions.py`,
  `02_repro_and_rigor.py`, `03_injection_tests.py`, `04_injection_floor_leak.py`,
  `05_regime_and_sharpe.py`.
- **Outputs (NOT committed, temporary `/tmp` — will be deleted):**
  `/tmp/a1_modeledge/{VERDICT.md, oos_meta.json, rigor_summary.json,
  injection_results.json, injection_floor_leak.json, regime_sharpe.json,
  oos_predictions.parquet, per_date_ic.parquet, panel_label_history.parquet}`.
- **Prod-or-exp:** EXPERIMENT / scratch. Read-only re-score of the **prod**
  manifest, but the audit itself is not a committed artifact.
- **Inputs (existing, read-only — these ARE durable):** manifest
  `walkforward_manifest_gbdt_prod_recipe_v2.json` (37 PIT artifacts); feature
  panel `data/alpha158_291_fundamental_dataset.parquet`; label panel
  `data/alpha158_291_fundamental_dataset_rawlabel.parquet` (umbrella RenQuant
  tree). Label `fwd_60d_excess`, val cut 2024-02-01, 147,066 OOS rows / 508 dates.
- **Reproducibility check:** reproduced the committed `genuine_ic` to 4dp
  (0.0415 vs committed 0.0417) — the OOS table is faithful to prod.
- **Best-known?** Best read-only audit available **of this model on this panel**;
  NOT best-achievable absent a durable, committed re-run.
- **Scope / limits:** current-watchlist, survivorship-biased; genuine_ic CI
  **[−0.031, +0.129] includes 0**; the metric fails the slow-persistence
  injection (predictor-side persistence balloons genuine 0.042 → 0.29), so it is
  NOT clean leak removal; per-regime BULL_CALM (79% of OOS) genuine ≈ −0.003.

### A2 — multi-factor combination (Gu–Kelly–Xiu construction)
- **Scripts (NOT committed, temporary):** `/tmp/a2_combo/{combo.py, combo_model.py,
  walkforward.py, eval.py}`.
- **Outputs (NOT committed, temporary `/tmp` — will be deleted):**
  `/tmp/a2_combo/{VERDICT.md, manifest.json, economics.csv, factor_corr.csv,
  _intermediate.pkl, _model_stage.pkl, _wf_stage.pkl, _eval_stage.pkl}`.
- **Prod-or-exp:** EXPERIMENT / scratch.
- **Inputs (existing, read-only):** prices `/tmp/sighunt/bars.parquet` (134
  names, 2018-05-30 → 2026-06-26, also scratch); earnings/fundamentals
  `data/fmp_harvest/earnings_291.parquet` + `key_metrics_291` / `financial_growth_291`
  / `income_statement_291` (annual, PIT via SEC acceptedDate); sector_map from
  `strategy_config.golden.json`. Label fwd-20d (primary) + 5d.
- **Construction:** 10 long-set factors, cross-sectional rank → inverse-normal z,
  sector + 120d-beta neutralized; walk-forward 17 blocks, refit/63d, purge 20d,
  OOS span 2022-05-31 → 2026-06-26 = **1002 dates**; EW / Ridge(α=10) / shallow
  GBM combos; Spearman rank-IC, NW-t lag20, block-bootstrap 95% CI.
- **Best-known?** Best read-only combination test on this factor set + panel;
  hyperparams deliberately fixed (1 ridge α, 1 GBM config) to avoid OOS-peeking,
  so it is a single-spec read, not a tuned ceiling.
- **Scope / limits:** every combo **dominated by single mom_12_1** (combo net L/S
  Sharpe ≤ baseline; EW −0.09, Ridge +0.23, GBM +0.74 vs mom +1.11); mom itself
  is a recent-bull artifact; current-watchlist / survivorship-biased.

### BEAR / short audit
- **Source:** the per-regime cut of the **same A1 scratch** (`05_regime_and_sharpe.py`
  → `/tmp/a1_modeledge/regime_sharpe.json`, `VERDICT.md` §3) plus the short-leg /
  intraday reads from the same session — **all temporary `/tmp`, NOT committed.**
- **Prod-or-exp:** EXPERIMENT / scratch.
- **Inputs:** same as A1 (prod manifest re-score), regime labels from the book's
  classifier.
- **Best-known?** Best read-only short-side read on this model; NOT a durable
  artifact.
- **Scope / limits:** BEAR genuine +0.236 on **n ≈ 50 dates only (effective N
  small)**, bootstrap CI includes 0; it is a **V-recovery LONG-ranking** that
  config forbids acting on as a short (`regime_params.BEAR.max_position_pct = 0`);
  short leg net-negative; intraday adds nothing. Thin-slice, untradable long, not
  a short edge.

### Durable, committed evidence (NOT `/tmp`) — see §5
The price-trend / regime-momentum / fundamentals scans (`sighunt.py`,
`robustness.py`, `regimemom.py`, `fundamentals_scan.py`) and their write-ups in
§5 ARE committed and durable; those are the parts of §1 a reviewer can re-fetch.

---

## §5 References (this session's evidence — already shipped, read-only)

- `doc/design/2026-06-28-renquant105-alpha-discovery.md` — price-trend candidate
  table + regime-conditioning lead (`sighunt.py`, `robustness.py`,
  `regimemom.py`).
- `doc/research/2026-06-28-renquant105-fundamentals-scan.md` — value/quality/growth
  scan (`fundamentals_scan.py`).
- `doc/research/2026-06-27-renquant105-trend-signal-baseline.md` — live-ledger
  trend-signal diagnostic (verdict UNDETERMINED on ≈1 overlap-ratio).

All scans are **read-only**: no orders, no git in the live tree, no canonical
writes. Every panel is **current-watchlist / survivorship-biased**, so each
verdict is "no robust edge surfaced **under this diagnostic**", not a universal
proof of exhaustion — the diagnostics agree, and the inputs (large-cap
cross-section) are the **suspected** reason (consistent with the literature), not
a proven cause.
