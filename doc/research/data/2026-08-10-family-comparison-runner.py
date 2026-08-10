"""Family-comparison runner (JOIN-ONLY, r2) — the orchestrator half of the
frozen design doc/design/2026-08-09-family-comparison-freeze.md (orch#951).

r2 (review P0): all model internals (fold-8 training, normalization,
scoring) moved to renquant-model `scripts/family_comparison_replay_scorer.py`
(model#220), which publishes a hash-pinned predictions artifact. This
runner consumes that artifact and does ONLY what belongs here: label join,
live-record join, coverage accounting, the frozen outcome table, and the
bootstrap. The REPLAY numbers are byte-identical to r1's (asserted by the
r2 rerun reproducing the committed evidence files).

Identity pins (fail-closed): the predictions CSV's sha256 must equal the
model#220 manifest value; the extension parquet's sha256 must equal the
manifest's `ext_parquet_sha256` (labels must come from the same build the
predictions were scored on).

Usage:
  python 2026-08-10-family-comparison-runner.py <predictions.csv> \
      <ext_fund.parquet> <runs.db> <out_prefix>
Outputs <out_prefix>_daily.csv, _coverage.csv, _summary.json verbatim.
"""
import hashlib, json, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd

if len(sys.argv) != 5:
    sys.exit("usage: runner.py <predictions.csv> <ext_fund.parquet> "
             "<runs.db> <out_prefix>")
PRED, EXT, DB, OUT = sys.argv[1:5]
OUT = Path(OUT)
W0, W1 = "2026-05-20", "2026-07-31"       # doc s3
MIN_LIVE, K = 30, 5                        # doc s3
BLOCK, B, BOOT_SEED = 5, 2000, 99          # doc s3
LABEL5 = "fwd_5d_excess"
# model#220 manifest pins (doc/design/frozen/…-replay-predictions.csv.manifest.json)
PRED_SHA = "b549940e0c70a42b63335961872aff978136ed387fe9ee9b45d6d386b118cc8f"
EXT_SHA = "7da2f2797c1fdaf0024556e88e69b6ef6ecaed5ab88e9e3ba03d50d91dd3c6f2"

# boundary assertion on the frozen constants (rehearsal fix M2): the
# 2026-05-07 boundary-label exception cannot intersect the window
assert W0 > "2026-05-07", "window would intersect the boundary-label date"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


pred_sha = file_sha256(PRED)
assert pred_sha == PRED_SHA, f"predictions sha {pred_sha[:12]} != model#220 pin"
ext_sha = file_sha256(EXT)
assert ext_sha == EXT_SHA, f"ext parquet sha {ext_sha[:12]} != manifest pin"

pred = pd.read_csv(PRED, dtype={"date": str})
assert list(pred.columns) == ["date", "ticker", "replay_score"], pred.columns
assert pred.date.min() >= W0 and pred.date.max() <= W1, "predictions outside window"
assert not pred.duplicated(["date", "ticker"]).any(), "duplicate prediction keys"

labels = pd.read_parquet(EXT, columns=["date", "ticker", LABEL5])
labels["date"] = labels["date"].astype(str).str[:10]
labels = labels[(labels.date >= W0) & (labels.date <= W1)]
# window-edge label presence (rehearsal fix M2): the build's 08-07 edge
# must deliver labels for W1 rows
assert labels[labels.date == W1][LABEL5].notna().any(), "W1 rows carry no labels"

exp = pred.merge(labels, on=["date", "ticker"], how="left")

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
  WHERE t.date>='{W0}' AND t.date<='{W1}' AND t.panel_score IS NOT NULL""", con)
con.close()

rows, cov = [], []
for d, lv in live.groupby("date"):
    lv = lv.set_index("ticker").panel_score.dropna()
    if len(lv) < MIN_LIVE:
        cov.append({"date": d, "skip": "live<30", "n_live": len(lv)})
        continue
    ex_d = exp[exp.date == d].set_index("ticker")
    inter = lv.index.intersection(ex_d.index)
    labelled = ex_d.loc[inter, LABEL5].dropna().index.sort_values()  # M3: deterministic ties
    cov.append({"date": d, "skip": "", "n_live": len(lv),
                "n_replay": len(ex_d), "n_intersection": len(inter),
                "n_labelled": len(labelled),
                "live_only": "|".join(sorted(set(lv.index) - set(ex_d.index))),
                "replay_only": "|".join(sorted(set(ex_d.index) - set(lv.index)))})
    if len(labelled) < K:
        cov[-1]["skip"] = "labelled<k"
        continue
    u = ex_d.loc[labelled]
    served_top = lv.loc[labelled].nlargest(K).index
    replay_top = u.replay_score.nlargest(K).index
    base = u[LABEL5].mean()
    oracle_top = u[LABEL5].nlargest(K).index   # doc s3 plumbing control
    rows.append({"date": d, "n_universe": len(labelled),
                 "served_topk_excess": float(u.loc[served_top, LABEL5].mean() - base),
                 "replay_topk_excess": float(u.loc[replay_top, LABEL5].mean() - base),
                 "oracle_topk_excess": float(u.loc[oracle_top, LABEL5].mean() - base)})
daily = pd.DataFrame(rows)
daily["diff_served_minus_replay"] = daily.served_topk_excess - daily.replay_topk_excess

# stationary bootstrap on daily diffs (block 5, B 2000, seed 99 — doc s3)
rng = np.random.default_rng(BOOT_SEED)
x = daily.diff_served_minus_replay.values
n = len(x)
means = []
for _ in range(B):
    out_idx = []
    while len(out_idx) < n:
        start = rng.integers(n)
        length = rng.geometric(1 / BLOCK)
        out_idx.extend(((start + np.arange(length)) % n).tolist())
    means.append(float(np.mean(x[np.array(out_idx[:n])])))
ci = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))

daily.to_csv(OUT.parent / (OUT.name + "_daily.csv"), index=False)
pd.DataFrame(cov).to_csv(OUT.parent / (OUT.name + "_coverage.csv"), index=False)
summary = {
    "design_doc": "doc/design/2026-08-09-family-comparison-freeze.md",
    "predictions_artifact": "renquant-model doc/design/frozen/"
                            "2026-08-10-family-comparison-replay-predictions.csv",
    "predictions_sha256": pred_sha,
    "ext_parquet_sha256": ext_sha,
    "window": [W0, W1], "k": K, "n_days": int(n),
    "n_skipped": int(sum(1 for c in cov if c.get("skip"))),
    "mean_served_topk_excess": float(daily.served_topk_excess.mean()),
    "mean_replay_topk_excess": float(daily.replay_topk_excess.mean()),
    "mean_diff_served_minus_replay": float(np.mean(x)),
    "median_diff_served_minus_replay": float(np.median(x)),
    "bootstrap_ci95_diff": ci,
    "oracle_mean_topk_excess_plumbing_control": float(daily.oracle_topk_excess.mean()),
    "verdict": None,   # the doc grants no verdict authority
}
(OUT.parent / (OUT.name + "_summary.json")).write_text(
    json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
