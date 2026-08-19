# Does the clf leg beat the served blend? — paired backtest

> ⚠️ **PARTLY SUPERSEDED — read
> [`2026-08-18-erratum-clf-backtest-attribution.md`](2026-08-18-erratum-clf-backtest-attribution.md)
> first.** Every number below reproduced exactly under double-audit, and the
> §1 verdict (`B − A = +0.05863`, CI90 lower > 0) stands. **Two readings do
> not:** (a) §1a/§3's attribution of `A − D = −0.031` to the momentum leg is
> **WITHDRAWN** — it is a dilution artefact of the unweighted z-sum, *less*
> negative than the zero-information prediction, and it collapses 86% under
> this run's own winsorized column; (b) §4b's "the certification does not
> reproduce" is **inverted** — on this backtest's window model#76's own
> instrument gives +0.0155 (CI90 lower −0.045), so +0.02843 is *larger*, not
> 41%. §4a's harness grade is also overstated: the baseline level is 12.56%
> below the sibling vol-switch run and that gap is unexplained.

STATUS: **BACKTEST**, executed under the operator's 2026-08-18 policy
(verbatim: "用backtest代替所有数据积累" — backtests replace
evidence-accumulation waits). It is **not** a preregistered confirmatory and
is **not** a live shadow readout. Nothing here changes production; the
output is input to a deployment discussion, not an authorization.

DATE: 2026-08-18 (run at 2026-08-19T00:03:01Z, runtime 208.9 s
`[VERIFIED — results JSON run_utc/runtime_sec]`).

