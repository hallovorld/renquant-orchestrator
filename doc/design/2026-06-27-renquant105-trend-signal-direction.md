# renquant105 — repointed direction: catch more + more-accurate multi-period TREND signals (evidence-graded)

This document supersedes the closed intraday framing of renquant105. The goal
is trend-signal **RECALL** + **PRECISION** on **multi-day holds** — explicitly
**NOT** intraday / day-trading.

**Status: PROPOSAL — this RFC defines a pre-registration SCHEMA / measurement
PLAN, NOT a completed pre-registration.** It does **NOT** authorize retraining and
does **NOT** establish a lever ranking. It records the corrected (regraded)
evidence, marks the model-vs-gate question **UNDETERMINED**, gives the objective
its measurement *schema* (the exact event/horizon/entry/exit/capacity/cost/
thresholds are NOT frozen here — §5), instantiates the validation spine for THIS
problem, and specifies the factorial + data-audit **contract** that a future
experiment must satisfy. The ranking of levers is an output of that measurement,
not an input.

**Execution is GATED on a separate artifact.** No experiment arm may run until a
**versioned, immutable pre-registration artifact** — committing the EXACT primary
trend contract (one event def, horizon, entry/exit, capacity, cost, thresholds),
the §4 factorial cells, the §6 split geometry, the §11 effective-sample bar, and
the §4 correction family/method — has received **SEPARATE review** and merge.
This RFC is the schema; that artifact is the pre-registration. The §11 shared
effective-sample contract (and any model-vs-gate ordering) is consistent with
PR #200 and is NOT unlocked by raw history alone.

## 1. Goal (operator-confirmed)

Catch MORE real trends (**recall** — currently the system barely trades; see the
denominator reconciliation in §7 before quoting a number) and catch them
MORE-ACCURATELY (**precision** — fewer false signals), then trade them holding
for the trend's duration (multi-day). Explicitly **NOT** intraday, **NOT**
high-frequency, **NOT** day-trading. The objective's measurement SCHEMA is in §5
(the EXACT event/horizon/thresholds are frozen in the separate §5
pre-registration artifact, not here); "catch more, more accurately" is not by
itself a measurable target.

## 2. Evidence base (GRADED — and the grades are corrected to match the estimand)

Grade legend:

- **[VERIFIED]** = adversarially vote-verified (3 independent verifiers,
  primary sources) AND the claim does not exceed the cited papers' estimand.
- **[SCOPED PRIOR]** = the primary sources are real and in-scope for THEIR
  estimand, but applying them to OUR estimand (multi-day directional return
  forecasting) is an extrapolation, not a verified result. Treat as a prior to
  be tested empirically, not a theorem.
- **[SOURCED·UNVERIFIED]** = primary source + quote found, but the adversarial
  vote did NOT complete (deep-research hit a monthly spend limit mid-run —
  these were *abstained*, NOT refuted).
- **[THEORY]** = established theory (and we state its applicability limits).
- **[DATA·THIN]** = measured on our ledger but sample too thin to be
  conclusive.

