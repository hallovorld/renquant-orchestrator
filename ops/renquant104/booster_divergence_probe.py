#!/usr/bin/env python3
"""How do same-recipe boosters behave UNDER ONE SPECIFIED SYNTHETIC PROBE? (GOAL-4)

orch#692 established that 30 artifacts share one admission fingerprint while holding
**12 distinct boosters**, and it deliberately stopped there: *"a digest mismatch means
different learned models. It does NOT follow that their predictions differ materially."*
This closes that gap — and it closes it in the direction that makes the gate's blindness
costly rather than cosmetic.

MEASURED 2026-07-31 — 12 boosters, one common synthetic input, N=2000 rows,
seed 20260731:

    spearman vs the served booster : min 0.4814  median 0.5980  max 0.8313
    top-decile overlap             : min 29.0%   median 40.0%

**These are results under this probe, and nothing else.** The input is standard normal in
the post-normalisation feature space: 158 of 172 features are `global_z` upstream and 5
are `robust_z`, but **9 are `identity`** and for those a standard normal is simply the
wrong distribution.

WHAT MAY NOT BE INFERRED FROM THEM `[codex on orch#690/#698]`. An earlier version of this
docstring called the numbers a **bound** on real-panel disagreement, on the grounds that
*"correlated inputs generally push tree models toward agreeing"*. **That direction is not
established here and is not a general property of tree ensembles.** An arbitrary
independent Gaussian input can yield either MORE or LESS agreement than the served feature
distribution — especially with identity-scaled features and nonlinear splits. The claim is
withdrawn, and with it three things it was used to support:

  * that the gate's inability to distinguish these artifacts carries a ~60% cost in
    production;
  * that the measured spread is a bound in either direction;
  * that the staged candidates are "not near-copies" of the incumbent **on real inputs**.

What the numbers do establish is narrower and still worth having: **as functions, these 12
boosters are not the same function.** Fed identical vectors they rank them differently.
Whether that separation survives on the served cross-section is unmeasured.

THE REQUIRED EVIDENCE for any production claim is a real served-panel comparison. That
needs the 172-feature panel rebuilt through the pipeline's feature engineering, which this
read-only probe does not do.

WHAT WOULD REPLACE THIS. Scoring all 12 on a real served panel. That needs the 172-feature
panel rebuilt through the pipeline's feature engineering, which this read-only probe does
not do.

Read-only. Loads artifacts, writes nothing, never invokes git.

Exit codes: ``0`` every pair agrees above `--min-spearman`, ``1`` at least one falls
below (or fewer than two distinct boosters were found), ``2`` usage/IO error — so a probe
that found nothing to compare cannot read as agreement.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys


def load_boosters(root: str, query: str) -> tuple[dict, list[str]]:
    """digest -> (artifact, Booster, feature_cols). One entry per DISTINCT booster.

    Keyed by digest so a corpus with 30 copies of 12 models scores 12 times, not 30 —
    and so an artifact appearing twice cannot weight the summary.
    """
    import xgboost as xgb
    out, skipped = {}, []
    for path in sorted(glob.glob(os.path.join(root, query))):
        try:
            with open(path, "rb") as fh:
                payload = json.loads(fh.read())
        except (OSError, ValueError) as exc:
            skipped.append(f"{os.path.basename(path)}: {type(exc).__name__}")
            continue
        if not isinstance(payload, dict):
            skipped.append(f"{os.path.basename(path)}: root is "
                           f"{type(payload).__name__}")
            continue
        raw = payload.get("booster_raw_json")
        cols = payload.get("feature_cols")
        if not isinstance(raw, str) or not isinstance(cols, list) or not cols:
            skipped.append(f"{os.path.basename(path)}: no booster or feature_cols")
            continue
        try:
            b = xgb.Booster()
            b.load_model(bytearray(raw, "utf-8"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{os.path.basename(path)}: {type(exc).__name__}: {exc}")
            continue
        out.setdefault(hashlib.sha256(raw.encode()).hexdigest()[:12],
                       (os.path.basename(path), b, list(cols)))
    return out, skipped


def probe(boosters: dict, served: str, n_rows: int, seed: int) -> dict:
    import numpy as np
    import xgboost as xgb
    from scipy.stats import spearmanr

    cols = boosters[served][2]
    mismatched = [h for h, (_, _, c) in boosters.items() if c != cols]
    if mismatched:
        # Different feature sets are not comparable on one matrix, and scoring them
        # anyway would silently compare different functions of different inputs.
        return {"status": "feature_set_mismatch", "mismatched": mismatched}

    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_rows, len(cols)))
    dm = xgb.DMatrix(X, feature_names=cols)
    scores = {h: boosters[h][1].predict(dm) for h in boosters}

    k = max(1, n_rows // 10)
    top_served = set(np.argsort(-scores[served])[:k])
    rows = []
    for h in boosters:
        rows.append({
            "booster": h,
            "artifact": boosters[h][0],
            "spearman_vs_served": float(
                spearmanr(scores[served], scores[h]).statistic),
            "top_decile_overlap": len(
                top_served & set(np.argsort(-scores[h])[:k])) / k,
            "is_served": h == served,
        })
    others = [r for r in rows if not r["is_served"]]
    return {
        "status": "probed",
        "n_distinct_boosters": len(boosters),
        "n_rows": n_rows, "seed": seed, "n_features": len(cols),
        "served_booster": served,
        "served_artifact": boosters[served][0],
        "rows": sorted(rows, key=lambda r: -r["spearman_vs_served"]),
        "spearman_min": min(r["spearman_vs_served"] for r in others) if others else None,
        "spearman_median": float(np.median(
            [r["spearman_vs_served"] for r in others])) if others else None,
        "top_decile_overlap_min": min(
            r["top_decile_overlap"] for r in others) if others else None,
        "top_decile_overlap_median": float(np.median(
            [r["top_decile_overlap"] for r in others])) if others else None,
        "scope_note": (
            "RESULTS UNDER THIS SYNTHETIC PROBE ONLY. The input is standard normal in "
            "the post-normalisation feature space; 9 of 172 features are `identity` and "
            "for those it is the wrong distribution. NO production inference follows: "
            "not a cost, not a bound, and not a claim about real-panel agreement. An "
            "independent Gaussian can yield MORE or LESS agreement than the served "
            "distribution -- the direction is not established and is not a general "
            "property of tree ensembles. What this establishes is that these boosters "
            "are not the same FUNCTION. Whether that separation survives on the served "
            "cross-section requires a real-panel comparison, which this does not do."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--query", default="*.json")
    ap.add_argument("--served-artifact", required=True,
                    help="basename of the SERVED artifact — named, never guessed")
    ap.add_argument("--rows", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260731)
    ap.add_argument("--min-spearman", type=float, default=0.99)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        boosters, skipped = load_boosters(a.root, a.query)
    except ImportError as exc:
        print(f"divergence probe: {exc}", file=sys.stderr)
        return 2
    if len(boosters) < 2:
        print(f"divergence probe: {len(boosters)} distinct booster(s) under "
              f"{a.root}/{a.query} — nothing to compare, which is not the same as "
              f"agreement", file=sys.stderr)
        return 1

    served = next((h for h, v in boosters.items() if v[0] == a.served_artifact), None)
    if served is None:
        print(f"divergence probe: served artifact {a.served_artifact!r} not among the "
              f"loaded boosters — it must be named, never guessed", file=sys.stderr)
        return 2

    rep = probe(boosters, served, a.rows, a.seed)
    rep["skipped"] = skipped
    if rep["status"] != "probed":
        print(f"divergence probe: {rep['status']}: {rep.get('mismatched')}",
              file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"{rep['n_distinct_boosters']} distinct booster(s), "
              f"{rep['n_rows']} synthetic rows, {rep['n_features']} features, "
              f"seed {rep['seed']}")
        print(f"served: {rep['served_booster']} ({rep['served_artifact']})\n")
        print(f"{'booster':14s} {'artifact':46s} {'spearman':>9s} {'top10%':>8s}")
        for r in rep["rows"]:
            print(f"{r['booster']:14s} {r['artifact'][:46]:46s} "
                  f"{r['spearman_vs_served']:9.4f} {r['top_decile_overlap']:8.1%}")
        print(f"\nvs served — spearman: min {rep['spearman_min']:.4f} "
              f"median {rep['spearman_median']:.4f}")
        print(f"            top decile overlap: min {rep['top_decile_overlap_min']:.1%} "
              f"median {rep['top_decile_overlap_median']:.1%}")
        for s in skipped:
            print(f"  SKIPPED {s}")
        print("\n" + rep["scope_note"])

    return 0 if (rep["spearman_min"] is not None
                 and rep["spearman_min"] >= a.min_spearman) else 1


if __name__ == "__main__":
    raise SystemExit(main())
