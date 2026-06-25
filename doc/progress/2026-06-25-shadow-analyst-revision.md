# Shadow GBDT with analyst rating-revision (an_rev3)

2026-06-25. Operator: feed the analyst data to the SHADOW model and retrain it.

## Why shadow (not primary)
The per-regime placebo-clean evidence on the analyst signal is **weak / inside the
~0.036 leakage-floor noise**, and a component decomposition showed no single piece is
robust: the consensus LEVEL even leans negative in BULL_VOLATILE while the rating
REVISION (`an_rev3` = Δ3-month consensus) is benign-to-mildly-positive. That is exactly
the profile that does NOT justify touching the live primary, but DOES justify a SHADOW
home where it accrues live OOS evidence at zero book risk (the antidote to
deployed-but-dark — a real path-to-live, not a dark default-off flag).

## What was done
- `scripts/build_shadow_analyst_panel.py` — builds a SHADOW training panel = the prod
  alpha158-fund panel + one extra column `an_rev3`, merged point-in-time (`merge_asof`
  backward by date, per ticker → no lookahead). **Revision-only by design** (drop the
  consensus level the decomposition flagged as harmful). Writes to a SEPARATE
  `data/shadow_analyst/` dir; the prod panel is never modified.
- Trained the shadow GBDT on it (`train_gbdt.py --data-dir data/shadow_analyst
  --drop-sentiment --strategy-config none`). The feature flows in automatically — the
  trainer auto-discovers panel columns minus the meta/label set, and the scorer reads
  `feature_cols` from the artifact, so **NO renquant-model code change was needed**.

## Result (3-fold pooled OOS IC, same recipe, only an_rev3 differs)
| model | OOS IC mean | folds | n_feat |
|---|---|---|---|
| **+ an_rev3** | **+0.0530** | [0.0941, −0.0038, 0.0687] | 170 |
| baseline (no an_rev3) | +0.0494 | [0.0829, 0.0026, 0.0628] | 169 |
| **Δ (an_rev3 adds)** | **+0.0036** | [+0.011, −0.006, +0.006] | |

an_rev3 nudges pooled OOS IC up **+0.0036** — it does NOT degrade the model (so "the
analyst model is worse" was an overclaim; it's marginally better here), but it is far
too small to be conclusive in-sample. Live shadow OOS is the right adjudicator.
`an_rev3` got identity normalization (fine for a tree model) and is confirmed in the
artifact's `feature_cols`.

## Path to live (deliberately NOT wired yet — avoids a score-time footgun)
The shadow scorer requires `an_rev3` to be present in the LIVE inference frame at score
time (it reads `feature_cols` and KeyErrors on a missing column). The current live
feature pipeline does NOT produce `an_rev3`, so wiring a `shadow_models[]` entry now
would crash the shadow run. Dependency-ordered path:
1. Land base-data **#25** (Finnhub fetcher) + cron **#408** → daily analyst series accrues.
2. Wire `an_rev3` into the live inference frame (renquant-pipeline feature build reads the
   accumulating grades/Finnhub series → `an_rev3` column), mirroring the fundamentals join.
3. Add the `shadow_models[]` entry in `strategy_config.shadow.json` pointing at the
   artifact under `artifacts/shadow/` + place the artifact.
4. The shadow e2e then scores it live (isolated `alpaca_shadow` state) → accrue OOS IC.
   Graduate toward primary ONLY if it clears a pre-registered live bar.

## Notes
- Artifact: `data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json` (gitignored
  data; reproducible from the build script + `data/fmp_harvest/grades_historical_291.parquet`).
- Rich analyst features (estimates / price-targets) are single-snapshot → NOT usable until
  the daily cron accrues publish-date history (would be lookahead today). an_rev3 (from the
  monthly grades-historical series) is the only leak-free analyst feature available now.
