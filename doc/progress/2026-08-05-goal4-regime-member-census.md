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

**Member 2 — momentum residual v0 (ledger-served): ZERO per-regime evidence.**
Its artifact carries no `wf_gate_metadata` at all.

### Correction (codex on orch#807): what the PROD blend actually is

The first version of this census froze the member list as panel + clf +
momentum and called it "the live blend". **That was wrong.** The pinned PROD
config declares **two** components — panel primary and slow momentum residual.
The clf top-decile leg belongs to the SHADOW profiles (the RC/RCS lanes), not to
production `[VERIFIED — pinned `strategy_config.json`, 2026-08-05]`.

Freezing a member list in code is the same error one level up from the one this
census exists to find: a claim about a configuration that has moved. The member
list is now **derived from the pinned config** at run time, `--config` selects a
shadow profile, an unrecognised component becomes a labelled ROW rather than a
silent drop, and a config with no components REFUSES instead of returning an
empty census. Run against the RCS shadow profile, the clf leg appears and is
also unmeasured.

## THE STATEMENT

The PROD blend is **one member measured on the decisive axis and one unmeasured**,
and the measured one is negatively informative in the regime that carries 88% of
the book's buys. (The shadow blends add a clf leg that is likewise unmeasured.)

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

1. Stamp per-regime evidence for the momentum member (PROD) and the clf member
   (shadow) — until then half the PROD ensemble, and two thirds of the shadow
   ensembles, are unmeasured on the axis that decides.
2. Explain the BULL_CALM buy concentration (orch#805 item 2).
3. Only then: any ensemble weighting proposal, preregistered, per-arm placebo.

Suite: 14 tests. Two are bound to reality: one fails if the pinned PROD blend's
MEMBERSHIP changes (codex's second finding — the earlier test only re-ran the
census over its own hardcoded rows, so membership drift could not fail it), and
one fails if BULL_CALM ever stops being negative in every vintage or if a PROD
member gains evidence. Neither can go stale quietly.
