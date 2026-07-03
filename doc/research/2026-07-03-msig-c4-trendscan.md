# C4 — trend-scanning label through the REPAIRED WF gate — VERDICT: INCONCLUSIVE

STATUS:   confirmatory measurement of M-SIG candidate C4 against the FROZEN spec
          (`doc/design/2026-07-02-m-sig-signal-stack-spec.md`, #243 r4, §1.4/§2a/§3).
          Run 2026-07-03, strictly after S3 landed (renquant-backtesting#61, merged
          2026-07-03T09:21Z) — the spec's "earliest test: 2026-Q3, strictly after S3
          lands" precondition is satisfied. Freeze-first: every interpretation was
          pinned in `doc/research/evidence/2026-07-03-c4/c4_frozen_addendum.json`,
          committed BEFORE the harness ran (verifiable in this branch's commit order).
RESULT:   **Mechanical verdict INCONCLUSIVE on all 3 seeds, robust across the entire
          frozen margin bracket {0.015, 0.02, 0.025} and under the pooled sensitivity
          reading.** The gating-cell (BULL_CALM) placebo-difference point estimate is
          positive and above the frozen margin on every seed (+0.0378/+0.0258/+0.0353,
          mean +0.0330) — the #176 relative story REPRODUCES under the repaired
          discipline — but the Bonferroni-corrected one-sided 98.33% CI lower bound is
          below zero on every seed ([−0.018, −0.017, −0.010]). The test is honestly
          underpowered at the frozen bar: detecting ≥0.02 at this CI level needs a mean
          ≈ +0.069 at the measured SE (~0.023), i.e. ~2× the observed effect. Neither
          GO nor KILL. C4 casts NO stack vote.

---

## 1. The frozen spec row (quoted verbatim, #243 r4 §1.4)

> - **Estimand**: retrain target = signed t-stat of the strongest forward trend window
>   (López de Prado trend-scanning label), compared against the raw fwd_60d label, on the
>   PROPER (repaired) WF gate.
> - **Substrate**: alpha158 multi-horizon panel (exists) + the repaired WF gate (S1–S3;
>   S1/S2 merged, S3 pending as of this freeze).
> - **Placebo-difference margin (frozen NOW, not deferred; r3 corrects r2's justification)**:
>   **0.02**. […] **r3 is honest about this: the 0.02 margin is ARBITRARY, not derived from
>   a paired-noise argument** […] the build PR MUST additionally report a sensitivity check:
>   the same block-bootstrap CI evaluated against neighboring candidate margins
>   {0.015, 0.02, 0.025} […]
> - **Deterministic rule (r3: Bonferroni-corrected 98.33% level, per §2a)**: GO iff
>   placebo-difference (trend-scan minus raw, on the S3-repaired gate) block-bootstrap
>   98.33% CI lower bound > 0.02, evaluated on production WF; sim non-inferiority […] is a
>   required secondary condition […] sim Sharpe does not fall by more than 0.1 versus the
>   raw-label sim Sharpe over the same window […]
> - **CI, sample size**: shared default (block-bootstrap, block=60, n≥600, seeds {42,43,44}).
> - **Earliest test**: 2026-Q3, strictly after S3 lands.
> - **Prior evidence — EXPLORATORY/RETROSPECTIVE**: `#176` (measured): BULL_CALM
>   placebo-clean beats raw in 3/3 seeds, mean +0.0149 — **this number is retrospective.**
>   […] the eventual C4 build PR's result must come from a genuinely fresh run on the
>   repaired gate — it may not simply re-cite +0.0149 as if it were the frozen-gate outcome.

Shared defaults applied (spec §0/§2a): KILL iff the same-level CI upper bound < 0.02;
else INCONCLUSIVE; one-sided α = 0.05/3 ≈ 0.01667 (Bonferroni k=3 over {C2,C3,C4});
seeds {42,43,44} all run and reported; n≥600 floor.

## 2. What was measured (operationalization — every pin frozen pre-run in the addendum)

- **"The S3-repaired gate" for C4** = the placebo-DIFFERENCE semantics S2/S3 merged into
  the production WF gate: `genuine_ic = aligned_real_ic − placebo_ic`, where the placebo
  leg evaluates the SAME frozen model score against the label shifted −2×label_horizon
  = −120 sessions per ticker (clipped ±0.5) and `aligned_real_ic` is the same score vs
  the real label on exactly the rows where the shifted label exists
  (`renquant-backtesting src/renquant_backtesting/wf_gate/runner.py` — `_gate_shift_days
  = 2 * _label_horizon`; `analysis/analyze_manifest_sanity_placebo.py::shift_diagnostics`;
  per-date cross-sectional Spearman, ≥5 names). Note S3's governance state: v2's absolute
  ceiling remains the ENFORCED production gate; the genuine-IC difference is v3
  SHADOW-ONLY diagnostics there. C4's frozen rule was pre-registered on the DIFFERENCE
  test, so that is what gates here — this run does not promote v3 to enforcement anywhere.
- **Estimand**: per (date, cell) paired series
  `Δgenuine(t) = [ic_real_ts(t) − ic_placebo_ts(t)] − [ic_real_raw(t) − ic_placebo_raw(t)]`,
  both arms scored against RAW `fwd_60d_excess` (the trend-scan label is a TRAINING
  target only). Gating quantity = mean over the BULL_CALM cell (frozen pre-run per spec
  design rule 2: "BULL_CALM is the binding cell"; the C4 row itself names no cell — the
  pooled reading is reported as a sensitivity below).
- **Arms**: XGB rank:pairwise, production params (η=0.05, depth 5, mcw 50, subsample 0.7,
  colsample 0.7, 100 rounds), identical except the training label; label construction
  verbatim from the 06-23 lineage (signed max-|t| OLS slope t-stat over forward windows
  {0,5,10,20} and {0,5,10,20,60} from `fwd_{5,10,20,60}d_excess_raw`).
- **WF**: 8 cuts, 3-year rolling train, 1-year test, test years 2018–2025, embargo = 65
  sessions (> the 60-session label horizon; the 06-23 cuts had a ~21-session gap →
  training-label windows reached ~30 sessions into the test year). The embargo repairs
  train/test label-window overlap as a purity measure only — the branch-measured fact
  that a 90d embargo does NOT remove the shuffled-label floor (see §8) is respected: no
  absolute IC is trusted anywhere in this memo; only the paired difference gates.
- **CI**: carried-mask moving-block bootstrap on the full contiguous trading-date axis
  (block=60, n_boot=2000; the C3 round-2 corrected pattern — blocks can never splice
  regime episodes or inter-cut calendar gaps; adapted from
  `scripts/c3_residual_momentum.py::block_bootstrap_conditional_mean`).
- **Seed rule (frozen)**: XGB seed = bootstrap seed = s ∈ {42,43,44}; final GO only if
  all 3 seeds GO; final KILL only if all 3 KILL; else INCONCLUSIVE.

## 3. Headline numbers (gating cell BULL_CALM, frozen margin 0.02)

| seed | n dates | mean Δgenuine | 98.33% one-sided [lb, ub] | boot SE | verdict |
|------|---------|---------------|---------------------------|---------|---------|
| 42   | 663     | **+0.0378**   | [−0.0183, +0.0898]        | 0.0252  | INCONCLUSIVE |
| 43   | 663     | **+0.0258**   | [−0.0172, +0.0815]        | 0.0232  | INCONCLUSIVE |
| 44   | 663     | **+0.0353**   | [−0.0104, +0.0803]        | 0.0216  | INCONCLUSIVE |

**Final: INCONCLUSIVE** (all seeds; neither lb > 0.02 anywhere, nor ub < 0.02 anywhere).
n = 663 ≥ 600 clears the floor, but that is only ~11 nominal blocks (measured axis
coverage: 30 full 60-session blocks, 24 usable in-cell) — exactly the thin-block regime
the spec's own §0 power note warns about.

Decomposition (means over the gating cell; diagnostic):

| seed | genuine_ts | genuine_raw | real_ts | placebo_ts | real_raw | placebo_raw |
|------|-----------|-------------|---------|------------|----------|-------------|
| 42   | +0.0292   | −0.0086     | +0.0398 | +0.0106    | +0.0188  | +0.0274     |
| 43   | +0.0227   | −0.0031     | +0.0364 | +0.0137    | +0.0138  | +0.0170     |
| 44   | +0.0414   | +0.0060     | +0.0395 | −0.0019    | +0.0282  | +0.0222     |

This REPRODUCES the #176 relative story under the repaired discipline: trend-scan's
placebo-clean level is positive and stable (+0.023…+0.041), raw's is seed-noise around
zero (−0.009…+0.006) because raw's placebo leg carries roughly as much IC as its real
leg in BULL_CALM. (The retrospective +0.0149 is cited here for lineage only; per the
spec it is NOT this candidate's result and this run does not treat it as one.)

## 4. Margin sensitivity + pooled sensitivity (both frozen requirements)

- **Margins {0.015, 0.02, 0.025}: INCONCLUSIVE at every margin, all seeds.** The
  conclusion is NOT margin-fragile: the CI lower bounds (≈ −0.01…−0.02) sit below zero,
  far below even the friendliest bracket value, and the upper bounds (≈ +0.08) far above
  the harshest. No GO/KILL flip anywhere in the bracket.
- **Pooled (ALL) sensitivity reading: INCONCLUSIVE on all seeds** — and the pooled point
  estimate is ≈ zero (−0.0066/−0.0090/+0.0029, n=1399): the BULL_CALM gain is offset
  elsewhere. Had ALL been frozen as the gating cell, the verdict would still be
  INCONCLUSIVE, with a near-zero point estimate.

## 5. Mandatory per-regime cuts (design rule 2; diagnostic, non-gating)

| cell | n dates | mean Δgenuine (seeds 42/43/44) | mechanical reading |
|------|---------|--------------------------------|--------------------|
| BULL_CALM (gates) | 663 | +0.0378 / +0.0258 / +0.0353 | INCONCLUSIVE ×3 |
| ALL | 1399 | −0.0066 / −0.0090 / +0.0029 | INCONCLUSIVE ×3 |
| BULL_VOLATILE | 685 | −0.0507 / −0.0394 / −0.0349 | mechanical KILL ×3 |
| BEAR | 51 | +0.0092 / −0.0551 / +0.0902 | n-floor not met |

**The BULL_VOLATILE cell reads a mechanical KILL on all three seeds** (ub < 0.02 with
negative means): under the repaired discipline the trend-scan label is WORSE than raw
there. Only BULL_CALM gates (frozen pre-run), but this asymmetry — helps the calm cell,
hurts the volatile cell, nets to ≈zero pooled — is the same shape as the analyst-feature
finding (adds BULL_CALM only / hurts BULL_VOLATILE) and materially weakens the case that
a trend-scan retrain would be a net portfolio win. Per-regime multiplicity: these cells
are reported per design rule 2, they cast no vote and consume no alpha budget.

## 6. Window-artifact check (the canonical price-trend NULL precedent)

Motivation: the repo's canonical price-trend result (memory: mom_12_1's 5y/h20 "edge"
was a 2021-26 window artifact that collapsed at 8y). The 8 OOS test years directly
bracket that window; per-year Δgenuine, BULL_CALM, mean over seeds:

| year | 2018 | 2019 | 2020 | 2021 | 2022* | 2023 | 2024 | 2025 |
|------|------|------|------|------|-------|------|------|------|
| Δgenuine | +0.134 | +0.093 | −0.093 | +0.018 | −0.123 | −0.028 | +0.076 | −0.056 |
| n | 106 | 105 | 50 | 117 | 4 | 124 | 101 | 56 |

(*2022 has only 4 BULL_CALM dates — noise.)

- **Pre-2021: +0.0740** (per-seed +0.068/+0.074/+0.080, n=261) vs **2021+: +0.0064**
  (+0.018/−0.005/+0.006, n=402).
- **C4's edge is NOT the 2021-26 artifact — it has the OPPOSITE era profile**: it
  concentrates in 2018-2019 (cells never inspected by any prior trend-scan work in this
  repo) and is ≈flat in the 2021+ era. That clears the specific precedent this check
  targets, but it is NOT good news: the era closest to live deployment shows essentially
  no advantage, and the year-level series sign-flips (−0.093 in 2020, +0.076 in 2024),
  which is exactly why the honest CI is wide.

## 7. Positive controls (S-REL R2; all PASS — the INCONCLUSIVE is admissible)

Score-level, frozen pre-run in the addendum (disclosed deviation D4: planting a
calibrated effect through XGB training is not reliably sizeable to 2× bar; what the
plant exercises is the full aligned/placebo IC computation + paired difference +
carried-mask bootstrap + verdict rule — the machinery whose output is the verdict).

- **PC-A (planted detection at ~2× bar)**: plant `z(rank(score_raw)) + w·z(rank(y_real))`,
  w grid-calibrated to the BULL_CALM Δgenuine closest to +0.04 → w\*=0.04, realized plant
  +0.0350; **GO on all 3 bootstrap seeds** (lb ≈ +0.0332 > 0.02). Detection works.
  Honest caveat: the planted score's Δgenuine series is far less volatile than a real
  trained-model difference, so PC-A validates the CORRECTNESS of the detection
  arithmetic, not the POWER of the test at realistic noise — the real measurement's SE
  (~0.023) is the power statement, and it is what produces the INCONCLUSIVE.
- **PC-B (permuted candidate)**: within-date permutation of the trend-scan scores →
  Δgenuine +0.0093, never GO (INCONCLUSIVE ×3). ✓
- **PC-C (both arms permuted — true-zero paired null)**: Δgenuine +0.0045, **mechanical
  KILL ×3** (ub ≈ +0.016 < 0.02) — the KILL branch demonstrably fires on a true null
  against the +0.02 margin; the real candidate's failure to KILL is therefore
  informative, not a machinery artifact. ✓
- Committed synthetic fixture: `tests/test_msig_c4_trendscan.py` (9 tests: label
  sign/persistence/missing-data, gap-respecting bootstrap, frozen verdict semantics,
  end-to-end planted-GO and null-never-GO).

## 8. Power (illustrative, per the spec's own convention) — why this is structural

At the measured bootstrap SE (~0.022-0.025) the minimal mean detectable above the 0.02
margin at one-sided 98.33% is ≈ 0.02 + 2.13·SE ≈ **+0.067…+0.073** — about 2× the
observed +0.033. Equivalently, if the true effect equals the observed point estimate,
the SE would need to shrink to ≈0.006 — ~14× more effective blocks than the 24 usable
ones the full 2018-2025 panel already provides. Waiting for accrual cannot close that
by 2027-Q3 (≈+5 blocks). **Under the current frozen protocol, C4 is structurally
INCONCLUSIVE-at-deadline**: per spec §3 it will be excluded from the stack denominator,
not counted as a KILL. (This is the spec's §2a conservatism working as designed — "a
candidate that would have read GO at the naive 95% level may now read INCONCLUSIVE" —
though here even a naive one-sided 95% bound would not clear: lb95 ≈ mean − 1.645·SE ≈
−0.004…+0.000.)

## 9. Sim non-inferiority (required secondary condition) — NOT RUN, fail-closed

The production sim requires published per-cut artifacts through the production harness;
none exist for a trend-scan model family. Frozen consequence (addendum, pinned pre-run):
a primary GO could NOT have been recorded as C4 GO without it. Moot here (primary is
INCONCLUSIVE). The cheap top-minus-bottom-quintile fwd_60d spread proxy (diagnostic
ONLY, structurally incapable of satisfying the frozen condition) points AGAINST
non-inferiority: raw 60d spread +0.202 vs trend-scan +0.121 per date; non-overlapping
60-session Sharpe 0.51 vs 0.37 (n=25 windows) — directionally consistent with the
06-23 branch's naive portfolio finding and, at hardened settings there, with
indistinguishability (below).

## 10. Full retrospective lineage (disclosure — includes UNMERGED history the spec did not cite)

Everything here predates the 2026-07-02 freeze, is EXPLORATORY/RETROSPECTIVE, and casts
no vote. The spec's C4 row cites only the merged #176 state; a history search for this
run surfaced three FURTHER follow-ups on the unmerged `feat/drift-free-label-trial`
branch (commits `297ca31b`, `aa5fdbf0`, `2ebe46f9`) that materially sharpen the prior:

1. **#176 (merged)**: BULL_CALM placebo-clean beats raw 3/3 seeds, mean +0.0149;
   label-shuffle null wide and leaky (~+0.04); "promote to the PROPER gate."
2. **Embargo-gap hypothesis TESTED and REFUTED (`297ca31b`, unmerged)**: a 90d embargo
   barely moves the shuffled-label floor (raw +0.0360 → +0.0367) — the floor is label
   autocorrelation/undetermined, NOT the embargo gap. (This run's 65-session embargo is
   therefore a purity repair for train/test label overlap, not a floor fix; consistent
   with S3's framing of the floor as "embargo-leakage/label-autocorrelation".)
3. **Naive portfolio P&L REJECTED trend-scan (`aa5fdbf0`, unmerged)**: top-20% selection
   by trend-scan realized LOWER fwd_60d alpha than raw in every regime.
4. **Hardened P&L walk-back to INCONCLUSIVE (`2ebe46f9`, unmerged)**: with 90d embargo +
   non-overlapping rebalances + 10bps costs the naive result evaporates (BULL_CALM raw
   +0.162/Sh 1.80 vs trend-scan +0.114/Sh 2.21, n≈10; ALL tied) — statistically
   indistinguishable at that n.

Net prior: relative IC-style edge in BULL_CALM (stable), portfolio value unproven and
possibly negative, all under leaky/underpowered harnesses. This run's repaired-gate
result — positive but underpowered BULL_CALM difference, negative BULL_VOLATILE,
≈zero pooled, proxy spread favoring raw — is CONSISTENT with that entire picture.

## 11. Prospectivity affirmation (scoped honestly)

**No prior script in this repo's git history — merged or unmerged — computed C4's
gating estimand before this run**: the aligned-real vs 2×-horizon-shift score-placebo
genuine-IC paired difference (S2/S3 semantics), on embargo-repaired cuts, with the
carried-mask block-bootstrap and the Bonferroni-corrected decision rule. Verified
against all six trend-scan lineage scripts (1×-shift TRAINED-placebo gate,
seed-robustness, 2× label-shuffle, embargo-test, portfolio-sim, hardened-pnl — none
compute a 2×-shift score-placebo or any bootstrap CI). Test years 2018/2019 appear in
NO prior trend-scan computation (all prior work used 2020-2025 test windows).
**Weaker than full prospectivity, stated plainly**: the underlying panel, the label
construction, the XGB recipe, and the 2020-2025 test era were all previously inspected
(D5) — no second panel exists for C4 by construction. The genuinely fresh elements are
the estimand, the discipline, and the 2018/2019 cells; those fresh cells happen to
carry the largest positive readings (§6), which cuts both ways: they are the least
data-mined AND the least deployment-relevant era.

## 12. Consequence for the M-SIG stack / G106 (V4-corrected composition)

- **C4: INCONCLUSIVE, recorded.** Casts no vote (neither the 2nd GO nor a KILL). Under
  spec §3 it stays out of `N_resolved`; per §8 above it is structurally
  inconclusive-at-deadline absent a protocol change.
- **Family state ({C2,C3,C4}, k=3, unchanged — #268)**: C3 UNADJUDICATED/open (#268:
  PIT rerun judged not worth a near-term task; on the S5/S8 ledger it cannot reach
  n≥600 by 2027-Q3 → tracks INCONCLUSIVE). C2 non-voting/open (#275: the ≥20%
  coverage-delta reopening precondition measured at −0.02% — refuted; exploratory
  placebo-clean ≈ 0). C4 INCONCLUSIVE (this run). **N_resolved = 0; GO count = 0.**
- **G106 arithmetic (composition per #268: ≥2-of-4 with C1 never voting — i.e. ≥2 GO
  needed from {C2,C3,C4} by 2027-Q4)**: with all three measured/assessed channels now
  at {non-voting, unadjudicated, inconclusive} and each candidate's route to a formal
  GO requiring either new data infrastructure (C3: PIT regime/universe history), a new
  frozen prereg on new evidence (C2: as-filed vintage data), or an operator-amended
  protocol (C4: see reopening conditions), the published composite ≈0.45–0.50 (V4) is
  now clearly stale on the high side. My estimate — assumptions stated, not a frozen
  number: p(C4 formal GO by 2027-Q4) ≈ 0.05–0.10, p(C3) ≈ 0.10, p(C2) ≈ 0.05–0.10 ⇒
  P(≥2 GO) ≈ **0.01–0.03** under current protocols. **The spec's no-early-KILL rule
  governs**: G106 is NOT declared dead here — C2's 2026-Q4 N3-gated slot and the
  reopening routes below remain open — but capital-planning should read the stack as
  tracking the §0 kill branch (benchmark-sleeve default + PIT accrual + 107 re-scoped
  execution-only) unless one of the reopenings lands.
- `doc/research/VERDICTS.md` lives on the unmerged #265 branch; on its rebase, add the
  C4 row pointing at this memo (the #268 pattern — not edited here to avoid conflicting
  with that in-flight ledger).

## 13. Reopening conditions (S-REL R4 — a NEW frozen prereg, never a tweak-rerun)

C4 may be re-measured only under one of:
1. **Production-gate replay**: trend-scan-label artifacts published per cut and run
   through the actual production `wf_gate` runner (removes deviation D1) — worth doing
   only bundled with (3), since it shares this run's power ceiling;
2. **Materially more independent history** (e.g. a validated panel extension backward,
   or a cross-sectional widening that genuinely adds effective blocks — not more of the
   same 292 names);
3. **An operator-amended protocol** re-freezing the decision rule with a
   power-compatible bar (e.g. gating on a one-sided level consistent with a realistic
   MDE, or replacing the point-margin rule with a sequential design) — explicitly an
   operator decision because it trades FWER control for decidability;
4. **A sim-first route**: since §5/§9 suggest the portfolio-level question (BULL_VOLATILE
   harm, spread give-up) may bind before the IC-level one, a production-sim
   non-inferiority run could be REQUIRED to precede any IC re-measurement.

## 14. Deviations (all disclosed; the addendum was not edited after results)

D1 production runner mirrored, not executed (per-cut artifact manifests do not exist for
a hypothetical label family; semantics cited line-by-line — the C3/#268, C2/#275
precedent). D2 substrate: C4's own row (alpha158 multih panel) governs over design rule
1's S5/S8 default; tension disclosed. D3 sim secondary condition not runnable —
fail-closed consequence pinned pre-run (§9). D4 positive controls score-level (§7).
D5 partial data-reuse relative to the retrospective lineage (§11). Run-time discovery,
disclosed here rather than patched into the frozen addendum: the unmerged-branch
lineage (§10 items 2-4) was found AFTER the addendum was committed; it changes no
frozen parameter and no verdict — it strengthens the retrospective-context section
only.

## 15. Evidence boundary

- OOS window 2018-04-06 → 2025-08-20 (1854-session bootstrap axis; the 2×-shift placebo
  leg truncates the aligned set ~120 sessions before the panel end of 2026-02-11).
- n: 663 BULL_CALM dates (per seed), 1399 pooled; 30 full 60-session blocks, 24 usable
  in-cell — thin-block regime, stated.
- Universe: fixed 292-name alpha158 panel (current constituents applied historically; no
  delisting handling) → survivorship-tilted ABSOLUTE levels; both arms share the tilt;
  the paired difference is within-panel comparative. Same limitation class as C2/C3
  (#275/#268) — a confirmatory claim about live deployability additionally needs the
  production sim (§9).
- Regime cells from the GMM regime dataset (argmax per ticker-date), BEAR cell
  effectively unmeasured (n=51).
- Multiple-comparisons frame: voting family {C2,C3,C4}, k=3, one-sided α=0.05/3 frozen
  at spec time; the margin bracket, per-regime cells, pooled reading, and per-year table
  are reported diagnostics that cast no vote; the 3-seed check is a robustness check on
  one corrected result.

## 16. Reproduce

```
# from a renquant-orchestrator checkout, umbrella venv, read-only on all data
RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 42 --out OUT
RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 43 --out OUT
RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py train --seed 44 --out OUT
RenQuant/.venv/bin/python scripts/msig_c4_trendscan.py analyze --out OUT \
    --evidence doc/research/evidence/2026-07-03-c4
RenQuant/.venv/bin/python -m pytest tests/test_msig_c4_trendscan.py -q
```

Evidence: `doc/research/evidence/2026-07-03-c4/` — `c4_frozen_addendum.json` (committed
pre-run), `c4_results.json` (input sha256s, per-seed score-file sha256s, code sha,
env lock, full per-cell/per-year/PC results), `c4_per_date_series.csv.gz` (all per-date
IC legs, all seeds). Total wall time ≈ 4 min (48 XGB fits + analysis).
