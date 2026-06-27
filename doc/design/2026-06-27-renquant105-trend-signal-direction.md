# renquant105 — repointed direction: catch more + more-accurate multi-period TREND signals (evidence-graded)

This document supersedes the closed intraday framing of renquant105. The goal
is trend-signal **RECALL** + **PRECISION** on **multi-day holds** — explicitly
**NOT** intraday / day-trading.

**Status: PROPOSAL.** This RFC does **NOT** authorize retraining and does
**NOT** establish a lever ranking. It records the corrected (regraded) evidence,
marks the model-vs-gate question **UNDETERMINED**, operationally defines the
objective, instantiates the validation spine for THIS problem, and pre-registers
the factorial experiment + data-audit contract that will **MEASURE** (not
assert) the direction. The ranking of levers is an output of that measurement,
not an input.

## 1. Goal (operator-confirmed)

Catch MORE real trends (**recall** — currently the system barely trades; see the
denominator reconciliation in §7 before quoting a number) and catch them
MORE-ACCURATELY (**precision** — fewer false signals), then trade them holding
for the trend's duration (multi-day). Explicitly **NOT** intraday, **NOT**
high-frequency, **NOT** day-trading. The objective is made operational in §5;
"catch more, more accurately" is not by itself a measurable target.

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
| **[DATA·THIN]** | Our live ledger is too short and too impaired to settle model-vs-gate. | Our decision ledger (orchestrator PR #200, read-only): faithful LIVE history too short (fwd_20d = 11 aged dates, ~1–2 effective independent blocks; fwd_60d = 0; sim rows unfaithful — NULL scorer provenance, raw_score up to +270 vs PatchTST's intrinsic ~−0.198 → excluded). Directional-only short-horizon IC sits AT/BELOW the ~0.036 shuffled-label floor (fwd_5d +0.017, fwd_10d +0.051). The PR #200 killed-winner decomposition (missed_by_model vs killed_by_gate) is **parameter-dependent, scorer-mixed, non-causal, and based on ~1–2 independent blocks** — it does NOT establish a stable model-vs-gate ratio. | See §3: the only conclusions this supports are (a) provenance is inadequate, (b) the live gate often admits nothing, (c) model quality is UNMEASURED. **Re-measure when live ages to ≥30 fwd_20d dates (~mid-Aug-2026) or faithful per-name PatchTST score history + provenance is wired (#133 follow-through).** |

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

## 4. Pre-registered factorial experiment (replaces the asserted lever order)

There is **no asserted lever ordering** in this RFC. The direction of the work
will be MEASURED by a pre-registered factorial, run in `renquant-model` for the
training internals (CLAUDE.md hard boundary — the orchestrator orchestrates +
validates, it does not implement training internals) and validated by the spine
in §6. "Fresher retrain" and "new trend target" are **separate factors** — never
bundled — so each effect is interpretable.

Arms (each a separate, pre-registered cell):

- **A — Baseline reproduced.** The current production artifact, re-run on the
  frozen evaluation, to confirm reproducibility and fix the reference point.
- **B — Fresh data only.** Identical pipeline and label to A; **only** the
  training cutoff / data vintage changes. Isolates the staleness effect.
- **C — Trend-label change only.** Frozen data identical to A; **only** the label
  changes (the trend/momentum target of §5). Isolates the label effect.
- **D — Both.** Fresh data AND trend label. Tests interaction vs B+C.
- **E — Orthogonal analyst feature on the winning base.** ONLY after the §7 data
  audit passes; added on top of whichever of A–D wins, to measure marginal OOS
  IC + residual correlation/turnover (this is the *measurement* that the
  Fundamental Law motivates but does not prove).

Common contract across ALL arms (no exceptions):

- Identical outer/inner folds, identical universe, identical cost / turnover
  policy, identical capacity assumptions.
- One shared **trial ledger** counting every arm + every secondary horizon
  (§5) — secondary horizons are pre-registered alternatives, not hidden trials.
- Compare **paired** OOS policy returns (stateful replay, §6) AND event
  recall/precision lift, with explicit **multiplicity control** across the
  cells.
- Promotion only on net-of-cost improvement with block-aware uncertainty; see
  §6 kill/promote thresholds.

The marginal-utility test for any new feature (incl. the analyst feature)
estimates marginal OOS IC and residual correlation/turnover BEFORE any claim of
incremental value — replacing the deleted "orthogonal alpha > input-frequency"
assertion.

## 5. Operationally-defined objective (one primary, the rest pre-registered)

"Catch more trends, more accurately, hold for the trend's duration" is made
operational as ONE primary objective:

- **Trend EVENT definition:** a named, falsifiable event (e.g. forward run of a
  defined magnitude over the holding window) with explicit **event start / end**
  rules.
- **Holding policy:** horizon, **entry time** (point-in-time, with release/lag),
  **exit / time barrier**, capacity cap, turnover budget, and a measured cost
  model (commission + slippage + borrow where relevant).
- **Objective function:** a utility or **constrained precision–recall** target —
  e.g. *maximize net recall subject to floors on precision, capacity, turnover,
  drawdown, and cost*. The exact thresholds are frozen before any arm is run.

**Secondary horizons are PRE-REGISTERED ALTERNATIVES, NOT hidden trials:**
fwd_10d / fwd_20d, and triple-barrier / multi-horizon labels are listed up front
and counted in the shared trial ledger (§4). They do not become silent extra
attempts that inflate the false-discovery surface.

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
- **Effective-N / power:** report effective independent observations (block /
  overlap aware), not raw row counts, and the minimum detectable effect.
- **Full trial accounting:** every arm and secondary horizon enters one trial
  ledger feeding PBO / Deflated-Sharpe multiplicity control.
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
(c) **Freeze the trend event, portfolio policy, metrics, costs, N_eff, and the
trial ledger** (§5/§6) before any arm is run.
(d) **Audit the analyst-revision data** (§7-style audit, see below) before it can
be elevated to an experiment factor.
(e) **Pre-register and run the factorial** (§4: A→B/C→D→E) in `renquant-model`,
validated by the spine, with paired stateful replays.
(f) Re-run the PR #200 baseline at ~mid-Aug-2026 (≥30 fwd_20d dates) or once
faithful per-name PatchTST score history + provenance is wired.

**Analyst-revision data is NOT "ready" because 283/291 rows exist.** Before it
can become an experiment factor it must pass a DATA AUDIT + placebo: point-in-
time publication timestamps, vendor revision history, restatement handling,
coverage-by-date, lag policy, survivorship controls, freshness, and train/live
parity. Until that audit passes it is a **candidate, not a lever**.

**BLOCKED until measured:** any model-vs-gate ordering, any lever ranking, and
any absolute net-edge claim. This document remains a **proposal** — it sets the
measurement contract; it does not pre-judge its outcome.
