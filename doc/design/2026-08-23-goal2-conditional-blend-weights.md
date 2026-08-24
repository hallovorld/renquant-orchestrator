# GOAL-2: conditional blend weights — a meta-learner over the existing legs

STATUS: design for review. No implementation in this PR. Operator-directed
2026-08-23; the operator delegated the two open design decisions (output form,
horizon) and mandated design → codex approval → implementation → deploy.

## 1. Estimand

Does a per-leg weight vector **w(state)**, conditioned on SLOW state variables,
beat the served **uniform z-sum** of the same legs, on 60-trading-day forward
DGTW-adjusted returns of the blended cross-sectional score?

Null = uniform weights = current production. Everything else is the alternative.

## 2. The two delegated decisions, and why they landed here

**Output = (b) dynamic weights on the existing z-blend legs** — not (a) a
replacement scorer, not (c) hard on/off routing.
- The served blend is an unweighted z-sum, and the weighting slot is already
  reserved in the system design (MoE AC5) — this fills a designed hole rather
  than opening a new estimand.
- Bounded failure: weights are clamped to [0, w_max] and renormalised;
  degenerate output ⇒ uniform ⇒ byte-identical to production.
- (c) hard routing is the form the frozen gates already killed three times
  (sector 27.8% < 33.3% chance with adjacent-quarter Spearman −0.185; daily
  dispersion contrast negative; momentum/reversal all-arm KILL). Soft weights
  conditioned on SLOW state are the one surviving hypothesis (orch#966), and
  the operator's macro variables (yield trend, VIX) are slow variables —
  the intuition and the surviving door coincide.

**Horizon = 60d, 104 lane only.** 105 consumes nothing from this line unless
it survives Stage 1. Intraday horizons would be a different model; they are
not this design.

## 3. Data — no new granularity, no new infrastructure

- **Base-model outputs**: the shadow fleet already records daily cross-sections
  for prod legs + `momentum_fast_v1`, `momentum_residual_v0`,
  `topdecile_clf_blend_leg`. This IS the meta-panel's X, already produced.
- **State variables (all daily, all free)**: VIX level and 3-month trend, 10Y
  yield 3-month trend, multi-month realized cross-sectional dispersion,
  regime label. Slow by construction — the surviving timescale.
- **Labels**: `ticker_forward_returns.fwd_60d` plus the backtest corpus.
- **10-minute data: explicitly rejected as a prerequisite.** The conditioning
  variables are slow and the label is 60d; finer granularity adds engineering
  and noise, not information. It belongs to 105 execution, which also does not
  need it in v1.

## 4. Stage 0 — ESS first, or nothing (~1 week, $0)

1. Assemble the meta-panel (leg scores × state × fwd returns), committed
   script, read-only inputs.
2. **Compute the effective sample BEFORE freezing any rule**: non-overlapping
   observation dates spaced ≥ h trading days, per horizon. Live data gives
   n_eff=2 at h=60 [measured 2026-08-23]; the backtest corpus must be measured
   the same way, and the yearly concentration of the edge (2020/2025/2026)
   counted against it, not around it.
3. Screen-grade conditional-skill table: per-leg IC by state tercile. SCREEN
   only — no decision follows from Stage 0.

**KILL: if n_eff at h=60 < 12 independent observations, Stage 1 is NOT run**
and that is the finding. (12 is the floor for a block-t to mean anything at
all; it is deliberately harsher than hope.)

### 4a. Two floors, not one — the feasibility floor does NOT authorize Stage 1

`[REVISED 2026-08-24, codex review]` An earlier revision used `n_eff >= 12` as
though clearing it were sufficient to proceed. It is not, and conflating the
two floors is how an underpowered fit gets authorized by a number that was
never about fitting:

- **FEASIBILITY floor — `n_eff >= 12`.** Below it, no statistic on this corpus
  means anything and the line stops. This is the floor already stated above and
  it is unchanged.
- **MODEL-EVALUATION floor — derived, and much higher.** Stage 1 does not
  compute one statistic; it *fits* a conditional learner over state buckets and
  evaluates it out of sample. Every (state bucket x evaluation fold) cell needs
  its own independent observations, so the requirement is a product, not a
  threshold:

  | state buckets | folds | min indep obs / cell | required n_eff |
  |---|---|---|---|
  | 2 | 2 | 5 | **20** |
  | 3 (the terciles §4.3 uses) | 2 | 5 | **30** |
  | 3 | 3 | 5 | **45** |
  | 3 | 3 | 8 | **72** |

  **Every one of these exceeds 12.** So there is a real band —
  `12 <= n_eff < 20` at the most permissive shape — in which Stage 0's
  descriptive table is measurable and **Stage 1 is still not runnable**. That
  band is a legitimate outcome, not a gap to be argued past.

For calibration on how far away this is: live data gives **n_eff = 2 at h=60**
[measured 2026-08-23]. The backtest corpus may do better, but the gap to 30 is
the thing Stage 0 is actually measuring, and the design should not pretend the
answer is likely.

**Stage 1 is authorized only when the realized n_eff clears the MODEL-EVALUATION
floor for the exact shape frozen in §5a — not the feasibility floor.**

## 5. Stage 1 — the simplest conditional model (shape only; frozen in a SECOND prereg, §5a)

- Model: ridge gating or depth-≤2 xgb, strong regularisation. NOTHING larger:
  a transformer at this n_eff is guaranteed memorisation of which years were
  good, indistinguishable in-sample from discovery.
- Prereg frozen BEFORE the run: folds, fold-defining constants (they are
  prereg content), the comparison statistic (block-t on non-overlapping
  blocks, gap ≥ h — never a borrowed 1.96), and the placebo discipline the WF
  gate applies (shuffled-label floor ≈ +0.04 is the known leakage floor;
  nothing under it counts).
- Comparison: w(state) blend vs uniform blend, same legs, same corpus.
- **Known trap, avoided by construction**: arms with different leg-counts
  measure DILUTION, not contribution [memory: served-blend-is-unweighted-zsum,
  08-18]. Both arms here always carry ALL legs; only weights differ.

**KILL: Stage 1 fails placebo or fails to beat uniform ⇒ line closed, written
up, no Stage 2.**

### 5a. This design does NOT authorize a Stage-1 run — a second prereg must merge first

`[REVISED 2026-08-24, codex review]` As written, §5 leaves the model choice
("ridge **or** depth-≤2 xgb"), the folds, the regularisation grid, `w_max`, and
the numerical meaning of "beats uniform" to be settled later. Settling them
later, after Stage 0 has shown the data, is not a scheduling detail — it is
choosing the decision rule with the outcome partly visible, which is the defect
class this programme has hit repeatedly and which no amount of downstream rigour
repairs. **This section removes that freedom rather than promising not to use
it.**

Approving this design authorizes **Stage 0 only**. A label-bearing Stage-1 run
requires a SECOND design/prereg PR, reviewed and merged, that freezes:

1. **One** model — not a disjunction. `ridge` or `depth-<=2 xgb`, chosen and
   named, with its hyperparameters as literals (penalty/depth, and the full
   grid if any search is permitted at all).
2. The **state buckets** (count and boundaries) and the **folds** — including
   the fold-defining constants, which are prereg content, not implementation
   (fold-defining constants belong IN the frozen table, not in the runner).
3. `w_max` and any clamp, as numbers.
4. A **numerical** promotion criterion. "Beats uniform" is not a criterion:
   state the statistic, the threshold, and the dependence-aware inference
   (block-t over non-overlapping blocks with gap >= h — never a borrowed 1.96),
   plus the placebo floor the WF gate applies.
5. The realized `n_eff` from Stage 0, and an explicit demonstration that it
   clears the §4a MODEL-EVALUATION floor **for the shape frozen in that same
   PR** — per state bucket, per fold, counted before the rule.

**The binding constraint on that second PR: Stage 0's results may NOT be used to
choose any of items 1–4.** Stage 0 is descriptive by construction (§4.3) and it
runs on the same corpus Stage 1 will be evaluated on, so a model or threshold
picked to suit its table is a rule fitted to the data it will be tested on.
Items 1–4 must be justified from theory, prior work, or house convention that
predates the Stage-0 output. If they cannot be — if the honest answer is "we
would need to see the table first" — then **this corpus is burned for Stage 1**
and the second PR must say so and propose a fresh corpus, exactly as the
candidate-manifest rule requires elsewhere in this programme (orch#993).

Stage 0 may of course *report* whatever it finds, and its n_eff measurement is
precisely what item 5 consumes — measuring the sample is not the same as
choosing the rule from the sample.

## 6. Stage 2 — capacity, only on survival

Larger models (deeper xgb, attention over leg histories) and richer state,
each against the same frozen comparison. Reaching Stage 2 requires Stage 1
surviving review — not merely being run.

## 7. Deployment path (if it survives everything)

The weight vector ships as a slow artifact (weekly refresh at most), through
the WF gate like any scorer change, then shadow before prod. No fast loop:
the hypothesis is slow-state; a daily-updating weight vector would be the
already-killed fast-routing hypothesis wearing new clothes.

## 8. Explicitly NOT in this design

- No 10-minute or finer data pipeline.
- No coupling to 105 until post-Stage-1 survival.
- No new base models — this line weighs existing legs. (New legs are their own
  WF-gated lines.)
- No claim that this fixes `genuine_ic ≈ 0`. If no leg has conditional skill,
  Stage 0's table will say so, and that is a finding worth having.

## 9. Review

codex (haorensjtu-dev). Implementation only after design approval.
