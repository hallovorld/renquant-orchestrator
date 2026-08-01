#!/usr/bin/env python3
"""How independent are the WF gate's economic cuts? (GOAL-6, evaluation path)

The gate's economic arm reports counts — `n_positive_cuts`, `n_cuts_beat_spy_apy` — over
a set of walk-forward windows. A count is only as strong as the independence of the things
counted, and nothing in the repo measured that.

MEASURED 2026-07-31 on `prod/panel-ltr.alpha158_fund.previous.json`:

    cuts               : 3 windows of ~364 d
    sum of lengths     : 1089 d
    calendar covered   : 816 d
    REDUNDANCY         : 1.33x            (1.00 = disjoint)
    overlap cut1<->cut2: 183 d = 50% of the shorter window
    overlap cut2<->cut3:  90 d = 25%

So `n_positive_cuts: 3` is **three correlated observations**, not three independent ones —
and "absolute returns positive (3/3 cuts)" is the reason recorded in the 2026-07-05
operator override that admitted this artifact.

A HYPOTHESIS THIS REFUTED. Going in, the expectation was that the economic arm leaves
calendar on the table — 43 manifest folds, only a few evaluated. It does not: the
evaluated union covers **816 of the corpus's 882 days (92.5%)**, leaving 66 days. The
problem is not unused time, it is **reused** time.

THE STRUCTURAL CEILING, which is the part that matters. At the current ~364-day window,
882 days of corpus admits **at most 2 disjoint windows**. So the economic arm cannot
report more than n=2 independent observations without shortening the window:

    364 d window -> at most 2 disjoint
    252 d window -> at most 3
    182 d window -> at most 4

That is a design constraint on the gate, not a bug in it, and it is what any "N of N cuts"
threshold has to be calibrated against.

WHAT THIS DOES NOT DO. It does not re-score anything, does not compute an effective
sample size under an assumed correlation, and does not propose a threshold. Redundancy and
pairwise overlap are geometry — they are exactly derivable from the window boundaries and
carry no assumption. Turning geometry into an effective-n requires a correlation this tool
does not measure, and this programme has a standing correction about doing that from an
assumed rho.

Read-only. Opens artifacts, writes nothing, never invokes git.

Exit codes: ``0`` the cuts are disjoint, ``1`` they overlap or the artifact carries no
usable cut set, ``2`` usage/IO error — so a broken invocation cannot read as independence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import hashlib
import json
import os
import subprocess
import sys


def _gate_block(payload: dict) -> tuple[dict | None, str]:
    """Canonical first, legacy recorded. Reading one location silently is how two
    claims got retracted this week."""
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        return None, "malformed metadata container"
    md = (meta or {}).get("wf_gate_metadata")
    if isinstance(md, dict) and md:
        return md, "metadata.wf_gate_metadata"
    md = payload.get("wf_gate_metadata")
    if isinstance(md, dict) and md:
        return md, "wf_gate_metadata (legacy top-level)"
    return None, ""


def _cuts(block: dict) -> tuple[list[tuple[dt.date, dt.date]], list[str]]:
    """Parsed (start, end) pairs, plus a reason for each one that could not be read.

    A cut that fails to parse is REPORTED, never dropped: silently shrinking the cut set
    would make the remaining ones look more independent than they are, which is the exact
    quantity under measurement.
    """
    raw = block.get("cuts")
    if not isinstance(raw, list):
        return [], [f"`cuts` is {type(raw).__name__}, not a list"]
    out, bad = [], []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            bad.append(f"cut {i} is {type(c).__name__}, not an object")
            continue
        try:
            s = dt.date.fromisoformat(str(c["start"])[:10])
            e = dt.date.fromisoformat(str(c["end"])[:10])
        except (KeyError, ValueError) as exc:
            bad.append(f"cut {i}: {type(exc).__name__}: {exc}")
            continue
        if e <= s:
            bad.append(f"cut {i}: end {e} is not after start {s}")
            continue
        out.append((s, e))
    return out, bad


def analyse(cuts: list[tuple[dt.date, dt.date]]) -> dict:
    if not cuts:
        return {"n_cuts": 0}
    lengths = [(e - s).days for s, e in cuts]
    lo, hi = min(s for s, _ in cuts), max(e for _, e in cuts)
    outer_span = (hi - lo).days
    # TRUE UNION, by merging overlapping intervals `[codex on orch#696]`. The first
    # version used the OUTER SPAN (earliest start to latest end), which counts a GAP
    # between two disjoint cuts as covered -- so redundancy fell BELOW 1 for genuinely
    # disjoint windows and the documented invariant "1.00 means disjoint" was false.
    merged: list[list] = []
    for s, e in sorted(cuts):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    union = sum((e - s).days for s, e in merged)
    pairs = []
    for (s1, e1), (s2, e2) in itertools.combinations(cuts, 2):
        ov = (min(e1, e2) - max(s1, s2)).days
        if ov > 0:
            pairs.append({
                "a": f"{s1}..{e1}", "b": f"{s2}..{e2}", "overlap_days": ov,
                "frac_of_shorter": round(
                    ov / min((e1 - s1).days, (e2 - s2).days), 4)})
    return {
        "n_cuts": len(cuts),
        "cut_lengths_days": lengths,
        "sum_of_lengths_days": sum(lengths),
        "calendar_union_days": union,
        # The outer span is retained separately: it is what a reader means by "the cuts
        # run from X to Y", and conflating it with the union is the defect above.
        "outer_span_days": outer_span,
        "n_merged_intervals": len(merged),
        "union_start": lo.isoformat(), "union_end": hi.isoformat(),
        # Exactly 1.00 iff the cuts are disjoint: sum of lengths over the TRUE union.
        # Above 1.00, the same calendar is counted more than once. It can never fall
        # below 1.00 now -- that was the outer-span bug.
        "redundancy": round(sum(lengths) / union, 4) if union else None,
        "overlapping_pairs": pairs,
        "disjoint": not pairs,
    }


def ceiling(corpus_days: int, window_days: int) -> int:
    """How many DISJOINT windows of this length fit in the corpus at all."""
    return corpus_days // window_days if window_days > 0 else 0


def corpus_span(manifest_path: str) -> dict:
    """The corpus span, DERIVED from the walk-forward manifest rather than asserted.

    The published "882 days" was a number in prose. Reviewed `[codex on orch#696]`: an
    experiment-facing conclusion needs the source bound to a fingerprint and the
    derivation recorded, or the reader cannot audit it. So this returns the manifest's
    digest, its row key, the fold count and the first/last cutoff — and the span is the
    subtraction, shown.
    """
    if not manifest_path or not os.path.exists(manifest_path):
        return {"status": "manifest_missing", "manifest_path": manifest_path}
    try:
        with open(manifest_path, "rb") as fh:
            raw = fh.read()
        man = json.loads(raw)
    except (OSError, ValueError) as exc:
        return {"status": "manifest_unreadable",
                "why": f"{type(exc).__name__}: {exc}"}
    if not isinstance(man, dict):
        return {"status": "manifest_unreadable",
                "why": f"top-level JSON is {type(man).__name__}"}
    best, key = [], ""
    for k, rows in man.items():
        if not isinstance(rows, list):
            continue
        ds = [r.get("cutoff_date") for r in rows
              if isinstance(r, dict) and isinstance(r.get("cutoff_date"), str)]
        if len(ds) > len(best):
            best, key = ds, k
    if not best:
        return {"status": "no_cutoff_rows",
                "why": "no list of rows carrying `cutoff_date` was found — this is NOT "
                       "a zero-fold corpus, it is an unparsed manifest"}
    # A structurally bad upstream manifest must be a CONTROLLED non-passing result,
    # not an uncaught ValueError three frames from the file that caused it. Reviewed
    # `[codex on #696]`: the comprehension below used to raise straight out of a
    # comprehension, so a malformed `cutoff_date` looked like this tool crashing
    # rather than like the manifest being unreadable -- and a crash and a refusal are
    # only distinguishable if one of them says which input was wrong.
    parsed, bad = [], []
    for d in best:
        try:
            parsed.append(dt.date.fromisoformat(d[:10]))
        except ValueError:
            bad.append(d)
    if bad:
        return {"status": "manifest_unreadable",
                "manifest_path": os.path.basename(manifest_path),
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "rows_key": key,
                "why": f"{len(bad)} of {len(best)} cutoff_date value(s) are not ISO "
                       f"dates; first offender: {bad[0]!r}"}
    ds = sorted(parsed)
    return {
        "status": "derived",
        "manifest_path": os.path.basename(manifest_path),
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "rows_key": key,
        "n_folds": len(ds),
        "first_cutoff": ds[0].isoformat(),
        "last_cutoff": ds[-1].isoformat(),
        "corpus_days": (ds[-1] - ds[0]).days,
        "derivation": "corpus_days = last_cutoff - first_cutoff over the manifest's "
                      "cutoff_date rows",
    }


def _repo_provenance(path: str) -> dict:
    """Which repository, at which ref, and where inside it — for a file on this disk.

    Reviewed `[codex on #696]`: *"evidence.json has only basenames and hashes. It does
    not identify the producing repository/ref, repository-relative source paths, or
    producer/run/artifact identity, so a reader cannot locate or interpret the hashed
    inputs outside this workstation layout."* Exactly right: a basename plus a digest
    lets a reader VERIFY a file they already have and does nothing to help them FIND it.

    Everything here is derived from the file's own checkout — the remote URL, HEAD, and
    the path relative to the repo root — never from this tool's assumptions about where
    repos live. A file outside any git checkout gets `in_git: false` rather than a
    guess, because a fabricated repo-relative path is worse than none.
    """
    out = {"basename": os.path.basename(path), "in_git": False}
    d = os.path.dirname(os.path.abspath(path))
    try:
        root = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, timeout=10)
        if root.returncode != 0:
            return out
        top = root.stdout.strip()
        head = subprocess.run(["git", "-C", top, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        url = subprocess.run(["git", "-C", top, "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", top, "status", "--porcelain", "--", path],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        out.update({
            "in_git": True,
            "repo": os.path.basename(top),
            "repo_remote": url or None,
            "repo_head": head or None,
            "repo_relative_path": os.path.relpath(os.path.abspath(path), top),
            "tracked_and_clean": dirty == "",
        })
    except (OSError, subprocess.SubprocessError):
        return out
    return out


def _producer_identity(payload: dict, block: dict) -> dict:
    """Producer / run / artifact identity, taken from the artifact's OWN metadata.

    Read rather than reconstructed: every field here is a key the producer wrote. A
    field the artifact does not carry is reported as `None`, never inferred — the point
    is to let a reader interpret the hashed input, and an invented producer id would
    defeat that more thoroughly than an absent one.
    """
    return {
        "train_run_id": payload.get("train_run_id"),
        "trained_date": payload.get("trained_date"),
        "kind": payload.get("kind"),
        "side_label": payload.get("side_label"),
        "label_col": payload.get("label_col"),
        "gate_run_at": block.get("run_at"),
        "gate_eval_scope": block.get("wf_eval_scope"),
        "gate_sanity_manifest_path": block.get("sanity_manifest_path"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--corpus-days", type=int,
                    help="span of the available corpus, to report the disjoint ceiling. "
                         "Prefer --manifest, which DERIVES it and records the source")
    ap.add_argument("--manifest", default=None,
                    help="walk-forward manifest; the corpus span is derived from its "
                         "cutoff_date rows and the manifest is fingerprinted")
    ap.add_argument("--evidence-out", default=None,
                    help="write the evidence manifest (artifact + manifest digests, "
                         "cuts, derivation) here")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not os.path.exists(a.artifact):
        print(f"cut independence: {a.artifact} does not exist", file=sys.stderr)
        return 2
    try:
        with open(a.artifact, "rb") as fh:
            payload = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        print(f"cut independence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print(f"cut independence: top-level JSON is {type(payload).__name__}",
              file=sys.stderr)
        return 2

    block, source = _gate_block(payload)
    if block is None:
        print(f"cut independence: {os.path.basename(a.artifact)} carries no gate block "
              f"— no cut set to measure, which is not the same as independent cuts",
              file=sys.stderr)
        return 1

    cuts, bad = _cuts(block)
    with open(a.artifact, "rb") as fh:
        artifact_sha = hashlib.sha256(fh.read()).hexdigest()
    rep = {"artifact": os.path.basename(a.artifact),
           "artifact_sha256": artifact_sha,
           "artifact_provenance": _repo_provenance(a.artifact),
           "producer": _producer_identity(payload, block),
           "gate_stamp_source": source,
           "unreadable_cuts": bad, **analyse(cuts)}
    if a.manifest:
        rep["corpus"] = corpus_span(a.manifest)
        rep["corpus_provenance"] = _repo_provenance(a.manifest)
        if rep["corpus"].get("status") == "derived" and not a.corpus_days:
            a.corpus_days = rep["corpus"]["corpus_days"]
    if a.corpus_days and cuts:
        w = max(rep["cut_lengths_days"])
        rep["corpus_days"] = a.corpus_days
        rep["max_disjoint_windows_at_current_length"] = ceiling(a.corpus_days, w)
    rep["scope_note"] = (
        "Redundancy and overlap are GEOMETRY, derived from the window boundaries with no "
        "assumption. They are not an effective sample size: converting geometry into an "
        "effective n needs a correlation this tool does not measure, and doing that from "
        "an assumed value is a standing correction in this programme.")

    if a.evidence_out:
        os.makedirs(os.path.dirname(a.evidence_out) or ".", exist_ok=True)
        with open(a.evidence_out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2, sort_keys=True)
    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"{rep['artifact']}  [{source}]")
        for b in bad:
            print(f"  UNREADABLE CUT: {b}")
        if not cuts:
            print("  no readable cuts")
        else:
            print(f"  cuts               : {rep['n_cuts']} "
                  f"({rep['cut_lengths_days']} d)")
            print(f"  sum of lengths     : {rep['sum_of_lengths_days']} d")
            print(f"  calendar covered   : {rep['calendar_union_days']} d "
                  f"({rep['union_start']} .. {rep['union_end']})")
            print(f"  REDUNDANCY         : {rep['redundancy']}x  (1.0 = disjoint)")
            for p in rep["overlapping_pairs"]:
                print(f"    overlap {p['a']} vs {p['b']}: {p['overlap_days']} d "
                      f"= {p['frac_of_shorter']:.0%} of the shorter window")
            if "max_disjoint_windows_at_current_length" in rep:
                print(f"  at this window length, {rep['corpus_days']} d of corpus "
                      f"admits at most "
                      f"{rep['max_disjoint_windows_at_current_length']} DISJOINT "
                      f"window(s)")
        print("\n" + rep["scope_note"])

    return 0 if (cuts and rep["disjoint"] and not bad) else 1


if __name__ == "__main__":
    raise SystemExit(main())
