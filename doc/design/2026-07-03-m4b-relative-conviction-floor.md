# M4-b: re-derive the conviction floor as a RELATIVE quantity (prerequisite for the M4 enable)

STATUS: design RFC (docs only, design-via-PR). Companion to renquant-pipeline **#162**
(M4/BL-1 per-bar raw recentering, merged-as-default-OFF path) and to the unified-107 master
plan (#231) Term IC row **M4**. BLOCKING CONTRACT: `recenter_raw_per_bar` MUST NOT be
enabled in strategy-104 until this design's TWO-STAGE evaluation (§3) renders a Stage-2
CONFIRMED winner — a Stage 1 replay verdict alone authorizes shadow deployment only, never
a live enable — delivered as one combined config flip, never two half-states (§3, §6, §7).
DATE: 2026-07-03

---

## 0. Why this document exists (the footgun #162 refused to ship)

Pipeline #162 fixes the sign-laundering defect (calibrator ER=0 neutral at raw −0.2902 vs
live per-bar centers at −0.036…−0.053; `calibrator_sign_laundered` = 44–45/~90 on
07-01/07-02) by recentering the calibrator input per bar. Its own shadow replay then shows
the consequence downstream, honestly:

| date | run_id | n | center | laundered before → after | admitted @ `mu_floor 0.03` before → after |
|---|---|---|---|---|---|
| 2026-07-02 | 2026-07-02-live-85496d1c | 83 | −0.0362 | 45 → 0 | **22 → 1** |
| 2026-07-01 | 2026-07-01-live-01c54b39 | 83 | −0.0529 | 44 → 0 | **17 → 1** |
| 2026-06-30 | 2026-06-30-live-b616357c | 83 | −0.0464 | 43 → 0 | **18 → 1** |
| 2026-06-26 | 2026-06-26-live-3d74ce5c | 79 | −0.0473 | 46 → 0 | **18 → 0** |
| 2026-06-25 | 2026-06-25-live-6c3aa3fa | 76 | −0.2973 | 26 → 0 | 5 → 6 |
| 2026-06-24 | 2026-06-24-live-710e3805 | 73 | −0.2817 | 23 → 0 | 3 → 3 |

(Source: #162 PR body; evidence JSON committed in renquant-pipeline
`doc/evidence/2026-07-02-bl1-recenter-shadow-replay.json`; replay reproduces stored prod μ
exactly on 07-01/02 and the live laundered counters 44/45 exactly.)

Read: the absolute `conviction_gate.mu_floor = 0.03` was mostly gating the calibrator's
+2–3% unconditional drift intercept (07-02 μ mean +0.0189 → −0.0024 post-recentering), not
conviction. Remove the intercept and the absolute floor admits ~0–1 names on drifted
cross-sections — near-sell-only. This is the SAME algebra as the 2026-06-29 demean incident
(strategy-104 `doc/design/2026-06-29-conviction-gate-demean-revert.md`): an absolute bar
imposed on a quantity that has become relative. That incident's fix was to revert the
relative transform; here the relative transform (recentering) is the correct fix to a real
defect, so the floor — not the transform — must move. Enabling M4 without re-deriving the
floor would be shipping a footgun we have already explained twice (the
check-existing-contract lesson, renquant-pipeline #140/#147 history). Hence M4-b: this
design re-derives the floor BEFORE any enable.

## 1. The floor's purpose, restated from evidence (not from its original label)

The floor was introduced as an absolute promise — "only buy names whose calibrated
E[R−SPY] ≥ 3%" (pipeline #140, 2026-06-23 config annotation). Four measured findings say
that is not what it does, and constrain what a re-derived floor SHOULD do:

1. **The absolute promise was illusory.** The +2–3% calibration intercept meant "μ ≥ 0.03"
   was largely "intercept + ε ≥ 0.03". #162's replay: 17–22 of the floor-clearing names on
   06-26…07-02 evaporate once the intercept is removed. The floor's REAL historical
   admissions were mostly drift, not conviction.
2. **Among what it admits, it separates almost nothing (RS-2).** The floor-clearing pool is
   ~80–88% thin-margin post-retrain (μ ∈ [0.030, 0.0375), within 25% of the floor; 07-01:
   15/17, 06-30: 16/20 — `doc/research/2026-07-02-rs2-lane-a-timing.md`, descriptive
   score-density observation, no CI, honestly labeled as such there and here).
3. **Margin is ≈ orthogonal to stability (M3 AC-FAIL).** The uncertainty-haircut replay
   (`doc/research/2026-07-02-m3-haircut-replay.md`) measured margin/SE p50 = 1.28, p10 =
   0.14, p90 = 11.0: many thin-margin names are STABLY thin, many fat-margin names are
   unstable. The haircut removed MORE winners than losers at the 20d horizon (18W/15L at
   k=0.5; 28W/22L and Δ −0.51 pp at k=1.0) and left 20–24% of admits thin-margin. So
   "distance above an absolute bar" is not a proxy for reliability, and a stability penalty
   is not a substitute for a conviction floor.
4. **The motivating fixtures defeat per-name history (OXY/GRMN forensics).** The
   thin-margin entries the floor was supposed to catch (OXY 07-01 — bought; GRMN) were
   fresh entrants with 1–2 μ observations in the current scorer era: any history-based
   per-name statistic is UNDEFINED exactly when it is needed. A re-derived floor must be
   computable from the current bar's cross-section alone (or from a model-predicted
   quantity), never from per-name history.
