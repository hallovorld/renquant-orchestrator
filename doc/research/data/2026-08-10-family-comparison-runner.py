"""Family-comparison runner — ONE execution of the frozen design
doc/design/2026-08-09-family-comparison-freeze.md (orch#951).

Every constant is FROM THE DOC (none is a runner choice — the L3 lesson):
window 2026-05-20..2026-07-31; >=30 live names/day; per-day intersection
universe; k=5 only; outcome = top-k mean fwd_5d_excess minus the
intersection mean; REPLAY = mean score of the three fold-8 boosters
trained with the harness's frozen seed tuple (42,43,44) by the harness's
own recipe (per-row purge, train-stat normalization, rank:pairwise
per-date groups, 100 rounds); stationary bootstrap block 5, B 2000,
seed 99 on the daily SERVED-minus-REPLAY differences. NO verdict field.

DRAFT until orch#951 merges; doc text wins over this file on any mismatch.

Usage:
  python <runner>.py <harness.py> <frozen_corpus.parquet> \
      <ext_fund.parquet> <runs.db> <out_prefix>
Outputs <out_prefix>_daily.csv, _coverage.csv, _summary.json verbatim.
"""
import ast, hashlib, json, sqlite3, sys
from pathlib import Path
import numpy as np
import pandas as pd
import xgboost as xgb

if len(sys.argv) != 6:
    sys.exit("usage: runner.py <harness.py> <frozen_corpus.parquet> "
             "<ext_fund.parquet> <runs.db> <out_prefix>")
HARNESS, FROZEN, EXT, DB, OUT = sys.argv[1:6]
OUT = Path(OUT)
W0, W1 = "2026-05-20", "2026-07-31"       # doc s3
MIN_LIVE, K = 30, 5                        # doc s3
BLOCK, B, BOOT_SEED = 5, 2000, 99          # doc s3
LABEL5 = "fwd_5d_excess"
LABEL60 = "fwd_60d_excess"
LABEL_SESSIONS = 60                        # harness constant (60d label)


def harness_constants():
    tree = ast.parse(Path(HARNESS).read_text())
    out = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("FEATS", "CUTS", "PARAMS", "SEEDS",
                                           "CORPUS_SHA256")):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    need = {"FEATS", "CUTS", "PARAMS", "SEEDS", "CORPUS_SHA256"}
    assert set(out) == need, f"harness constants missing: {need - set(out)}"
    return out


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


H = harness_constants()
FEATS, CUTS, PARAMS, SEEDS = H["FEATS"], H["CUTS"], H["PARAMS"], H["SEEDS"]
# doc s2 frozen identities, asserted (not assumed): the seed tuple and the
# fold-8 trait (train <= 2025-12-31, the last fold) named by the doc
assert tuple(SEEDS) == (42, 43, 44), f"seed tuple {SEEDS} != doc s2 (42,43,44)"
assert len(CUTS) == 8 and CUTS[7][1] == "2025-12-31", (
    f"CUTS[7] {CUTS[7]!r} is not fold-8 (train <= 2025-12-31)")
frozen_sha = file_sha256(FROZEN)
assert frozen_sha == H["CORPUS_SHA256"], (
    f"frozen corpus sha {frozen_sha[:12]} != harness pin")

# ── fold-8 training, the harness's own recipe (doc s2) ──────────────────
fz = pd.read_parquet(FROZEN, columns=["date", "ticker", LABEL60] + FEATS)
fz["date"] = fz["date"].astype(str).str[:10]
tr_s, tr_e, te_s, _ = CUTS[7]
tr = fz[(fz.date >= tr_s) & (fz.date <= tr_e)].dropna(subset=[LABEL60])
# per-row purge on the corpus's own calendar (harness _endpoint_map)
dates = sorted(fz.date.unique())
idx = {d: i for i, d in enumerate(dates)}
ep = {d: (dates[i + LABEL_SESSIONS] if i + LABEL_SESSIONS < len(dates) else None)
      for d, i in idx.items()}
n0 = len(tr)
tr = tr[tr.date.map(lambda d: ep.get(d) is not None and ep[d] < te_s)]
Xtr = tr[FEATS].fillna(0).values.astype(np.float64)
ytr = tr[LABEL60].clip(-5, 5).values.astype(np.float64)
mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0) + 1e-9
Xtr = ((Xtr - mu) / sd).clip(-5, 5)
si = np.argsort(tr["date"].values)
_, gsz = np.unique(tr["date"].values[si], return_counts=True)
dtr = xgb.DMatrix(Xtr[si], label=ytr[si]); dtr.set_group(gsz)
boosters = [xgb.train({**PARAMS, "seed": s}, dtr, num_boost_round=100)
            for s in SEEDS]
print(f"fold-8 trained: rows {len(tr)} (purged {n0 - len(tr)}), "
      f"seeds {SEEDS}", flush=True)

# ── extension window scoring + labels (doc s3) ──────────────────────────
exp = pd.read_parquet(EXT, columns=["date", "ticker", LABEL5] + FEATS)
exp["date"] = exp["date"].astype(str).str[:10]
exp = exp[(exp.date >= W0) & (exp.date <= W1)]
# boundary-label assertion (doc s3), on the OBJECTS the doc claims:
# (a) the 2026-05-07 boundary-label exception cannot intersect the
#     window's labels because the window STARTS after it — assert the
#     frozen constant, not the already-filtered rows (which is vacuous);
# (b) the last label date needed (W1 + 5 sessions = the build's 08-07
#     edge) is realized: window-edge rows exist and carry labels.
assert W0 > "2026-05-07", "window start does not clear the boundary-label date"
edge = exp[exp.date == W1]
assert len(edge) > 0 and edge[LABEL5].notna().any(), (
    "window-edge labels not realized in the extension build")
Xe = ((exp[FEATS].fillna(0).values.astype(np.float64) - mu) / sd).clip(-5, 5)
de = xgb.DMatrix(Xe)
exp = exp.assign(replay=np.mean([b.predict(de) for b in boosters], axis=0))

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
    # doc s3 ties rule: "index order after sort" — sort the universe index
    # so nlargest tie-breaking is deterministic, not SQL/parquet row order
    labelled = ex_d.loc[inter, LABEL5].dropna().index.sort_values()
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
    replay_top = u.replay.nlargest(K).index
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
    "window": [W0, W1], "k": K, "n_days": int(n),
    "n_skipped": int(sum(1 for c in cov if c.get("skip"))),
    "frozen_corpus_sha256": frozen_sha,
    "ext_parquet_sha256": file_sha256(EXT),
    "fold8_train_rows": int(len(tr)), "fold8_purged": int(n0 - len(tr)),
    "seeds": list(SEEDS),
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
