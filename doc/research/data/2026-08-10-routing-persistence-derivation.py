"""Sector-routing persistence pre-test (Stage 0) — versioned derivation.
Reads ONLY the committed #936 dailies; writes the decisions CSV + summary.
The question: does 'best model per sector' persist quarter-to-quarter
enough for ANY trailing-performance routing policy to work?"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr, binomtest

HERE = Path(__file__).parent
D = pd.read_csv(HERE / "2026-08-09-l2s-daily.csv", index_col="date", parse_dates=True)
ARMS = ["panel", "mom_slow", "mom_fast"]
SECS = ["software", "industrial", "finance", "ai_chip", "consumer", "datacenter_hw"]
rows = []
for s in SECS:
    t = pd.DataFrame({a: D[f"{s}__{a}_net"] for a in ARMS}).resample("QE").apply(
        lambda x: (1 + x).prod() - 1).dropna()
    for i in range(len(t) - 1):
        cur, nxt = t.iloc[i], t.iloc[i + 1]
        rows.append({"sector": s, "q_decision": str(t.index[i].date()),
                     "q_outcome": str(t.index[i + 1].date()),
                     "winner_now": cur.idxmax(), "winner_next": nxt.idxmax(),
                     "hit": int(cur.idxmax() == nxt.idxmax()),
                     "rank_spearman": float(spearmanr(cur.rank(), nxt.rank())[0]),
                     "incumbent_next_ret": float(nxt[cur.idxmax()]),
                     "blind_ew_next_ret": float(nxt.mean()),
                     "oracle_next_ret": float(nxt.max())})
df = pd.DataFrame(rows)
df.to_csv(HERE / "2026-08-10-routing-persistence-decisions.csv", index=False)
bt = binomtest(int(df.hit.sum()), len(df), 1 / 3, alternative="greater")
summary = {"n_decisions": len(df), "hit_rate": round(float(df.hit.mean()), 4),
           "chance": 1 / 3, "binomial_p_one_sided": round(float(bt.pvalue), 4),
           "mean_adjacent_spearman": round(float(df.rank_spearman.mean()), 4),
           "incumbent_mean_ret_q": round(float(df.incumbent_next_ret.mean()), 4),
           "oracle_mean_ret_q": round(float(df.oracle_next_ret.mean()), 4),
           "oracle_capture": round(float(df.incumbent_next_ret.mean() / df.oracle_next_ret.mean()), 3),
           "blind_ew_mean_ret_q": round(float(df.blind_ew_next_ret.mean()), 4),
           "incumbent_minus_blind_q": round(float((df.incumbent_next_ret - df.blind_ew_next_ret).mean()), 4),
           "scope_note": ("evaluates ONLY the 1-quarter argmax follow-the-winner rule; "
                          "other lookbacks/hysteresis untested (their own prereg if pursued); "
                          "54 rows = 6 correlated sectors x ~9 quarters, not independent"),
           "frame": "replay (all #937/#944 caveats apply); rerun on served data when it accrues"}
(HERE / "2026-08-10-routing-persistence-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary))
