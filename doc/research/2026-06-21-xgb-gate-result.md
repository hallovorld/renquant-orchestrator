# XGB WF-gate result — positive IC + placebo-clean, blocked only by the BULL_CALM regime

Result of gating the fresh XGB (retrained 2026-06-21 on latest data, `oos_mean_ic +0.053`) through
the production WF gate, per the operator's XGB-to-prod P0. **Verdict: FAIL → NOT promoted (never
bypass).** But the failure is narrow and the model is the strongest of the session.

## Verdict (production WF gate, 60d, fresh XGB)

| check | result |
|---|---|
| WF config parity | PASS |
| **WF 3-cut trading sim** | **PASS** — Sharpe +0.94 / +0.18 / +0.97; SPY-benchmark met; beat SPY 1/3 |
| **§5.2 real IC** | **+0.0543 (POSITIVE)** |
| shuffled IC | −0.0004 (≈0, clean) |
| **§5.2 time-shift placebo** | **+0.0343 < threshold +0.0379 → PASS** (aligned_real_ic +0.0759, threshold NOT floored) |
| **§5.2 regime-sanity IC** | **FAIL — BULL_CALM, CHOPPY** |
| trade monotonicity | FAIL — BULL_CALM |
| **VERDICT** | **FAIL** (regime-sanity + monotonicity) |

`[VERIFIED — /tmp/xgb_gate4.log, ephemeral; with the path fix below]`

## Why this matters (the confirmed finding)
- **XGB has genuine positive cross-sectional IC (+0.054) and passes the placebo + WF-floor + beats
  SPY** — the FIRST model this session to clear placebo. PatchTST (60d/20d/pruned) all sat at
  ~−0.02 and failed placebo.
- **So the features DO contain extractable signal; XGB captures it, PatchTST does not.** The earlier
  GBDT-vs-PatchTST diagnostic is now confirmed by an honest gate run, not just self-reported IC.
- **The one remaining wall is the BULL_CALM (and CHOPPY) regime** — regime-sanity IC + monotonicity.
  This is the *same* regime wall that fails every model. It is now the ONLY thing between XGB and a
  gate pass.

## What was NOT done (discipline)
- **NOT promoted.** Gate verdict = FAIL; operator's condition was "if it passes" — it did not.
  Never bypass the gate.
- The XGB-to-prod config swap was applied then **reverted to git-known-good** (prod=hf_patchtst,
  shadow=xgb); the live config is clean, no lasting change.

## Infra bug surfaced (separate, important)
The GBDT WF-corpus manifest (`walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json`) stores
**relative** artifact uris (`artifacts/walkforward_gbdt_prod_recipe_v2/<date>/panel-ltr.json`); the
gate resolves them against the manifest's own dir (`artifacts/sim/`) → doubled path
(`artifacts/sim/artifacts/...`) → corpus not found → 3/3 WF cuts fail. **This is the same failure
that has broken `weekly_wf_promote` since 2026-05-24** (R4 #383/#384 did not fully fix it). Worked
around here with an absolute-uri manifest copy; a proper fix (absolute uris, or resolve against the
strategy dir) belongs in its own PR and would unblock the scheduled promote chain.

## Honest caveats / next
- **Is the BULL_CALM/CHOPPY regime failure a real model defect or a regime-specific measurement
  issue?** Not yet diagnosed (earlier BULL_CALM monotonicity was a real n=93 inversion for the
  PatchTST experiments; XGB may differ). This is the decisive next diagnostic.
- The path bug means any *promotion-grade* re-run should use a corrected manifest, not the workaround.
- The lever has shifted: not "find signal" (XGB has it) but **the BULL_CALM regime gate**.
