# MoE Stage −1 preliminary diagnostics — switching looks dead on the 33-date overlap, a 75/25 blend hypothesis, one prereg defect

Design under test: `doc/design/2026-08-07-moe-revision-2-power-and-membership.md`
(revision 3, merged orch#910). Every threshold below was frozen there BEFORE any
of these runs: gate `sd(paired ΔIC) < 0.0929`, plausible-effect ceiling
`ΔIC = 0.05`, history = the label-bearing dates of `ticker_forward_returns`.

## Scope — preliminary diagnostics, NOT the preregistered gate run

(Relabelled after codex review r1 of this PR; the first draft called these
"verdicts" and one of them a "PASS", which overstated both.)

The frozen gate is defined **on the 541-date point-in-time history** (design
§4.4: *"measured on the frozen 541-date history, per (sector, challenger)
pair"*). This record does not contain that measurement: the panel arm exists
for only **33 served dates** (2026-05-04..07-10) `[VERIFIED — 33 non-null
panel_ic rows in the committed CSV]`, so every paired quantity below lives on
the 33-date overlap, and the remaining 350 replay rows have no panel arm to
pair against. The preregistered kill/pass rule therefore **cannot execute yet
— for any arm, including the blend**. Everything below is a preliminary
diagnostic: the frozen inequality applied to the only overlap that exists,
useful for prioritisation, not a Stage −1 verdict. **orch#905 (the
served-matrix emitter) blocks the first valid gate result for every arm.**
Any 541-date MDE quoted below is a projection, never a realised pass.

SD convention: every `sd` in this record is the **population SD (ddof=0)** —
the generating script's numpy default. Where the committed CSV allows
recomputation, the sample-SD (ddof=1) value is shown alongside; no diagnostic
outcome changes under either convention `[VERIFIED — recomputed from the
committed CSV this session]`. The §4.4 amendment in this PR freezes
**ddof=1** for all future runs, including the 541-date gate run.

Reproduction anchor: `data/2026-08-08-stage-minus1-ic-series.csv` — the per-date
IC series for all three arms (383 rows). Raw per-name scores stay out of the
repo; the replay script (session scratchpad `stage_minus1_momentum_replay.py`)
rebuilds them from production components in ~10 min.

**What the committed CSV can and cannot reproduce.** It carries per-date
whole-book `panel_ic / slow_ic / fast_ic` (+ name counts) only. Diagnostic 1
(whole-book paired stats, correlations, full-history means) recomputes
directly from it. The per-sector tables, the blend rows, and the transfer
regression were derived from **per-name** scores and per-date top-3 realised
returns that lived only in the session scratchpad — neither those series nor
the derivation script are committed, so those numbers are **not independently
reproducible from this PR** and are graded accordingly below
(hypothesis / data point, not conclusion). The 541-date rerun under orch#905
must commit its derivation artifacts.

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

## Diagnostic 1 — whole-book switching fails the gate bound on the overlap

Paired against the panel on the 33-date overlap
`[VERIFIED — recomputed from the committed CSV this session]`:

| challenger | full-history mean IC (n) | mean Δ vs panel | sd(Δ) ddof=0 / ddof=1 | vs gate bound 0.0929 (33d diagnostic) |
|---|---|---|---|---|
| slow momentum 252/21 | +0.0101 (364d) | +0.0507 | **0.1725 / 0.1752** | **over, ~1.9×** |
| fast momentum 63/5 | −0.0205 (324d) | −0.0740 | **0.1484 / 0.1507** | **over, ~1.6×** |

Pairing was the line's only hope (§4.4 showed the unpaired comparison dead at
any available history), and it cancels less than half the variance:
`corr(panel, slow) = +0.570`, `corr(panel, fast) = +0.446`, while momentum's own
`sd(IC_t)` (0.217 / 0.249) is roughly **double** the panel's 0.1233.

Recorded, not acted on: slow's `mean Δ +0.0507` is positive with `t ≈ 0.38` —
undetectable at this depth, and saying more than that is the noise-into-prod
path the gate exists to block. A 541-date reversal would require the full
history's pairing to roughly halve the overlap `sd(Δ)`; unlikely, but the
frozen verdict belongs to the 541-date run, not this diagnostic.

## Diagnostic 2 — per-sector switching fails the bound by 3–5× on the overlap

First run of the per-sector gate produced **zero paired rows**: the momentum
reader's `sector_of()` is a coarse vendor taxonomy ("Technology") while the
panel arm sliced by the 15-label `strategy_config` `sector_map`. 同名≠同层.
Fixed by threading the config map through BOTH arms; rerun `[VERIFIED — prior
work, 2026-08-08 session replay; per-name inputs not committed, so this table
is not reproducible from the PR artifacts — data points, not conclusions]`:

