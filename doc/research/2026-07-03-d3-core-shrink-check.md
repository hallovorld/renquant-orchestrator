# D3 incumbent-book core-shrink check — VERDICT: NULL (no core helps; raw reads uniformly negative)

STATUS: research measurement, read-only on all production data, FROZEN-SPEC
EXECUTION with the three-commit freeze-first discipline: commit 1 = the frozen
mini-spec (`doc/research/evidence/2026-07-03-d3-core-shrink/frozen_spec.json`)
BEFORE any core was selected or any statistic computed; commit 2 = harness +
controls (`scripts/d3_core_shrink_check.py`); commit 3 = this memo + evidence.
**0 deviations** against the frozen spec. This is the incumbent-book core-shrink
measurement RS-5 (#282 §4) explicitly deferred to the D3 memo — the LAST input
to the D3 down-cap decision. No watchlist/config change; D3/L1 remains the
decision point (master plan §1.5, delegated per the §1 protocol).

## 0. Verdict, stated first

**NULL under the frozen gate — and one-directional.** None of the six frozen
core definitions (LIQ/SEP/SECBAL × {60, 90}) clears the pre-registered bar in
EITHER direction (HELPS or HURTS), on either arm. But the structure of the null
matters for D3:

1. **No help, anywhere.** All 18 member×seed raw paired deltas are NEGATIVE
   (−0.012 … −0.050 pooled ΔIC); all 6 S8 pick-quality deltas are negative
   (−0.9% … −4.1% per 60d, none significant). The mirror-image hypothesis —
   that the incumbent book contains a high-separability core whose pick quality
   improves when the panel shrinks to it (RS-5's liquid-core REV echo; the
   #264 §5 prior) — does **not** replicate on the incumbent book. Nothing here
   even leans toward "shrink helps".
2. **Not a gated HURTS either.** The frozen gate demands all-3-seed unanimity
   on point ≤ −0.010, CI UB < 0, AND placebo-clean sign agreement. SECBAL-90
   was the nearest miss (all seeds material and CI-significant negative; seed
   44's placebo-clean read +0.004 broke unanimity). The placebo leg is doing
   real work (§5): a large share of the raw degradation is a mechanical
   small-training-panel effect that shuffled labels reproduce.
3. **Selection adds nothing over random shrink.** Random same-size cores
   degrade about the same (§6) — the driver is training-panel SIZE, not which
   names are kept. Within-book breadth is load-bearing for panel training —
   mirror-consistent with #264 §5's random-wave correction (random ADDS mostly
   improved the incumbent book; removals hurt it).
4. **The decomposition D3 actually needs (§6):** the cost is in *retraining on
   the shrunken panel*, not in *restricting the book*. The no-retrain
   diagnostics read ≈0-to-slightly-positive on the E35 substrate and
   insignificantly negative on S8. If D3 elects a down-cap, the evidence says:
   do not shrink the TRAINING panel expecting IC gains, and do not price the
   BOOK restriction as an IC gain either — its measured effect is ≈0/negative.

## 1. The question and where it comes from

M8 (#261, verified #264) established that ADDING 100 similarity-selected names
degrades ranking on the incumbent book itself (−0.048 gate delta), while #264's
random-wave control showed random adds mostly IMPROVE the incumbent-book IC —
correcting the mechanism story to "the dilution was similarity-specific" and
raising the prior that a high-separability CORE might out-carry breadth. RS-5
(#282 §4) found an exploratory in-design echo (liquid-core REV +0.0179 vs full
+0.0128 on the fallback small-cap panel) and explicitly recorded that the
incumbent-book core-shrink check "belongs to the D3 memo's own scope". This
memo executes that check: **does shrinking the incumbent panel to a
high-separability core improve the CORE'S OWN realized pick quality?**

## 2. Frozen spec (commit 1; cited, not restated — full text in evidence)

- **Incumbent book**: WF arm baseline = the 133 watchlist tickers in the E35
  dataset (exactly M8's baseline arm). S8 arm full book = the 135 equity
  incumbents (watchlist ∩ pick-table = 142 names — "the 142-name panel" —
  minus the 7 sector/benchmark ETFs).
- **Cores (3 definitions × sizes {60, 90} = 6 members)**:
  - **LIQ**: top-N by full-span median daily dollar volume (outcome-free; bar
    store verified split-consistent).
  - **SEP**: top-N by per-name |IC| under a production-params XGB trained
    2016-01→2017-06 and scored 2017-08→2018-09-30 — a selection window whose
    outcomes resolve by 2018-12, **strictly disjoint** from every evaluation
    label (test dates start 2019-02). M8's rejected disjoint-window
    alternative is available here precisely because incumbents (unlike M8's
    candidates) have deep pre-2019 coverage; 120/133 SEP-eligible, the 13
    post-2018 listings recorded as a coverage limit.
  - **SECBAL**: sector-balanced SEP (M8's largest-remainder allocation +
    release rule verbatim) — separates separability from sector concentration.
- **WF arm (PRIMARY, gating)**: E35 harness at full M8 parity (same 7 CUTS,
  production `PANEL_LTR_PARAMS`, 100 rounds, same featurization/normalization,
  label `fwd_60d_excess`). Paired estimand on the core's own dates and names:
  Δ_t = IC(core-trained model on core names) − IC(133-trained model on the
  SAME names, same rows). Seeds {42,43,44}; M8's qualifying-cut rule applied
  to the core (measured: all 7 cuts qualify for every member — deep incumbent
  coverage); pooled over n=1,618 test dates (2019–2025); moving-block
  bootstrap (block 60, 2,000 draws); within-date train-label-shuffle placebo
  pairs per seed.
- **Gate** (Bonferroni over 6 members × 2 directions, one-sided 99.5833%
  bounds; ±0.010 E36/M8 materiality band): HELPS iff ALL seeds have point ≥
  +0.010 AND CI LB > 0 AND placebo-clean Δ > 0; HURTS symmetric; else NULL.
  Seed unanimity per #264 §5's gate-design note (gate statistic moves ~±0.02
  across seeds).
- **S8 arm (SUPPORTING)**: durable pick table `oos_pick_table_recipe_v2`
  (content-hash-anchored; 508 dates 2024-02→2026-02), NO retraining — pure
  book-restriction read: per-date top-decile-within-core minus
  top-decile-within-full-book mean realized `fwd_60d_excess_raw` (raw-label
  join rate 1.0000), same Bonferroni level, bar ±5 bps/60d (S9 (b)-bar).
- **Controls (mandatory)**: WF positive plant (0.9·rank(score)+0.1·rank(label)
  on SEP-60) must clear HELPS on all seeds; WF true-null = offset-seed
  baseline retrains {142,143,144} vs {42,43,44} through the identical
  machinery — no member-direction may clear; S8 oracle core (outcome-selected)
  must clear; 6 random S8 cores must not.

## 3. WF arm results (PRIMARY; pooled ΔIC on the core's dates, n=1,618)

| Member | raw Δ (s42 / s43 / s44) | 99.58% UB (s42 / s43 / s44) | placebo-clean (s42 / s43 / s44) | gated |
|---|---|---|---|---|
| LIQ-60 | −0.0501 / −0.0441 / −0.0426 | −0.0092 / **+0.0054** / −0.0053 | −0.0348 / −0.0018 / −0.0102 | NULL |
| LIQ-90 | −0.0157 / −0.0146 / −0.0118 | +0.0067 / +0.0150 / +0.0096 | +0.0031 / +0.0195 / −0.0172 | NULL |
| SEP-60 | −0.0271 / −0.0269 / −0.0268 | +0.0065 / +0.0061 / +0.0059 | −0.0015 / −0.0031 / +0.0116 | NULL |
| SEP-90 | −0.0287 / −0.0192 / −0.0215 | −0.0090 / **+0.0018** / −0.0011 | −0.0255 / +0.0015 / +0.0082 | NULL |
| SECBAL-60 | −0.0318 / −0.0306 / −0.0255 | −0.0049 / −0.0030 / **+0.0052** | −0.0147 / −0.0187 / +0.0191 | NULL |
| SECBAL-90 | −0.0290 / −0.0248 / −0.0262 | −0.0131 / −0.0028 / −0.0056 | −0.0159 / −0.0086 / **+0.0040** | NULL |

- **HELPS never comes close**: 18/18 seed-member points are negative; no CI
  lower bound is above −0.038.
- **HURTS misses on unanimity legs** (pre-registered, not post-hoc): LIQ-90 /
  SEP-60 fail materiality+UB; LIQ-60, SEP-90, SECBAL-60 each have one seed
  with UB > 0; SECBAL-90 clears materiality and UB < 0 on ALL seeds and fails
  only seed 44's placebo-clean sign (+0.0040).
- fwd_20d secondary (seed 42, diagnostic): negative for all 6 members
  (−0.018 … −0.045) — sign-consistent.

## 4. S8 arm results (SUPPORTING; top-decile pick-quality Δ, raw 60d excess units, 508 dates)

| Member | pooled Δ (per 60d) | 99.58% bounds (seed 42) | read |
|---|---|---|---|
| LIQ-60 | −0.0094 | [−0.0380, +0.0315] | NULL |
| LIQ-90 | −0.0238 | [−0.0653, +0.0250] | NULL |
| SEP-60 | −0.0253 | [−0.1037, +0.0506] | NULL |
| SEP-90 | −0.0410 | [−0.1101, +0.0067] | NULL |
| SECBAL-60 | −0.0334 | [−0.0987, +0.0329] | NULL |
| SECBAL-90 | −0.0411 | [−0.1093, +0.0035] | NULL |

All three bootstrap seeds agree everywhere (per-seed bounds in evidence).
Points are uniformly negative — restricting the book shrinks the top-decile
candidate pool (~14 → ~6–9 picks/date) and realized pick quality drops, but
nothing is significant at the Bonferroni level on this 508-date,
BULL_CALM-dominated window.

## 5. Controls (all PASS — the machinery detects effects and passes nulls)

- **WF positive plant** (SEP-60, all seeds): Δ = +0.0874/+0.0870/+0.0870, CI
  LB ≥ +0.0842 — clears the full HELPS bar ×3. **PASS.**
- **WF true-null** (offset-seed retrains, all 6 members × 3 seed-pairs):
  max |Δ| = 0.0063, no member-direction clears any gate leg combination.
  **PASS** — and it calibrates the retrain-noise floor at ~±0.006, so the
  member deltas (−0.012 … −0.050) are 2–8× retrain noise.
- **S8 oracle core**: Δ = +0.0662, LB +0.0187 on all seeds → SUPPORTIVE-POS.
  **PASS.** **S8 random nulls**: 6/6 NULL. **PASS.**
- **Placebo structure (interpretive, important)**: the placebo deltas
  themselves are systematically negative (grand mean −0.023 across the 18
  member-seed placebo pairs) — a core-trained model underperforms the
  133-trained model on core names EVEN WITH shuffled labels. The known ~+0.04
  embargo-leakage floor is training-panel-size dependent. Consequently the
  placebo-clean residuals (raw − placebo) are small/mixed-sign (member means
  −0.016 … +0.002): the raw degradation is substantially a MECHANICAL
  small-panel effect, and a label-specific signal-dilution component is not
  separately established. This is exactly what the frozen placebo leg was for;
  it is why SECBAL-90 is NULL and not HURTS.

## 6. Mechanism: it's the training panel, not the names (diagnostics, not gated)

- **Random-core retrain reference** (3 uniform draws/size, seed 42): 60-name
  random cores Δ = −0.031/−0.042/−0.037; 90-name Δ = −0.005/−0.009/−0.009.
  The designed cores sit inside or below the random band (LIQ-60 −0.050 is
  WORSE than every random-60 draw). **Liquidity/separability/sector-balance
  selection buys nothing over random shrink; panel size dominates.** Shrink
  133→90 costs ~1–3 raw IC points; 133→60 costs ~3–5.
- **Selection-only read** (133-trained model, no retrain, IC on core names vs
  full universe, seed 42): LIQ-60 +0.0218, SECBAL-60 +0.0118, SEP-60 +0.0053,
  LIQ-90 +0.0031, SEP-90 −0.0024, SECBAL-90 −0.0040. The cores are, if
  anything, slightly EASIER to rank under the full-panel model — the
  degradation in §3 is created by retraining narrow, not by the core names
  being harder.
- **Per-regime (EXPLORATORY**, committed C3 regime series — labels NOT
  point-in-time, inherits all C3 substrate caveats): the degradation
  concentrates in BEAR (e.g. SEP-60: BEAR −0.107 n=251 vs BULL_CALM −0.013
  n=1,140) — small-panel models degrade most exactly where the book needs
  ranking most. Reporting only; the gate does not read these.
- **Core overlap** (correlated tests, stated): SEP-60∩SECBAL-60 = 54/60;
  LIQ-60∩SEP-60 = 28/60. The 6 members are far from independent; Bonferroni
  k=12 is conservative.

## 7. What this feeds into D3 (cite, don't re-litigate)

Per the frozen consequence mapping (spec `d3_consequence_mapping`, NULL
branch, with the §6 decomposition):

- **No IC-level evidence that shrinking the incumbent book improves the
  core's own pick quality.** The down-cap case in D3 must rest on its other
  legs — M7's primary-panel result (still INCONCLUSIVE pending Norgate, #282),
  new-data arguments, ops/cost — not on an intrinsic core-quality gain.
- **Both BR-path hedges have now reported**: M8 (adds) = NO-GO; this check
  (shrink-and-retrain) = NULL with uniformly negative raw reads. Term BR
  should not be priced as an IC gain from panel-composition moves on the
  current information set.
- **If D3 nonetheless elects a down-cap** (for cost/ops/data reasons): keep
  the TRAINING panel broad. The measured cost lives in retraining on the
  shrunken panel (§3); pure book restriction reads ≈0/insignificantly
  negative (§4, §6 selection-only). A book-restriction decision should be
  evidenced by a production-scorer shadow replay (ops-level), not by this
  harness.
- This memo renders evidence, not the decision; L1/D3 synthesis follows the
  master-plan §1 delegation protocol.

## 8. Evidence boundary

- **WF arm**: alpha158_816 E35 corpus — May-2026 R1K membership projected
  back (survivorship inflates BOTH arms' absolute IC; the paired same-row
  delta controls most of it); alpha158-only features (production adds
  fundamentals); absolute ICs carry the ~+0.04 embargo-leakage floor, which
  §5 shows is panel-size-dependent — only paired differences are read, and
  the placebo-clean residual is the honest signal-specific read. All 7 cuts
  qualify (test 2019–2025, n=1,618 pooled dates); no costs modeled (a shrink
  REDUCES costs, so the no-help conclusion is conservative only against the
  cost term, which cannot rescue a negative IC read).
- **S8 arm**: 508 dates 2024-02-02→2026-02-11, BULL_CALM-dominated
  (M3/V3-class era caveats), survivorship 292-name panel, resolved outcomes
  end with the table; overlaps WF cuts 6–7 test windows — the two arms are
  CORRELATED reads, not independent replications.
- **SEP definition**: separability measured on a 2017-08→2018-09 disjoint
  window — 1–7 years stale relative to evaluation; a "fresher" outcome-based
  selection window disjoint from ALL cuts does not exist by construction.
  13/133 names SEP-ineligible (post-2018 listings).
- **Multiplicity**: Bonferroni k=12 (6 members × 2 directions), one-sided
  99.5833% block-bootstrap bounds, block 60, n_boot 2,000; training seeds
  {42,43,44} all run and reported, none cherry-picked; members are strongly
  overlapping (correlation stated in §6).
- **Implementation note (not a deviation)**: the spec's "round(0.1·n)" for
  S8 decile size is implemented as floor(0.1·n + 0.5) (deterministic
  half-up), and the S8 read uses bootstrap-seed unanimity as frozen.

## 9. Reopening conditions (recorded; none is a re-pitch)

1. **R1**: PIT-clean panel-era outcome accrual (S5 ledger wiring / decision
   ledger reaching adequate fwd_60d coverage on the live book) → re-run the
   S8 arm on non-survivorship, production-scorer data. This is the
   substrate-quality reopening, not a redesign.
2. **R2**: if D3 elects book-restriction for non-IC reasons, the next
   evidence is a ≥10-session production-scorer shadow replay restricted to
   the chosen core (ops harness, not this one).
3. **R3**: a fundamentals-augmented rerun (alpha158+fund featurization
   parity with production) is admissible future work if D3 needs it; it does
   not reopen this verdict by itself.

## 10. Reproduction

```bash
# umbrella venv (xgboost); stages in order; evaluate ~6 min on M-series
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/d3_core_shrink_check.py select
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/d3_core_shrink_check.py evaluate
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/d3_core_shrink_check.py s8
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/d3_core_shrink_check.py verdict
```

Evidence: `doc/research/evidence/2026-07-03-d3-core-shrink/{frozen_spec,
core_selection, wf_results, s8_results, verdict, manifest}.json` +
`{wf_per_date,s8_per_date}.json.gz` (per-date series sufficient to recompute
every bootstrap). The manifest records SHA-256 of every input (dataset,
strategy config, GICS map, pick table, raw-label join source, 133-name bar
store combined fingerprint, regime series) and of the harness code. WF stage
runtime 373 s (≈420 XGB fits).
