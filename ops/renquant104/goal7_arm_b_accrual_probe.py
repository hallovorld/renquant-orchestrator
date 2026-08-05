#!/usr/bin/env python3
"""GOAL-7: is Arm B actually ACCRUING, or has it silently stopped?

The frozen registration (`doc/research/2026-08-05-goal7-momentum-per-regime-prereg.md`)
says Arm B — the only arm that may CERTIFY — becomes eligible when the primary
regime BULL_CALM has **≥ 30 evaluation dates with matured labels**, and puts that
"not before ~2027". A date that far out is exactly the kind of promise nothing
checks: if the weekly training job stops, the ledger simply never grows, Arm B
never arrives, and **no alarm distinguishes that from waiting**.

This is that check. It answers three questions and refuses to blur them:

1. **How much has actually accrued?** Rows in the artifact ledger, their cutoff
   dates, which of those are BULL_CALM under the PRODUCTION regime chain, and
   which of those have MATURED labels.
2. **Is the job still firing?** The gap between the newest ledger row and today,
   against the job's own weekly cadence. A ledger that stopped growing is the
   finding; a ledger that never started is a different one.
3. **When would eligibility arrive?** Projected from the OBSERVED cadence, and
   REFUSED outright when there are too few rows to observe a cadence at all —
   which is the state today.

MEASURED 2026-08-05 `[VERIFIED — this session]`: **1 ledger row** (cutoff
2026-08-02, genesis). One row cannot establish a rate, so this projects nothing
and says so. What it can already say: `com.renquant.momentum-train-weekly` is
installed and its next fire is Saturday.

A SEPARATE, MEASURED input to the projection, from the Arm A run: BULL_CALM is
**1684 of 2380** production-regime dates = **70.8 %** `[VERIFIED — orch#825]`.
So ≥30 BULL_CALM cutoffs needs roughly 42 weekly scorings, plus the 60-business-
day maturity of the last one. That is consistent with the registration's
"~2027" — it is not a new claim, it is the arithmetic behind the old one, and
it is stated so the date stops being folklore.

Read-only. Usage:
    python ops/renquant104/goal7_arm_b_accrual_probe.py [--as-of YYYY-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

RQ = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                 "/Users/renhao/git/github/RenQuant"))
LEDGER = (RQ / "backtesting" / "renquant_104" / "artifacts" / "momentum" /
          "momentum_artifact_ledger.jsonl")

PRIMARY_REGIME = "BULL_CALM"
MIN_DATES_PRIMARY = 30           # registration §3/§5/§6
LABEL_HORIZON_BDAYS = 60         # fwd_60d_excess
CADENCE_DAYS = 7                 # the job fires weekly (Saturday 05:00)
#: How many missed firings before "still accruing" becomes "it stopped". Two,
#: not one: a single late run is an operator restarting a machine.
STALE_AFTER_MISSED = 2
#: Fewer rows than this and no cadence can be OBSERVED. Projecting from one
#: point is not a projection, it is the assumption wearing a number.
MIN_ROWS_TO_PROJECT = 3

STATE_NO_LEDGER = "LEDGER_ABSENT"
STATE_UNREADABLE = "LEDGER_UNREADABLE"
STATE_GENESIS_ONLY = "GENESIS_ONLY_NO_CADENCE_YET"
STATE_ACCRUING = "ACCRUING"
STATE_STOPPED = "STOPPED_ACCRUING"
STATE_ELIGIBLE = "ARM_B_ELIGIBLE"


class LedgerUnreadable(Exception):
    """Could not read the accrual evidence. NOT the same as 'nothing accrued'.

    Carries the STATE it maps to, so :func:`probe_result` can return a
    structured row for it. A declared state a caller can never observe is not a
    state `[codex on orch#836]` — and a daily report needs to tell unavailable
    evidence from an ordinary not-yet-eligible result.
    """

    def __init__(self, message: str, state: str = "LEDGER_UNREADABLE") -> None:
        super().__init__(message)
        self.state = state


def read_ledger(path: pathlib.Path = LEDGER) -> list[dict]:
    """Every row, with EVERY field the accrual calculation needs validated.

    [codex on orch#836] The first version skipped a row with no `cutoff_date`
    and let a malformed one raise a raw ValueError. Both hide a broken producer
    behind something that reads like "nothing accrued yet" — which is precisely
    the state this probe exists to tell apart from "it stopped".
    """
    if not path.is_file():
        raise LedgerUnreadable(f"no ledger at {path}", STATE_NO_LEDGER)
    # [codex on orch#836, round 3] `is_file()` succeeding does not make the bytes
    # readable: permissions, a mid-read I/O error, or non-UTF-8 content all raise
    # AFTER the existence check and would escape the state machine, leaving --json
    # with no LEDGER_UNREADABLE row. Unavailable evidence has to stay observable
    # through every path that can make it unavailable, not just the obvious one.
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerUnreadable(f"cannot read {path}: {type(exc).__name__}: {exc}")
    rows = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerUnreadable(f"{path} line {i}: {exc}")
        if not isinstance(row, dict):
            raise LedgerUnreadable(
                f"{path} line {i}: row is {type(row).__name__}, not an object")
        raw = row.get("cutoff_date")
        if raw is None:
            raise LedgerUnreadable(
                f"{path} line {i}: no cutoff_date — a row the accrual cannot "
                "count is a broken producer, not an empty ledger")
        try:
            dt.date.fromisoformat(str(raw))
        except ValueError as exc:
            raise LedgerUnreadable(
                f"{path} line {i}: cutoff_date {raw!r} is not a date ({exc})")
        rows.append(row)
    return rows


def _business_days_after(day: dt.date, n: int) -> dt.date:
    """Calendar date n business days after ``day`` (weekends only; holidays are
    NOT modelled, so a maturity date computed here is the EARLIEST possible —
    stated because an optimistic maturity would make Arm B look closer."""
    seen = 0
    cur = day
    while seen < n:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            seen += 1
    return cur


def regimes_for(dates: list[dt.date]) -> dict:
    """Production regime per cutoff, or a stated absence.

    Never invents a regime: if the production chain cannot be run here, the
    per-date regime is ``None`` with a reason, and every downstream count says
    UNKNOWN rather than assuming the primary.
    """
    try:
        for repo in ("renquant-backtesting", "renquant-pipeline", "renquant-model"):
            src = pathlib.Path("/Users/renhao/git/github") / repo / "src"
            if src.is_dir() and str(src) not in sys.path:
                sys.path.insert(0, str(src))
        os.environ.setdefault("RENQUANT_REPO_ROOT", str(RQ))
        from renquant_backtesting.analysis.analyze_manifest_sanity_placebo import (
            build_regime_series)
        frame = build_regime_series(dates)
        out = {}
        for row in frame.to_dict("records"):
            out[row["date"].date()] = row.get("regime")
        return {"by_date": out, "unavailable_because": None}
    except Exception as exc:  # noqa: BLE001 — a probe never breaks a run
        return {"by_date": {}, "unavailable_because": f"{type(exc).__name__}: {exc}"}


def probe(as_of: dt.date, *, path: pathlib.Path = LEDGER) -> dict:
    rows = read_ledger(path)
    cutoffs = sorted({dt.date.fromisoformat(str(r["cutoff_date"]))
                      for r in rows if r.get("cutoff_date")})
    reg = regimes_for(cutoffs) if cutoffs else {"by_date": {},
                                                "unavailable_because": "no cutoffs"}
    per_date = []
    for c in cutoffs:
        regime = reg["by_date"].get(c)
        matures = _business_days_after(c, LABEL_HORIZON_BDAYS)
        per_date.append({
            "cutoff_date": c.isoformat(),
            "regime": regime,
            "regime_known": regime is not None,
            "label_matures_on_or_after": matures.isoformat(),
            "matured": matures <= as_of,
        })
    primary_matured = [d for d in per_date
                       if d["regime"] == PRIMARY_REGIME and d["matured"]]
    newest = cutoffs[-1] if cutoffs else None
    days_since = (as_of - newest).days if newest else None
    missed = (days_since // CADENCE_DAYS) if days_since is not None else None

    if not cutoffs:
        state = STATE_GENESIS_ONLY
    elif len(primary_matured) >= MIN_DATES_PRIMARY:
        state = STATE_ELIGIBLE
    elif missed is not None and missed >= STALE_AFTER_MISSED:
        state = STATE_STOPPED
    elif len(rows) < MIN_ROWS_TO_PROJECT:
        state = STATE_GENESIS_ONLY
    else:
        state = STATE_ACCRUING

    projection: dict = {"projected": False}
    if state == STATE_ELIGIBLE:
        # [codex on orch#836] `need` goes <= 0 here and the arithmetic produced
        # a "projected eligibility" date in the PAST. A reached threshold is not
        # a forecast.
        projection["refused_because"] = (
            f"already eligible: {len(primary_matured)} matured "
            f"{PRIMARY_REGIME} date(s) >= the {MIN_DATES_PRIMARY} the "
            "registration requires — there is nothing left to project")
    elif len(cutoffs) >= MIN_ROWS_TO_PROJECT:
        span = (cutoffs[-1] - cutoffs[0]).days
        rate = (len(cutoffs) - 1) / span if span else 0.0
        known = [d for d in per_date if d["regime_known"]]
        share = (sum(1 for d in known if d["regime"] == PRIMARY_REGIME) / len(known)
                 if known else None)
        projection = {
            "projected": bool(rate and share),
            "observed_cutoffs_per_day": rate,
            "observed_primary_share": share,
            "note": "projected from the OBSERVED cadence and the OBSERVED "
                    "primary-regime share of THIS ledger, not from the "
                    "registration's assumed weekly rate",
        }
        if rate and share:
            need = MIN_DATES_PRIMARY - len(primary_matured)
            days = need / (rate * share) if (rate * share) else None
            if days:
                last_cut = as_of + dt.timedelta(days=days)
                projection["projected_eligible_on_or_after"] = (
                    _business_days_after(last_cut, LABEL_HORIZON_BDAYS).isoformat())
    else:
        projection["refused_because"] = (
            f"{len(cutoffs)} cutoff(s) — fewer than {MIN_ROWS_TO_PROJECT}; a rate "
            "cannot be OBSERVED from this, and projecting from the registration's "
            "assumed cadence would report an assumption as a measurement")

    return {
        "as_of": as_of.isoformat(),
        "ledger": str(path),
        "n_rows": len(rows),
        "n_cutoffs": len(cutoffs),
        "newest_cutoff": newest.isoformat() if newest else None,
        "days_since_newest_cutoff": days_since,
        "missed_firings": missed,
        "cadence_days": CADENCE_DAYS,
        "regime_source_unavailable_because": reg["unavailable_because"],
        "per_cutoff": per_date,
        "n_primary_matured": len(primary_matured),
        "n_needed_primary": MIN_DATES_PRIMARY,
        "state": state,
        "projection": projection,
    }


def probe_result(as_of: dt.date, *, path: pathlib.Path = LEDGER) -> dict:
    """:func:`probe`, but an unreadable/absent ledger becomes a STRUCTURED row.

    The exception stays available for callers that want it; this is the shape a
    daily report consumes, because a report that gets an exception where it
    expected a row cannot distinguish "evidence unavailable" from "not eligible
    yet" — and those are the two things this probe exists to keep apart.
    """
    try:
        return probe(as_of, path=path)
    except LedgerUnreadable as exc:
        return {
            "as_of": as_of.isoformat(), "ledger": str(path),
            "state": exc.state, "unavailable_because": str(exc),
            "n_rows": None, "n_cutoffs": None, "newest_cutoff": None,
            "days_since_newest_cutoff": None, "missed_firings": None,
            "cadence_days": CADENCE_DAYS,
            "regime_source_unavailable_because": None,
            "per_cutoff": [],
            # NOT zero. A count of the primary regime is unknown when the
            # ledger cannot be read, and zero would read like a measurement.
            "n_primary_matured": None, "n_needed_primary": MIN_DATES_PRIMARY,
            "projection": {"projected": False,
                           "refused_because": "the ledger could not be read"},
        }


def render(r: dict) -> str:
    out = [f"GOAL-7 Arm B accrual — as of {r['as_of']}", ""]
    if r.get("unavailable_because"):
        out.append(f"  STATE: {r['state']}")
        out.append(f"  {r['unavailable_because']}")
        out.append("  Evidence UNAVAILABLE — this is NOT 'nothing accrued'. "
                   "Every count below is unknown,\n  not zero.")
        return "\n".join(out)
    out.append(f"  ledger rows ................. {r['n_rows']}")
    out.append(f"  distinct cutoffs ............ {r['n_cutoffs']}")
    out.append(f"  newest cutoff ............... {r['newest_cutoff']} "
               f"({r['days_since_newest_cutoff']}d ago, "
               f"{r['missed_firings']} missed {r['cadence_days']}d firing(s))")
    out.append(f"  matured {PRIMARY_REGIME} dates ...... "
               f"{r['n_primary_matured']} of {r['n_needed_primary']} needed")
    if r["regime_source_unavailable_because"]:
        out.append(f"  regime source UNAVAILABLE: {r['regime_source_unavailable_because']}"
                   "\n    every regime count above is UNKNOWN, not zero")
    out.append("")
    for d in r["per_cutoff"]:
        out.append(f"  {d['cutoff_date']}  regime={d['regime'] or 'UNKNOWN':<14}"
                   f"matures {d['label_matures_on_or_after']}"
                   f"{'  MATURED' if d['matured'] else ''}")
    out.append("")
    out.append(f"  STATE: {r['state']}")
    p = r["projection"]
    out.append("  projection: " + (
        p.get("projected_eligible_on_or_after", "none")
        if p.get("projected") else f"REFUSED — {p.get('refused_because', '')}"))
    out.append("  NOTE: maturity ignores market holidays, so every 'matures' date is the\n"
               "        EARLIEST possible — an optimistic maturity would make Arm B look\n"
               "        closer than it is.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = probe_result(dt.date.fromisoformat(args.as_of), path=LEDGER)
    print(json.dumps(r, indent=2) if args.json else render(r))
    # Structured either way, so a daily report always gets a row — and an
    # unreadable ledger still exits NON-ZERO rather than looking ordinary.
    if r["state"] in (STATE_NO_LEDGER, STATE_UNREADABLE):
        return 2
    return 1 if r["state"] == STATE_STOPPED else 0


if __name__ == "__main__":
    sys.exit(main())
