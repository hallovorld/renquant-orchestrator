#!/usr/bin/env python3
"""Same-recipe boosters, scored on the REAL panel: 35.7% of the top decile disagrees.

orch#698 measured that boosters sharing one recipe fingerprint are not the same function.
It did so on a **synthetic probe**, and said in its own title that it licensed no
production inference. This is the production measurement it deferred, and it **corrects
#698's headline number**.

MEASURED 2026-08-01 — 12 distinct boosters (one config fingerprint `sha256:f8fb2259b`,
172 features each, `eval_ic` 0.0454–0.0743) scored on the live
`alpha158_291_fundamental_dataset` panel over its last 20 sessions (2026-04-07 … 2026-05-04,
144–153 names/date):

=================================================  ==============
per-date median pairwise Spearman                   0.854
per-date median top-decile OVERLAP                  0.643
**median top-decile DISAGREEMENT**                  **35.7%**
worst pair on the worst date                        **67% replaced**
=================================================  ==============

**#698's synthetic probe reported ~60% disagreement. On real data the median is 35.7%** —
the synthetic figure overstated the typical case by ~1.7×, though the real *range* reaches
it: the worst pair on 2026-04-13 replaced 67% of the top decile. The synthetic headline is
withdrawn as a description of production; the direction it claimed survives, the magnitude
does not.

WHY THIS MATTERS AND WHERE IT POINTS. `renquant-pipeline`#244 measured that **53 of 53**
stamped artifacts carry `candidate_artifact_used=false` — every "WF gate passed" is a
statement about the recipe, and 51 of 53 share one fingerprint. Put together: **the gate
that admits capital cannot distinguish models that replace a third of the traded top
decile, and up to two thirds in the tail.** That is the ensemble premise's real problem —
not that members are too similar to be worth blending, but that nothing validates which
member is serving.

ASSUMPTIONS, STATED. `transform_feature_frame` is **imported** from
`renquant_pipeline.kernel.panel_pipeline.feature_transform`, never restated. It is called
with ``source_space="panel"`` because the input is the prebuilt alpha158 panel; the
artifact's own ``feature_source_contract`` field is a **documentation dict**, not a
selector, so this is MY choice and not a value read off the artifact `[假设]`. Scoring the
live path instead would use ``"raw"`` and could give different numbers.

WHAT IS NOT CLAIMED. That any booster is better than another — no label is touched here
and no forward return is computed. That 35.7% is a stable long-run figure: this is 20
consecutive sessions at the panel's frontier, not a history. That blending them would
help; disagreement is a precondition for an ensemble to be worth anything, not evidence
that one works.

Read-only. Loads artifacts and the panel, writes only under ``--out``.

Exit codes: ``0`` scored, ``1`` fewer than two distinct boosters (nothing to compare),
``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOP_FRACTION = 0.10
MIN_NAMES = 50


def distinct_boosters(artifact_glob: str) -> dict[str, dict]:
    """One artifact per distinct booster, keyed by the booster bytes' digest.

    Keyed on `booster_raw_json`, which is the FUNCTION. Keying on the config fingerprint
    would collapse all 12 into one — that collapse is the defect being measured, so it
    must not also be the method.
    """
    seen: dict[str, dict] = {}
    for p in sorted(glob.glob(artifact_glob)):
        try:
            d = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        b = d.get("booster_raw_json")
        if not isinstance(b, str) or not b:
            continue
        d["_artifact"] = Path(p).name
        seen.setdefault(hashlib.sha256(b.encode()).hexdigest()[:12], d)
    return seen


def score_day(day: pd.DataFrame, boosters: dict) -> dict[str, pd.Series]:
    import xgboost as xgb  # noqa: PLC0415
    from renquant_pipeline.kernel.panel_pipeline.feature_transform import (  # noqa: PLC0415,E501
        transform_feature_frame,
    )
    out = {}
    for h, (bst, d) in boosters.items():
        X = transform_feature_frame(day, d["feature_cols"], d, source_space="panel")
        s = bst.predict(xgb.DMatrix(X, feature_names=list(d["feature_cols"])))
        out[h] = pd.Series(s, index=day["ticker"].to_numpy())
    return out


def pair_stats(scores: dict[str, pd.Series], k: int) -> dict:
    hs = sorted(scores)
    sp, ov = [], []
    for a, b in itertools.combinations(hs, 2):
        sp.append(float(np.corrcoef(scores[a].rank(), scores[b].rank())[0, 1]))
        ta = set(scores[a].nlargest(k).index)
        tb = set(scores[b].nlargest(k).index)
        # Overlap as a FRACTION OF k, not Jaccard: the operational question is "how much
        # of the traded top decile changes", and Jaccard's union denominator answers a
        # different one.
        ov.append(len(ta & tb) / k)
    return {"n_pairs": len(sp),
            "spearman_median": float(np.median(sp)) if sp else None,
            "overlap_median": float(np.median(ov)) if ov else None,
            "overlap_min": float(np.min(ov)) if ov else None}


def run(artifact_glob: str, panel_path: Path, n_dates: int) -> dict:
    import xgboost as xgb  # noqa: PLC0415
    arts = distinct_boosters(artifact_glob)
    if len(arts) < 2:
        return {"status": "too_few_boosters", "n_distinct": len(arts)}
    boosters = {}
    for h, d in arts.items():
        b = xgb.Booster()
        b.load_model(bytearray(d["booster_raw_json"], "utf-8"))
        boosters[h] = (b, d)

    pan = pd.read_parquet(panel_path)
    pan["date"] = pd.to_datetime(pan["date"])
    dates = sorted(pan["date"].unique())[-n_dates:]

    rows = []
    for dt_ in dates:
        day = pan[pan["date"] == dt_].copy()
        if len(day) < MIN_NAMES:
            # Recorded, never dropped silently: a thin date excluded without a trace
            # would make the remaining ones look more representative than they are.
            rows.append({"date": str(pd.Timestamp(dt_).date()), "n_names": len(day),
                         "status": "SKIPPED_THIN"})
            continue
        k = max(1, round(TOP_FRACTION * len(day)))
        st = pair_stats(score_day(day, boosters), k)
        rows.append({"date": str(pd.Timestamp(dt_).date()), "n_names": len(day),
                     "k": k, "status": "scored", **st})

    scored = [r for r in rows if r["status"] == "scored"]
    med_ov = np.median([r["overlap_median"] for r in scored]) if scored else None
    return {
        "status": "checked",
        "n_distinct_boosters": len(arts),
        "boosters": {h: {"artifact": d["_artifact"], "trained_date": d.get("trained_date"),
                         "eval_ic": d.get("eval_ic"),
                         "config_fingerprint": d.get("config_fingerprint"),
                         "n_features": len(d.get("feature_cols") or [])}
                     for h, d in arts.items()},
        "n_dates_scored": len(scored),
        "n_dates_skipped_thin": sum(1 for r in rows if r["status"] == "SKIPPED_THIN"),
        "per_date": rows,
        "median_top_decile_overlap": float(med_ov) if med_ov is not None else None,
        "median_top_decile_disagreement": (float(1 - med_ov)
                                           if med_ov is not None else None),
        "worst_pair_overlap": (float(min(r["overlap_min"] for r in scored))
                               if scored else None),
        "assumptions": [
            "source_space='panel' is MY choice: the artifact's `feature_source_contract` "
            "is a documentation dict, not a selector. The live path would use 'raw'.",
            "`transform_feature_frame` is imported from renquant-pipeline, never restated.",
        ],
        "not_claimed": [
            "that any booster is better — no label or forward return is touched",
            "that this is a stable long-run figure — it is consecutive sessions at the "
            "panel frontier, not a history",
            "that blending helps — disagreement is a precondition, not evidence",
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
        print(f"divergence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if rep["status"] != "checked":
        print(f"only {rep['n_distinct']} distinct booster(s) — nothing to compare",
              file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True, default=str))
    else:
        print(f"  {rep['n_distinct_boosters']} distinct boosters over "
              f"{rep['n_dates_scored']} scored date(s) "
              f"({rep['n_dates_skipped_thin']} skipped thin)")
        print(f"  {'date':<12}{'n':>5}{'k':>4}{'spearman':>10}{'ovlp_med':>10}{'ovlp_min':>10}")
        for r in rep["per_date"]:
            if r["status"] != "scored":
                print(f"  {r['date']:<12}{r['n_names']:>5}{'':>4}  {r['status']}")
                continue
            print(f"  {r['date']:<12}{r['n_names']:>5}{r['k']:>4}"
                  f"{r['spearman_median']:>10.4f}{r['overlap_median']:>10.3f}"
                  f"{r['overlap_min']:>10.3f}")
        print(f"\n  median top-decile DISAGREEMENT: "
              f"{rep['median_top_decile_disagreement']:.1%}")
        print(f"  worst pair on any date replaced "
              f"{1 - rep['worst_pair_overlap']:.0%} of the top decile")
        for s in rep["assumptions"]:
            print(f"  [assumption] {s}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
