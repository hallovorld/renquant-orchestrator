"""Conditional tables per DEFINITIONS.md. No parameter search beyond it."""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

SCRATCH = Path(__file__).resolve().parent
H = 60
MIN_DAYS_IN_BLOCK = 15
MIN_BLOCKS_FOR_T = 5
STATES = ["disp20", "breadth", "spyvol20", "scoredisp", "skill60"]
OUTCOMES = ["y_z10", "y_r10", "y_zdec", "y_rdec"]


def add_blocks(df):
    df = df.copy().sort_index()
    df["block"] = np.arange(len(df)) // H
    # trailing remainder block kept only if >= 30 days
    last = df["block"].max()
    if (df["block"] == last).sum() < 30 and last > 0:
        df = df[df["block"] != last]
    return df


def block_t(sub, full_blocked, ycol):
    """sub: rows in the cell (subset of full_blocked). Returns mean, n, nb, t, tcrit."""
    n = len(sub)
    if n == 0:
        return np.nan, 0, 0, np.nan, np.nan
    means = []
    for b, g in sub.groupby("block"):
        if len(g) >= MIN_DAYS_IN_BLOCK:
            means.append(g[ycol].mean())
    nb = len(means)
    m_daily = sub[ycol].mean()
    if nb >= MIN_BLOCKS_FOR_T:
        arr = np.array(means)
        t = arr.mean() / (arr.std(ddof=1) / np.sqrt(nb))
        tcrit = stats.t.ppf(0.975, nb - 1)
    else:
        t = tcrit = np.nan
    return m_daily, n, nb, t, tcrit


def one_way(df, label):
    df = add_blocks(df)
    lines = [f"\n===== {label} (n={len(df)}, blocks={df['block'].nunique()}) ====="]
    # unconditional
    for y in OUTCOMES:
        m, n, nb, t, tc = block_t(df.dropna(subset=[y]), df, y)
        lines.append(f"UNCOND {y:7s} mean={m:+.4f} n={n} n_blocks={nb} "
                     f"block_t={t:+.2f} t_crit={tc:.2f}" if nb else "UNCOND thin")
    for s in STATES:
        d = df.dropna(subset=[s])
        if len(d) < 90:
            lines.append(f"\n-- {s}: only {len(d)} days, skipped")
            continue
        edges = d[s].quantile([1 / 3, 2 / 3]).values
        terc = pd.cut(d[s], [-np.inf, *edges, np.inf], labels=["T1_low", "T2_mid", "T3_high"])
        lines.append(f"\n-- {s} (tercile edges {edges[0]:.4g}, {edges[1]:.4g}; n={len(d)})")
        for y in ["y_z10", "y_r10"]:
            row = []
            for lev in ["T1_low", "T2_mid", "T3_high"]:
                sub = d[terc == lev].dropna(subset=[y])
                m, n, nb, t, tc = block_t(sub, d, y)
                tstr = f"t={t:+.2f}(c{tc:.2f})" if nb >= MIN_BLOCKS_FOR_T else "t=NA"
                row.append(f"{lev}: {m:+.4f} n={n} nb={nb} {tstr}")
            lines.append(f"   {y}: " + " | ".join(row))
    # two-way disp20 x spyvol20 median splits
    d = df.dropna(subset=["disp20", "spyvol20"])
    md, mv = d["disp20"].median(), d["spyvol20"].median()
    lines.append(f"\n-- TWO-WAY disp20 x spyvol20 (medians {md:.4g}, {mv:.4g})")
    for y in ["y_z10", "y_r10"]:
        for dl, dmask in [("dispLO", d["disp20"] <= md), ("dispHI", d["disp20"] > md)]:
            row = []
            for vl, vmask in [("volLO", d["spyvol20"] <= mv), ("volHI", d["spyvol20"] > mv)]:
                sub = d[dmask & vmask].dropna(subset=[y])
                m, n, nb, t, tc = block_t(sub, d, y)
                tstr = f"t={t:+.2f}(c{tc:.2f})" if nb >= MIN_BLOCKS_FOR_T else "t=NA"
                row.append(f"{vl}: {m:+.4f} n={n} nb={nb} {tstr}")
            lines.append(f"   {y} {dl}: " + " | ".join(row))
    return "\n".join(lines)


for name, path in [("CLF-WF (primary)", "series_clf.csv"),
                   ("PHASE-A XGB (secondary, LOOK-AHEAD)", "series_phasea.csv")]:
    df = pd.read_csv(SCRATCH / path, parse_dates=["date"]).set_index("date")
    print(one_way(df, f"{name} — ALL DAYS"))
    bull = df[df["regime"] != "BEAR"]
    print(one_way(bull, f"{name} — BULL-ONLY (prod_gmm != BEAR)"))