| Grade | Claim | Sources / basis | External-validity limit |
|---|---|---|---|
| **[VERIFIED]** | Raw minute / high-frequency returns are microstructure-NOISE-dominated **for integrated-variance / volatility estimation**; under that estimand naïve realized variance does not identify daily integrated variance and sampling as-fast-as-possible degrades the variance estimate. | Aït-Sahalia–Mykland–Zhang (2005, RFS 18:351); Zhang–Mykland–Aït-Sahalia (two-scales): "microstructure noise totally swamps the variance of the price signal"; Bandi–Russell (2008, REStud 75:339): realized variance "does not identify the daily integrated variance". | The verified result is about **variance/parameter estimation under microstructure noise**, NOT about multi-day directional return prediction. AMZ explicitly note that **modeling** the noise can make sampling as often as possible optimal — i.e. the "finite optimal sampling" result is conditional on a naïve estimator. This claim is verified ONLY for the literal in-scope statement above. |
| **[SCOPED PRIOR]** | "Minute / intraday features cannot improve multi-day directional forecasts." | Extrapolated from the variance-estimation literature above; NOT directly tested by it. | This is an **empirical ABLATION decision, not a theorem.** The cited papers do not study return forecasting; absence of evidence here is not evidence of absence. Parking minute input is a starting prior to be confirmed/refuted by a measured ablation (§4 step E-class), not a settled fact. |
| **[SCOPED PRIOR]** | "High-frequency data's ONLY proven cross-sectional value is volatility / risk." | Extrapolated from the same microstructure literature; reinforced (weakly) by Gu–Kelly–Xiu (2020, RFS 33:2223) using monthly characteristics and by modest intraday realized-skewness results (~24 bps/wk). | Gu–Kelly–Xiu use monthly characteristics and ZERO intraday features — they do **not test or reject** intraday features, so they cannot "prove" HF has no directional value. The realized-skewness result is small and short-horizon. The honest statement is: we have **no positive evidence** that HF adds multi-day directional alpha and a strong prior that it is dominated by noise — which justifies parking it as the LAST ablation, not asserting a proof. |
| **[SOURCED·UNVERIFIED]** | Multi-day / monthly cross-sectional returns are driven by SLOW predictors; momentum / reversal / liquidity dominate; baseline IC is structurally LOW. | Gu–Kelly–Xiu (2020): 94 characteristics (61 annual / 13 quarterly / 20 monthly, ZERO intraday); dominant predictors = momentum / reversal / liquidity; monthly stock-level R² only 0.33–0.40% → baseline IC structurally low. Momentum premium accrues OVERNIGHT not intraday (Lou–Polk–Skouras 2019, "Tug of War"). Intraday realized-skewness adds only MODEST weekly cross-sectional value (~24 bps/wk). | The adversarial vote did not complete; treat as sourced but unconfirmed. |
| **[THEORY]** | At LOW baseline IC, a LOW-CORRELATION orthogonal signal CAN raise IR (Fundamental Law: IR = IC·√breadth). | Grinold–Kahn Fundamental Law of Active Management. | **Applicability limit:** `breadth` is the number of INDEPENDENT bets that survive correlation / turnover / capacity constraints — NOT the number of low-correlation feature families. Adding a feature may raise IC, raise the transfer coefficient, or do nothing. The Law does **NOT** imply "orthogonal alpha > input-frequency refinement"; that ordering is removed (see §3) and replaced by a measured marginal-utility experiment (§4). |
| **[DATA·THIN]** | Our live ledger is too short and too impaired to settle model-vs-gate. | Our decision ledger (orchestrator PR #200, read-only): faithful LIVE history too short (fwd_20d ≈ 9 aged dates ≈ 0.45 effective non-overlapping blocks — roughly ONE independent observation, not nine; fwd_60d = 0; sim rows unfaithful — NULL scorer provenance, raw_score up to +200 vs PatchTST's intrinsic ~−0.198, scorer-mixture not PatchTST-primary → excluded). Per-horizon significance is now judged by #200's **on-cohort shuffled-label placebo** (shuffle WITHIN each date to preserve cross-sectional/time dependence), which is itself underpowered at ≈1 block; the old **0.036** figure is a FOREIGN reference (other experiment/horizon/purge) and is **no longer a pass/fail bar**. The PR #200 killed-winner decomposition (missed_by_model vs killed_by_gate) is **parameter-dependent, scorer-mixed, non-causal, and rests on ~1 effective block** (ratio spans ≈ [0.91, 2.80] and reverses) — it does NOT establish a stable model-vs-gate ratio. | See §3: the only conclusions this supports are (a) provenance is inadequate, (b) the live gate often admits nothing, (c) model quality is UNMEASURED. **Unblock is the shared effective-sample contract of §11 — a conservative overlap-ratio descriptor now; the real unblock is a pre-registered minimum-effect/power calc + an empirical dependence estimator on a FAITHFUL homogeneous cohort — NO calendar date is implied before that calc exists** (consistent with PR #200, which now scores sufficiency in effective non-overlapping blocks `n_dates / horizon_n` at `--min-eff-blocks` default 6: 30 adjacent overlapping 20-day dates ≈ 1.5 blocks → insufficient). |

## 3. Model vs gate: UNDETERMINED

The earlier draft of this RFC simultaneously (a) admitted the ledger is too thin
to settle the model-vs-gate split and (b) used a "MODEL is ~3.6× the bottleneck"
number to put gate work AFTER model work. That is internally inconsistent and is
**withdrawn**. The PR #200 decomposition is parameter-dependent, scorer-mixed,
non-causal, and rests on ~1–2 independent blocks, so it cannot order the work.

**Model-vs-gate priority is UNDETERMINED.** The only defensible current
conclusions are:

- (a) **Ledger / score provenance is inadequate** (NULL scorer provenance, sim
  rows unfaithful, no persisted per-name raw+μ+fwd history) — so directional IC
  and any decomposition are not yet trustworthy.
- (b) **The live conviction gate often admits nothing** in production (subject to
  the denominator reconciliation in §7).
- (c) **Model quality is UNMEASURED** at the horizons that matter for a
  multi-day trend objective.

Because these are independent and low-risk, **observability/provenance fixes and
gate-correctness verification may proceed IN PARALLEL** with (and ahead of) any
model experiment. Neither is gated on the other, and neither establishes a
lever ranking.

**Any future model-vs-gate ORDERING is gated on a faithful replay, not on raw
history** (consistent with PR #200, finding 1). It REQUIRES: (i) a **faithful
homogeneous scorer/artifact cohort** (PatchTST-only with exact production run
provenance — today's ledger is a panel_ltr_xgboost-dominant **scorer mixture**,
only ~85 hf_patchtst rows ledger-wide), and (ii) a **STATEFUL production replay**
of the actual ordered gate stack + capacity (using the persisted
`selected`/`blocked_by`), with paired counterfactual deltas and block CIs. The
PR #200 `(mu − mean) ≥ mu_floor` rule is **ONE synthetic threshold**, not the
deployed gate. **More raw history alone must NOT unlock the synthetic-threshold
decomposition** — N_eff sufficiency (§11) is necessary but not sufficient; the
faithful homogeneous cohort + stateful replay are also required.

## 4. Factorial experiment SCHEMA (replaces the asserted lever order)

There is **no asserted lever ordering** in this RFC. This section is the factorial
**schema** that the mandatory pre-registration artifact (§5) must instantiate
before any arm runs; it is run in `renquant-model` for the training internals
(CLAUDE.md hard boundary — the orchestrator orchestrates + validates, it does not
implement training internals) and validated by the spine in §6. "Fresher retrain"
and "new trend target" are **separate factors** — never bundled — so each effect
is interpretable.

Arms (each a separate cell of the factorial schema; values frozen in the §5
pre-registration artifact):

- **A — Old-cutoff baseline, REBUILT through the B pipeline.** A is NOT "re-run
  the production artifact". A is **rebuilt from the OLD training cutoff using the
  EXACT same pinned code / config / data-construction pipeline as B** — so A and B
  differ in **vintage only**, never in code, environment, preprocessing,
  training procedure, or artifact history. Before A is used as the reference, it
  must be **proven to PARITY** with the current production artifact within
  **declared tolerances** (IC / recall / precision / policy-return deltas under
  the pre-registered tolerance band). The production artifact's own performance is
  kept as a **SEPARATE OBSERVATIONAL reference**, never as arm A itself. (Rebuild,
  not "re-run", is what makes the A-vs-B contrast isolate freshness.)
- **B — Fresh data only.** Identical pinned pipeline, code, config, and label to
  A; **only** the training cutoff / data vintage changes. With A rebuilt the same
  way, A-vs-B isolates the **vintage** effect alone.
- **C — Trend-label change only.** Frozen data + identical pinned pipeline to A;
  **only** the label changes (the trend/momentum target of §5). Isolates the
  label effect.
- **D — Both.** Fresh data AND trend label. Tests the interaction vs B+C.
- **E — Orthogonal analyst feature, evaluated on UNTOUCHED data AFTER base
  selection.** ONLY after the §7 data audit passes. E is **not** "added to
  whichever A–D wins" as a free extra arm: the base winner is selected by the
  pre-registered §4 selection rule on the base folds, then E is evaluated on a
  **held-out / untouched** evaluation set under the nested outer loop, measuring
  marginal OOS IC + residual correlation/turnover. This is the *measurement* the
  Fundamental Law motivates but does not prove — not a selection-biased add-on.

**Primary contrasts = a 2×2 freshness × label factorial** (A/B/C/D):

| | OLD label | TREND label |
|---|---|---|
| **OLD cutoff** | A | C |
| **FRESH cutoff** | B | D |

- **Primary contrasts (pre-registered, named):** the **freshness main effect**
  (B−A and D−C), the **label main effect** (C−A and D−B), and the
  **freshness×label interaction** ((D−C)−(B−A)). These three contrasts — not
  arbitrary cell-vs-cell comparisons — are the confirmatory tests.
- **Selection rule:** the base winner among {A,B,C,D} is chosen by the
  pre-registered objective of §5 (constrained-PR / utility) on the **inner**
  folds only; E is then evaluated on **untouched** data under the outer loop. The
  rule is fixed in the pre-registration artifact before any arm runs.
- **Nested outer evaluation:** tuning / model selection happens in the INNER
  loop; all reported effects, the base-winner selection, and the E evaluation are
  scored on the **outer** held-out folds the inner loop never saw — so selection
  bias does not leak into the reported lift.
- **Correction FAMILY + METHOD (named):** family = the full pre-registered trial
  set (the four cells, the three primary contrasts, every secondary horizon of
  §5, and E). Method = control the **family-wise error rate** across the
  confirmatory contrasts via **Holm–Bonferroni**, and report **PBO** +
  **Deflated-Sharpe** (Bailey–López de Prado) over the full trial ledger for the
  policy-return surface. Secondary horizons (fwd_10/fwd_20/triple-barrier/
  multi-horizon) are **pre-registered ALTERNATIVES, NOT trial-multipliers** —
  they enter the family count but do not become silent extra discovery attempts.
- Identical outer/inner folds, identical universe, identical cost / turnover
  policy, identical capacity assumptions, across ALL arms (no exceptions).
- One shared **trial ledger** counting every cell, every contrast, every
  secondary horizon, and E.
- Compare **paired** OOS policy returns (stateful replay, §6) AND event
  recall/precision lift; promotion only on net-of-cost improvement with
  block-aware uncertainty; see §6 kill/promote thresholds.

The marginal-utility test for any new feature (incl. the analyst feature)
estimates marginal OOS IC and residual correlation/turnover **on untouched data,
after** the base winner is fixed — BEFORE any claim of incremental value,
replacing the deleted "orthogonal alpha > input-frequency" assertion.

## 5. Objective measurement SCHEMA (NOT a completed pre-registration)

This section is a **SCHEMA**: it enumerates the slots that the objective must
fill, but it does **NOT** freeze their values. "A named event", "a utility or
constrained-PR target", and "thresholds frozen later" are open choices — so this
RFC pre-registers **nothing**; it specifies what a pre-registration must contain.

The slots that the mandatory pre-registration artifact (below) must fill with
EXACT, immutable values before any arm runs:

- **Trend EVENT definition:** a named, falsifiable event (event **magnitude**,
  **start**, **end**, over an explicit holding window) — one primary def, no
  "e.g."
- **Holding policy:** horizon, **entry time** (point-in-time, with release/lag),
  **exit / time barrier**, capacity cap, turnover budget, and a measured cost
  model (commission + slippage + borrow where relevant).
- **Objective function:** a utility or **constrained precision–recall** target —
  e.g. *maximize net recall subject to floors on precision, capacity, turnover,
  drawdown, and cost* — with the EXACT floors/thresholds named.

**Mandatory versioned pre-registration artifact (execution gate).** Rather than
committing the exact contract inside this direction RFC, this RFC REQUIRES a
separate, **versioned, immutable pre-registration artifact** that fills every
slot above with concrete values, plus the §4 factorial cells + selection rule +
correction family/method, the §6 split geometry, and the §11 effective-sample
bar. That artifact must receive its **own SEPARATE review and merge** before ANY
experiment arm (A–E) runs. Execution is gated on that separately-reviewed
immutable pre-registration; nothing in §4–§7 authorizes running an arm by itself.

**Secondary horizons are PRE-REGISTERED ALTERNATIVES, NOT trial-multipliers:**
fwd_10d / fwd_20d, and triple-barrier / multi-horizon labels are listed up front
in the pre-registration artifact and counted in the shared trial ledger (§4).
They do not become silent extra attempts that inflate the false-discovery
surface.

## 6. Validation spine — instantiated for THIS problem

The spine names (purged CV / Deflated Sharpe / PBO / placebo / embargo /
triple-barrier / meta-label) are necessary but are NOT a design by themselves.
For the multi-day overlapping-label problem this RFC specifies:

- **Split geometry for OVERLAPPING multi-day labels:** outer/inner purged +
  embargoed CV sized to the label horizon so the embargo exceeds the label
  overlap; state the exact outer fold count and inner tuning protocol.
- **Point-in-time inputs:** universe, fundamentals, and analyst revisions taken
  at their release timestamps with explicit **release-time lags** — no
  look-ahead from restatements or backfills.
- **Effective-N / power:** sufficiency is scored in **effective non-overlapping
  blocks** (`n_dates / horizon_n`), gated at a pre-registered minimum (PR #200
  uses `--min-eff-blocks` default 6; 30 adjacent overlapping 20-day dates ≈ 1.5
  blocks → insufficient), with **multiple-regime coverage** and **block-bootstrap
  CIs** as the reporting standard. Report effective independent observations, NOT
  raw row counts, and the **minimum detectable effect** (the power calc). The
  unblock target follows N_eff, **never a raw-date / calendar count** (§11).
- **Full trial accounting:** every arm, contrast, and secondary horizon enters
  one trial ledger feeding the §4 Holm–Bonferroni FWER control plus PBO /
  Deflated-Sharpe over the policy-return surface.
- **On-cohort placebo (renamed, per #200):** per-horizon significance uses an
  **on-cohort shuffled-label placebo** — shuffle the score WITHIN each date to
  preserve cross-sectional/time dependence — compared as a p-value of observed IC
  vs the placebo distribution, multiplicity-corrected across horizons. The legacy
  **0.036** "leakage floor" is a FOREIGN reference (different experiment / horizon
  / purge) and is **NOT** a pass/fail bar here.
- **Stateful portfolio replay:** measured costs, turnover, capacity, and the
  holding policy of §5 — paired across arms.
- **Promotion / kill thresholds:** pre-registered net-of-cost lift with
  block-aware uncertainty; an arm that does not clear them is killed, not
  re-tuned.

**Explicit limit:** Deflated Sharpe on daily portfolio returns does NOT
substitute for uncertainty on **event recall/precision** — the recall/precision
estimates carry their own (block-aware) confidence intervals.

## 7. Production denominator + gate correctness (reconciliation required)

The "~0/84" framing and PR #200's "5.5 admits/date overall, ~13.2 on aged dates"
describe **different denominators / stacks** and must be reconciled before either
is quoted as the production admit rate. **Action:** state the exact production
stack and denominator (which gate version, which universe, which date window,
live vs sim) that produces each number; do not present "~0/84" and "5.5/date" as
if they measure the same thing.

The zero-admit gate is an **operational CORRECTNESS problem first**, not merely
an alpha lever. Independently of model strength, the gate must be repaired /
verified for:

- **sign** (is the admit direction correct given PatchTST's intrinsically
  negative scores?),
- **calibration / threshold UNITS** (raw vs μ vs demeaned; the documented
  raw>0 footgun),
- **demeaning universe** (which cross-section the demean is taken over),
- **train/live parity** (config-fingerprint parity; no additive-drift
  fail-closed silently zeroing admits).

A broken gate is fixed **regardless** of whether model ranking is weak. Any
change to the gate's **economic selectivity** (i.e. how much it admits) is a
SEPARATE change that is validated on its own through the §6 paired stateful
replay — gate *correctness* and gate *selectivity* are not the same change and
are not bundled.

## 8. Reused methodology spine (provenance)

The validation discipline and the decision-ledger / champion-challenger / daily
retrospective machinery are reused from the closed intraday suite and repointed
from "intraday cross-sectional alpha" → "multi-period TREND recall + precision"
(this is "option A": reuse the spine, don't re-derive). The instantiation for
THIS problem is in §6.

## 9. Separate, framing-agnostic track: 104 reliability fixes

Equities `client_order_id` dedup, run-lock, P&L daily-loss breaker,
intraday-granular freshness gate — worth landing regardless of the renquant105
framing; own PR track. Independent of everything above.

## 10. First concrete steps + what is still blocked

Low-risk work that can start NOW, in parallel, with no ranking implied:

(a) **Fix score/gate provenance** and build a faithful historical decision
replay (#133 follow-through) — prerequisite for trusting ANY decomposition.
(b) **Reconcile the production denominator** (§7) and **verify gate correctness**
(sign / units / demean universe / parity) — independent of model strength.
(c) **Author the versioned, immutable pre-registration ARTIFACT** (§5): freeze the
trend event, portfolio policy, metrics, costs, the §11 N_eff bar, the §4 cells +
selection rule + correction family/method, and the trial ledger — then send it
for its own SEPARATE review and merge. No arm runs before that artifact is
reviewed.
(d) **Audit the analyst-revision data** (§7-style audit, see below) before it can
be elevated to an experiment factor.
(e) **Run the factorial** (§4: A→B/C→D→E) in `renquant-model` ONLY after the (c)
pre-registration artifact is separately reviewed and merged; validated by the
spine, with paired stateful replays.
(f) Re-run the PR #200 baseline only once the shared effective-sample contract
(§11) is met — i.e. once a pre-registered minimum-effect/power calc + an
empirical dependence estimator on a FAITHFUL homogeneous cohort declare
sufficiency (≥ the pre-registered N_eff in effective non-overlapping blocks,
multiple regimes, block-bootstrap CIs) AND faithful per-name PatchTST score
history + provenance is wired. NO calendar date is implied before that calc
exists.

**Analyst-revision data is NOT "ready" because 283/291 rows exist.** Before it
can become an experiment factor it must pass a DATA AUDIT + placebo: point-in-
time publication timestamps, vendor revision history, restatement handling,
coverage-by-date, lag policy, survivorship controls, freshness, and train/live
parity. Until that audit passes it is a **candidate, not a lever**.

**BLOCKED until measured:** any model-vs-gate ordering, any lever ranking, and
any absolute net-edge claim. This document remains a **proposal / measurement
SCHEMA** — it sets the contract; it does not pre-judge its outcome, and execution
is gated on the §5 separately-reviewed immutable pre-registration.

## 11. Shared effective-sample contract (single source, consistent with #200)

Every "unblock", "re-measure", and "sufficiency" claim in this RFC points HERE,
and HERE matches PR #200's renamed criteria verbatim — there is ONE contract, not
a per-section count:

> **a conservative overlap-ratio descriptor now; the real unblock is a
> pre-registered minimum-effect/power calc + an empirical dependence estimator on
> a FAITHFUL homogeneous cohort — NO calendar date is implied before that calc
> exists.**

Concretely, consuming #200:

- Sufficiency is scored in **effective non-overlapping blocks** (`n_dates /
  horizon_n`), gated at a pre-registered minimum (#200: `--min-eff-blocks`
  default **6**). **30 adjacent overlapping 20-day dates ≈ 1.5 blocks → still
  insufficient.** Today's `fwd_20d` ≈ 9 aged dates ≈ **0.45** blocks — roughly ONE
  independent observation. The previously-cited "≥30 fwd_20d dates (~mid-Aug-2026)"
  raw-date / calendar unblock is **WITHDRAWN** everywhere in this RFC.
- The unblock target is the **N_eff / power calc + dependence estimator**, with
  **multiple-regime** coverage and **block-bootstrap CIs**, NOT a row count and
  NOT a calendar date.
- Per-horizon significance uses #200's **on-cohort shuffled-label placebo** (shuffle
  WITHIN date), not the foreign **0.036** floor.
- **N_eff alone does NOT unlock a model-vs-gate ordering or the synthetic-threshold
  decomposition.** That additionally REQUIRES a **faithful homogeneous
  scorer/artifact cohort** (PatchTST-only with production provenance) and a
  **STATEFUL production replay** of the ordered gate stack + capacity (§3). More
  raw history alone unlocks nothing.