| sector | clock | paired dates | mean Δ | sd(Δ) | vs gate bound 0.0929 |
|---|---|---|---|---|---|
| consumer | slow | 22 | +0.2308 | 0.5166 | over |
| industrial | slow | 21 | +0.3442 | 0.3799 | over |
| finance | slow | 22 | −0.1863 | 0.3907 | over |
| consumer | fast | 22 | −0.0285 | 0.3187 | over |
| industrial | fast | 21 | +0.1061 | 0.3573 | over |
| finance | fast | 22 | −0.2542 | 0.3430 | over |

An 8–26-name sector Spearman is so noisy that the sector axis is **less**
measurable than the whole book, not more. The "chips→fast momentum" class of
hypothesis is not refuted here — it is **unmeasurable on this book's data**,
which for routing purposes is the same practical read at this depth. No other
sector reached the 8-name floor on ≥15 paired dates at all.

## Diagnostic 3 — a hypothesis is generated: the 75/25 panel/slow rank blend

Rank-blend `(1−w)·rank(panel) + w·rank(challenger)` on common names, paired
against the panel, same 33 dates `[VERIFIED — prior work, 2026-08-08 session
replay; the per-date blended series is not committed, so this table is not
reproducible from the PR artifacts]`:

| blend | sd(Δ) ddof=0 | vs gate bound 0.0929 | mean Δ | t @33d |
|---|---|---|---|---|
| panel + 25% slow | 0.0521 | under | +0.0204 | +0.50 |
| panel + 25% fast | 0.0366 | under | −0.0208 | −0.73 |
| panel + 50% slow | 0.1206 | over | — | — |

(ddof=1 scales the 33-date values by √(33/32) ≈ 1.015 `[DERIVED — ddof
ratio at n=33]`; nothing crosses the bound either way.)

The blend arm is 75% panel, so the paired difference is small-variance — this
is where pairing works mechanically. But two things stop this from being a
PASS, and the first draft of this record got both wrong:

1. **It is not the preregistered measurement** (see Scope): 33 overlap
   dates, not the frozen 541-date history. The projected 541-date
   MDE ≈ 0.028 `[DERIVED — 2.8·0.0521/√27.05]` is a projection, not a
   realised pass.
2. **It is not a frozen candidate.** The design's C1 is the **equal-weight**
   rank blend (§7); a 25% slow weight was never preregistered, nor was the
   evaluated weight set {25%, 50%} × {slow, fast}, nor a winner rule.
   Picking 25/slow after seeing those results is exploratory tuning —
   calling it "the first PASS of the line" (as the first draft did) converts
   exploration into confirmation, exactly the failure this design's review
   history names.

**Status of the 75/25 panel/slow blend: a hypothesis generated on the
33-date overlap, nothing more.** Before any production-facing Stage 1 claim
it needs (a) a design amendment preregistering the allowed blend weights and
the winner rule, frozen before the data exists to pick a winner, and (b) an
out-of-sample evaluation of that frozen plan on the 541-date served matrix
(orch#905). The observation that the fast clock *hurts* in a blend (negative
mean Δ) is likewise hypothesis-grade; the fast clock keeps its patrol/ntfy
role on the design's grounds, not this record's.

## The ΔIC→bps transfer (§4.3), and a prereg defect found by running it

`top_n = 3` (`rotation.panel_buy_top_n`), `round_trip = 10 bps`
(2 × `rotation.joint_actions.slippage_pct = 0.0005`)
`[VERIFIED — pinned strategy_config]`. Regressing mean top-3 `fwd_20d` on
`IC_t` over the 33 paired dates `[VERIFIED — prior work, 2026-08-08 session
replay; the per-date top-3 realised-return series is not committed, so this
regression is not reproducible from the PR artifacts — a data point, not a
conclusion]`:

```
β̂ = +3308 bps of top-3 return per 1.0 IC
t(iid) = +3.17          t(n_eff-adjusted) = +0.71
break-even ΔIC = 0.0030
blend hypothesis's mean Δ +0.0204 → implied +67 bps vs 10 bps cost, IF real
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

Every open question now funnels into **one blocker: the panel arm is 33
served dates.** orch#905 (the served-matrix emitter) blocks the **first valid
Stage −1 gate result for every arm — whole-book, per-sector, and the blend
hypothesis alike** — and the economics gate (transfer β̂ at usable power)
simultaneously. It stopped being "blocks stages 1–4" and became "blocks every
verdict this line can produce." Single highest-leverage item in the MoE line.

Projections, not passes `[DERIVED — MDE = 2.8·sd/√27.05 at the measured
overlap sd; t scaling by √(541/33)]`: at 541 paired dates the blend
hypothesis's MDE would be ≈ 0.028 (under the 0.05 ceiling) and the transfer's
adjusted t ≈ 2.9 — **if** the overlap `sd(Δ)` and β̂ hold at full depth,
which is precisely what the real run must measure.

Diagnostic-dead on the overlap (a reversal would need the overlap `sd(Δ)`
overstated by ~2–5×, but the frozen verdict belongs to the 541-date run):
whole-book switching, per-sector switching, and the fast clock inside a
blend. Design-dead independently of this record (orch#910 arithmetic): the
skill-gate MoE, the sector×regime flat grid, additive-δ experts.
