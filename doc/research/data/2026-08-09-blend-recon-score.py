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

Identity binding (review P1): the panel artifact's file-byte sha256 is
verified against the golden config's expected_content_sha256 pin
(abbrev-tolerant prefix match, the blend_scorer convention); the momentum
artifact's embedded content_sha256 is verified against the ledger row in
force; the pipeline checkout revision whose transform is imported is
recorded. The reconstruction is CONDITIONAL on these recorded inputs.

Coverage accounting (review P1): per-day counts for panel/momentum-finite/
live/intersection plus BOTH asymmetric differences are persisted
(<out_prefix>_coverage.csv, identifiers included) and the run FAILS CLOSED
if any live-scored name is absent from the offline composite.

Usage:
  python 2026-08-09-blend-recon-score.py <panel_artifact.json> \
      <momentum_artifact.json> <golden_config.json> <ledger.jsonl> \
      <ext_fund.parquet> <runs.db> <W0> <W1> <out_prefix>
Writes <out_prefix>_daily.csv, <out_prefix>_coverage.csv and
<out_prefix>_summary.json verbatim — the committed evidence files are
these outputs, unmodified. Read-only on all inputs.
"""
import hashlib, json, sqlite3, subprocess, sys
from pathlib import Path
import numpy as np
import pandas as pd

PIPELINE_SRC = "/Users/renhao/git/github/renquant-pipeline"
sys.path.insert(0, PIPELINE_SRC + "/src")
from renquant_pipeline.kernel.panel_pipeline.feature_transform import transform_feature_frame
import xgboost as xgb

if len(sys.argv) != 10:
    sys.exit("usage: 2026-08-09-blend-recon-score.py <panel_artifact.json> "
             "<momentum_artifact.json> <golden_config.json> <ledger.jsonl> "
             "<ext_fund.parquet> <runs.db> <W0> <W1> <out_prefix>")
PANEL_ART, MOM_ART, GOLDEN, LEDGER, PANEL_PQ, DB, W0, W1, OUT = sys.argv[1:10]
OUT = Path(OUT)


def _norm(d):
    return str(d or "").removeprefix("sha256:").lower()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

# ── identity binding, fail-closed ────────────────────────────────────────
golden = json.loads(Path(GOLDEN).read_text())
comps = golden["ranking"]["panel_scoring"]["components"]
panel_pin = _norm(next(c["expected_content_sha256"] for c in comps
                       if "expected_content_sha256" in c))
panel_sha = file_sha256(PANEL_ART)
assert len(panel_pin) >= 8 and panel_sha.startswith(panel_pin), (
    f"panel artifact sha {panel_sha[:12]} does not match golden pin {panel_pin}")

mom = json.loads(Path(MOM_ART).read_text())
ledger_rows = [json.loads(l) for l in open(LEDGER)]
in_force = [r for r in ledger_rows
            if str(r.get("cutoff_date", "9999")) <= W0]
assert in_force, f"no ledger row in force at {W0}"
ledger_sha = _norm(in_force[-1]["artifact_content_sha256"])
mom_sha = _norm(mom.get("content_sha256"))
assert mom_sha == ledger_sha, (
    f"momentum artifact content sha {mom_sha[:12]} != ledger row "
    f"{in_force[-1].get('row_index')} recorded {ledger_sha[:12]}")

pipeline_rev = subprocess.run(
    ["git", "-C", PIPELINE_SRC, "rev-parse", "HEAD"],
    capture_output=True, text=True).stdout.strip()

art = json.loads(Path(PANEL_ART).read_text())
cols = [str(c) for c in art["feature_cols"]]
booster = xgb.Booster()
booster.load_model(bytearray(art["booster_raw_json"].encode("utf-8")))
mom_scores = pd.Series(mom["scores"], dtype=float)
print(f"panel leg: trained {art.get('trained_date')} sha={panel_sha[:12]} "
      f"(golden pin ok) | mom leg: cutoff {mom.get('cutoff_date')} "
      f"sha={mom_sha[:12]} (ledger row ok) n={len(mom_scores)} | "
      f"pipeline rev {pipeline_rev[:12]}", flush=True)

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

rows, cov_rows = [], []
for d, g in panel.groupby("date"):
    g = g.set_index("ticker")
    z1 = (g.pleg - g.pleg.mean()) / g.pleg.std(ddof=0)
    mm = mom_scores.reindex(z1.index)
    fin = mm.notna()
    z2 = pd.Series(np.nan, index=z1.index)
    z2[fin] = (mm[fin] - mm[fin].mean()) / mm[fin].std(ddof=0)
    comp = (z1 + z2).dropna()
    lv = live[live.date == d].set_index("ticker").panel_score.dropna()
    off_only = sorted(set(comp.index) - set(lv.index))
    live_only = sorted(set(lv.index) - set(comp.index))
    inter = comp.index.intersection(lv.index)
    cov_rows.append({
        "date": str(d)[:10],
        "n_panel_scored": int(len(g)), "n_mom_finite": int(fin.sum()),
        "n_offline_composite": int(len(comp)), "n_live": int(len(lv)),
        "n_intersection": int(len(inter)),
        "n_offline_only": len(off_only), "n_live_only": len(live_only),
        "offline_only_names": "|".join(off_only),
        "live_only_names": "|".join(live_only),
    })
    # Fail-closed coverage criterion: every live-scored name must be
    # offline-composable — a live-only name means the offline
    # reconstruction is missing part of the surface it claims to rebuild.
    assert not live_only, (
        f"{str(d)[:10]}: live-scored names missing from the offline "
        f"composite: {live_only}")
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
pd.DataFrame(cov_rows).to_csv(OUT.parent / (OUT.name + "_coverage.csv"), index=False)
summary = {
    "window": [W0, W1],
    "panel_leg_trained": art.get("trained_date"),
    "panel_leg_file_sha256": panel_sha,
    "panel_leg_golden_pin": panel_pin,
    "mom_leg_cutoff": mom.get("cutoff_date"),
    "mom_leg_sha256": mom.get("content_sha256"),
    "mom_leg_ledger_row_index": in_force[-1].get("row_index"),
    "pipeline_checkout_rev": pipeline_rev,
    "ext_parquet_sha256": file_sha256(PANEL_PQ),
    "coverage_fail_closed": "no live-only names on any day (asserted)",
    "n_days": int(len(daily)),
    "median_spearman": float(daily.spearman.median()) if len(daily) else None,
    "min_spearman": float(daily.spearman.min()) if len(daily) else None,
    "mean_top5_overlap": float(daily.top5_overlap.mean()) if len(daily) else None,
}
(OUT.parent / (OUT.name + "_summary.json")).write_text(
    json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
