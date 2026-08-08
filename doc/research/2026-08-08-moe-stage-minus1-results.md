# MoE Stage −1 results — switching is dead, a low-weight blend survives, and one prereg defect

Design under test: `doc/design/2026-08-07-moe-revision-2-power-and-membership.md`
(revision 3, merged orch#910). Every threshold below was frozen there BEFORE any
of these runs: gate `sd(paired ΔIC) < 0.0929`, plausible-effect ceiling
`ΔIC = 0.05`, history = the label-bearing dates of `ticker_forward_returns`.

Reproduction anchor: `data/2026-08-08-stage-minus1-ic-series.csv` — the per-date
IC series for all three arms (383 rows). Raw per-name scores stay out of the
repo; the replay script (session scratchpad `stage_minus1_momentum_replay.py`)
rebuilds them from production components in ~10 min.

## How the challenger arms were produced

Offline replay over **383 label dates** (every `as_of_date` with ≥30 non-null
`fwd_20d` rows), reusing production components end to end — nothing
reimplemented:

| component | source |
|---|---|
| TR-return derivation | `renquant-model/tools/momentum_train_run.LiveReaders` |
| point-in-time universe | same runner's `resolve_universe(asof)` (panel dataset, not today's list) |
| score assembly | `renquant_model_momentum.train.train_momentum_artifact` |
| params | frozen `v0` (252/21) and `v1_fast` (63/5) |
| labels | `ticker_forward_returns.fwd_20d`, read-only |

Point-in-time holds **by construction**: neither clock has fitted parameters —
only frozen constants — and the score at date `t` reads only the window ending
at `t − skip`. (codex round-2 P1 on orch#910 demanded this property; for these
two challengers it is structural, not procedural.)

The panel arm is the served history: 33 usable dates (2026-05-04..07-10, median
71 names/date), `mean IC +0.0223`, `sd 0.1233`
`[VERIFIED — candidate_scores(role='candidate') ⋈ fwd_20d, best run per date]`.
Why only 33: the 2024–2025 "scored" runs are `sim` runs carrying 1–13
candidates, not full-breadth scoring — the panel's historical breadth exists
only inside WF artifacts, which is exactly the orch#905 gap.

## Verdict 1 — whole-book switching: DEAD

Paired against the panel on the 33-date overlap
`[VERIFIED — replay output ⋈ panel series]`:

| challenger | full-history mean IC (n) | mean Δ vs panel | sd(Δ) | gate < 0.0929 |
|---|---|---|---|---|
| slow momentum 252/21 | +0.0101 (364d) | +0.0507 | **0.1725** | **FAIL** |
| fast momentum 63/5 | −0.0205 (324d) | −0.0740 | **0.1484** | **FAIL** |

Pairing was the line's only hope (§4.4 showed the unpaired comparison dead at
any available history), and it cancels less than half the variance:
`corr(panel, slow) = +0.570`, `corr(panel, fast) = +0.446`, while momentum's own
`sd(IC_t)` (0.217 / 0.249) is roughly **double** the panel's 0.1233.

Recorded, not acted on: slow's `mean Δ +0.0507` is positive with `t ≈ 0.38` —
undetectable at this depth, and saying more than that is the noise-into-prod
path the gate exists to block.

## Verdict 2 — per-sector switching: DEAD BY 3–5×

First run of the per-sector gate produced **zero paired rows**: the momentum
reader's `sector_of()` is a coarse vendor taxonomy ("Technology") while the
panel arm sliced by the 15-label `strategy_config` `sector_map`. 同名≠同层.
Fixed by threading the config map through BOTH arms; rerun:

| sector | clock | paired dates | mean Δ | sd(Δ) | gate |
|---|---|---|---|---|---|
| consumer | slow | 22 | +0.2308 | 0.5166 | FAIL |
| industrial | slow | 21 | +0.3442 | 0.3799 | FAIL |
| finance | slow | 22 | −0.1863 | 0.3907 | FAIL |
| consumer | fast | 22 | −0.0285 | 0.3187 | FAIL |
| industrial | fast | 21 | +0.1061 | 0.3573 | FAIL |
| finance | fast | 22 | −0.2542 | 0.3430 | FAIL |

An 8–26-name sector Spearman is so noisy that the sector axis is **less**
measurable than the whole book, not more. The "chips→fast momentum" class of
hypothesis is not refuted here — it is **unmeasurable on this book's data**,
which for routing purposes is the same verdict. No other sector reached the
8-name floor on ≥15 paired dates at all.

## Verdict 3 — the low-weight blend clears the gate (first PASS of the line)

Rank-blend `(1−w)·rank(panel) + w·rank(challenger)` on common names, paired
against the panel, same 33 dates:

| blend | sd(Δ) | gate < 0.0929 | mean Δ | t @33d |
|---|---|---|---|---|
| **panel + 25% slow** | **0.0521** | **PASS** | **+0.0204** | +0.50 |
| panel + 25% fast | 0.0366 | PASS | −0.0208 | −0.73 |
| panel + 50% slow | 0.1206 | FAIL | — | — |

The blend arm is 75% panel, so the paired difference is small-variance — this
is where pairing actually works. **The surviving hypothesis is the 75/25
panel/slow-momentum rank blend**: measurable at the frozen 541-date depth
(projected MDE ≈ 0.028 < ceiling 0.05), sign positive, significance absent at
33 paired dates. The fast clock *hurts* in a blend (negative Δ) and keeps its
patrol/ntfy role only.

## The ΔIC→bps transfer (§4.3), and a prereg defect found by running it

`top_n = 3` (`rotation.panel_buy_top_n`), `round_trip = 10 bps`
(2 × `rotation.joint_actions.slippage_pct = 0.0005`)
`[VERIFIED — pinned strategy_config]`. Regressing mean top-3 `fwd_20d` on
`IC_t` over the 33 paired dates:

```
β̂ = +3308 bps of top-3 return per 1.0 IC
t(iid) = +3.17          t(n_eff-adjusted) = +0.71
break-even ΔIC = 0.0030
C1's mean Δ +0.0204 → implied +67 bps vs 10 bps cost, IF the effect is real
```

**Prereg defect, recorded visibly instead of resolved conveniently:** §4.3
froze "β̂ significantly positive" without freezing WHICH standard error. The
iid t passes; the n_eff-adjusted t does not. Choosing after seeing both is
exactly the failure codex's round-1 review named — so the transfer gate is
treated as **NOT CLEARED** (and not as a line-kill either: the ambiguity is a
spec defect, not evidence). The amendment freezing the n_eff-adjusted
convention for all future runs is in this PR (§4.3, one paragraph, marked as an
amendment dated 2026-08-08).

## Where this leaves the line

Every open question now funnels into **one blocker: the panel arm is 33 served
dates.** At 541 paired dates, C1's MDE ≈ 0.028 and the transfer's adjusted
t ≈ 2.9 if β̂ holds. orch#905 (the served-matrix emitter) is therefore the
single highest-leverage item in the entire MoE line — it stopped being
"blocks stages 1–4" and became "blocks the only surviving hypothesis and the
economics gate simultaneously."

Dead and staying dead: whole-book switching, per-sector switching, the
skill-gate MoE, the sector×regime flat grid, additive-δ experts, and the fast
clock inside a blend.