5. **The recentered scale is centered ~0 by construction (M4 shadow table).** Post-M4,
   μ distributions have median ≈ 0 (07-02: p10/p90 −0.0207/+0.0129). Any fixed absolute
   number on this scale encodes an implicit, unstable quantile of a distribution whose
   dispersion varies by bar and regime.

**Restated purpose (what the re-derived floor must admit):** names whose RECENTERED μ shows
genuine relative conviction — separation from the per-bar cross-sectional center — while:

- (a) never longing a below-center name (the sign-laundering class stays dead; BL-4 remains
  the permanent backstop per #162 / #231);
- (b) keeping expected breadth compatible with the existing selection budget
  (`panel_buy_top_n = 3`, QP caps) and NOT silently widening it (A-2 contract, §5);
- (c) being invariant to calibrator drift/vintage (the failure class M4 fixes must not be
  re-introduced through the floor);
- (d) degrading predictably across regimes — a zero-admission bar must be an explainable
  statement ("nothing is separated today"), never a structural artifact of scale mismatch.

**What the floor is NOT (pinned):** not an absolute expected-return promise (that died with
the intercept); not a stability/uncertainty filter (M3: orthogonal, and directionally
harmful on retired-era data); not a substitute for a validated model (D1 verdict still
pending — no floor makes an unvalidated μ trustworthy).

## 2. Candidate re-derivations

All candidates operate on the RECENTERED μ cross-section (post-#162 scale). Each carries a
frozen evaluation criterion; §4 fixes the common protocol. Per-bar statistics are computed
on the FULL scored candidate cross-section (pre-veto), never on a post-veto subset — the
pipeline #147 footgun lesson.

### (a) Cross-sectional quantile floor — admit top-K% of recentered μ per bar

`admit ⇔ μ ≥ Quantile_{1−K}(bar μ) AND μ > 0`

- **Pros:** breadth-stable by construction across calibrator drift and regime shifts;
  unit-free (immune to any residual intercept/scale change in future calibrator vintages);
  matches the rank-centric semantics of the panel LTR scorer and of "center of the
  cross-section" that #162 adopted (median); computable per-bar with no per-name history
  (survives the OXY/GRMN fresh-entrant problem); one parameter (K), pinned by the
  matched-breadth protocol (§4) rather than hand-tuned — but see §3: pinning K on the same
  window whose outcomes then judge the winner is in-sample family selection, not "zero
  tuning freedom"; that is why §3/§6 require a prospective stage before any live enable.
- **Cons:** unconditional breadth — on a genuinely conviction-free day it would still
  nominate names; the `μ > 0` side-condition (never long below-center) is therefore part of
  the rule, not optional. Stacks a relative gate on the relative `VetoWeakBuys` rank floor
  (mean + 1σ) — the redundancy the 2026-06-29 doc warned about; the evaluation must measure
  the MARGINAL effect over the veto stack, not assume it. K inherits no economic meaning
  (it is a breadth choice, honestly).
- **Frozen criterion:** at matched breadth (§4), realized fwd expectancy of admitted set
  beats the current absolute floor's, block-5 bootstrap 95% CI excluding 0 at the primary
  horizon; P(zero-admission bar) ≤ baseline's.

### (b) Dispersion-scaled floor — admit names separated beyond bar noise

`admit ⇔ μ ≥ k · MAD(bar μ) AND μ > 0` (MAD = median absolute deviation about the per-bar
median; consistent with #162's median-center choice, robust to the heavy raw tails it
documents)

- **Pros:** admits only genuinely separated names; adapts to regime dispersion (compressed
  BULL_CALM cross-sections admit fewer, dispersed regimes admit more); a zero-admission
  bar is an honest "nothing separates today", satisfying §1(d) by meaning rather than by
  construction; no per-name history needed.
- **Cons:** breadth varies — the near-sell-only failure mode returns in a milder, honest
  form, and prolonged compressed regimes could re-create a structural no-buy state (must be
  bounded by an explicit max-consecutive-zero-admission alarm, not silently accepted); k
  has no closed-form derivation (pinned by matched breadth in evaluation, but its LIVE
  breadth will then drift with dispersion — that drift is the point, and must be monitored
  against the A-2 contract, §5); MAD on ~70–90 candidates is fine, but on thin bars (<20
  scored names) it is noisy — reuse #162's thin-cross-section fallback posture.
- **Frozen criterion:** same expectancy-vs-baseline bar as (a), PLUS its regime behavior
  must show admitted-count monotone in bar dispersion (sanity that it does what it claims),
  PLUS max consecutive zero-admission bars in replay ≤ the baseline's observed maximum.

### (c) Absolute floor re-anchored to the recentered scale

`admit ⇔ μ ≥ c` with c re-derived once (candidate anchor: a round-trip cost hurdle,
~0.005, the "alternative considered" in the 2026-06-29 revert doc — economically
meaningful, unlike a re-tuned 0.03)

- **Pros:** simplest — one number, zero pipeline change beyond the config value; keeps the
  gate's existing code path and tests; a cost-hurdle reading gives the floor back an honest
  economic meaning ("clears round-trip cost"), which (a)/(b) lack.
- **Cons:** **re-drifts by construction** — any residual intercept or scale change in a
  future calibrator vintage silently re-breaks it; this is the exact failure class M4
  exists to kill, re-introduced one layer down. The 06-29 doc already rejected the
  cost-hurdle variant "for now" because the hurdle value cannot be validated until live
  forward returns realize (~Aug 2026). Retained here as the honest BASELINE-SHAPED
  candidate: if neither (a) nor (b) beats it at matched breadth, the added machinery is
  unjustified.
- **Frozen criterion:** same protocol; (c) is additionally the tie-break fallback — see
  §4 "no-winner route".

### (d) NGBoost σ-based band — admit names whose lower conviction bound clears zero

`admit ⇔ μ − k·σ_model > 0` (σ_model = the NGBoost head's per-name predicted σ — the real
uncertainty band M3's verdict named as the proper prerequisite for any uncertainty-aware
gate)

- **Pros:** per-name and model-predicted, so it covers fresh entrants (OXY/GRMN) where
  every history-based proxy is undefined — the only candidate that addresses M3's
  fresh-entrant finding head-on rather than sidestepping it; principled: gates on
  "conviction distinguishable from zero", which is the statement we actually want.
- **Cons, stated honestly (this is NOT free):** the σ head is TRAINED and PROMOTED (NGB
  artifact md5 `30b0460a`, promoted 2026-05-17; `ngboost.enabled=false` in strategy-104
  with the full E55 disable rationale inline) but the **σ-wire is OFF per the 2026-05-17
  A/B** (umbrella `doc/research/failed-experiments-log.md`): global σ-on NULL (+3.01pp, CI
  lower bound at 0), per-regime σ-on −4.70pp SUSPECT-neg, per-regime + hysteresis −7.89pp
  SUSPECT-neg; consistent with the earlier E55 27-month A/B (−3.78 APY pts). Those A/Bs
  tested σ in RANKING/sizing (`score_mode = mu − λσ`), not as an admission band, so they do
  not literally condemn this use — but **reopening the σ-wire is a separate decision with
  its own recorded negative history and must be re-pitched on its own merits, never
  smuggled in as a floor re-derivation**. Additional real costs: the promoted head predates
  the current panel_ltr_xgboost era and its σ lives on its own label scale/horizon
  (calibration to the 60d μ scale unverified); wiring σ onto candidates is new pipeline
  surface (audit F9: `_last_sigma` computed and discarded today); freshness/promotion story
  for a second artifact.
- **Frozen criterion:** same expectancy bar as (a); ADDITIONALLY gated on a recorded
  operator decision to reopen the σ-wire question (out of scope for M4-b), and on a
  σ-calibration check (predicted σ rank-correlates with realized |μ − fwd| on the replay
  window) BEFORE its expectancy read counts.

### Candidate summary

| | rule (on recentered μ) | breadth | drift-immune | fresh entrants | zero-admit mode | cost to build | recommendation |
|---|---|---|---|---|---|---|---|
| (a) quantile | top-K% AND μ>0 | stable by construction | yes | covered | only via μ>0 (rare) | small (gate math only) | **PRIMARY candidate** |
| (b) dispersion | μ ≥ k·MAD AND μ>0 | regime-varying (honest) | yes | covered | by design (needs alarm) | small | **CHALLENGER** |
| (c) re-anchored absolute | μ ≥ c (~cost hurdle) | drift-varying | **no — re-drifts** | covered | structural (the incident class) | trivial | fallback baseline |
| (d) NGB σ-band | μ − k·σ > 0 | model-dependent | yes | **best (predicted σ)** | honest | **largest** (σ-wire reopen + calibration + freshness) | deferred; own decision |

**Recommendation (a prior, not a pre-judgment — all four run through §4):** (a) as primary
— it is the only candidate that satisfies §1(b)+(c) by construction and needs no new
history, artifact, or reopened decision; (b) as challenger because its zero-admission mode
is the more honest semantics if the expectancy evidence supports paying the breadth
volatility; (c) as the fallback that keeps us honest about whether relative machinery earns
its complexity; (d) deferred behind its own σ-wire decision.

## 3. What the evaluation must fix that M3's could not

M3's replay compared rules at UNMATCHED admission rates — the haircut variants admitted
fewer names than the baseline, so expectancy deltas conflated "which names" with "how
many". The M4-b protocol matches admission rates across variants (same expected breadth),
so the comparison isolates the SHAPE of the admission rule.

**This does NOT make the replay a frozen authorization protocol by itself (corrected
2026-07-03 review).** Matched breadth still selects AMONG rule families (a)–(d) and pins
each family's one free parameter (K, k, c, or σ-k) using the SAME replay window whose
forward outcomes then decide the winner. Fixing the parameter does not remove the
family-selection degree of freedom, and judging the winner on the window that chose it is
in-sample model selection, not a frozen contract — the exact failure class this document
exists to close for the FLOOR, must not be reopened one level up for the RULE FAMILY.

**Two-stage promotion contract (replaces the single-stage "matched breadth ⇒ enable"
reading of earlier drafts):**

- **Stage 1 — nomination (this replay).** The matched-breadth replay over the existing
  window may NOMINATE a provisional winning family + parameter per the win criteria in §4.
  Stage 1 output is a `candidate-for-shadow` verdict, not an authorization to change live
  behavior. A nested holdout inside the replay window is not substituted here: the
  resolved-outcome sample is already dominated by retired-era streams and BULL_CALM (§7),
  too thin to split further without losing the power to distinguish families at all; the
  prospective stage below is the real out-of-sample test, not a same-window split.
- **Stage 2 — prospective shadow validation (required before live enable).** The Stage 1
  nominee runs in SHADOW mode (§6) over sessions that occur AFTER Stage 1 concludes — never
  sessions already in the replay corpus. Stage 2 re-applies the §4 win criteria as a
  confirmatory (not exploratory) check against this untouched window. Only a nominee that
  clears Stage 2 may go into a strategy-104 config PR. This is the same nominate-then-
  confirm structure already applied to `renquant-backtesting` #61's WF-gate threshold this
  session (retrospective evidence nominates, prospective evidence authorizes) — reused here
  rather than re-derived, since the underlying problem (a threshold/family chosen while
  looking at the outcomes it is judged against) is identical.
- Stage 2's minimum window length and re-confirmation cadence are set in the
  replay-implementation PR (§6 step 2), informed by how many prospective sessions are
  needed for the block-5 bootstrap CI (§4 Statistics) to stop being dominated by the
  Stage-1 sample; this document does not pre-commit a specific session count because that
  number depends on live session-arrival rate, which is outside this design's evidence.

## 4. Pre-registered evaluation protocol (frozen here, before any replay runs)

**Substrate.** The S5/S8 substrate per #231: stored `candidate_scores.raw_panel`
cross-sections replayed through the live prod calibrator with #162's committed tool
(`scripts/shadow_replay_bl1_recenter.py` pattern — replay fidelity already demonstrated:
exact μ reproduction on 07-01/02), joined to realized forward outcomes with the M3/#234
canonical-run discipline: one canonical daily full run per date (latest `created_at` with
≥40 candidate rows), read-only DB, deterministic seed, evidence JSON committed. S5
(decision-ledger wiring) and S8 (durable OOS pick table, `RenQuant#430`) are the named
dependencies; until S5 producers are live the replay is bounded by what `runs.alpaca.db`
already stores (sufficient for the admission layer; outcome joins per below).

**Variants.** Baseline = current absolute floor on the PRE-recentering scale (`μ ≥ 0.03`,
exactly today's production rule). Candidates (a)–(d) of §2 on the recentered scale. BL-4
and the full veto stack applied identically to all arms (marginal-effect measurement).

**Matched admission rates.** Target breadth B = the baseline's mean floor-clearing count
over the replay window. Each candidate's single parameter is set ONCE, on the replay
window, such that its mean floor-clearing count equals B (±0.5). Per-bar counts may differ
(that is each rule's shape); means may not. No per-bar re-tuning.

**Matching the mean alone does not protect the A-2 selection-budget contract (corrected
2026-07-03 review)** — two rules can share a mean admitted count and differ sharply in
operational behavior that changes downstream QP/top_n dynamics. The frozen comparison
additionally pins, per candidate vs. baseline over the SAME replay window:

- **`top_n` saturation frequency** — the fraction of bars where the floor-clearing count
  ≥ `panel_buy_top_n` (3), i.e. how often the floor is not actually the binding constraint
  because top_n already caps selection;
- **p90 / p95 admitted-count** — not just the mean, since a fat right tail can spike QP
  pressure on specific bars even at a matched mean;
- **QP spill pressure** — the fraction of bars where the floor-clearing count exceeds what
  QP/portfolio construction can fully size under its caps (correlation/sector guards +
  whole-share constraints), i.e. bars where QP must drop or truncate otherwise-admitted
  candidates. The replay-implementation PR (§6 step 2) must compute this against the actual
  QP step's caps, not approximate it from admitted-count alone;
- **Consecutive zero-admission streak length** — the longest run of bars with zero
  floor-clearing names, both mean-matched AND streak-matched (a candidate whose zero-runs
  cluster differently than baseline's changes the live "how long between opportunities"
  experience even at equal total admission).

A candidate must match baseline within a pre-registered tolerance (set in the
replay-implementation PR, before results are seen) on ALL FOUR of these, in addition to the
mean, to be considered non-disruptive to the A-2 contract. A candidate that matches the
mean but diverges on saturation/percentile/spill/streak is not disqualified outright, but
must report the divergence explicitly in the results doc as an A-2-adjacent finding (per
§5's freeze-and-report clause), not silently pass on mean-match alone.

**Outcomes.** Primary: realized fwd_20d excess over SPY (fwd_60d is unresolvable for the
live window until ~Aug 2026 — same honest deviation M3 recorded); fwd_10d and fwd_5d as
sensitivity; winner = excess > the 11 bps cost proxy (M3's convention). Weekend mapping and
resolvability rules exactly as M3.

**Cuts.** Per-regime (with the honest expectation, from M3, that resolved outcomes are
currently ~all BULL_CALM — a BEAR/CHOPPY-unmeasured verdict must say so and blocks nothing
beyond what it measures); per-era (retired-scorer vs panel_ltr_xgboost) — a winner on
retired-era μ streams only is a provisional winner, re-confirmed forward as panel-era
outcomes age in.

**Statistics.** Date-block bootstrap, block-5 primary (M3 measured block-13 degenerate at
this sample size), block-1 sensitivity carried alongside; CIs are descriptive of the window
(M3's caveat inherited verbatim).

**Frozen Stage 1 win criteria (the gate for a `candidate-for-shadow` verdict, NOT for the
strategy-104 config PR — see §3's two-stage contract and §6):**

1. Winner's Δ expectancy vs the CURRENT absolute-floor baseline, at matched breadth,
   > 0 with block-5 95% CI excluding 0 at the primary horizon;
2. not-worse (point estimate) in every regime/era cut with ≥5 resolved dates;
3. winners-removed ≤ losers-removed relative to baseline (the M3 axis, now at matched
   breadth);
4. P(zero-admission bar) ≤ baseline's on the replay window (for (b): max consecutive
   zero-admission bars ≤ baseline's observed max, plus the monotone-in-dispersion sanity);
5. admission-distribution match (top_n saturation frequency, p90/p95 admitted-count, QP
   spill pressure, consecutive zero-admission streak — the four metrics pinned above),
   within the pre-registered tolerance set in the replay-implementation PR;
6. zero post-hoc edits — any deviation from this section is recorded in the results doc
   and downgrades the run to exploratory.

**Frozen Stage 2 win criteria (the gate for the strategy-104 config PR).** The Stage 1
nominee re-clears criteria 1–5 above, computed fresh against the Stage 2 prospective
window (§3) — confirmatory, not exploratory: the parameter is NOT re-fit on Stage 2 data,
only re-evaluated. A nominee that fails any Stage 2 criterion returns to the no-winner
route below; it does not get a second parameter fit.

**No-winner route (pre-registered).** If no candidate clears Stage 1 criteria 1–6, or a
Stage 1 nominee fails Stage 2: M4 stays dark
(`recenter_raw_per_bar` remains false), BL-4 remains the permanent interim guard — exactly
#231's M4 Plan-B ("keep BL-4 permanent → M3 weakens") — and the floor question re-enters
via S5-aged panel-era outcomes, not via a re-run of the same window with new parameters.

## 5. Interaction contracts (what this change must NOT move)

- **A-2 / top_n widening (RS-2, `doc/research/2026-07-02-rs2-lane-a-timing.md`):**
  `panel_buy_top_n` stays 3. The floor re-derivation is matched-breadth BY CONSTRUCTION
  (§4) and therefore must not silently widen admissions; any breadth increase remains
  behind A-2's own dedicated frozen marginal-rank test, which itself waits on D1. If the
  winning variant's live floor-clearing counts drift above the replay-window B by >25% over
  any 10-session window, that is an A-2-adjacent event: freeze, report, do not ride it.
- **QP / selection budget:** the floor gates candidacy only; QP caps, correlation/sector
  guards, top_n, and whole-share constraints remain the binding selection budget. The R4
  selection-budget refactor (#231 Term TC) is orthogonal and not blocked by, nor blocking,
  M4-b.
- **Sizing (state it, per the contract):** Kelly (`fractional 0.3`,
  `sigma_horizon_days 60`, `use_calibrator_mu true`) consumes μ LEVELS, not ranks. A
  quantile/dispersion floor changes ADMISSION only — sizing is untouched by M4-b itself.
  But M4 (recentering) changes the μ levels feeding Kelly (07-02 mean +0.0189 → −0.0024):
  post-enable, admitted-name Kelly targets shrink mechanically. That is an M4
  combined-enable review item (expected deployment delta must be stated in the enable PR),
  NOT a floor-design item — routed there explicitly so it cannot fall between the two.
- **Demean stays OFF — do not stack relative transforms:**
  `conviction_gate.demean_cross_sectional` remains `false`. Recentering happens once, at
  the calibrator INPUT (#162); re-enabling gate-level demean on top would subtract the
  center twice. The 2026-06-29 revert stands; this design does not re-litigate it.
- **BL-4 signal-direction gate:** permanent, before and after the enable (per #162 and the
  #231 fallback note). The floor is not its replacement.
- **Enable sequencing with M4 (the two-half-states ban):** the ONLY allowed transition is
  one combined strategy-104 config flip: `recenter_raw_per_bar: false→true` AND the
  re-derived floor, in the same commit, active+golden in lockstep, drift-pinning test
  updated. Forbidden half-states: recenter-ON + absolute 0.03 floor (near-sell-only — the
  #162 table); recenter-OFF + relative floor (changes live admissions on the drifted scale
  with no D1 verdict and no validated benefit). Rollback is the same single combined
  revert.

## 6. Rollout

**Corrected 2026-07-03 (review):** a Stage 1 replay winner is a `candidate-for-shadow`,
never a live enable. Section 6 previously allowed an immediate strategy-104 config PR
straight off the replay verdict, which contradicted §7's own admission that the replay's
resolved outcomes are retired-era/BULL_CALM-dominated and therefore provisional. The
rollout below now requires Stage 2 (§3) between "replay winner" and "live enable," so this
section is consistent with §7 rather than more aggressive than it.

1. **This PR** — the design, evidence restatement, frozen protocol (docs only).
2. **Replay implementation PR** (orchestrator, separate): read-only DB script per §4,
   committed evidence JSON, parameters imported from this doc — any divergence is a
   recorded deviation.
3. **Stage 1 replay verdict recorded either way** (candidate-for-shadow / no-winner),
   reviewed under the normal control plane. A Stage 1 winner authorizes SHADOW deployment
   only — no config, pipeline, or live-behavior change yet.
4. **If Stage 1 nominee:** deploy the nominee in shadow/observe-only mode (implementation
   detail for the replay-implementation PR — logging the nominee's admission decisions
   alongside the live baseline's, per the same non-gating-shadow pattern already used by
   `renquant-pipeline` #161's admission shadow logger) over the Stage 2 prospective window
   (§3). No strategy-104 change at this step.
5. **Stage 2 confirmatory verdict** — the Stage 1 nominee re-evaluated against the
   prospective window per the Stage 2 win criteria (§4). Recorded either way.
6. **If Stage 2 confirms:** strategy-104 config PR (design-via-PR) with the ONE combined
   flip (§5), deployed via promote_pin (merged ≠ live until the live machine syncs pins),
   with a monitored window and the combined single revert as rollback.
7. **If no Stage 1 nominee, or a nominee fails Stage 2:** pre-registered NULL route (§4) —
   M4 dark, BL-4 permanent, revisit on S5-aged panel-era outcomes.

## 7. Honest limits

- The replay window's resolved outcomes are dominated by retired-era μ streams and
  BULL_CALM (M3's finding); a winner here is provisional until panel-era outcomes age in.
- fwd_60d — the horizon μ actually targets — is unresolvable until ~Aug 2026; fwd_20d
  primary is a stated compromise, inherited from M3, not a preference.
- D1 (first WF-gate verdict on the live primary) is still pending: no floor choice
  validates μ itself. If D1 fails, the floor question is moot until the model question is
  answered.
- The thin-margin (RS-2) figure motivating urgency is descriptive, not inferential — this
  design treats it as motivation, and puts the inferential weight entirely on §4.