RUNNER: `doc/research/data/2026-08-18-served-blend-plus-clf-derivation.py`
(this PR). Estimand, corpus, refit ladder, embargo, DGTW instrument and
inference machinery are copied **VERBATIM** from the reviewed vol-switch
confirmatory runner `doc/research/data/2026-08-18-vol-switch-derivation.py`
(orch#1002/#1003, sha256 `e6002a85…`), whose own lineage is the tail_q90
runner (#996/#999); the momentum readers are the verbatim tail_q90
`MomReaders`. `tests/test_served_blend_clf_runner.py` enforces byte-identity
on all 20 reused definitions, so the reuse cannot drift into a rewrite.

PROVENANCE: every number below is `[VERIFIED — read from the committed
doc/research/data/2026-08-18-served-blend-plus-clf-results.json /
…-series.csv / …-blocks.csv / …-refit-ledger.json as written by this run]`
unless tagged otherwise.

---

## 1. VERDICT

**YES — B_3leg beats A_prod on this corpus, under the inherited bar.**

Paired per-date difference `B_3leg − A_prod`, aggregated to the 28 complete
non-overlapping 60-trading-day blocks of the primary corpus
(2017-01-03..2023-09-29, 340 weekly cross-sections):

| statistic | value |
|---|---|
| **block mean (the number)** | **+0.05863** SD/60d |
| blocks | **28** (all complete blocks contribute) |
| positive blocks | 21/28 = **75.0%** |
| ρ̂₁ / ESS (counted BEFORE the verdict) | +0.218 / **17.98** (floor 6) |
| Newey-West(1), df=27 | SE 0.02763, **t = +2.122** (crit 1.703), CI90 lower **+0.01157** |
| stationary bootstrap (E[blk]=2, 10,000, seed 0) | **q05 = +0.01061**, q95 = +0.10596 |
| disagreement between the two inference legs | **False** |
| winsorized ±0.50 SD per-date difference | **+0.01107** (≥ 0, same sign) |
| per-date (unaggregated) mean difference | +0.06003 |

Bar (**inherited verbatim, not invented or tuned here**): CI90 lower bound
> 0 — model#75's frozen decision rule, the rule model#76 passed. Both
inference legs clear it, they do not split, and the guards
(n_blocks ≥ 15, ESS ≥ 6) were satisfied and printed before any verdict
language was emitted.

### 1a. …but read §3 before acting on it

The verdict is real and the arithmetic is clean. The **mechanism is not the
one the question implies.** Per-arm levels on the identical common universe:

| arm | legs | per-date mean DGTW top-decile spread |
|---|---|---|
| A_prod (served today) | z(xgb) + z(mom) | **+0.08926** |
| B_3leg (the candidate) | z(xgb) + z(mom) + z(clf) | **+0.14928** |
| C_2leg (model#76's arm) | z(xgb) + z(clf) | **+0.15420** |
| D_solo (model#76's baseline) | z(xgb) | **+0.12171** |

**A_prod is the worst of the four arms — it sits BELOW solo-xgb.** On this
corpus the momentum leg subtracts from the panel model rather than adding
to it, and most of `B − A` is that drag being diluted, not the clf leg
being strong. §3 decomposes it.

> ⚠️ **WITHDRAWN (erratum, same day).** The ORDERING above is real; the
> ATTRIBUTION in the second sentence is not. Adding a second leg to an
> unweighted z-sum halves the informative leg's weight even when the added
> leg carries nothing, so `A − D` measures dilution, not the momentum leg.
> Under the zero-information null the predicted `A − D` is **−0.03565**,
> i.e. *more* negative than the −0.03073 measured. See the erratum §2.

---

## 2. Computability — the momentum leg (asked first, answered first)

**Finding: the served momentum ledger contains NO historical rows, and the
momentum series is nevertheless fully reconstructible PIT. Nothing was
fabricated.**

- The served ledger
  `artifacts/momentum/momentum_artifact_ledger.jsonl` holds **3 rows**, at
  cutoffs **2026-08-02 / 2026-08-08 / 2026-08-15** — genesis 2026-08-02,
  i.e. **zero coverage inside the 2017-2023 corpus**. The runner asserts
  this (it fails closed if the ledger ever does cover the corpus, so this
  rationale cannot go stale silently).
- That is a fact about the **serving surface**, not about computability.
  `momentum_residual_v0` has **no fitted state**: the owning library's own
  contract is that "training" is the rolling estimation itself. The score
  is a deterministic function of OHLCV total returns, volume, SPY and a
  sector map over the formation window — an equal-weight mean of the
  per-date cross-sectional z-scores of five features (residual-momentum
  alpha t-stat vs SPY, information discreteness, sector momentum, signed
  volume agreement, downside-beta penalty), requiring ≥3 of 5 finite.
- The runner therefore **recomputes the leg per scoring date through the
  owning library**, `renquant_model_momentum.train_momentum_artifact`
  (pure over injected readers, no disk, no clock), with `params_v0()`
  (window 252, skip 21, min_obs 200, min_features 3, min_side_obs 30) —
  the recipe the served config pins as
  `momentum-v0-fd65161a20b29314`. This is not a new idea: the merged
  tail_q90 runner already reconstructs the same leg over a historical
  weekly grid the same way.
- **All four arms are computable on the full primary corpus.** Coverage:
  the momentum leg scores 263 names at the corpus start rising to 292 at
  the end; the common universe averages **277.6** names/date (min 263, max
  292) against **281.3** panel-usable — the momentum leg costs ≈3.7
  names/date, ≈1.3%.
- **PIT is asserted per date, not assumed** (G10): measured effective
  train cutoff ≤ nominal formation-window bound < scoring date. The leg
  reads no forward label at all; its declared 21-business-day skip is an
  *input embargo*, not a label horizon.

---

## 3. The decomposition — what is actually driving `B − A`

Same machinery, same 28 blocks. **DIAGNOSTIC, not part of the frozen
decision rule** — reported because without it the verdict reads as a claim
the data does not support.

| contrast | block mean | NW t | boot [q05, q95] | clears CI90>0? |
|---|---|---|---|---|
| **B − A** (frozen primary) | **+0.05863** | +2.122 | [+0.0106, +0.1060] | **YES** |
| C − D (the certification's own contrast) | +0.02843 | +1.358 | [−0.0058, +0.0616] | no |
| B − D (candidate vs the certified baseline) | +0.02790 | +1.237 | [−0.0085, +0.0652] | no |
| **A − D** (the momentum leg's own contribution) | **−0.03073** | −0.810 | [−0.0915, +0.0323] | no (negative) |
| C − B (what momentum costs inside the 3-leg blend) | +0.00053 | +0.017 | [−0.0480, +0.0452] | no (≈0) |

Read together:

1. **The clf leg's own contribution is +0.028 and does NOT clear the bar**
   on this harness (C − D, and equivalently B − D). Whatever else is true,
   this corpus does not independently re-certify the clf leg.
2. **The momentum leg's own contribution is −0.031** (A − D), with only
   32% of blocks positive. It is not statistically distinguishable from
   zero either — but it is the only leg whose point estimate is negative.
3. `B − A` is large and significant chiefly because **A is the low arm**.
   The served scorer is an *unweighted* z-sum, so adding a third leg
   mechanically cuts each existing leg's share from ½ to ⅓. Adding the clf
   both contributes its own (weak) signal and dilutes the momentum leg's
   drag; those two effects are summed in `B − A` and this design cannot
   separate them.
4. `C − B ≈ +0.0005` says that once the clf leg is present, **the momentum
   leg contributes essentially nothing** — the 2-leg z(xgb)+z(clf)
   construction is as good as the 3-leg one on this corpus.

The honest one-line summary: **on this corpus the candidate beats what is
served, but the cleanest reading of why is that the momentum leg is not
earning its half of the served blend — not that the clf leg is strong.**

> ⚠️ **WITHDRAWN (erratum, same day).** Items 2 and 4 above and this summary
> line read `A − D` and `C − B` as leg attributions. They are not: the
> unweighted z-sum confounds a leg's information with its dilution of the
> others in *every* contrast this design produced, and ρ(xgb, mom) was not
> persisted, so the momentum leg's own sign is **unidentifiable** from this
> run in either direction. `A − D` also collapses 86% under this run's own
> winsorized column (−0.03073 → −0.00430) and was never statistically
> established (NW t −0.810; 0/28 LOBO subsets establish `D > A`). The
> surviving statement is the frozen primary `B − A` and the descriptive
> ordering `{B, C} > D > A`. See the erratum §2 and §5.

---

## 4. Controls

### 4a. Harness control — PASSES (this is the strong one)

> ⚠️ **DOWNGRADED (erratum, same day).** The STRUCTURAL checks below pass
> exactly and that is not in question. The **level** does not: `+0.12171`
> here vs the sibling committed vol-switch run's `+0.13919` on the identical
> corpus = **−12.56%**, while a random 1.3% universe restriction moves the
> level **−0.29%** — 43× short of the gap. Treat arm LEVELS from this
> harness as carrying an unquantified offset; the paired contrasts (where a
> common offset cancels) are the trustworthy reads. Erratum §4.

The runner's construction is checked against the committed, reviewed
vol-switch run over the **identical** corpus, grid, estimand and prod
recipe:

| check | result |
|---|---|
| frozen corpus geometry (G9, tolerance EXACT) | 1,697 td / 821 ON days / 28 blocks / 340 weekly — **all four match** |
| refit cutoff selected per scoring date | **identical on 340/340 dates** |
| panel-usable names per date | **identical on 340/340 dates** (mean 281.3) |
| solo-xgb level | mine **+0.12171** (momentum-restricted common universe) vs vol-switch's committed **+0.13919** (full panel universe); per-date Pearson r = **0.829** `[DERIVED — the two committed series CSVs joined on date]` |

The embargo/ladder/scoring/panel path reproduces the reviewed runner
exactly on every structural check. The −0.0175 level gap is attributable to
(i) the declared momentum-universe restriction, which changes DGTW cell
composition and top-decile membership, and (ii) input-store vintage — the
panel parquet and SPY digests differ between the two runs (both are
live-refreshed surfaces; the historical slice reproduced identically in
shape, but value-level identity was **not** verified). I do not claim a
cleaner attribution than that.

### 4b. Certification cross-check — DOES NOT REPRODUCE, and I say so

> ⚠️ **INVERTED (erratum, same day).** There is no shrinkage to explain. The
> gap is the **corpus window**: 84% of model#76's certified +0.06873 comes
> from the 645 dates AFTER this backtest's corpus ends. Restricted to this
> window, model#76's OWN instrument gives **+0.01554, CI90
> [−0.04481, +0.07117]** — INCONCLUSIVE. So +0.02843 is *larger* than the
> certification's same-window number, not "~41% of the magnitude", and the
> instrument-difference explanation below is not the leading mechanism. The
> clf leg is not impeached by this backtest. What IS true: +0.0687 is a
> recent-regime number whose published CI used block length = label horizon
> (60 = 60), the geometry this program has retracted as a defect. Erratum §3.

model#76 certified `z(xgb)+z(clf)` vs solo-xgb at **+0.0687/60d, CI90
[+0.0156, +0.1269]**, on two disjoint seed draws.

This harness measures the same arm pair at **+0.02843, CI90 lower
−0.00723 (NW) / −0.00580 (bootstrap) — NOT DISTINGUISHABLE from zero.**

Same **sign**, ~41% of the magnitude, and the intervals overlap on
[+0.0156, +0.0616] — so the two are not in contradiction. But it did
**not** land near +0.0687 and it did **not** clear the bar, and per the
task's own instruction that is stated plainly rather than dressed up as a
passed positive control.

This is a **directional** cross-check, not a numeric identity check, and it
was labelled as such in the runner **before** the run: model#76's estimand
is the 10-seed-averaged, placebo-differenced "clean" **top-10** spread over
**5 purged folds** on its own corpus; this runner's is the DGTW-adjusted
**top-decile** spread on an **expanding quarterly ladder** over
2017-01-03..2023-09-29 with a single pinned seed. Two different
instruments; a gap between them impeaches neither on its own. What it does
mean is concrete: **the +0.0687 certification does not reproduce at that
magnitude on the served corpus/estimand, and any deployment case that
leans on "+0.0687" as if it were a property of the served construction is
leaning on a number this backtest could not recover.**

---

## 5. ON-state sub-read (reported, never decisive)

The vol-window lane is live, so the ON slice (SPY 20td realized vol >
0.135 — the fixed definition frozen in orch#1001 and CONFIRMED in
orch#1003) is reported for `B − A`:

| slice | weekly dates | blocks | block mean | NW t | boot [q05, q95] |
|---|---|---|---|---|---|
| ON | 165 | 19 | **+0.06253** | +1.559 | [−0.0051, +0.1305] |
| OFF | 171 | 23 | **+0.09592** | — | — |
| all (decisive) | 340 | 28 | +0.05863 | +2.122 | [+0.0106, +0.1060] |

ON-state ρ̂₁ +0.362, ESS 8.91. **The effect is not concentrated in the ON
state** — the OFF-state block mean is larger, and the ON slice on its own
would be NOT DISTINGUISHABLE. Nothing here supports gating this candidate
on the vol window, and nothing here contradicts the vol-switch
certification either (that certification is about the panel's tail skill in
ON states, a different estimand from this arm-vs-arm difference).

---

## 6. What was measured, exactly

- **Corpus** 2017-01-03..2023-09-29, 1,697 trading days, weekly (every 5th
  trading day) = 340 cross-sections, 28 complete non-overlapping
  60-trading-day blocks.
- **Arms** per-date cross-sectional **unweighted z-sum**, ddof=0,
  NaN-propagating — the served contract
  (`blend_scorer.BlendPanelScorer.score`; per-component weights are
  deliberately absent, weighting is the MoE stage's own change).
  A_prod is verified against the **pinned** production config
  (`renquant-strategy-104/configs/strategy_config.json`,
  `panel_scoring.kind == "blend"`, components 0/1 and their fingerprints
  asserted by the runner). The runtime-pinned copy under
  `RenQuant/.subrepo_runtime/` was compared: its `panel_scoring` block —
  `kind` and both components — is **identical**; the two configs differ
  only on QP cash-drag knobs and comment text
  `[VERIFIED — direct diff of the two config files]`.
- **Pairing** all four arms score **one common per-date universe** (every
  leg finite, label finite, all three DGTW characteristics finite), so the
  same names and the same DGTW-adjusted labels are used and **only the
  ranking varies**. Arm-universe identity is asserted per date (G12).
- **Legs, all refit/recomputed strictly PIT**: 30 quarterly expanding
  refits, cutoffs 2016-Q2..2023-Q3, embargo `C + 60td ≤ d` asserted per
  date in both directions (admissible *and* newest). xgb = the served
  artifact's recipe verbatim (fp `sha256:f8fb2259b2bf1537`,
  rank:pairwise, 172 features, best_iter 100). clf = the shadow artifact's
  recipe verbatim (fp `sha256:1d8f167f…`, binary:logistic, seed 42, 100
  rounds, label = per-date `rank(pct=True) ≥ 0.9` of `fwd_60d_excess`,
  read from the artifact's own `classifier_label_spec`; realized clf
  positive rate 0.102 at every cutoff). Both legs share one normalization
  per cutoff — their `feature_cols` and `feature_norm_kind` are asserted
  **equal**.
- **Estimand** DGTW-adjusted top-decile spread at h=60 (STD60 × ROC60 ×
  BETA60 terciles, 27 cells, self-excluded cell-mean benchmark, ≥15/cell
  else flagged-unadjusted; 26.7% of rows flagged on average), label =
  the panel's own `fwd_60d_excess` in SD units.

---

## 7. Caveats — the ones that would change a decision

1. **SURVIVORSHIP.** 292-name survivor panel, today's OHLCV store. Every
   arm's **level** is inflated. This is why the paired contrast is the
   primary statistic — but survivorship can also distort a *contrast*
   whenever two arms load differently on the survivors, and a momentum leg
   is exactly the kind of leg that does. Not corrected; a PIT-universe
   rerun is the fix, and this backtest does not substitute for it.
2. **This is a BACKTEST standing in for forward accumulation** (operator
   policy). The corpus ends **2023-09-29** — it says nothing about 2024-2026,
   and the served blend went live only in August 2026.
3. **The mechanism is dilution, not addition** (§3). A deployment argued
   as "add the clf leg because it adds alpha" is not what these numbers
   show. If the goal is the +0.060 level gain, `C_2leg` (drop momentum,
   keep clf) scores +0.15420 vs B's +0.14928 — nominally the best arm, and
   simpler. **That comparison is a diagnostic read of this backtest, not a
   preregistered test of a "drop the momentum leg" hypothesis**; treating
   it as a deployment recommendation would be selecting an arm after
   seeing the results.
4. **The momentum leg has never had a performance readout.** GOAL-8 S1
   (orch#777, the prereg that put it in the served blend) is explicit: S1
   is an OPERATIONAL rung measuring serving reliability only — "No
   performance readout happens at S1; the S2 comparison has its own
   prereg, frozen before unblinding." So the −0.031 here is the **first**
   performance number on that leg, it arrives from a backtest rather than
   from S2's frozen comparison, and it is **not significant**. It should be
   treated as a flag that S2 matters, not as a result that pre-empts it.
5. **Serving freshness.** Production publishes the momentum artifact
   weekly and serves that cross-section until the next publish; this
   runner recomputes it at each weekly grid date, so the leg here is up to
   ~7 calendar days **fresher** than served. That flatters A_prod (and B),
   i.e. it works *against* the reported `B − A` only through what the two
   share. No lookahead is introduced — the 21-business-day input embargo
   holds either way.
6. **Sentiment gate.** Both legs are trained on the production-gated frame
   for parity; the deployed clf shadow artifact carries no such stamp. A
   declared deviation from that artifact's own preprocessing.
7. **Sector map.** The momentum leg's sector-momentum feature reads the
   **current** umbrella sector map for historical dates — a point-in-time
   impurity in 1 of its 5 equal-weight features. Declared, not corrected.
8. **Not a prereg.** The estimand, corpus, arms, statistic and bar were
   frozen in the runner's docstring before the run, the bar was inherited
   rather than chosen, and no threshold or alternative statistic was
   searched. But this had no external freeze-then-review gate, so it
   carries less evidential weight than orch#1003 did. One guard fix
   happened between runs — see §8.

---

## 8. Run honesty

The first execution **aborted on the runner's own G10 guard** at scoring
date 2018-01-23: I had written the momentum PIT assertion in the wrong
direction (`nominal window bound ≤ measured cutoff`). The measured cutoff
lands on or *before* the nominal bound whenever that bound is a market
holiday — here nominal 2017-12-25 (Christmas) → measured 2017-12-22. The
guard was corrected to assert the chain the artifact's contract actually
defines, `measured ≤ nominal < scoring date`, and the run repeated.

**No output file was written by the aborted run** (the guard fires inside
the scoring loop, all writes happen after it) and **no statistic was
computed or seen** before the fix. The fix is a guard-direction correction
in this runner's own new code, not a change to any frozen quantity, arm,
statistic or bar. Every number in this memo comes from the single completed
run.

---

## 9. What this does and does not authorize

**Does not** authorize a production change. The served blend is untouched.

What it supports, at most: putting `B_3leg` — and, given §3/§7.3, the
question of whether the **momentum leg is earning its place at all** — into
the normal design/shadow path, with the S2 momentum comparison (GOAL-8's
own next rung) as the thing that actually answers it on live data. The two
numbers a reader should carry away are **+0.0586 (B−A, clears the inherited
bar)** and **+0.0284 (the clf leg's own contribution, does not)**.
