# PREREG (FROZEN 2026-08-05) — the deployed momentum member, evaluated PER REGIME

**Frozen before any arm is computed.** Amending anything under a `FROZEN`
heading after the first arm runs voids the registration; a change requires a new
registration with a new number and the old one left in place.

## 0. Why this registration exists

The slow momentum residual is a **PROD blend member** (pinned
`strategy_config.json`, component 1) and it has **zero per-regime evidence**
`[VERIFIED — orch#807/#809 census, 2026-08-05: no artifact for this member
carries `wf_gate_metadata` at all]`.

Its own acceptance evidence — `renquant-model` prereg
`2026-08-01-goal7-residual-momentum-prereg.md`, E1 — is a **pooled** mean
per-date Spearman IC. Tonight's measurement says a pooled IC on this book can be
a regime-mix artifact: the other PROD member's pooled genuine IC is positive
while the regime carrying 136 of 154 buys is negative, because a 50-date regime
with +0.335 drags the mean up `[VERIFIED — orch#805]`.

That does **not** retro-invalidate the momentum study. E1 was preregistered and
run as specified, and a post-hoc re-slice of a completed confirmatory study is
**exploratory by construction** and cannot change its verdict. What it does say
is that a pooled acceptance number is not sufficient evidence for a member of a
blend whose trading is concentrated in one regime — and that gap is what this
registration closes.

## 1. FROZEN object under test

The **served** slow momentum residual as the blend loads it: the ledger-pointer
leg at `artifacts/momentum/momentum_artifact_ledger.jsonl`, params fingerprint
`momentum-v0-fd65161a20b29314`, formation window as stamped in the artifact.
No parameter is re-fit, re-tuned or re-selected in this study. If the served
params fingerprint changes, this registration is void for the new one.

## 2. FROZEN estimand

For each regime `R` in `{BULL_CALM, BULL_VOLATILE, BEAR, CHOPPY}`:

> **E1(R)** = the mean, over evaluation dates whose production regime label is
> `R`, of the per-date Spearman rank IC between the momentum score and
> `fwd_60d_excess`.

**Primary decision estimand: `E1(BULL_CALM)`.** Named here, before any arm is
computed, because BULL_CALM is where 136 of the strategy's 154 buys land
`[VERIFIED — stamped `trade_buy_regime_counts_total`]`. The other three are
**secondary and cannot change the verdict** — this is the pre-commitment that
stops the BEAR number being promoted to the headline after the fact, which is
precisely the error the pooled figure already commits.

Regime labels come from the **production regime chain** (`build_regime_series`),
never from a label invented for this study.

## 3. FROZEN: what is measurable NOW, and what is not

The served artifact's only ledger row is `cutoff_date = 2026-08-02`
`[VERIFIED — 1 row, n_scored 144]`. `fwd_60d_excess` for that date does not
mature until ~2026-10-27. **The SERVED member therefore cannot be evaluated on
matured labels in this study, and this registration does not pretend otherwise.**

Two arms, and the distinction is frozen here so it cannot be blurred later:

- **Arm A (RECONSTRUCTION, exploratory).** Recompute the momentum score from the
  historical OHLCV panel using the served params, and measure E1(R) on matured
  labels. This is **not the served artifact** — it is what the recipe would have
  produced. It can motivate; it cannot certify.
- **Arm B (SERVED, confirmatory).** E1(R) on the accumulating ledger once
  ≥ 20 evaluation dates have matured labels. Not runnable before ~2026-10-27.
  **Only Arm B can certify.**

Any claim that does not name its arm is inadmissible.

## 4. FROZEN placebo, per arm and per regime

Each arm carries, **within each regime separately**:
- a within-date label shuffle (5 replications), and
- the same 2× horizon label shift the WF gate's enforced leg uses,

and reports `genuine_ic(R) = IC(R) − placebo_ic(R)` beside the raw. A regime's
raw IC is reported **only** with its own matched placebo. This is the discipline
the existing embargo-leakage floor note already requires: trust placebo-clean
DIFFERENCES, not absolute IC.

## 5. FROZEN: sample-size floor and what a small regime may say

A regime with **fewer than 30 evaluation dates** is reported with its `n_dates`
and is **explicitly barred from supporting any conclusion**, in either direction.
This is frozen because the census already showed BULL_VOLATILE at `n_dates`
11–16, where an earlier draft of mine described a "trend" that the sample could
not support.

## 6. FROZEN decision rule — what this changes

- If **Arm B** shows `genuine_ic(BULL_CALM) > 0` with its matched placebo clean:
  the momentum member has evidence on the axis that decides, and GOAL-4 step 1
  is satisfied for this member.
- If **Arm B** shows `genuine_ic(BULL_CALM) ≤ 0`: the PROD blend has **two**
  members and **neither** has positive evidence in the regime carrying its
  trading. That is a finding about the blend, and it goes to the operator as
  one — not as a silent re-weighting.
- Arm A alone changes **nothing**. It can only justify running Arm B or
  designing a different candidate.

## 7. FROZEN: what would change my mind

If the per-regime split turns out to be an artifact of the regime LABEL rather
than of the signal — e.g. E1(R) is stable under a reasonable alternative regime
definition, or the BULL_CALM/BEAR gap collapses when regimes are defined on a
different volatility axis — then the whole "pooled is a regime mix" line of
argument is weaker than tonight's evidence suggests, and this registration's
premise, not just its result, should be reported as damaged.

## 8. Not covered

- No parameter search, no horizon search, no universe change.
- No statement about the clf member (shadow-only) or about the primary panel
  member, both of which have their own records.
- No live behaviour change of any kind. Nothing in this document authorises a
  weighting change.
