# 2026-08-05 — GOAL-4 Phase-0: the ensemble question was being asked on the wrong axis

## STATUS

GOAL-4's premise re-assessment gets its first MEASURED input. Not a kill, not a
revival — a re-scope, with a reproducible census behind it.

## WHAT

`scripts/goal4_regime_member_census.py` (read-only) walks every stamped artifact,
deduplicates by profile digest, and reports each live blend member's `genuine_ic`
**per regime**, at the 2× shift the enforced placebo leg itself uses.

## WHY THIS DIRECTION

orch#805 (measured 2026-08-05): the primary panel recipe's genuine IC is +0.335
in BEAR — where the strategy places **zero** buys — and negative in BULL_CALM,
where 136 of its 154 buys land. The pooled +0.0089 that every promote/reject and
every fleet comparison has been read off is a **regime-mix artifact**: BEAR's
+0.335 over 50 dates drags a pool that is 80% BULL_CALM into positive territory.

An ensemble is a weighting over members. So GOAL-4's prior question is not "do
the 12 boosters differ" (orch#698 answered that, and correctly claimed nothing
about production from a synthetic input). It is: **does any member have positive
genuine IC in the regime the book actually trades?**

## EVIDENCE

`[VERIFIED — this session 2026-08-05, `scripts/goal4_regime_member_census.py`
against `RenQuant/backtesting/renquant_104/artifacts`]`

**Member 1 — panel primary (XGB recipe), 8 distinct vintages, 2026-07-05 → 08-04:**

| run_at | BULL_CALM | BEAR | BULL_VOLATILE | CHOPPY |
|---|---|---|---|---|
| 2026-07-05 | −0.0294 | +0.3347 | −0.0800 | −0.0254 |
| 2026-07-06 | −0.0295 | +0.3346 | −0.0800 | −0.0410 |
| 2026-07-12 | −0.0307 | +0.3415 | −0.0803 | −0.0677 |
| 2026-07-13 | −0.0313 | +0.3415 | −0.0803 | −0.0677 |
| 2026-07-18 | −0.0328 | +0.3415 | −0.0875 | −0.0677 |
| 2026-07-26 | −0.0339 | +0.3417 | −0.1203 | −0.0682 |
| 2026-08-02 | −0.0294 | +0.3388 | −0.1294 | −0.0656 |
| 2026-08-04 | −0.0300 | +0.3388 | −0.1290 | −0.0656 |

- **BULL_CALM: NEGATIVE in 8/8** (min −0.0339, max −0.0294). Stable over a month,
  not noise.
- **BEAR: POSITIVE in 8/8** (+0.3346 … +0.3417). Also stable.
- BULL_VOLATILE: negative in 8/8 and **degrading** (−0.080 → −0.129).
- All eight carry the SAME `candidate_recipe_fingerprint`
  `sha256:cfdd6cb8e950da0f`, which is exactly the known "the gate admits on
  recipe hash only" property. So this shape is a property of the RECIPE, not of
  any single training run.

**Members 2 and 3 — clf top-decile fwd60, momentum residual v0:
ZERO per-regime evidence.** Neither artifact carries `wf_gate_metadata` at all.

## THE STATEMENT

The live blend is **one member measured on the decisive axis and two unmeasured**,
and the measured one is negatively informative in the regime that carries 88% of
the book's buys.

That does not say the blend is bad. It says **GOAL-4 cannot be evaluated on the
pooled number**, and no ensemble weighting can be justified until the other two
members are measured on the same axis. A member that is negatively informative in
BULL_CALM does not stop being so by being averaged.

## SCOPE — what this does NOT claim

- NOT a verdict on the z-blend switch or on any shadow lane. The live book runs
  the pinned config; this is evidence about members, not about the book.
- NOT "trade only in BEAR". BEAR is 10% of days, the regime label is itself an
  HMM estimate, and acting on a post-hoc regime slice without preregistration is
  the exact error the ledger warns about.
- NOT an explanation of WHY buys concentrate in BULL_CALM — admission gates,
  sizing, or the signal itself. **Not measured.** That is the next question and
  it is answerable from the decision ledger plus the newly-persisted served
  matrix (renquant-pipeline#268) with no new modelling.

## NEXT

1. Stamp per-regime evidence for the clf and momentum members — until then two
   thirds of the ensemble is unmeasured on the axis that decides.
2. Explain the BULL_CALM buy concentration (orch#805 item 2).
3. Only then: any ensemble weighting proposal, preregistered, per-arm placebo.

Suite: 10 new tests, incl. one bound to the LIVE corpus that fails if BULL_CALM
ever stops being negative in every vintage, or if a fleet member gains evidence —
so this record cannot silently go stale.
