"""Blend-composite reconstruction — task #26 serving-fidelity, cell 3.

Question: on blend-served days, does rebuilding the composite from its two
legs offline reproduce the scores live recorded in ticker_daily_state?

Recipe (the golden config's blend, strategy-104
`configs/strategy_config.golden.json` ranking.panel_scoring):
  leg 0  panel_ltr_xgboost artifact (booster bytes + its own normalization,
         through the production transform, source_space='panel' for
         panel-origin rows);
  leg 1  momentum_residual v0 — the ledger-served dated artifact's static
         per-name `scores` (weekly publish cadence; the row in force on
         the compared dates);
  composite = z(leg0) + z(leg1), z cross-sectional ddof=0 over each leg's
  finite universe (blend_scorer.py semantics; NaN propagates, so the
  composite scores the legs' intersection).

Under blend, ticker_daily_state.panel_score records the COMPOSITE
(blend_scorer.py:315) — that is the comparison target.

Usage:
  python 2026-08-09-blend-recon-score.py <panel_artifact.json> \
      <momentum_artifact.json> <ext_fund.parquet> <runs.db> \
      <W0> <W1> <out_prefix>
Writes <out_prefix>_daily.csv and <out_prefix>_summary.json verbatim —
the committed evidence files are these outputs, unmodified.
Read-only on all inputs.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/renhao/git/github/renquant-pipeline/src")
from renquant_pipeline.kernel.panel_pipeline.feature_transform import transform_feature_frame
import xgboost as xgb

if len(sys.argv) != 8:
    sys.exit(__doc__.strip().splitlines()[-8])
PANEL_ART, MOM_ART, PANEL_PQ, DB, W0, W1, OUT = sys.argv[1:8]
OUT = Path(OUT)

art = json.loads(Path(PANEL_ART).read_text())
cols = [str(c) for c in art["feature_cols"]]
booster = xgb.Booster()
booster.load_model(bytearray(art["booster_raw_json"].encode("utf-8")))

mom = json.loads(Path(MOM_ART).read_text())
mom_scores = pd.Series(mom["scores"], dtype=float)
print(f"panel leg: trained {art.get('trained_date')} | mom leg: cutoff "
      f"{mom.get('cutoff_date')} sha {mom.get('content_sha256', '')[:8]} "
      f"n={len(mom_scores)}", flush=True)

panel = pd.read_parquet(PANEL_PQ)
panel["date"] = pd.to_datetime(panel["date"])
panel = panel[(panel.date >= W0) & (panel.date <= W1)]
X = transform_feature_frame(panel, cols, art, source_space="panel")
panel = panel.assign(pleg=booster.predict(xgb.DMatrix(X.values.astype(float))))

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
live = pd.read_sql_query(f"""
  WITH canonical AS (
    SELECT run_date, run_id FROM (
      SELECT run_date, run_id,
             ROW_NUMBER() OVER (PARTITION BY run_date
                                ORDER BY created_at DESC, run_id DESC) AS rn
      FROM pipeline_runs WHERE run_type='live') WHERE rn = 1)
  SELECT t.date, t.ticker, t.panel_score FROM ticker_daily_state t
  JOIN canonical c ON c.run_id = t.run_id
  WHERE t.date>='{W0}' AND t.date<='{W1}' AND t.panel_score IS NOT NULL
    AND t.active_scorer='blend'""", con)
con.close()
live["date"] = pd.to_datetime(live["date"])

rows = []
for d, g in panel.groupby("date"):
    g = g.set_index("ticker")
    z1 = (g.pleg - g.pleg.mean()) / g.pleg.std(ddof=0)
    mm = mom_scores.reindex(z1.index)
    fin = mm.notna()
    z2 = pd.Series(np.nan, index=z1.index)
    z2[fin] = (mm[fin] - mm[fin].mean()) / mm[fin].std(ddof=0)
    comp = z1 + z2
    lv = live[live.date == d].set_index("ticker").panel_score
    j = pd.concat([comp.rename("off"), lv.rename("live")], axis=1).dropna()
    if len(j) >= 10:
        rows.append({
            "date": str(d)[:10], "n": len(j),
            "spearman": float(j.off.corr(j.live, method="spearman")),
            "top5_overlap": len(set(j.nlargest(5, "off").index)
                                & set(j.nlargest(5, "live").index)),
        })
daily = pd.DataFrame(rows)
daily.to_csv(OUT.parent / (OUT.name + "_daily.csv"), index=False)
summary = {
    "window": [W0, W1],
    "panel_leg_trained": art.get("trained_date"),
    "mom_leg_cutoff": mom.get("cutoff_date"),
    "mom_leg_sha256": mom.get("content_sha256"),
    "n_days": int(len(daily)),
    "median_spearman": float(daily.spearman.median()) if len(daily) else None,
    "min_spearman": float(daily.spearman.min()) if len(daily) else None,
    "mean_top5_overlap": float(daily.top5_overlap.mean()) if len(daily) else None,
}
(OUT.parent / (OUT.name + "_summary.json")).write_text(
    json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
