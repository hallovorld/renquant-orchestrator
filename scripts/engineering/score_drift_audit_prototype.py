#!/usr/bin/env python3
"""Score-distribution drift audit prototype (#108 L6 sidecar, catalog item 3).

PSI of today's rank_score distribution vs a trailing-20-run baseline from
the REAL score DB. Severity: PSI<0.10 INFO, <0.25 WARN, else CRITICAL
(industry-standard PSI bands). Read-only; production wiring = an AuditTask
joined before order emission.
"""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    qs = np.quantile(expected, np.linspace(0, 1, bins + 1))
    qs[0], qs[-1] = -np.inf, np.inf
    e, _ = np.histogram(expected, qs)
    a, _ = np.histogram(actual, qs)
    e = np.clip(e / e.sum(), 1e-6, None)
    a = np.clip(a / a.sum(), 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


def severity(v: float) -> str:
    return "INFO" if v < 0.10 else ("WARN" if v < 0.25 else "CRITICAL")


if __name__ == "__main__":
    c = sqlite3.connect(DB)
    df = pd.read_sql(
        "SELECT run_id, rank_score FROM candidate_scores "
        "WHERE rank_score IS NOT NULL", c)
    sizes = df.groupby("run_id").size()
    full = sizes[sizes >= 30].index.tolist()          # full scoring runs only
    full.sort()                                        # run_id starts with date
    assert len(full) >= 3, f"need >=3 full runs, have {len(full)}"
    latest, baseline_ids = full[-1], full[-21:-1]
    base = df[df.run_id.isin(baseline_ids)]["rank_score"].values
    cur = df[df.run_id == latest]["rank_score"].values
    v = psi(base, cur)
    print(f"baseline: {len(baseline_ids)} runs / {len(base)} scores; "
          f"latest run {latest}: {len(cur)} scores")
    print(f"PSI = {v:.4f} → {severity(v)}")
    # self-test: synthetic collapse must scream
    collapsed = np.full(80, np.median(base))
    v2 = psi(base, collapsed)
    assert severity(v2) == "CRITICAL", v2
    print(f"self-test: synthetic calibrator collapse PSI={v2:.2f} → CRITICAL ✓")
