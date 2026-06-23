# XGB WF-gate result — positive aggregate IC + overall-placebo-clean; failed regime sanity (NOT promoted)

Result of gating the fresh XGB (retrained 2026-06-21 on latest data, `oos_mean_ic
+0.053`) through the production WF gate, per the operator's XGB-to-prod P0.
**Verdict: FAIL → NOT promoted (never bypass).** This record states only what the
run supports; it does not declare the remaining blocker uniquely identified (see
the bounded diagnosis in #167).

## Verdict (production WF gate, 60d, fresh XGB)

| check | result |
|---|---|
| WF config parity | PASS |
| **WF 3-cut trading sim** | **PASS** — Sharpe +0.94 / +0.18 / +0.97; SPY-benchmark met; beat SPY 1/3 |
| **§5.2 real IC (aggregate)** | **+0.0543 (POSITIVE)** |
| shuffled IC | −0.0004 (≈0, clean) |
| **§5.2 overall time-shift placebo** | **+0.0343 < threshold +0.0379 → PASS** (aligned_real_ic +0.0759, threshold NOT floored) |
| **§5.2 regime-sanity IC** | **FAIL — BULL_CALM, CHOPPY** |
| trade monotonicity | FAIL — BULL_CALM |
| **VERDICT** | **FAIL** (regime-sanity + monotonicity) |

`[VERIFIED — /tmp/xgb_gate4.log, ephemeral; with the path fix below]`

## What this does and does not establish
- **Does:** XGB has positive *aggregate* cross-sectional IC (+0.054) and clears the
  *overall* time-shift placebo + WF Sharpe floor + beats SPY 1/3 — the first model
  this session to clear the overall placebo (PatchTST 60d/20d/pruned all sat ~−0.02
  and failed it). Consistent with the earlier GBDT-vs-PatchTST diagnostic: the
  features contain extractable signal that XGB captures and PatchTST does not.
- **Does NOT:** establish a robust per-regime edge, or that XGB is one diagnostic
  away from a pass. The gate FAILs on regime-sanity (BULL_CALM, CHOPPY) +
  BULL_CALM monotonicity, and the follow-up diagnostic (#167) finds the dominant,
  reliable regime (BULL_CALM, 425 dates) is genuinely weak while the aggregate
  +0.054 is BEAR-inflated. So the regime failure is a substantive blocker, not a
  formality, and is **not** characterised as "the only thing between XGB and a pass."

## What was NOT done (discipline)
- **NOT promoted.** Gate verdict = FAIL; operator's condition was "if it passes" — it did not. Never bypass the gate.
- The XGB-to-prod config swap was applied then **reverted to git-known-good** (prod=hf_patchtst, shadow=xgb); the live config is clean, no lasting change.

## Infra bug surfaced (separate, important)
The GBDT WF-corpus manifest (`walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json`) stores
**relative** artifact uris (`artifacts/walkforward_gbdt_prod_recipe_v2/<date>/panel-ltr.json`); the
gate resolves them against the manifest's own dir (`artifacts/sim/`) → doubled path
(`artifacts/sim/artifacts/...`) → corpus not found → 3/3 WF cuts fail. **This is the same failure
that has broken `weekly_wf_promote` since 2026-05-24** (R4 #383/#384 did not fully fix it). Worked
around here with an absolute-uri manifest copy; a proper fix (absolute uris, or resolve against the
strategy dir) belongs in its own PR and would unblock the scheduled promote chain.

## Next
- The regime failure's interpretation is settled (bounded) in #167: gate FAIL is correct, no gate change.
- Any *promotion-grade* re-run should use a corrected manifest, not the workaround.
