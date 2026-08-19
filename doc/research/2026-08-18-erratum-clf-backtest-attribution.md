# ERRATUM to the served-blend + clf paired backtest (orch#1007)

STATUS: **erratum.** It corrects the INTERPRETATION of
`doc/research/2026-08-18-served-blend-plus-clf-backtest.md`. **No number in
that memo is wrong** — I reproduced all four arm levels and all five
contrasts exactly. What is wrong is what two of them were said to mean.

DATE: 2026-08-18. TRIGGER: the double-audit required before a
capital-adjacent conclusion (LONG ledger; `double-audit-for-major-conclusions`).
The audit was an independent re-derivation, not a re-run of the runner.

---

## 1. What is withdrawn

The backtest memo says, in §1a and again in §3:

> **A_prod is the worst of the four arms — it sits BELOW solo-xgb.** On this
> corpus the momentum leg subtracts from the panel model rather than adding
> to it

and closes §3 with:

> the cleanest reading of why is that the momentum leg is not earning its
> half of the served blend

**That attribution is WITHDRAWN.** `A − D = −0.03073` is not the momentum
leg's contribution. It is not evidence that the momentum leg is harmful,
and it must not be cited as a reason to change the served blend.

**What is NOT withdrawn:** every arithmetic value, the frozen primary
verdict `B − A = +0.05863` (NW t +2.122, CI90 lower +0.01157) under the
inherited bar, and the descriptive ordering `{B, C} > D > A` — which holds
in all four available reads.

## 2. Why it collapses — two independent, sufficient reasons

### 2a. `A − D` is the dilution penalty the memo itself diagnoses, applied
### to a different pair and then left uncorrected

§3 item 3 is right that an **unweighted** z-sum cuts each leg's share when a
leg is added, and that `B − A` therefore sums "clf adds signal" with
"momentum's share shrinks". The same arithmetic governs `A − D`: going from
one leg to two halves the informative leg's weight **whether or not the
second leg carries any information at all.**

Under the null *"momentum carries ZERO information"*, an unweighted 2-leg
z-sum mechanically predicts `A − D = −0.03565` at ρ(xgb, mom) = 0
`[DERIVED — independent second derivation]`. The measured `−0.03073` is
**less negative than the zero-information prediction.** Dilution-corrected:
**+0.00424, NW t +0.139** `[DERIVED]` — and indistinguishable from zero at
every ρ(xgb, mom) ∈ [−0.2, +0.5].

So the memo applied a dilution argument to `B − A` and then read the very
same artefact as an attribution when it appeared in `A − D`.

### 2b. It collapses ~86% under the run's own shipped alternative estimand

The runner computed the winsorized ±0.50 SD column for every arm and
reported the winsorized read only for `B − A`. Read for `A − D`, from the
committed results JSON `[VERIFIED — I read these values myself from
doc/research/data/2026-08-18-served-blend-plus-clf-results.json]`:

| | A_prod | D_solo | A − D |
|---|---:|---:|---:|
| per-date mean spread | +0.08926 | +0.12171 | **−0.03245** |
| block mean | +0.08866 | +0.11939 | **−0.03073** |
| **winsorized ±0.50 SD** | **+0.01515** | **+0.01944** | **−0.00430** |

**86% of the gap lives in the untrimmed tails.** The audit's paired
computation gives `−0.00447, t −0.343` `[DERIVED]`. Either way the contrast
does not survive the run's own robustness column.

### 2c. It was never statistically established in the first place

`A − D`: NW t **−0.810** against crit 1.703; bootstrap [−0.0915, +0.0323];
9/28 blocks positive; sign test p 0.0872; Wilcoxon p 0.2545. LOBO keeps the
**sign** stable (0/28 flips) but **0/28** subsets establish `D > A`. The
memo said this ("not statistically distinguishable from zero either") and
then leaned on the point estimate anyway. That is the error the LONG ledger
calls asserting past what was measured.

## 3. A SECOND correction, in the opposite direction — §4b was too hard on
## the clf leg, for the wrong reason

§4b reports that model#76's certified `C − D = +0.0687` "does not
reproduce" at +0.02843 and attributes the gap to instrument differences.
The dominant driver is neither instrument nor defect — it is the **corpus
window** `[DERIVED — independent re-derivation, which reproduces model#76's
published CI to all digits before restricting]`:

| model#76's own instrument, on | n dates | mean | CI90 |
|---|---:|---:|---|
| its full corpus 2017-09-21..2026-04-28 | 2,161 | **+0.06873** | [+0.01557, +0.12688] |
| **restricted to this backtest's window (≤ 2023-09-29)** | 1,516 | **+0.01554** | **[−0.04481, +0.07117]** |
| the post-window remainder 2023-09-30..2026-04-28 | 645 | +0.19372 | [+0.07445, +0.26163] |

**84% of the certified effect comes from 645 of 2,161 dates, all of them
after this backtest's corpus ends.** On the matched window model#76's own
instrument would have returned INCONCLUSIVE. This harness's **+0.02843 is
therefore LARGER than the certification's own same-window number, not 41%
of it.** §4b compared a full-corpus number against a matched-window number
and read the difference as shrinkage.

Two consequences, and they point opposite ways:

- The clf leg is **not** impeached by this backtest — §4b's implication that
  it under-delivered is withdrawn.
- The certified **+0.0687 is concentrated in 2023-10 onward**, i.e. it is a
  recent-regime number, and its published CI used **block length = label
  horizon (60 = 60)** — the geometry this program has since retracted as a
  defect (`renquant-model doc/research/2026-07-30-erratum-block-length-equals-horizon.md`).
  §4b's closing sentence — that a deployment case leaning on "+0.0687" is
  leaning on a number this backtest could not recover — stands, for a
  sharper reason than it gave.

## 4. An open harness question §4a understates

§4a grades the harness control "PASSES (this is the strong one)". The
structural checks do pass exactly (340/340 refit cutoffs, 340/340
panel-usable counts, frozen geometry). But the **baseline level does not
reproduce**: `D_solo = +0.12171` here against the sibling committed
vol-switch run's unconditional `+0.13919` on the identical corpus —
**−12.56%**, per-date r = 0.829 `[VERIFIED — I read both committed results
JSONs myself: doc/research/data/2026-08-18-served-blend-plus-clf-results.json
and doc/research/data/2026-08-18-vol-switch-results.json]`.

§4a attributes this to the declared ~1.3% momentum-universe restriction.
Under the same estimand a random 1.3% restriction moves the level
**−0.29%** `[DERIVED]` — **43× short** of the observed gap. §4a does concede
that value-level identity was not verified; this erratum makes that concrete.
Until it is explained, every level this harness reports carries an
unquantified offset, and the paired contrasts are the only reads that
should be trusted (a common offset cancels in a paired difference).

## 5. What the backtest actually supports now

- **`B_3leg` beats `A_prod` by +0.05863/60d on this corpus under the
  inherited bar.** Unchanged, and it is a paired contrast, so §4's offset
  concern does not touch it.
- **Nothing here says the momentum leg is harmful.** Its own information is
  **unidentifiable** from this run: ρ(xgb, mom) per date was not persisted,
  and no weighted or orthogonalized arm was run, so information and dilution
  cannot be separated in any contrast this design produced.
- **Nothing here re-certifies the clf leg either** (`C − D` does not clear
  the bar on this window — and neither does model#76's own instrument on
  this window).
- **No production configuration change is supported by this backtest.**

## 6. What would settle it

Gaps as measured, not a plan:

1. Persist per-date ρ(xgb, mom); without it, momentum's own sign is not
   determinable in either direction.
2. Run a **weighted or orthogonalized** arm — the unweighted z-sum confounds
   information with dilution in every contrast, `A − D` included.
3. Explain the −12.56% baseline gap against the vol-switch sibling, or stop
   reporting arm LEVELS from this harness.
4. Any momentum verdict needs its own preregistration. `A − D` was a post-hoc
   diagnostic on a run frozen for `B − A`; it fails the run's own inherited
   bar in both directions.
5. The served coverage regime differs materially from the backtest's
   (144-name artifact universe, 80–89-name serving cross-section, vs ~278
   here). Top-decile-of-278 is not the production selection problem.

## 7. Process note

The backtest memo was written and merged before this audit completed. That
ordering is the error to avoid repeating: a capital-adjacent conclusion
should carry its double-audit **into** review, not after merge. The memo's
own guards are what made the correction cheap — it shipped the winsorized
column, the decomposition table and the per-arm levels that refute its
reading, rather than only the numbers that supported it.

Related: `doc/research/2026-08-18-served-blend-plus-clf-backtest.md`,
`renquant-model` model#75 (frozen bar) / model#76 (certification),
`renquant-model doc/research/2026-07-30-erratum-block-length-equals-horizon.md`.
