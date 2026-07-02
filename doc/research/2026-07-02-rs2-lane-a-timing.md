# RS-2: lane-A timing — enable A-1/A-3 now, DEFER A-2 behind D1-or-M3 (delegated decision)

STATUS: research recommendation (delegated per the 2026-07-02 grant; operator NOTIFIED).
DATE: 2026-07-02
QUESTION (#231 §6): run the cash-drag de-throttle experiments before or after D1's first
WF-gate verdict, given the model has no standing validation?

## The decisive measurement (reproducible one-liner, runs.alpaca.db)

Thin-margin share of the floor-clearing pool (mu ∈ [0.030, 0.0375) = within 25% of the
floor — the OXY class):

| run | names ≥ floor | thin-margin | share | avg admitted mu |
|---|---|---|---|---|
| 07-01 | 17 | 15 | **88%** | 0.0351 |
| 06-30 | 20 | 16 | **80%** | 0.0353 |
| 06-26 | 22 | 17 | 77% | 0.0360 |
| 06-25 / 06-23 / 06-22 | 6 / 8 / 9 | 6 / 4 / 6 | 100 / 50 / 67% | 0.031–0.041 |

```sql
select run_id, sum(mu>=0.03), sum(mu>=0.03 and mu<0.0375), round(avg(case when mu>=0.03 then mu end),4)
from candidate_scores where role='candidate' and run_id in (<full runs>) group by run_id;
```

**The admitted pool is ~80–88% thin-margin post-retrain.** The conviction floor is doing
almost no separation: nearly everything that clears it clears it barely, with no
uncertainty penalty (M3 not yet built) and no model verdict (D1 not yet rendered).

## Recommendation — split lane A by what each knob actually admits

| Knob | What it changes | Verdict | Basis |
|---|---|---|---|
| **A-1 `qp_cash_drag_lambda` 0 → 0.05** | allocation among names the QP ALREADY admitted — no new-name admission | **ENABLE NOW** (after the 10-session shadow sweep) | exposure delta bounded by existing per-name/sector/correlation caps; solver default is 0.05 — we are un-disabling a shipped control |
| **A-3 one-share floor for high-price names** | removes the selection-by-share-price ARTIFACT (BLK vs OXY) — swaps which admitted name gets the slot, does not widen the pool | **ENABLE NOW** | artifact removal, measured in the OXY forensics; net effect is ordering-fidelity (buy-side TC), the exact deficit S-TC measured at 0.09 |
| **A-2 `panel_buy_top_n` 3 → 5–6** | admits MORE names per session from a pool measured **~85% thin-margin** | **DEFER** until EITHER D1 renders a verdict OR M3's uncertainty haircut (`mu − k·SE > floor`) lands — whichever first | at top_n=6 the worst case adds ~3 thin-margin entries/day ≈ +9pp/day of unvalidated-model exposure; a week of that rotates the entire ~40% deployable sleeve into OXY-class picks with no guard |

**Deployment AC unaffected**: POC-B put lane A's shrinkage-realistic ceiling at ~40–43%
regardless; lane B (the sleeve) carries the ≥60% deployment AC in the interim, which is
exactly the #231 S6/S7 division of labor.

## Why this is the right risk order (theory)

TC repair (A-1/A-3) raises IR at **zero incremental model risk** — it changes HOW admitted
conviction is expressed, not WHICH names get money. Pool widening (A-2) raises exposure to
the unvalidated μ-ordering itself; with the measured pool ~85% thin-margin, its expected
benefit is second-order (the 4th–6th picks are statistically indistinguishable from the
3rd) while its risk is first-order. Enable the free lever, defer the risky one behind the
guard that makes it safe (M3) or the evidence that makes it earned (D1).
