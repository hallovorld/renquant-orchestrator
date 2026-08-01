#!/usr/bin/env python3
"""Which model lanes have walk-forward evidence, and which have none? (GOAL-6)

WHY THIS EXISTS. A goal anchor said the certified clf recipe had no out-of-sample
corpus. I reported that anchor stale, citing 43 folds / 178,191 rows — numbers that are
real but belong to `walkforward_gbdt_prod_recipe_v2`, the GBDT production recipe, not to
clf. I measured one lane and retired an anchor about another, removing a TRUE premise
from the work queue.

A number that names no lane invites exactly that. So this reports coverage **per lane
directory**, always with the directory name attached, and it refuses to aggregate across
lanes into a single reassuring total.

WHAT A FOLD COUNT IS AND IS NOT. It counts dated fold directories present on disk. It
does not open them, does not check that a fold contains a usable artifact, and says
nothing about leakage or quality. "43 folds exist" is a statement about directories.

Read-only: lists directories, opens nothing, never invokes git.

Exit codes: ``0`` every declared lane has at least `--min-folds`, ``1`` at least one lane
is below it or missing entirely, ``2`` usage/IO error — so a broken invocation cannot be
mistaken for full coverage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fold_dirs(root: str) -> list[str]:
    """Dated fold directory names directly under `root`, sorted.

    A missing root yields [] and the CALLER reports it as missing — returning [] for
    both "no folds" and "no directory" would let a vanished corpus read as an empty one.
    """
    if not os.path.isdir(root):
        return []
    return sorted(n for n in os.listdir(root)
                  if DATED.match(n) and os.path.isdir(os.path.join(root, n)))


def survey(artifacts_root: str, lanes: list[str]) -> dict:
    rows = []
    for lane in lanes:
        path = os.path.join(artifacts_root, lane)
        exists = os.path.isdir(path)
        folds = fold_dirs(path)
        rows.append({
            "lane": lane,
            "corpus_dir_exists": exists,
            "n_folds": len(folds),
            "first_fold": folds[0] if folds else None,
            "last_fold": folds[-1] if folds else None,
        })
    return {
        "artifacts_root": os.path.basename(os.path.normpath(artifacts_root)),
        "lanes": rows,
        "scope_note": (
            "Counts dated fold DIRECTORIES. It does not open them, does not verify a "
            "fold holds a usable artifact, and says nothing about leakage or quality. "
            "Reported per lane and never summed: a total across lanes is what let one "
            "lane's 43 folds stand in for another lane's zero."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts-root", required=True)
    ap.add_argument("--lanes", nargs="+", required=True,
                    help="walk-forward corpus directory names, one per lane")
    ap.add_argument("--min-folds", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = survey(a.artifacts_root, list(a.lanes))
    except OSError as exc:
        print(f"wf-corpus coverage: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for r in rep["lanes"]:
            if not r["corpus_dir_exists"]:
                print(f"MISSING   {r['lane']}: no corpus directory — this lane has no "
                      f"walk-forward evidence of its own")
            elif r["n_folds"] < a.min_folds:
                print(f"THIN      {r['lane']}: {r['n_folds']} fold(s) "
                      f"({r['first_fold']}..{r['last_fold']}), below --min-folds "
                      f"{a.min_folds}")
            else:
                print(f"COVERED   {r['lane']}: {r['n_folds']} folds "
                      f"({r['first_fold']}..{r['last_fold']})")
        print("\n" + rep["scope_note"])

    short = [r for r in rep["lanes"]
             if not r["corpus_dir_exists"] or r["n_folds"] < a.min_folds]
    return 1 if short else 0


if __name__ == "__main__":
    raise SystemExit(main())
