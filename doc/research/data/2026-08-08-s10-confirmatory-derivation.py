"""Section 10 confirmatory run — every rule frozen in orch#912; zero live choices.

PRIMARY: slow momentum, rank blend w=0.25, whole book, paired dIC vs panel alone.
Panel arm = the emitted WF replay matrix (point-in-time). Labels = fwd_20d.
Purge (10.3, r2 form): retain date t only if its H=20 forward-label interval
overlaps NO hypothesis-generating date's interval. Purged row GOVERNS.

Two modes:

VERIFY (default) — recomputes all four frozen gate steps for the full-sample
and governing purged rows from the committed CSV alone; no other input needed:
    python 2026-08-08-s10-confirmatory-derivation.py

DERIVE (--derive) — the original derivation that produced the CSV, recorded
for provenance. It hard-depends on uncommitted machine-local inputs (the
bt#110 replay parquets, the Stage -1 momentum JSON, the read-only labels DB)
and will NOT run from this repo alone.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr, rankdata

SP = Path(__file__).parent
CSV = SP / "2026-08-08-s10-confirmatory-rows.csv"
H = 20
W = 0.25


def derive():
    """Provenance only: requires uncommitted local inputs (see module docstring)."""
    import json, sqlite3, glob

    # panel arm: emitted replay matrix
    panel_scores = {}
    for f in sorted(glob.glob(str(SP/"served_matrix_replay/*/wf_replay_panel__wfreplay-2026-08-08.parquet"))):
        d = Path(f).parent.name
        df = pd.read_parquet(f)
        panel_scores[d] = dict(zip(df["ticker"], df["score"]))
    print(f"panel replay dates: {len(panel_scores)}")

    # challenger arm: slow momentum raw scores from the Stage -1 replay
    mom = {r["date"]: (r.get("slow") or {}).get("scores")
           for r in json.load(open(SP/"stage_minus1_momentum_ic.json"))}
    mom = {d: s for d, s in mom.items() if s}
    print(f"slow momentum dates: {len(mom)}")

    # labels
    c = sqlite3.connect("file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro", uri=True)
    fwd = {}
    for d, t, f in c.execute("SELECT as_of_date,ticker,fwd_20d FROM ticker_forward_returns WHERE fwd_20d IS NOT NULL"):
        fwd.setdefault(d, {})[t] = f

    # trading-day axis for interval arithmetic = the label table's own date axis
    axis = sorted(fwd)
    pos = {d: i for i, d in enumerate(axis)}
    hyp = [r["date"] for r in json.load(open(SP/"panel_ic_series.json"))]  # the 33 generating dates
    hyp_iv = [(pos[d], pos[d] + H) for d in hyp if d in pos]

    rows = []
    for d in sorted(set(panel_scores) & set(mom) & set(fwd)):
        ps, ms, fv = panel_scores[d], mom[d], fwd[d]
        common = [t for t in ps if t in ms and t in fv]
        if len(common) < 30:
            continue
        p = np.array([ps[t] for t in common]); m = np.array([ms[t] for t in common])
        y = np.array([fv[t] for t in common])
        if len(set(p)) < 2 or len(set(m)) < 2:
            continue
        ic_p = spearmanr(p, y).correlation
        blend = (1 - W) * rankdata(p) + W * rankdata(m)
        ic_b = spearmanr(blend, y).correlation
        if ic_p != ic_p or ic_b != ic_b:
            continue
        # top-3 by panel score for the transfer
        top3 = [common[i] for i in np.argsort(-p)[:3]]
        i0 = pos[d]
        contaminated = any(i0 <= e and s <= i0 + H for s, e in hyp_iv)
        rows.append({"date": d, "ic_p": ic_p, "ic_b": ic_b, "delta": ic_b - ic_p,
                     "r_top3": float(np.mean([fv[t] for t in top3])),
                     "contaminated": contaminated})
    df = pd.DataFrame(rows)
    df.to_csv(CSV, index=False)
    return df


def gate(sub, name):
    n = len(sub); ne = n / H
    sd = sub["delta"].std(ddof=1)
    bound = 0.05 * np.sqrt(ne) / 2.8
    mean_d = sub["delta"].mean()
    t_adj = mean_d / (sd / np.sqrt(ne)) if sd > 0 else float("nan")
    # moving-block bootstrap, block length 2H >= gap H, 2000 resamples, seeded
    rng = np.random.default_rng(20260808)
    L = 2 * H
    vals = sub["delta"].values
    nb = max(1, int(np.ceil(n / L)))
    boots = []
    for _ in range(2000):
        idx = np.concatenate([np.arange(s, min(s + L, n))
                              for s in rng.integers(0, max(1, n - L + 1), nb)])[:n]
        boots.append(vals[idx].mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    # transfer on the same subset
    x = sub["ic_p"].values; yy = sub["r_top3"].values
    b, a = np.polyfit(x, yy, 1)
    resid = yy - (a + b * x)
    se_iid = np.sqrt(resid.var(ddof=2) / ((x - x.mean()) ** 2).sum())
    t_beta = (b / se_iid) / np.sqrt(n / ne)
    level_ok = sub["ic_b"].mean() >= sub["ic_p"].mean()
    print(f"\n== {name}: n={n} n_eff={ne:.1f}")
    print(f"  1 measurability  sd(D,ddof=1)={sd:.4f}  bound={bound:.4f}  -> {'PASS' if sd<bound else 'FAIL'}")
    print(f"  2 effect         mean D={mean_d:+.4f}  t_adj={t_adj:+.2f}  CI95=[{lo:+.4f},{hi:+.4f}]"
          f"  -> {'PASS' if (mean_d>0 and t_adj>=2.0 and lo>0) else 'FAIL'}")
    print(f"  3 economics      beta={b*1e4:+.0f}bps/IC t_adj={t_beta:+.2f}; "
          f"implied={mean_d*b*1e4:+.1f}bps vs 10bps -> "
          f"{'PASS' if (t_beta>=2.0 and mean_d*b*1e4>10) else 'FAIL'}")
    print(f"  4 level guard    mean icB={sub['ic_b'].mean():+.4f} vs icP={sub['ic_p'].mean():+.4f}"
          f" -> {'PASS' if level_ok else 'FAIL'}")


if __name__ == "__main__":
    if "--derive" in sys.argv:
        df = derive()
    else:
        df = pd.read_csv(CSV)
        print(f"verify mode: {len(df)} rows from {CSV.name}")
    print(f"paired dates total: {len(df)}  (contaminated: {int(df['contaminated'].sum())})")
    gate(df, "FULL SAMPLE (descriptive)")
    gate(df[~df["contaminated"]], "PURGED (GOVERNS)")
