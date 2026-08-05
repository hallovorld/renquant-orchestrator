#!/usr/bin/env python3
"""GOAL-4: does the shadow fleet actually DISAGREE with prod?

WHY. The fleet exists to accumulate evidence separating candidate scorers from
the deployed one. That only works if the candidates rank names differently. A
lane whose top-K is prod's top-K would have bought the same names that day and
produced **no separating evidence at all** — it is an expensive way to re-run
prod. Nothing in the fleet measures this today: every lane reports its own
decision, and agreement with prod is invisible because no one compares them.

MEASURED 2026-08-04 `[VERIFIED — this session]`, against
`2026-08-04-live-a199b993` (prod, 83 scored):

    lane               n   spearman   top10   resid/sd   prod_sd   state
    blend             81     0.6058    5/10      91.9%    1.3448   DIVERGED
    blend_mom         82     0.9997   10/10       1.1%    1.3394   SAME_TOP_K_AS_PROD
    blend_rb_mom      82     0.9272    8/10      49.4%    1.3394   DIVERGED
    blend_mom_fast     —          —       —          —         —   RAN_AND_SCORED_NOTHING
    blend_rb_fast      —          —       —          —         —   RAN_AND_SCORED_NOTHING

`blend_mom` picked prod's **entire top 10** and is, to ~1 % of the score's own
cross-sectional dispersion, an affine rescaling of prod. Two more lanes recorded
a run and scored nothing. So of five shadow lanes, one produced no separating
evidence because it agreed and two because they did not score.

WHAT THIS IS NOT, and the caveat is bigger than the finding. **`blend_mom` has
exactly one date.** All four of its runs are 2026-08-04 re-runs
`[VERIFIED — this session]`. One date cannot support a conclusion about a lane,
in either direction, and this file does not draw one: it is a claim about what
evidence the fleet HAS, not about whether any lane's model is good. `blend_mom`'s
momentum member is not judged here at all. A lane can agree with prod on a calm
day and diverge on the next — which is precisely why the number wants counting
over time rather than asserting once.

The one lane with a history diverges consistently: `blend` over six dates
(07-28 … 08-04) never matched prod's top 10, overlap 5–7 of 10
`[VERIFIED — this session]`.

THE RATIO'S DENOMINATOR IS NOT STABLE, so it is printed beside it. Prod's own
cross-sectional score sd went **0.17 → 1.35 (8x)** on 2026-08-04 when prod
itself became a two-component z-blend `[VERIFIED — this session]`. Any
`resid/sd` read across that boundary is comparing ratios whose denominator
moved. The probe therefore reports `prod_score_sd` on every row: a ratio whose
denominator is invisible is a number nobody can check.

NO INVENTED THRESHOLD. The verdicts are facts, not cutoffs:
  * ``NO_RUN`` / ``RAN_AND_SCORED_NOTHING`` — no evidence, for two different
    reasons that must not be collapsed;
  * ``SAME_TOP_K_AS_PROD`` — the lane's top-K set EQUALS prod's, so on this date
    it would have chosen the same names. Definitional, not a threshold;
  * ``DIVERGED`` — otherwise, reported with its counts.
The affine-residual ratio is reported as a MAGNITUDE and never converted into a
verdict: picking a cutoff for it after seeing these numbers is the forking path
this file is trying to expose, not commit.

THE REFERENCE IS VALIDATED FIRST `[codex on orch#826]`. If prod has no run on
the date, or too few scored names to define the requested top-K, the whole run
is REFUSED. Without that the probe kept going, every lane compared against an
empty prod set, and the summary reported the fleet as producing "no separating
evidence" — **a missing control published as a finding about the fleet.**

WHAT IT READS IS MUTABLE, so what it compared is hashed. A result that names
only a run id cannot prove the rows behind that id are the rows compared, so
each row carries `score_set_sha256` of the scored set actually read, and
``--out`` persists the bundle a document may cite.

Read-only (immutable sqlite URIs). Usage:
    python ops/renquant104/fleet_divergence_probe.py [--date YYYY-MM-DD] [--top-k 10] [--out F]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sqlite3
import sys

DATA = pathlib.Path(os.environ.get(
    "RENQUANT_REPO_ROOT", "/Users/renhao/git/github/RenQuant")) / "data"

PROD_LANE = "alpaca"
SHADOW_LANES = (
    "alpaca_shadow_blend",
    "alpaca_shadow_blend_mom",
    "alpaca_shadow_blend_mom_fast",
    "alpaca_shadow_blend_rb_mom",
    "alpaca_shadow_blend_rb_fast",
)

STATE_PROD_UNAVAILABLE = "PROD_BASELINE_UNAVAILABLE"
STATE_NO_DB = "LANE_DB_ABSENT"
STATE_NO_RUN = "NO_RUN_ON_THIS_DATE"
STATE_NO_SCORES = "RAN_AND_SCORED_NOTHING"
STATE_TOO_FEW = "TOO_FEW_COMMON_NAMES"
STATE_SAME_TOP = "SAME_TOP_K_AS_PROD"
STATE_DIVERGED = "DIVERGED"
#: States that mean this lane contributed no separating evidence on this date.
NO_EVIDENCE = (STATE_NO_DB, STATE_NO_RUN, STATE_NO_SCORES, STATE_TOO_FEW,
               STATE_SAME_TOP)

MIN_COMMON = 10


class ProdBaselineUnavailable(Exception):
    """There is no usable prod reference for this date.

    [codex on orch#826] Without this the probe kept going: every shadow lane
    then compared against an empty prod score set, landed in
    ``TOO_FEW_COMMON_NAMES``, and the summary line reported the whole fleet as
    producing "no separating evidence". **A missing control would have been
    published as a finding about the fleet.** The reference is now the first
    thing validated, and its absence refuses the run instead of colouring it.
    """


class LaneUnreadable(Exception):
    """The lane's evidence could not be read. NOT the same as "the lane did not
    run" — collapsing the two reports a broken probe as a quiet fleet."""


def lane_scores(lane: str, date: str, data: pathlib.Path = DATA
                ) -> tuple[str | None, dict[str, float]]:
    """``(run_id, {ticker: panel_score})`` for the lane's latest run on ``date``.

    An absent DB raises; an absent run returns ``(None, {})``; a run with no
    scored candidates returns ``(run_id, {})``. Three outcomes, because they are
    three different facts about the lane.
    """
    path = data / f"runs.{lane}.db"
    if not path.is_file():
        raise LaneUnreadable(f"no lane DB at {path}")
    try:
        con = sqlite3.connect(f"file://{path}?immutable=1", uri=True)
    except sqlite3.Error as exc:                       # pragma: no cover
        raise LaneUnreadable(f"{path}: {exc}") from exc
    try:
        row = con.execute(
            "select run_id from pipeline_runs where run_date=? "
            "and run_bundle_json is not null order by created_at desc limit 1",
            (date,)).fetchone()
        if not row:
            return None, {}
        run_id = row[0]
        rows = con.execute(
            "select ticker, panel_score from candidate_scores "
            "where run_id=? and role='candidate' and panel_score is not null",
            (run_id,)).fetchall()
    except sqlite3.Error as exc:
        raise LaneUnreadable(f"{path}: {exc}") from exc
    finally:
        con.close()
    return run_id, {t: float(s) for t, s in rows}


def score_set_sha256(scores: dict[str, float]) -> str:
    """A content hash of one lane's scored set.

    The probe reads MUTABLE sqlite. A committed result that names only a run id
    cannot prove the rows behind that id are the rows that were compared, so
    every persisted row carries the hash of what was actually read
    `[codex on orch#826]`.
    """
    payload = json.dumps(sorted((t, float(s)) for t, s in scores.items()),
                         separators=(",", ":"), sort_keys=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _spearman(x: list[float], y: list[float]) -> float:
    from scipy.stats import spearmanr

    return float(spearmanr(x, y)[0])


def _affine_residual_ratio(prod: list[float], lane: list[float]) -> float | None:
    """How much of the lane's score is NOT a rescaling of prod's.

    ``sd(lane - (a·prod + b)) / sd(prod)``. A lane that is a pure affine
    transform of prod scores 0 and cannot reorder anything; the ratio says how
    far past that it goes, in units of prod's own dispersion. Reported as a
    magnitude only — see the module docstring on why it is never a verdict.
    """
    import numpy as np

    p, m = np.asarray(prod, float), np.asarray(lane, float)
    sd = p.std(ddof=1)
    if sd == 0 or len(p) < 3:
        return None
    a, b = np.polyfit(p, m, 1)
    return float((m - (a * p + b)).std(ddof=1) / sd)


def compare(prod: dict[str, float], lane: dict[str, float], *, top_k: int) -> dict:
    common = sorted(set(prod) & set(lane))
    if len(common) < MIN_COMMON:
        return {"state": STATE_TOO_FEW, "n_common": len(common)}
    px = [prod[t] for t in common]
    lx = [lane[t] for t in common]
    top_prod = set(sorted(common, key=lambda t: -prod[t])[:top_k])
    top_lane = set(sorted(common, key=lambda t: -lane[t])[:top_k])
    import numpy as np

    out = {
        "n_common": len(common),
        # Printed with the ratio, always: the denominator moved 8x once
        # already, and a ratio without it cannot be compared across dates.
        "prod_score_sd": float(np.asarray(px, float).std(ddof=1)),
        "spearman_vs_prod": _spearman(px, lx),
        "top_k": top_k,
        "top_k_overlap": len(top_prod & top_lane),
        "affine_residual_ratio": _affine_residual_ratio(px, lx),
        "top_k_only_in_lane": sorted(top_lane - top_prod),
    }
    out["state"] = STATE_SAME_TOP if top_prod == top_lane else STATE_DIVERGED
    return out


def probe(date: str, *, top_k: int = 10, data: pathlib.Path = DATA) -> dict:
    prod_run, prod = lane_scores(PROD_LANE, date, data)
    # The REFERENCE is validated before anything is compared to it.
    if prod_run is None:
        raise ProdBaselineUnavailable(
            f"prod has no completed run on {date} — there is nothing to compare "
            f"the fleet against, and reporting the lanes as 'no separating "
            f"evidence' would publish a missing control as a finding")
    need = max(MIN_COMMON, top_k)
    if len(prod) < need:
        raise ProdBaselineUnavailable(
            f"prod run {prod_run} scored {len(prod)} name(s) on {date}, fewer "
            f"than the {need} needed to define a top-{top_k} — the reference "
            f"cannot support the comparison being asked for")
    rows = []
    for lane in SHADOW_LANES:
        try:
            run_id, scores = lane_scores(lane, date, data)
        except LaneUnreadable as exc:
            rows.append({"lane": lane, "state": STATE_NO_DB, "detail": str(exc)})
            continue
        if run_id is None:
            rows.append({"lane": lane, "state": STATE_NO_RUN})
            continue
        if not scores:
            rows.append({"lane": lane, "run_id": run_id, "state": STATE_NO_SCORES,
                         "detail": "a run row exists and no candidate carries a "
                                   "panel_score — the lane produced no evidence"})
            continue
        rows.append({"lane": lane, "run_id": run_id,
                     "score_set_sha256": score_set_sha256(scores),
                     **compare(prod, scores, top_k=top_k)})
    return {
        "date": date,
        "top_k": top_k,
        "prod_run_id": prod_run,
        "prod_n_scored": len(prod),
        "prod_score_set_sha256": score_set_sha256(prod),
        "lanes": rows,
        "n_lanes": len(rows),
        "n_lanes_with_no_separating_evidence": sum(
            1 for r in rows if r["state"] in NO_EVIDENCE),
    }


def render(result: dict) -> str:
    out = [f"fleet divergence vs prod — {result['date']}",
           f"  prod run {result['prod_run_id']} "
           f"({result['prod_n_scored']} scored)", ""]
    k = result["lanes"][0].get("top_k", 10) if result["lanes"] else 10
    out.append(f"  {'lane':26}{'n':>5}{'spearman':>10}{'top' + str(k):>8}"
               f"{'resid/sd':>10}{'prod_sd':>10}  state")
    for r in result["lanes"]:
        name = r["lane"].replace("alpaca_shadow_", "")
        if "spearman_vs_prod" not in r:
            out.append(f"  {name:26}{'—':>5}{'—':>10}{'—':>8}{'—':>10}"
                       f"{'—':>10}  {r['state']}")
            continue
        ratio = r["affine_residual_ratio"]
        out.append(
            f"  {name:26}{r['n_common']:>5}{r['spearman_vs_prod']:>10.4f}"
            f"{str(r['top_k_overlap']) + '/' + str(r['top_k']):>8}"
            f"{('—' if ratio is None else f'{ratio:.1%}'):>10}"
            f"{r['prod_score_sd']:>10.4f}  {r['state']}")
    n = result["n_lanes_with_no_separating_evidence"]
    out.append("")
    out.append(f"  {n} of {result['n_lanes']} shadow lane(s) produced NO "
               f"separating evidence on this date")
    out.append("  NOTE: this is about ONE date's ranking and what evidence the "
               "fleet can accumulate.\n        It is NOT a claim that any lane's "
               "model is bad. resid/sd is a MAGNITUDE,\n        never a verdict "
               "— no cutoff is applied to it, and it is NOT\n        comparable "
               "across dates on which prod_sd moved.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    import datetime as dt

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="persist the result bundle here — the record "
                                  "a document may cite, since the sqlite it "
                                  "reads is mutable")
    args = ap.parse_args(argv)
    try:
        # Module-global lookup at CALL time, not the def-time default: a test
        # (and an operator with RENQUANT_REPO_ROOT set) must be able to point
        # this at another tree without the CLI silently reading the live one.
        result = probe(args.date, top_k=args.top_k, data=DATA)
    except ProdBaselineUnavailable as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    except LaneUnreadable as exc:
        print(f"REFUSED: prod lane unreadable — {exc}", file=sys.stderr)
        return 2
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, indent=2),
                                          encoding="utf-8")
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 1 if result["n_lanes_with_no_separating_evidence"] else 0


if __name__ == "__main__":
    sys.exit(main())
