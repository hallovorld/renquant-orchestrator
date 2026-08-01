#!/usr/bin/env python3
"""Is the boosters' disagreement structured, or is it churn? — it is structured.

orch#712 measured that 12 same-recipe boosters disagree on **35.7%** of the real top
decile and closed with: *"disagreement is a precondition for an ensemble to be worth
anything, never evidence that one works."* This asks the next question that precondition
leaves open: **is the disagreement uniform churn, or is there a stable core?**

MEASURED 2026-08-01 — the same 12 boosters, the same 20 sessions of the live
`alpha158_291_fundamental_dataset` panel (2026-04-07 … 2026-05-04, 144–153 names/date,
`k` = 14–15), 3 528 top-decile slots in total:

======  =======  =========  =======  =========
votes    names    % names     slots    % slots
======  =======  =========  =======  =========
  1/12      220      29.8%       220       6.2%
  2/12      105      14.2%       210       6.0%
  …
 11/12       32       4.3%       352      10.0%
 12/12       76      10.3%       912      **25.9%**
======  =======  =========  =======  =========

**The distribution is not flat, and the precise shape matters.** By NAME it falls from
29.8% at 1/12 to a **plateau of 3.8–6.1% across 4/12–11/12**, then jumps to **10.3% at
12/12** — unanimity is a distinct second mode standing well clear of that plateau, though
it is smaller than the 2/12 bucket (14.2%). Calling it "U-shaped" was my first description
and a test caught it: `12/12` does not exceed `2/12`.

Weighted by what actually gets traded, unanimity is the single largest bucket:

  * **66.9%** of top-decile slots are held by names with a **majority** (≥7/12);
  * **25.9%** by **unanimous** names;
  * the 220 singleton appearances are 29.8% of names but only **6.2%** of slots.

Per date, the union of all twelve top deciles is a median of **38** names against `k = 15`
— **2.50×** one arm — of which a median of **4** are unanimous (23% of a top decile) and
**10** are singletons.

WHAT THIS ESTABLISHES, EXACTLY. That the precondition orch#712 named is met with room to
spare: there is a stable core an ensemble could concentrate on and a large, cheap tail it
could drop. **It does not establish that doing so would perform better.** No label and no
forward return is touched anywhere in this file — the panel's own `fwd_*` columns are never
read. A consensus rule that concentrates on names twelve models agree about could easily be
concentrating on twelve models' shared blind spot, and nothing here can tell those apart.

Read-only. Loads artifacts and the panel, writes only under ``--out``.

Exit codes: ``0`` scored, ``1`` fewer than two distinct boosters, ``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOP_FRACTION = 0.10
MIN_NAMES = 50

#: Never read. Named so the omission is checkable rather than asserted: this analysis is
#: label-free by construction, and a test asserts none of these appears in the source.
FORBIDDEN_LABEL_COLS = ("fwd_20d", "fwd_60d", "fwd_120d", "fwd_60d_excess", "label")


def distinct_boosters(pattern: str) -> dict[str, dict]:
    """Keyed on booster BYTES — keying on any fingerprint collapses all 12 into one."""
    out: dict[str, dict] = {}
    for p in sorted(glob.glob(pattern)):
        try:
            d = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("booster_raw_json"), str) \
                and d["booster_raw_json"]:
            out.setdefault(
                hashlib.sha256(d["booster_raw_json"].encode()).hexdigest()[:12], d)
    return out


def consensus(votes: collections.Counter, n_boosters: int) -> dict:
    """Vote histogram by NAME and by SLOT.

    Both are reported because they answer different questions and disagree sharply. A
    name picked by one booster is one name and **one** slot; a name picked by twelve is
    one name and **twelve** slots. Counting names alone says singletons dominate (29.8%);
    counting slots says they are 6.2% of what gets traded. Publishing only the first
    would understate the core by a factor of four.
    """
    by_name = collections.Counter()
    by_slot = collections.Counter()
    for _ticker, v in votes.items():
        by_name[v] += 1
        by_slot[v] += v
    return {"by_name": dict(by_name), "by_slot": dict(by_slot)}


def run(pattern: str, panel: Path, n_dates: int) -> dict:
    import xgboost as xgb  # noqa: PLC0415
    from renquant_pipeline.kernel.panel_pipeline.feature_transform import (  # noqa: PLC0415,E501
        transform_feature_frame,
    )
    arts = distinct_boosters(pattern)
    if len(arts) < 2:
        return {"status": "too_few_boosters", "n_distinct": len(arts)}
    boosters = {}
    for h, d in arts.items():
        b = xgb.Booster()
        b.load_model(bytearray(d["booster_raw_json"], "utf-8"))
        boosters[h] = (b, d)

    pan = pd.read_parquet(panel)
    pan["date"] = pd.to_datetime(pan["date"])
    dates = sorted(pan["date"].unique())[-n_dates:]
    n = len(boosters)

    name_hist, slot_hist = collections.Counter(), collections.Counter()
    per_date = []
    for dt_ in dates:
        day = pan[pan["date"] == dt_].copy()
        if len(day) < MIN_NAMES:
            per_date.append({"date": str(pd.Timestamp(dt_).date()),
                             "n_names": len(day), "status": "SKIPPED_THIN"})
            continue
        k = max(1, round(TOP_FRACTION * len(day)))
        votes = collections.Counter()
        for h, (mdl, d) in boosters.items():
            X = transform_feature_frame(day, d["feature_cols"], d, source_space="panel")
            s = pd.Series(
                mdl.predict(xgb.DMatrix(X, feature_names=list(d["feature_cols"]))),
                index=day["ticker"].to_numpy())
            for t in s.nlargest(k).index:
                votes[t] += 1
        c = consensus(votes, n)
        for v, cn in c["by_name"].items():
            name_hist[v] += cn
        for v, cn in c["by_slot"].items():
            slot_hist[v] += cn
        per_date.append({
            "date": str(pd.Timestamp(dt_).date()), "n_names": len(day), "k": k,
            "status": "scored",
            "union_size": len(votes),
            "n_unanimous": sum(1 for _t, v in votes.items() if v == n),
            "n_singleton": sum(1 for _t, v in votes.items() if v == 1)})

    scored = [r for r in per_date if r["status"] == "scored"]
    slots = sum(slot_hist.values())
    maj = sum(slot_hist.get(v, 0) for v in range(n // 2 + 1, n + 1))
    return {
        "status": "checked",
        "n_boosters": n,
        "n_dates_scored": len(scored),
        "n_dates_skipped_thin": len(per_date) - len(scored),
        "total_slots": slots,
        "vote_hist_by_name": {str(v): name_hist.get(v, 0) for v in range(1, n + 1)},
        "vote_hist_by_slot": {str(v): slot_hist.get(v, 0) for v in range(1, n + 1)},
        "pct_slots_majority": round(100 * maj / slots, 1) if slots else None,
        "pct_slots_unanimous": (round(100 * slot_hist.get(n, 0) / slots, 1)
                                if slots else None),
        "median_union_over_k": (
            round(float(np.median([r["union_size"] for r in scored]))
                  / float(np.median([r["k"] for r in scored])), 2) if scored else None),
        "per_date": per_date,
        "not_claimed": [
            "that a consensus rule would PERFORM better — no label or forward return is "
            "read anywhere in this file",
            "that agreement means correctness: twelve models sharing a recipe can share "
            "a blind spot, and nothing here separates the two",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact-glob", required=True)
    ap.add_argument("--panel", required=True, type=Path)
    ap.add_argument("--n-dates", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = run(a.artifact_glob, a.panel, a.n_dates)
    except (OSError, ValueError, KeyError, ImportError) as exc:
        print(f"consensus: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if rep["status"] != "checked":
        print(f"only {rep['n_distinct']} distinct booster(s)", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        n = rep["n_boosters"]
        print(f"  {n} boosters over {rep['n_dates_scored']} date(s), "
              f"{rep['total_slots']} top-decile slots")
        print(f"\n  {'votes':>7}{'names':>8}{'% names':>9}{'slots':>8}{'% slots':>9}")
        tot = sum(rep["vote_hist_by_name"].values())
        for v in range(1, n + 1):
            c = rep["vote_hist_by_name"][str(v)]
            s = rep["vote_hist_by_slot"][str(v)]
            print(f"  {v:>3}/{n}{c:>8}{100 * c / tot:>8.1f}%{s:>8}"
                  f"{100 * s / rep['total_slots']:>8.1f}%")
        print(f"\n  slots held by a MAJORITY (>={n // 2 + 1}/{n}): "
              f"{rep['pct_slots_majority']}%")
        print(f"  slots held by UNANIMOUS names      : {rep['pct_slots_unanimous']}%")
        print(f"  union of all arms / k              : {rep['median_union_over_k']}x")
        for s in rep["not_claimed"]:
            print(f"  [not claimed] {s}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
