"""Served-model reproduction check — task #26 full-width comparison, step 1.

Question: on 2026-05-20..08-07, does scoring the extension panel with the
SERVED artifact (its own booster + its own normalization, through the
PRODUCTION transform + scorer modules) reproduce the scores live recorded
in ticker_daily_state?

Everything model-side comes from the artifact + production code paths:
* booster: renquant_model_gbdt.scorer.load-equivalent (xgb.Booster from
  the artifact's booster_raw_json — same bytes serving loads);
* transform: renquant_pipeline...feature_transform.transform_feature_frame
  with the artifact's OWN metadata and its feature_source_contract.
Read-only inputs; writes CSV/JSON next to itself in scratch.
"""
import json, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/renhao/git/github/renquant-pipeline/src")
from renquant_pipeline.kernel.panel_pipeline.feature_transform import transform_feature_frame
import xgboost as xgb

if len(sys.argv) < 6:
    sys.exit("usage: served-repro-score.py <artifact.json> <ext_fund.parquet> <db> <W0> <W1> [scorer_filter] [out_prefix]")
ART, PANEL, DB, W0, W1 = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
SCORER_FILTER = sys.argv[6] if len(sys.argv) > 6 else None
OUT = Path(sys.argv[7]) if len(sys.argv) > 7 else Path("served_repro")

art = json.loads(ART.read_text())
cols = [str(c) for c in art["feature_cols"]]
contract = art.get("feature_source_contract")
print("artifact: trained", art.get("trained_date"), "| contract", contract,
      "| n feats", len(cols), flush=True)

booster = xgb.Booster()
booster.load_model(bytearray(art["booster_raw_json"].encode("utf-8")))

panel = pd.read_parquet(PANEL)
panel["date"] = pd.to_datetime(panel["date"])
panel = panel[(panel.date >= W0) & (panel.date <= W1)]
print("panel rows in window:", len(panel), "| dates", panel.date.nunique(), flush=True)

# The artifact's feature_source_contract documents BOTH spaces; rows from
# the prebuilt panel take 'panel' (alpha columns already normalized there,
# only raw fundamental columns get their stored stats applied).
space = "panel"
X = transform_feature_frame(panel, cols, art, source_space=space)
panel = panel.assign(offline_score=booster.predict(xgb.DMatrix(X.values.astype(float))))

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
live = pd.read_sql_query(f"""
  WITH canonical AS (
    SELECT run_date, run_id FROM (
      SELECT run_date, run_id,
             ROW_NUMBER() OVER (PARTITION BY run_date
                                ORDER BY created_at DESC, run_id DESC) AS rn
      FROM pipeline_runs WHERE run_type='live') WHERE rn = 1)
  SELECT t.date, t.ticker, t.panel_score, t.rank_score, t.active_scorer
  FROM ticker_daily_state t JOIN canonical c ON c.run_id = t.run_id
  WHERE t.date>='{W0}' AND t.date<='{W1}' AND t.panel_score IS NOT NULL
    {"AND t.active_scorer='" + SCORER_FILTER + "'" if SCORER_FILTER else ""}""", con)
con.close()
live["date"] = pd.to_datetime(live["date"])
print("live scored rows (canonical runs):", len(live),
      "| dates", live.date.nunique(),
      "| scorers", live.active_scorer.value_counts().to_dict(), flush=True)

m = panel[["date", "ticker", "offline_score"]].merge(live, on=["date", "ticker"])
rows = []
for d, g in m.groupby("date"):
    if len(g) < 10:
        continue
    rows.append({
        "date": str(d)[:10], "n": len(g),
        "spearman_panel": g.offline_score.corr(g.panel_score, method="spearman"),
        "spearman_rank": g.offline_score.corr(g.rank_score, method="spearman"),
        "top5_overlap_panel": len(
            set(g.nlargest(5, "offline_score").ticker)
            & set(g.nlargest(5, "panel_score").ticker)),
    })
daily = pd.DataFrame(rows)
daily.to_csv(OUT.parent / (OUT.name + "_daily.csv"), index=False)
summary = {
    "window": [W0, W1], "artifact_trained": art.get("trained_date"),
    "source_space": space,
    "n_joined_rows": int(len(m)), "n_days": int(len(daily)),
    "median_spearman_vs_panel_score": round(float(daily.spearman_panel.median()), 4) if len(daily) else None,
    "median_spearman_vs_rank_score": round(float(daily.spearman_rank.median()), 4) if len(daily) else None,
    "min_spearman_vs_panel_score": round(float(daily.spearman_panel.min()), 4) if len(daily) else None,
    "mean_top5_overlap_panel": round(float(daily.top5_overlap_panel.mean()), 2) if len(daily) else None,
}
(OUT.parent / (OUT.name + "_summary.json")).write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
