#!/usr/bin/env python3
"""The gate's recipe projection is invariant across the 12 boosters BY CONSTRUCTION.

And the fields that do vary include per-artifact out-of-sample IC the gate never reads.

MEASURED 2026-08-01 over the 30 stamped `panel-ltr.alpha158_fund*` artifacts, deduplicated
to **12 distinct boosters** by `booster_raw_json` digest:

=================================  ====
artifact fields present              40
  CONSTANT across all 12              23
  VARYING across the 12               17
=================================  ====

`run_wf_gate._recipe_projection` hashes six fields — `kind`, `feature_cols`,
`feature_norm_kind`, `label_col`, `lookahead_days`, `params` (plus structural
`feature_source_contract_keys`). **Every one of them is in the CONSTANT set.** So the
recipe fingerprint `sha256:cfdd6cb8e950da0f` is identical across all 12 not by accident but
by design, and a check built on it cannot distinguish them however many times it runs.

A FALSE FINDING THIS TOOL EXISTS TO PREVENT. The artifact's own `config_fingerprint`
(`sha256:f8fb2259b…`) never equals the stamp's `candidate_recipe_fingerprint`
(`sha256:cfdd6cb8e…`) on any of the 30. That is **not** a defect: the first hashes the
config (its `config_fingerprint_fields` carries the watchlist), the second hashes the model
recipe. Two names containing "fingerprint" are not one object, and comparing them would
publish a mismatch that is correct behaviour.

WHAT THE VARYING FIELDS CONTAIN — the part that matters. Among the 17: `oos_mean_ic`,
`oos_per_fold_ic` and `oos_std_ic`, each with **12 distinct values**. Every booster carries
its OWN out-of-sample evidence, and the admission path reads none of it.

AND WHY "JUST READ IT" IS THE WRONG FIX. That evidence is **3 folds** per artifact with
`oos_std_ic` between 0.0378 and 0.0484. Best minus worst is
``0.05676 - 0.04246 = 0.0143`` — between **0.51 and 0.66 standard errors** at n=3. The
recorded per-artifact evidence exists, is ignored, **and cannot rank these boosters
anyway**. A gate rewired to promote on `oos_mean_ic` would be ranking on noise, which is
worse than a gate that admits it is looking at the recipe.

Read-only. Opens artifacts, writes only under ``--out``.

Exit codes: ``0`` at least one projection field varies (the gate discriminates), ``1``
every projection field is constant while other fields vary (the blind spot), ``2``
usage/IO error, ``3`` SKIPPED — fewer than two distinct boosters, nothing to compare.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import sys
from pathlib import Path

#: The fields `run_wf_gate._recipe_projection` hashes, read from that function at
#: RenQuant/scripts/run_wf_gate.py:714 on 2026-08-01 — cited, not asserted.
#: `feature_source_contract_keys` is derived there rather than being an artifact field,
#: so it is named separately and not looked up.
PROJECTION_FIELDS = ("kind", "feature_cols", "feature_norm_kind", "label_col",
                     "lookahead_days", "params")
DERIVED_PROJECTION_FIELDS = ("feature_source_contract_keys",)

#: Per-artifact evidence that exists and that the projection excludes.
EVIDENCE_FIELDS = ("oos_mean_ic", "oos_per_fold_ic", "oos_std_ic", "eval_ic")


def _h(v: object) -> str:
    return hashlib.sha256(
        json.dumps(v, sort_keys=True, default=str).encode()).hexdigest()[:12]


def distinct_boosters(pattern: str) -> dict[str, dict]:
    """Keyed on the booster BYTES. Keying on any fingerprint would collapse all 12 into
    one — and that collapse is the thing being measured, so it must not be the method."""
    out: dict[str, dict] = {}
    for p in sorted(glob.glob(pattern)):
        try:
            d = json.loads(Path(p).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        b = d.get("booster_raw_json")
        if isinstance(b, str) and b:
            out.setdefault(hashlib.sha256(b.encode()).hexdigest()[:12], d)
    return out


def analyse(arts: dict[str, dict]) -> dict:
    keys: set[str] = set()
    for d in arts.values():
        keys |= set(d)
    varying, constant = [], []
    for k in sorted(keys):
        n = len({_h(d.get(k)) for d in arts.values()})
        (varying if n > 1 else constant).append({"field": k, "n_distinct": n})
    varying_names = {r["field"] for r in varying}

    proj = [{"field": f, "varies": f in varying_names} for f in PROJECTION_FIELDS]

    ev = {}
    for f in EVIDENCE_FIELDS:
        vals = [d.get(f) for d in arts.values()]
        nums = [v for v in vals if isinstance(v, (int, float))]
        ev[f] = {"n_distinct": len({_h(v) for v in vals}),
                 "min": min(nums) if nums else None,
                 "max": max(nums) if nums else None,
                 "in_projection": f in PROJECTION_FIELDS}

    # Is the recorded OOS evidence decisive? Reported as a ratio to its own standard
    # error, never as "the best one wins".
    decisive = None
    m = ev.get("oos_mean_ic") or {}
    sds = [d.get("oos_std_ic") for d in arts.values()
           if isinstance(d.get("oos_std_ic"), (int, float))]
    folds = {len(d["oos_per_fold_ic"]) for d in arts.values()
             if isinstance(d.get("oos_per_fold_ic"), list)}
    if m.get("min") is not None and sds and len(folds) == 1:
        n_folds = folds.pop()
        gap = m["max"] - m["min"]
        ses = sorted(s / math.sqrt(n_folds) for s in sds)
        decisive = {
            "n_folds_per_artifact": n_folds,
            "best_minus_worst_oos_mean_ic": gap,
            "oos_std_ic_min": min(sds), "oos_std_ic_max": max(sds),
            "gap_over_se_min": gap / ses[-1], "gap_over_se_max": gap / ses[0],
            "note": ("The per-artifact evidence exists, is ignored by the projection, "
                     "AND cannot rank these boosters: the best-worst gap is under one "
                     "standard error at this fold count. Rewiring the gate to promote "
                     "on oos_mean_ic would rank on noise."),
        }

    return {
        "n_distinct_boosters": len(arts),
        "n_fields": len(keys),
        "n_constant": len(constant),
        "n_varying": len(varying),
        "varying_fields": varying,
        "projection_fields": proj,
        "projection_fields_all_constant": not any(p["varies"] for p in proj),
        "derived_projection_fields_not_checked": list(DERIVED_PROJECTION_FIELDS),
        "evidence_fields": ev,
        "decisiveness": decisive,
        "not_a_finding": (
            "The artifact's `config_fingerprint` never equals the stamp's "
            "`candidate_recipe_fingerprint`. That is CORRECT: the first hashes the "
            "config (its `config_fingerprint_fields` carries the watchlist), the second "
            "hashes the model recipe. Two names containing 'fingerprint' are not one "
            "object."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact-glob", required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        arts = distinct_boosters(a.artifact_glob)
    except OSError as exc:
        print(f"projection-blindspot: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if len(arts) < 2:
        print(f"SKIPPED: {len(arts)} distinct booster(s) — nothing to compare.",
              file=sys.stderr)
        return 3

    rep = analyse(arts)
    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True, default=str))
    else:
        print(f"  {rep['n_distinct_boosters']} distinct boosters, {rep['n_fields']} "
              f"artifact fields: {rep['n_constant']} constant, {rep['n_varying']} varying")
        print("\n  the gate's recipe projection:")
        for p in rep["projection_fields"]:
            print(f"    {p['field']:<24}{'*** VARIES ***' if p['varies'] else 'CONSTANT'}")
        print("\n  per-artifact evidence the projection excludes:")
        for f, e in rep["evidence_fields"].items():
            rng = (f"{e['min']:.5f}..{e['max']:.5f}" if e["min"] is not None else "-")
            print(f"    {f:<20}{e['n_distinct']:>3} distinct  {rng:>20}"
                  f"  in_projection={e['in_projection']}")
        d = rep["decisiveness"]
        if d:
            print(f"\n  decisiveness of that evidence: best-worst "
                  f"{d['best_minus_worst_oos_mean_ic']:.5f} = "
                  f"{d['gap_over_se_min']:.2f}–{d['gap_over_se_max']:.2f} SE "
                  f"at {d['n_folds_per_artifact']} folds")
            print(f"    {d['note']}")
        print(f"\n  [not a finding] {rep['not_a_finding']}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rep, indent=2, sort_keys=True, default=str) + "\n")
        print(f"\nwrote {a.out}")

    return 1 if rep["projection_fields_all_constant"] and rep["n_varying"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
