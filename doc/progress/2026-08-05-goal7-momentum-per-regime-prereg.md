# 2026-08-05 — GOAL-7: the deployed momentum member gets a per-regime registration

## STATUS

Preregistration FROZEN. Nothing has been run. This is the prerequisite the
GOAL-4 census named as step 1, and it is also GOAL-7's own evaluation gap.

## What the census exposed about GOAL-7

The slow momentum residual is a PROD blend member and has **zero per-regime
evidence** `[VERIFIED — orch#807/#809]`. Its acceptance evidence
(`renquant-model` `2026-08-01-goal7-residual-momentum-prereg.md`, E1) is a
**pooled** mean per-date IC — the same quantity tonight's measurement showed can
be dominated by a minority regime on this book `[VERIFIED — orch#805]`.

That does not retro-invalidate the momentum study: E1 was preregistered and run
as specified, and a post-hoc re-slice of a completed confirmatory study is
exploratory by construction. It does say a pooled acceptance number is not
sufficient for a member of a blend whose trading is concentrated in one regime.

## The honest constraint this registration had to encode

The served artifact has **one** ledger row, `cutoff_date = 2026-08-02`
`[VERIFIED — 1 row, n_scored 144]`. Its `fwd_60d_excess` labels do not mature
until ~2026-10-27. So the served member **cannot** be evaluated on matured labels
now, and the registration says so rather than quietly substituting a
reconstruction for the real thing:

- **Arm A (reconstruction)** — recompute from the historical panel with the
  served params. Exploratory. Can motivate, cannot certify.
- **Arm B (served)** — the accumulating ledger, ≥20 matured dates, not runnable
  before ~2026-10-27. **Only Arm B certifies.**

A claim that does not name its arm is inadmissible.

## Frozen choices worth naming

- **Primary is `E1(BULL_CALM)`**, named before any arm runs, because 136 of 154
  buys land there. The other regimes are secondary and cannot change the
  verdict — the pre-commitment that stops a BEAR number being promoted to the
  headline afterwards, which is exactly what the pooled figure already does.
- **Per-regime placebos**, both a within-date shuffle and the gate's own 2×
  horizon shift, reported per regime beside the raw.
- **A regime with <30 dates supports no conclusion in either direction.** Frozen
  because the census found BULL_VOLATILE at n_dates 11–16, where an earlier draft
  of mine described a "trend" the sample could not support.
- **A what-would-change-my-mind clause**: if E1(R) is stable under an alternative
  regime definition, the "pooled is a regime mix" argument itself is weaker than
  tonight's evidence suggests, and the premise — not just the result — must be
  reported as damaged.

## Anchor correction

The loop's GOAL-7 anchor says "model#110 已开". `model#110` is **MERGED**
`[VERIFIED — 2026-08-05]`. The open GOAL-7 gap is not the dividend adjustment; it
is that the deployed member has no regime-conditioned evidence.

## NEXT

Arm A can be run under this registration as soon as it is merged. Arm B is
calendar-blocked to ~2026-10-27 and that is stated, not worked around.
