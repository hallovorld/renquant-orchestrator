#!/usr/bin/env python3
"""Reproducible extraction behind the AAPL admission-forensics note.

Read-only. Re-derives every decision-driving number in
``doc/research/2026-07-29-aapl-never-bought-forensics.md`` from two *runtime*
surfaces, never from today's ``strategy_config.json``:

* ``RenQuant/data/runs.<broker>.db`` — ``candidate_scores`` + ``pipeline_runs``
* ``RenQuant/logs/daily_104/<date>.log`` — the gate values each run resolved

Why this exists
---------------
A config file read today cannot establish what a run resolved weeks ago. Both
gate values are therefore parsed out of each run's own log lines:

* ``VetoWeakBuysTask: dropped N candidate(s) below rank_score
  floor=max(min=0.20, mean+1.00*std=X) = X  (n=M)``
* ``ConvictionGateTask: dropped N candidate(s) (mu_floor=Y)``

The run for a session is pinned by runtime evidence rather than by hand: the
VetoWeakBuys line reports the cross-section size ``M`` it actually gated on, so
we select the live run whose candidate row count equals ``M``. A date with
several runs (2026-07-28 had three) uses that day's LAST logged gate line, i.e.
the run that stood as the day's final decision.

That still leaves one gap, and it is closed by refusing rather than guessing:
if two live runs on a date happen to share the same candidate count, ``M`` does
not identify a run. ``pin_run`` raises :class:`AmbiguousRunError` and the
session is SKIPPED with a loud message instead of publishing a number drawn
from an arbitrarily chosen run. A dropped session is a visible gap; a silently
mis-pinned one is a wrong number wearing a provenance tag.

Usage
-----
    python3 scripts/aapl_admission_forensics.py \
        --ticker AAPL --since 2026-07-06 --until 2026-07-29 \
        --extra-session 2026-06-26

``--data-root`` defaults to ``runtime_paths.default_data_root()`` rather than a
hardcoded umbrella path (the defect Codex caught on PR #404).

Every number it prints carries its own provenance in the column header:
``logged_*`` comes from the log, ``recomputed_*`` from the DB.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from renquant_orchestrator.runtime_paths import default_data_root

# The floor formula as it appears in the log line itself, so a change to the
# pipeline's floor mode shows up as a recompute mismatch rather than silently
# validating the wrong arithmetic.
FLOOR_RE = re.compile(
    r"VetoWeakBuysTask: dropped (?P<dropped>\d+) candidate\(s\) below rank_score "
    r"floor=max\(min=(?P<min_floor>[\d.]+), mean\+(?P<std_mult>[\d.]+)\*std=[\d.]+\) "
    r"= (?P<floor>[\d.]+)\s+\(n=(?P<n>\d+)\)"
)
MU_FLOOR_RE = re.compile(r"ConvictionGateTask: dropped (?P<dropped>\d+) candidate\(s\) \(mu_floor=(?P<mu_floor>[\d.]+)")


@dataclass(frozen=True)
class LogFacts:
    """Gate values a single run actually resolved, parsed from its own log."""

    date: str
    floor: float
    min_floor: float
    std_mult: float
    n: int
    dropped: int
    mu_floor: float | None


def parse_log(path: Path) -> LogFacts | None:
    """Return the *last* gate lines in ``path``, or None if it never gated buys.

    The last line is the operative one: a date with several runs ends on the
    run that stood as that day's decision.
    """
    text = path.read_text(errors="replace")
    floors = list(FLOOR_RE.finditer(text))
    if not floors:
        return None
    f = floors[-1]
    mus = list(MU_FLOOR_RE.finditer(text))
    return LogFacts(
        date=path.stem,
        floor=float(f["floor"]),
        min_floor=float(f["min_floor"]),
        std_mult=float(f["std_mult"]),
        n=int(f["n"]),
        dropped=int(f["dropped"]),
        mu_floor=float(mus[-1]["mu_floor"]) if mus else None,
    )


def recompute_floor(scores: list[float], min_floor: float, std_mult: float) -> float:
    """The ``adaptive_mean_std`` floor: max(min_floor, mean + std_mult*stdev)."""
    return max(min_floor, statistics.fmean(scores) + std_mult * statistics.stdev(scores))


class AmbiguousRunError(RuntimeError):
    """More than one run on a date matches the logged candidate count.

    Raised rather than resolved. The whole point of pinning is that the
    published number names ONE run; silently picking among several would make
    the note's provenance claim false while looking fine.
    """


def pin_run(conn: sqlite3.Connection, date: str, n: int) -> str | None:
    """Select the live run on ``date`` whose candidate count equals the logged n.

    Fails closed on ambiguity. An earlier revision returned ``matches[-1]``
    with no ``ORDER BY``, so when two runs on the same date shared a candidate
    count it selected an arbitrary one — SQLite does not guarantee GROUP BY
    ordering — while the note claimed the session was pinned by runtime
    evidence. That is not a theoretical risk on this data: 2026-07-28 alone
    has three live runs carrying candidate scores, and the AAPL values differ
    between them.

    Returns None when nothing matches (caller skips the session); raises
    :class:`AmbiguousRunError` when more than one does.
    """
    rows = conn.execute(
        "SELECT cs.run_id, COUNT(*) FROM candidate_scores cs "
        "JOIN pipeline_runs p ON p.run_id = cs.run_id "
        "WHERE p.run_date = ? AND cs.run_id LIKE '%-live-%' "
        "AND cs.role = 'candidate' AND cs.rank_score IS NOT NULL "
        "GROUP BY cs.run_id ORDER BY cs.run_id",
        (date,),
    ).fetchall()
    matches = sorted(rid for rid, cnt in rows if cnt == n)
    if not matches:
        return None
    if len(matches) > 1:
        raise AmbiguousRunError(
            f"{date}: {len(matches)} live runs have exactly n={n} scored "
            f"candidates ({', '.join(matches)}). The candidate count alone "
            f"does not identify a run here, so any number published from it "
            f"would name a run chosen arbitrarily. Correlate against a "
            f"stronger runtime key (logged floor value, run timestamp, or the "
            f"run_id from the log line) before publishing this session."
        )
    return matches[0]


@dataclass
class SessionMetrics:
    date: str
    run_id: str
    n: int
    logged_floor: float
    recomputed_floor: float
    mu_floor: float | None
    ticker_rank_score: float | None
    ticker_mu: float | None
    ticker_rank: int | None
    ticker_percentile: float | None
    median_rank_score: float
    above_median: bool | None
    admitted: int
    admitted_and_mu: int

    @property
    def floor_matches(self) -> bool:
        return round(self.recomputed_floor, 3) == round(self.logged_floor, 3)

    @property
    def admitted_share(self) -> float:
        return 100.0 * self.admitted / self.n

    @property
    def both_share(self) -> float:
        return 100.0 * self.admitted_and_mu / self.n


def session_metrics(conn: sqlite3.Connection, facts: LogFacts, run_id: str, ticker: str) -> SessionMetrics:
    rows = conn.execute(
        "SELECT ticker, rank_score, mu FROM candidate_scores "
        "WHERE run_id = ? AND role = 'candidate' AND rank_score IS NOT NULL",
        (run_id,),
    ).fetchall()
    scores = [r[1] for r in rows]
    n = len(scores)
    median = statistics.median(scores)
    admitted = [r for r in rows if r[1] >= facts.floor]
    both = [r for r in admitted if r[2] is not None and facts.mu_floor is not None and r[2] >= facts.mu_floor]

    hit = [r for r in rows if r[0] == ticker]
    if hit:
        rs, mu = hit[0][1], hit[0][2]
        rank = sorted(scores, reverse=True).index(rs) + 1
        pct = 100.0 * sum(1 for s in scores if s < rs) / n
        above = rs > median
    else:
        rs = mu = rank = pct = above = None

    return SessionMetrics(
        date=facts.date,
        run_id=run_id,
        n=n,
        logged_floor=facts.floor,
        recomputed_floor=recompute_floor(scores, facts.min_floor, facts.std_mult),
        mu_floor=facts.mu_floor,
        ticker_rank_score=rs,
        ticker_mu=mu,
        ticker_rank=rank,
        ticker_percentile=pct,
        median_rank_score=median,
        above_median=above,
        admitted=len(admitted),
        admitted_and_mu=len(both),
    )


def summarize(sessions: list[SessionMetrics]) -> dict:
    """Aggregate over the sessions in which the ticker was actually scored."""
    scored = [s for s in sessions if s.above_median is not None]
    return {
        "scored_sessions": len(scored),
        "above_median": sum(1 for s in scored if s.above_median),
        "floor_match": sum(1 for s in scored if s.floor_matches),
        "mean_admitted_share": statistics.fmean([s.admitted_share for s in scored]) if scored else 0.0,
        "mean_both_share": statistics.fmean([s.both_share for s in scored]) if scored else 0.0,
        "mu_floors": sorted({s.mu_floor for s in scored if s.mu_floor is not None}),
    }


def collect(db: Path, log_dir: Path, ticker: str, dates: list[str]) -> list[SessionMetrics]:
    conn = sqlite3.connect(f"file:{db}?immutable=1", uri=True)
    try:
        out = []
        for date in dates:
            log = log_dir / f"{date}.log"
            if not log.exists():
                print(f"  {date}: no log file — session not assessable", file=sys.stderr)
                continue
            facts = parse_log(log)
            if facts is None:
                print(f"  {date}: log present but no buy-gate line — run never gated buys", file=sys.stderr)
                continue
            try:
                run_id = pin_run(conn, date, facts.n)
            except AmbiguousRunError as exc:
                # Skip loudly rather than publish a number from an arbitrarily
                # chosen run. A dropped session is a visible gap; a silently
                # mis-pinned one is a wrong number wearing a provenance tag.
                print(f"  SKIPPED (ambiguous): {exc}", file=sys.stderr)
                continue
            if run_id is None:
                print(f"  {date}: no live run with candidate count == logged n={facts.n}", file=sys.stderr)
                continue
            out.append(session_metrics(conn, facts, run_id, ticker))
        return out
    finally:
        conn.close()


def trading_dates(log_dir: Path, since: str, until: str) -> list[str]:
    return sorted(p.stem for p in log_dir.glob("????-??-??.log") if since <= p.stem <= until)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="operator data/state root (default: runtime_paths.default_data_root())",
    )
    ap.add_argument("--broker", default="alpaca")
    ap.add_argument("--log-dir", default="logs/daily_104")
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--since", default="2026-07-06")
    ap.add_argument("--until", default="2026-07-29")
    ap.add_argument("--extra-session", action="append", default=[], help="additional date outside the window")
    args = ap.parse_args()

    root = args.data_root if args.data_root is not None else default_data_root()
    db = root / "data" / f"runs.{args.broker}.db"
    log_dir = root / args.log_dir
    if not db.exists():
        print(f"FATAL: no score DB at {db}", file=sys.stderr)
        return 2

    dates = trading_dates(log_dir, args.since, args.until) + list(args.extra_session)
    print(f"window {args.since}..{args.until} + extras {args.extra_session}: {len(dates)} logged sessions\n")
    sessions = collect(db, log_dir, args.ticker, dates)

    hdr = (
        f"\n{'date':11}{'run':10}{'n':>5}{'logged':>8}{'recomp':>8}{'ok':>4}"
        f"{'mu_flr':>7}{'rank':>8}{'pct':>5}{'>med':>6}{'mu':>9}{'adm':>5}{'adm%':>7}{'both':>6}{'both%':>7}"
    )
    print(hdr)
    for s in sessions:
        rank = f"{s.ticker_rank}/{s.n}" if s.ticker_rank else "-"
        print(
            f"{s.date:11}{s.run_id.split('-live-')[-1]:10}{s.n:5}{s.logged_floor:8.3f}"
            f"{s.recomputed_floor:8.4f}{'Y' if s.floor_matches else 'N':>4}"
            f"{(s.mu_floor if s.mu_floor is not None else float('nan')):7.2f}{rank:>8}"
            f"{(s.ticker_percentile if s.ticker_percentile is not None else float('nan')):5.0f}"
            f"{str(s.above_median):>6}"
            f"{(s.ticker_mu if s.ticker_mu is not None else float('nan')):9.4f}"
            f"{s.admitted:5}{s.admitted_share:7.1f}{s.admitted_and_mu:6}{s.both_share:7.1f}"
        )

    r = summarize(sessions)
    print(
        f"\n{args.ticker} scored in {r['scored_sessions']} of {len(sessions)} gating sessions"
        f"\n  above the cross-sectional median : {r['above_median']}/{r['scored_sessions']}"
        f"\n  recomputed floor == logged floor : {r['floor_match']}/{r['scored_sessions']}"
        f"\n  mean share clearing the floor    : {r['mean_admitted_share']:.1f}%"
        f"\n  mean share clearing floor AND mu : {r['mean_both_share']:.1f}%"
        f"\n  distinct resolved mu_floor values: {r['mu_floors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
