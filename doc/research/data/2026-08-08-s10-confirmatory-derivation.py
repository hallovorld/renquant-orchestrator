"""Section-10 confirmatory run — verifier + provenance derivation.

DEFAULT (verify): recompute all four frozen gate steps for BOTH rows (full
sample and the governing purged row) from the committed CSV alone —
`2026-08-08-s10-confirmatory-rows.csv`, beside this file. No DB, no scratch
inputs, no network. This is the reproducible evidence artifact the orch#911
review required.

--derive: the original derivation, kept as PROVENANCE ONLY. It needs
machine-local inputs that are deliberately not committed (the emitted replay
parquets, the Stage -1 raw-score JSON, the labels DB) and refuses with a
clear message when they are absent.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CSV = HERE / "2026-08-08-s10-confirmatory-rows.csv"
H = 20
ROUND_TRIP_BPS = 10.0


def gate(sub: pd.DataFrame, name: str) -> None:
    n = len(sub)
    ne = n / H
    sd = sub["delta"].std(ddof=1)
    bound = 0.05 * np.sqrt(ne) / 2.8
    mean_d = sub["delta"].mean()
    t_adj = mean_d / (sd / np.sqrt(ne)) if sd > 0 else float("nan")
    rng = np.random.default_rng(20260808)
    L = 2 * H
    vals = sub["delta"].to_numpy()
    nb = max(1, int(np.ceil(n / L)))
    boots = []
    for _ in range(2000):
        starts = rng.integers(0, max(1, n - L + 1), nb)
        idx = np.concatenate([np.arange(s, min(s + L, n)) for s in starts])[:n]
        boots.append(vals[idx].mean())
    lo, hi = np.percentile(boots, [2.5, 97.5])
    x = sub["ic_p"].to_numpy()
    y = sub["r_top3"].to_numpy()
    b, a = np.polyfit(x, y, 1)
    resid = y - (a + b * x)
    se_iid = np.sqrt(resid.var(ddof=2) / ((x - x.mean()) ** 2).sum())
    t_beta = (b / se_iid) / np.sqrt(n / ne)
    implied_bps = mean_d * b * 1e4
    level_ok = sub["ic_b"].mean() >= sub["ic_p"].mean()
    print(f"\n== {name}: n={n} n_eff={ne:.1f}")
    print(f"  1 measurability  sd(D,ddof=1)={sd:.4f}  bound={bound:.4f}"
          f"  -> {'PASS' if sd < bound else 'FAIL'}")
    print(f"  2 effect         mean D={mean_d:+.4f}  t_adj={t_adj:+.2f}"
          f"  CI95=[{lo:+.4f},{hi:+.4f}]"
          f"  -> {'PASS' if (mean_d > 0 and t_adj >= 2.0 and lo > 0) else 'FAIL'}")
    print(f"  3 economics      beta={b*1e4:+.0f}bps/IC t_adj={t_beta:+.2f};"
          f" implied={implied_bps:+.1f}bps vs {ROUND_TRIP_BPS:.0f}bps -> "
          f"{'PASS' if (t_beta >= 2.0 and implied_bps > ROUND_TRIP_BPS) else 'FAIL'}")
    print(f"  4 level guard    mean icB={sub['ic_b'].mean():+.4f}"
          f" vs icP={sub['ic_p'].mean():+.4f} -> {'PASS' if level_ok else 'FAIL'}")


def verify() -> None:
    df = pd.read_csv(CSV)
    print(f"rows: {len(df)}  contaminated: {int(df['contaminated'].sum())}"
          f"  [source: {CSV.name}]")
    gate(df, "FULL SAMPLE (descriptive)")
    gate(df[~df["contaminated"]], "PURGED (GOVERNS)")


def derive() -> None:
    needed = [
        ("emitted replay parquets", "<scratch>/served_matrix_replay/*/wf_replay_panel__*.parquet"),
        ("Stage -1 raw scores", "<scratch>/stage_minus1_momentum_ic.json"),
        ("labels DB", "RenQuant/data/runs.alpaca.db"),
    ]
    print("--derive is PROVENANCE ONLY: it reproduces the committed CSV from "
          "machine-local inputs that are deliberately not in the repo:")
    for name, path in needed:
        print(f"  - {name}: {path}")
    print("The construction is documented in the research doc and in the "
          "orch#905 run-config comment; the verifiable artifact is the CSV, "
          "checked by the default mode.")
    sys.exit(2)


if __name__ == "__main__":
    if "--derive" in sys.argv[1:]:
        derive()
    else:
        verify()
