#!/usr/bin/env python3
"""A rebuild that touches a file is not a rebuild that advanced the data.

Measured 2026-07-29 on the live tree:

    file                                        mtime         newest DATA   age
    sec_fundamentals_daily.parquet              Jul 25        2026-07-24     5d
    alpha158_291_fundamental_dataset.parquet    Jul 29 13:13  2026-05-01    89d
    transformer_v4_wl200_clean.parquet          Jul 25        2026-04-28    92d

The alpha158 panel was WRITTEN TODAY and its newest row is from eighty-nine
days ago. Its own build script's success check is

    ARTIFACT_AGE=$(date -r "$ARTIFACT" "+%Y-%m-%d %H:%M:%S")

which reads the file's MTIME. Touching the file satisfies it. Nothing anywhere
asks whether the frontier moved.

This checker asks that question, and — the part that matters for whether a
retry is even the right response — it classifies WHY the frontier did not move,
because the three causes need three different reactions:

  * ``TRANSIENT``  the artifact is missing or unreadable. A retry is exactly
                   right; that is what the retry budget in `retry_advice` is for.
  * ``NOT_ADVANCING`` the file is fresh by mtime and stale by data. A retry MAY
                   help (an upstream fetch may have failed silently), but if the
                   upstream genuinely has no newer rows, retrying forever burns
                   a job slot and hides the real problem. Alarm, retry ONCE.
  * ``UPSTREAM_EMPTY`` the frontier has not moved across repeated observations
                   spanning more than one expected cadence. Retry is FUTILE.
                   This is a data-supply problem, not a job problem, and the
                   correct response is to escalate, not to re-run.

Conflating those is why "add a retry" so often produces a job that fails
forever quietly instead of failing once loudly.

Read-only: opens parquet metadata and reads dates. Writes nothing, retries
nothing itself — it advises.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liveness_common import alert  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")

TRANSIENT = "TRANSIENT"
NOT_ADVANCING = "NOT_ADVANCING"
UPSTREAM_EMPTY = "UPSTREAM_EMPTY"
HEALTHY = "HEALTHY"


@dataclass(frozen=True)
class WatchedArtifact:
    """A data artifact whose DATA frontier is supposed to advance."""
    name: str
    path: str
    #: column holding the observation date
    date_column: str = "date"
    #: how stale the newest row may be before this is a finding — for a
    #: LABEL-FREE artifact. Ignored when `label_horizon_tdays` is set.
    max_data_age_days: int = 7
    #: Forward-label horizon in TRADING days, when the artifact carries one.
    #: A `fwd_60d` label cannot exist until ~84 CALENDAR days after its feature
    #: date, so a flat age bound reports a structurally-correct panel as stale.
    #: This is the same single-axis error the two-axis shadow-freshness rule
    #: (renquant-pipeline#220) was built to fix — and the first revision of
    #: THIS checker walked straight into it, reporting two panels as
    #: UPSTREAM_EMPTY when both were as fresh as a 60d-label panel can be.
    label_horizon_tdays: int | None = None
    #: allowance above the structural floor before the frontier is a finding
    label_slack_days: int = 28
    #: how often the producing job runs; used to tell NOT_ADVANCING from
    #: UPSTREAM_EMPTY — a frontier that has not moved for more than one
    #: cadence is not a flaky fetch.
    cadence_days: int = 1


WATCHED: tuple[WatchedArtifact, ...] = (
    # No forward label: a flat bound is correct here.
    WatchedArtifact(
        name="sec-fundamentals-daily",
        path=os.path.join(RQ, "data/sec_fundamentals_daily.parquet"),
        max_data_age_days=7, cadence_days=1),
    # Both training panels carry fwd_5d/fwd_20d/fwd_60d_excess. The BINDING
    # horizon is the longest one actually trained on (60 trading days), so the
    # frontier is structurally ~84 calendar days behind and a flat bound is
    # meaningless.
    WatchedArtifact(
        name="alpha158-fund-panel",
        path=os.path.join(RQ, "data/alpha158_291_fundamental_dataset.parquet"),
        cadence_days=7, label_horizon_tdays=60),
    WatchedArtifact(
        name="transformer-panel",
        path=os.path.join(RQ, "data/transformer_v4_wl200_clean.parquet"),
        cadence_days=7, label_horizon_tdays=60),
)


#: Trading days -> calendar days. 5 trading days per 7 calendar days, rounded
#: up, matching the conversion the two-axis freshness rule uses.
def trading_to_calendar_days(tdays: int) -> int:
    return -(-tdays * 7 // 5)


def frontier_bound_days(art: "WatchedArtifact") -> tuple[int, str]:
    """(allowed age in days, how it was derived).

    A label-bearing artifact is bounded by its OWN structural floor plus
    slack. A label-free one by a flat maximum. Returning the derivation makes
    a false positive self-diagnosing rather than mysterious.
    """
    if art.label_horizon_tdays is None:
        return art.max_data_age_days, f"flat bound {art.max_data_age_days}d (no forward label)"
    floor = trading_to_calendar_days(art.label_horizon_tdays)
    return (floor + art.label_slack_days,
            f"structural floor {floor}d ({art.label_horizon_tdays} trading days) "
            f"+ {art.label_slack_days}d slack")


@dataclass(frozen=True)
class FrontierReading:
    name: str
    status: str
    newest_data: dt.date | None
    data_age_days: int | None
    mtime: dt.date | None
    detail: str

    @property
    def is_finding(self) -> bool:
        return self.status != HEALTHY

    def describe(self) -> str:
        nd = self.newest_data.isoformat() if self.newest_data else "?"
        mt = self.mtime.isoformat() if self.mtime else "?"
        return (f"[{self.status}] {self.name}: newest data {nd} "
                f"(age {self.data_age_days}d), file touched {mt}. {self.detail}")


def newest_data_date(path: str, date_column: str) -> dt.date | None:
    """Newest observation date, read from the column — never from mtime."""
    try:
        import pandas as pd
        frame = pd.read_parquet(path, columns=[date_column])
    except Exception:  # noqa: BLE001
        return None
    if frame.empty:
        return None
    try:
        import pandas as pd
        return pd.to_datetime(frame[date_column]).max().date()
    except Exception:  # noqa: BLE001
        return None


def read_frontier(art: WatchedArtifact, *, as_of: dt.date,
                  prior_frontier: dt.date | None = None,
                  prior_observed_on: dt.date | None = None) -> FrontierReading:
    """One observation cannot prove a frontier is permanently stuck.

    The first revision assigned UPSTREAM_EMPTY from a single stale snapshot
    plus a recent mtime, while this module's own docstring defines it as
    "across repeated observations". That mislabels a transient upstream
    failure as futile and forces ZERO retries — the exact opposite of the
    check-and-retry behaviour this was built for.

    A second revision required `prior_frontier` to EQUAL the current frontier,
    which proves SAMENESS but not ELAPSED TIME: two observations seconds apart
    trivially agree, and the docstring's condition is "spanning more than one
    expected cadence". So sameness alone still bought zero retries too
    cheaply. UPSTREAM_EMPTY now additionally requires `prior_observed_on` and
    at least `cadence_days` between that observation and `as_of` — i.e. the
    producer has had a full cadence window to move the frontier and did not.
    Same frontier but too soon stays NOT_ADVANCING with one retry.

    This checker stays stateless on purpose — it writes nothing — so the
    caller (a scheduled job that persists BOTH its last frontier and when it
    saw it) is what closes the loop. A caller that persists only the value
    cannot reach UPSTREAM_EMPTY, which is the safe direction: it retries once
    instead of escalating on unproven evidence.
    """
    p = Path(art.path)
    if not p.exists():
        return FrontierReading(art.name, TRANSIENT, None, None, None,
                               "artifact missing — a retry is the right "
                               "response (see retry_advice).")
    try:
        mtime = dt.date.fromtimestamp(p.stat().st_mtime)
    except OSError:
        mtime = None
    newest = newest_data_date(art.path, art.date_column)
    if newest is None:
        return FrontierReading(art.name, TRANSIENT, None, None, mtime,
                               f"could not read `{art.date_column}` — treat as "
                               f"unreadable, not as stale.")
    age = (as_of - newest).days
    bound, how = frontier_bound_days(art)
    if age <= bound:
        return FrontierReading(art.name, HEALTHY, newest, age, mtime,
                               f"within {bound}d — {how}.")

    # Stale. The distinction that decides whether retrying is sane:
    touched_recently = mtime is not None and (as_of - mtime).days <= art.cadence_days
    # Same frontier is necessary but NOT sufficient: two observations seconds
    # apart agree trivially. UPSTREAM_EMPTY's contract is "across repeated
    # observations spanning more than one expected cadence", so the elapsed
    # span has to be checked, not just the value.
    same_frontier = prior_frontier is not None and prior_frontier == newest
    span_days = (as_of - prior_observed_on).days if prior_observed_on else None
    spans_a_cadence = span_days is not None and span_days >= art.cadence_days
    if touched_recently and same_frontier and spans_a_cadence:
        return FrontierReading(
            art.name, UPSTREAM_EMPTY, newest, age, mtime,
            f"the file was touched within its {art.cadence_days}d cadence but "
            f"its frontier is {age}d old against a {bound}d bound ({how}) — "
            f"and an observation {span_days}d ago (>= the {art.cadence_days}d "
            f"cadence) saw the SAME frontier, so the producer has had a full "
            f"cadence window and moved nothing. Retrying is futile; this is a "
            f"data-supply problem. Escalate, do not re-run.")
    if touched_recently:
        if same_frontier and not spans_a_cadence:
            why = (f"a prior observation saw the same frontier, but only "
                   f"{span_days}d ago (< the {art.cadence_days}d cadence)"
                   if span_days is not None else
                   "a prior observation saw the same frontier, but its "
                   "timestamp was not supplied so the cadence span is unproven")
            return FrontierReading(
                art.name, NOT_ADVANCING, newest, age, mtime,
                f"touched within cadence but {age}d stale against a {bound}d "
                f"bound ({how}) — {why}, so 'permanently stuck' is not "
                f"established. Retry ONCE, then escalate.")
        return FrontierReading(
            art.name, NOT_ADVANCING, newest, age, mtime,
            f"touched within cadence but {age}d stale against a {bound}d bound "
            f"({how}) — an upstream fetch may "
            f"have failed silently. Retry ONCE, then escalate.")
    return FrontierReading(
        art.name, TRANSIENT, newest, age, mtime,
        f"{age}d stale and not touched within its {art.cadence_days}d cadence — "
        f"the producing job appears not to have run. A retry is appropriate.")


#: Retries per status. UPSTREAM_EMPTY is deliberately 0: a retry that cannot
#: possibly help is worse than none, because it converts a loud data problem
#: into a quiet recurring job failure.
RETRY_BUDGET = {TRANSIENT: 3, NOT_ADVANCING: 1, UPSTREAM_EMPTY: 0, HEALTHY: 0}


def retry_advice(reading: FrontierReading) -> tuple[int, str]:
    """(attempts, why). Advice only — this module never re-runs anything."""
    n = RETRY_BUDGET[reading.status]
    if n == 0 and reading.status == UPSTREAM_EMPTY:
        return 0, ("retry is futile: the job ran and the upstream had nothing "
                   "newer. Re-running cannot change that.")
    if n == 0:
        return 0, "nothing to retry."
    return n, f"retry up to {n}x, then escalate rather than loop."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    # This CLI is a single stateless observation: it passes no prior frontier
    # and no prior observation time, so it can NEVER return UPSTREAM_EMPTY —
    # the worst it reports is NOT_ADVANCING with one retry. That is deliberate.
    # Reaching the zero-retry status requires a caller that persists both the
    # last frontier AND when it saw it, and can therefore prove the frontier
    # held across a full cadence. Under-escalating is the safe failure here.
    readings = [read_frontier(a, as_of=as_of) for a in WATCHED]
    for r in readings:
        print(r.describe())
        if r.is_finding:
            n, why = retry_advice(r)
            print(f"    retry: {n} — {why}")

    findings = [r for r in readings if r.is_finding]
    if not findings:
        print(f"data-frontier check: {len(readings)} artifact(s) advancing "
              f"as of {as_of}")
        return 0
    if not args.dry_run:
        # ASCII-only title: an alarm about data problems must not fail to
        # deliver for an unrelated encoding reason.
        alert("RenQuant DATA FRONTIER",
              " | ".join(r.describe() for r in findings))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
