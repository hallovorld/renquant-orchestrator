# GOAL-7: the dividend fix IS deployed and correct 144/144 — and it cannot prove it

STATUS:   delivered (blocker resolved by positive verification; one latent hazard found and
          instrumented, not fixed here).
WHAT:     ships `ops/renquant104/momentum_dividend_coverage_probe.py` + 12 tests, which
          re-derives per served name whether the dividend input was read or substituted; verifies
          model#110 (the −66.7bp dividend-adjustment fix) is merged (2f5fd237, 2026-07-30) and
          deployed (pinned in the umbrella model pin `96fe2d3d`, actually executed by the weekly
          job), and finds all 144 served names correct — 113 HAS_DIVIDENDS, 31 ZERO_BY_ABSENCE,
          all 31 cross-checked as genuine non-payers.
WHY/DIR:  GOAL-7 (standalone momentum → shadow) — resolves the anchor's stale blocker (model#110
          listed open); the real remaining hazard is structural: a missing dividend column is
          indistinguishable from a genuine non-payer (both produce a zero series with an identical
          `content_sha256`), so a future payer losing its column would silently corrupt momentum
          with no artifact-level signal.
EVIDENCE: `git merge-base --is-ancestor` confirms model#110 is an ancestor of the deployed pin; the
          pinned `momentum_train_run.py:111` computes `total_return_close(raw["close"],
          raw["dividend"])`; probe run over the served artifact's 144 names finds 0
          `ZERO_BY_DATA`/`SOURCE_MISSING`, and all 31 `ZERO_BY_ABSENCE` names cross-checked against
          every other parquet source in the tree pay no dividend anywhere. `[VERIFIED — this
          session, git ancestry check + probe run over all 144 served names this session]`
NEXT:     model-side fix (renquant-model, repo boundary) — record per-name dividend provenance in
          the artifact and fail closed for a known-payer whose column goes missing; update the
          GOAL-7 anchor to reflect model#110 merged/blocker resolved. Arm B accrual is unchanged
          (0/30 matured BULL_CALM dates, 2027 horizon at weekly cadence) — this finding does not
          move that clock.

## Bottom line

The GOAL-7 anchor still lists **model#110 as open**, with "the −66.7 bp dividend
adjustment must collapse to ~0" as the blocker. Both are stale:

- **model#110 is MERGED and APPROVED** (merge sha `2f5fd237`, 2026-07-30) `[VERIFIED]`
- the umbrella model pin `96fe2d3d` (2026-08-04) **contains** it —
  `git merge-base --is-ancestor` returns true `[VERIFIED]`
- the weekly job runs `$MODEL_RUNTIME/tools/momentum_train_run.py` where
  `MODEL_RUNTIME=.subrepo_runtime/repos/renquant-model`, and **that pinned file
  computes `total_return_close(raw["close"], raw["dividend"])`** at line 111 `[VERIFIED]`

So this is a *merged AND deployed* verification, not the usual gap. The served
2026-08-02 artifact is dividend-adjusted.

**Coverage measured over the served artifact's own 144 names** `[VERIFIED — this session]`:

| | n |
|---|---:|
| `HAS_DIVIDENDS` (column present, non-zero) | **113** |
| `ZERO_BY_ABSENCE` (no column → zero substituted) | **31** |
| `ZERO_BY_DATA` (column present, sums to zero) | 0 |
| `SOURCE_MISSING` | 0 |

All 31 are genuine non-payers — ADBE AFRM AMD AMZN ANET APP CMG COHR COIN CRWD
DDOG FTNT GLD LITE MDB NET NFLX NOW ON PANW PLTR RBLX SMCI SNOW SOFI SPOT TEAM
TSLA WDAY ZM ZS. Cross-checked against every other parquet source in the tree:
**none of the 31 pays a dividend anywhere**. The numbers are right.

## The hazard, stated precisely

The served trainer reaches the dividend series like this:

```python
raw["dividend"] if "dividend" in raw.columns
else pd.Series(0.0, index=raw.index)
```

**A missing column is indistinguishable from a stock that pays nothing.** Both
produce a zero series; the artifact records neither. Today that substitution is
correct 31/31. The failure it cannot survive is a *payer* losing its column —
a vendor schema change, a partial rebuild, one interrupted backfill. That name's
momentum silently becomes a price return, **the artifact looks identical, and its
`content_sha256` still verifies.**

This is the standing lesson twice over: an `else` branch that returns a benign
value for a case nobody enumerated, and a digest that establishes identity while
saying nothing about validity.

### What I did NOT claim

An earlier draft of the probe rendered these 31 as *"got a PRICE return, not a
total return"*. That is **false**: for a genuine non-payer a price return **is**
the total return, so the substituted zero is numerically correct. I corrected the
wording before publishing — the defect is **indistinguishability, not a wrong
number**, and overstating it would have turned a real finding into a false one.

The probe also states, on a clean result, that it checks *column presence and
sign only — not dividend values*. A zero here is not a statement that the
dividends are right.

## Delivered

`ops/renquant104/momentum_dividend_coverage_probe.py` + 12 tests. Re-derives per
served name whether the dividend input was **read** or **substituted**, and
refuses to call a name clean merely because its dividend total is zero. Exits 1
when any name was substituted; refuses (exit 2) rather than reporting full
coverage when `formation_return` is absent or empty.

Every fixture is synthetic. A test bound to the live tree would pass for the
wrong reason today — all 31 are non-payers — and go red the day someone
backfills.

## Arm B accrual, unchanged and still the real GOAL-7 clock

```
ledger rows .................. 1
matured BULL_CALM dates ...... 0 of 30 needed
newest cutoff ................ 2026-08-02 (3d ago, 0 missed 7d firings)
STATE: GENESIS_ONLY_NO_CADENCE_YET
projection: REFUSED — 1 cutoff; a rate cannot be OBSERVED from this
```

The probe correctly refuses to project from a single cutoff. At a weekly cadence
30 matured BULL_CALM dates remains a **2027** horizon; nothing in this round
moves that, and no amount of instrumentation will.

## Next

1. **Model-side fix** (renquant-model, not this repo — boundary): record the
   per-name dividend provenance *in the artifact* so the distinction survives
   without re-deriving it from parquets, and fail closed for a name on the
   known-payer list whose column is absent.
2. Update the GOAL-7 anchor: model#110 is merged; the blocker is resolved.
