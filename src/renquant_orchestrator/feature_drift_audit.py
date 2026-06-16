"""Feature drift audit (#106/#108 — targeted de-drifting of the panel).

The WF sanity placebo fails when a model's scores correlate with a *future-
shifted* label as strongly as with the aligned one — i.e. the "alpha" is slow
cross-sectional drift, not horizon-specific signal. Pruning the slow-vol/
drawdown family (STD/MIN/IMIN) cut B2's placebo ratio 25.5→2.84, but it still
fails (gate needs < 2.0). This audit finds the *next* features to prune: those
whose per-date cross-sectional IC with the 120d-shifted label exceeds their IC
with the aligned label (``drift_excess > 0``), ranked by family.

Pure over a panel DataFrame so it is testable; ``audit_panel_file`` wraps a
parquet path for the CLI.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

_META = {"date", "ticker", "split_label",
         "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess"}


def _mean_cs_ic(df: pd.DataFrame, col: str, ycol: str,
                dates: list, min_names: int) -> float:
    from scipy.stats import spearmanr  # local: scipy import is slow
    ics: list[float] = []
    for d in dates:
        g = df.loc[df["date"] == d, [col, ycol]].dropna()
        if len(g) >= min_names and g[col].nunique() > 1 and g[ycol].nunique() > 1:
            ic = spearmanr(g[col], g[ycol])[0]
            if ic == ic:  # not NaN
                ics.append(float(ic))
    return float(np.mean(ics)) if ics else float("nan")


def drift_audit(
    panel: pd.DataFrame,
    label: str = "fwd_60d_excess",
    *,
    shift_days: int = 120,
    min_names: int = 20,
    sample_every: int = 1,
    exclude_prefixes: Iterable[str] = (),
) -> pd.DataFrame:
    """Per-feature aligned vs shifted-label IC. Returns a DataFrame sorted by
    ``drift_excess = |placebo_ic| - |aligned_ic|`` (descending).

    ``sample_every`` subsamples dates for speed (1 = every date).
    ``exclude_prefixes`` skips already-pruned families.
    """
    df = panel.sort_values(["ticker", "date"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    excl = tuple(exclude_prefixes)
    feats = [c for c in df.columns
             if c not in _META and df[c].dtype.kind in "fiub"
             and not (excl and c.startswith(excl))]
    df["__shifted"] = df.groupby("ticker")[label].shift(-int(shift_days))
    dates = sorted(df["date"].unique())[::max(1, int(sample_every))]
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for f in feats:
            a = _mean_cs_ic(df, f, label, dates, min_names)
            p = _mean_cs_ic(df, f, "__shifted", dates, min_names)
            rows.append((f, a, p))
    out = pd.DataFrame(rows, columns=["feature", "aligned_ic", "placebo_ic"]).dropna()
    out["drift_excess"] = out["placebo_ic"].abs() - out["aligned_ic"].abs()
    out["family"] = out["feature"].str.extract(r"^([A-Za-z]+)")
    return out.sort_values("drift_excess", ascending=False).reset_index(drop=True)


def family_drift(audit: pd.DataFrame) -> pd.DataFrame:
    """Mean drift_excess per feature family, descending."""
    audit = audit.copy()
    audit["abs_aligned_ic"] = audit["aligned_ic"].abs()
    g = (audit.groupby("family")
         .agg(mean_drift_excess=("drift_excess", "mean"),
              n=("feature", "size"),
              mean_aligned=("aligned_ic", "mean"),
              mean_abs_aligned=("abs_aligned_ic", "mean"))
         .sort_values("mean_drift_excess", ascending=False)
         .reset_index())
    return g


def suggest_prune_families(
    audit: pd.DataFrame,
    *,
    min_drift_excess: float = 0.02,
    max_abs_aligned: float = 0.02,
    collides_with: Iterable[str] = (),
) -> list[str]:
    """Families to prune next: high mean drift_excess AND near-zero aligned IC
    (so pruning sheds placebo without losing signal). ``collides_with`` drops
    prefixes that are a prefix of a keep-family (e.g. 'MA' collides with 'MAX')
    since the exclude knob is prefix-based."""
    fam = family_drift(audit)
    keep = set(collides_with)
    picks = []
    for _, r in fam.iterrows():
        f = r["family"]
        if (r["mean_drift_excess"] >= min_drift_excess
                and r["mean_abs_aligned"] <= max_abs_aligned
                and not any(other != f and other.startswith(f) for other in keep)):
            picks.append(f)
    return picks


def audit_panel_file(path: str | Path, label: str = "fwd_60d_excess",
                     **kw) -> pd.DataFrame:
    return drift_audit(pd.read_parquet(path), label, **kw)
