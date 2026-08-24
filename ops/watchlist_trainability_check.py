#!/usr/bin/env python3
"""Every served ticker must be trainable or DECLARED untrainable — no third state.

THE DEFECT (orch#1020). There are two watchlists and they drifted:

    .subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json  145  the daily decision
    backtesting/renquant_104/strategy_config.json                              142  the weekly tournament's universe

The tournament freezes its universe from the SECOND file, and artifacts come
from the tournament. So a ticker added to the served watchlist alone is scored
**never**: CRWV was added on the operator's request on 2026-08-19 and has been
silently inert every session since, alongside RKLB and SPCX.

WHY A GUARD AND NOT A REPORT. The system already has the right mechanism — an
`expected_non_trainable` declaration with a per-ticker REASON, which is why SPY
and the sector ETFs log `no_artifact` without anyone worrying:

    "SPY": "benchmark index (strategy_config.benchmark) — regime/relative-strength
            reference, not a per-ticker tournament admission candidate"

There is no third state in that design. A ticker is trained, or it is declared
with a reason. CRWV/RKLB/SPCX are neither — an accident wearing the same
`no_artifact` WARNING as the eight deliberate ones, which is exactly why nobody
saw it for five days. This check makes the accident a failure.

WHAT IT DOES NOT DO. It does not decide whether a name SHOULD be trainable —
that needs a minimum-history threshold that, per orch#1020's own measurement,
is not coded anywhere (1,344 rows is the empirical floor of the current 142, not
a declared requirement). This check only refuses the silent third state: add the
ticker to the tournament universe, or declare it with a reason. Either is a
reviewed act; drifting into neither is not.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

RQ_ROOT = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))

SERVED_CONFIG = (".subrepo_runtime/repos/renquant-strategy-104/configs/"
                 "strategy_config.json")
TOURNAMENT_CONFIG = "backtesting/renquant_104/strategy_config.json"
DECLARATION_GLOB = "logs/weekly_tournament_retrain/*.expected_non_trainable.json"

#: The weekly tournament writes the declaration and, beside it, the universe it
#: actually ran against. That sibling is the BINDING: a declaration is only
#: authoritative for the watchlist it accompanies.
RUN_UNIVERSE_SUFFIX = ".expected_watchlist.json"

#: Backstop for the case where the binding cannot be checked at all. The job is
#: weekly, so three missed runs is unambiguous — the producer has stopped, and a
#: declaration nobody is refreshing must not keep authorising silence.
MAX_DECLARATION_AGE_DAYS = 21


class InputMissing(RuntimeError):
    """An input could not be read.

    A distinct failure from "the sets disagree", and it must never be silently
    treated as an empty set: a moved config would then make `served - trained`
    empty-minus-empty and the check would pass on a fleet it never inspected.
    That is the vacuity this repo keeps rediscovering.
    """


def _watchlist(path: Path, label: str) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputMissing(f"cannot read the {label} config at {path}: {exc}") from exc
    wl = data.get("watchlist")
    if not isinstance(wl, list):
        raise InputMissing(
            f"the {label} config at {path} has no 'watchlist' list — "
            f"refusing to compare against an empty set")
    # Normalise FIRST, then decide emptiness. `["   "]` is a non-empty list that
    # normalises to an empty set, and the earlier check tested the list — so a
    # whitespace-only watchlist passed as "present" and then compared as nothing
    # (codex on #1047). The set is what the comparison uses, so the set is what
    # has to be non-empty.
    tickers = {str(t).strip().upper() for t in wl if str(t).strip()}
    if not tickers:
        raise InputMissing(
            f"the {label} config at {path} has a 'watchlist' with {len(wl)} "
            f"entries that normalise to NOTHING — refusing to compare against "
            f"an empty set")
    return tickers


def _declared(rq_root: Path, trained: set[str],
              today: dt.date | None = None) -> tuple[dict[str, str], Path]:
    """The newest declaration — BOUND to the run it describes, or refused.

    Selecting by newest filename alone is not enough (codex on #1047): if the
    weekly job stops producing declarations, a stale file goes on silencing a
    newly served ticker forever, and the silence is the exact defect this guard
    exists to end. So the declaration must be shown to describe the universe
    being checked, and a declaration that cannot be bound is UNVERIFIABLE —
    InputMissing — never authorisation.
    """
    candidates = sorted(rq_root.glob(DECLARATION_GLOB))
    if not candidates:
        raise InputMissing(
            f"no declaration file matched {DECLARATION_GLOB} under {rq_root} — "
            f"without it every untrainable name would look undeclared and this "
            f"check would fire on the eight deliberate ones")
    newest = candidates[-1]
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputMissing(f"cannot read {newest}: {exc}") from exc
    if not isinstance(data, dict):
        raise InputMissing(f"{newest} is not an object of ticker -> reason")

    # BINDING: the sibling records the universe that run actually used.
    sibling = newest.with_name(
        newest.name.replace(".expected_non_trainable.json", RUN_UNIVERSE_SUFFIX))
    try:
        run_universe = json.loads(sibling.read_text(encoding="utf-8"))["watchlist"]
        ran_against = {str(t).strip().upper() for t in run_universe if str(t).strip()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputMissing(
            f"{newest.name} has no readable run-universe sibling "
            f"({sibling.name}: {type(exc).__name__}) — the declaration cannot be "
            f"bound to the run it describes, so it is unverifiable, not "
            f"authorisation") from exc
    if ran_against != trained:
        only_run = sorted(ran_against - trained)[:5]
        only_cfg = sorted(trained - ran_against)[:5]
        raise InputMissing(
            f"{newest.name} describes a DIFFERENT universe than the tournament "
            f"config holds now (ran against {len(ran_against)}, config has "
            f"{len(trained)}; only-in-run={only_run} only-in-config={only_cfg}). "
            f"A declaration for another run does not authorise silence in this "
            f"one — re-run the weekly tournament, or reconcile the config")

    # FRESHNESS backstop, for the case where the binding happens to still match
    # but nothing is refreshing the file.
    stamp = newest.name.split(".")[0]
    try:
        age = ((today or dt.date.today()) - dt.date.fromisoformat(stamp)).days
    except ValueError:
        raise InputMissing(
            f"{newest.name} does not begin with an ISO date — its age cannot be "
            f"established, so its authority cannot be either") from None
    if age > MAX_DECLARATION_AGE_DAYS:
        raise InputMissing(
            f"{newest.name} is {age}d old (limit {MAX_DECLARATION_AGE_DAYS}d for a "
            f"WEEKLY producer) — the job that writes it has stopped, and a "
            f"declaration nobody refreshes must not keep authorising silence")
    # A blank reason is not a declaration. The mechanism's whole value is that
    # someone wrote down WHY; an empty string would let a name be silenced
    # without anyone having to justify it.
    return ({str(k).strip().upper(): str(v)
             for k, v in data.items() if str(v).strip()}, newest)


def undeclared_untrainable(rq_root: Path | None = None) -> tuple[list[str], dict]:
    """(offending tickers, evidence). Empty list == the invariant holds."""
    root = rq_root or RQ_ROOT
    served = _watchlist(root / SERVED_CONFIG, "served")
    trained = _watchlist(root / TOURNAMENT_CONFIG, "tournament")
    declared, decl_path = _declared(root, trained)
    offenders = sorted(served - trained - set(declared))
    return offenders, {
        "served_n": len(served),
        "tournament_n": len(trained),
        "declared_n": len(declared),
        "declaration_file": str(decl_path),
        "declaration_age_days": (dt.date.today() - dt.date.fromisoformat(
            Path(decl_path).name.split(".")[0])).days,
        "served_minus_tournament": sorted(served - trained),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rq-root", default=str(RQ_ROOT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        offenders, evidence = undeclared_untrainable(Path(args.rq_root))
    except InputMissing as exc:
        print(f"FAIL (input): {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": not offenders, "offenders": offenders,
                          **evidence}, indent=2, sort_keys=True))
    if offenders:
        print(
            f"FAIL: {len(offenders)} served ticker(s) can never be scored and are "
            f"not declared untrainable: {', '.join(offenders)}.\n"
            f"       served={evidence['served_n']} tournament={evidence['tournament_n']} "
            f"declared={evidence['declared_n']} ({evidence['declaration_file']})\n"
            f"       Fix by ONE of: add them to the tournament universe "
            f"({TOURNAMENT_CONFIG}) so artifacts get built, or declare them in the "
            f"expected_non_trainable file WITH a reason. Drifting into neither is "
            f"how CRWV stayed inert for five days after the operator asked for it.",
            file=sys.stderr)
        return 1
    print(f"OK: every served ticker is trained or declared "
          f"(served={evidence['served_n']}, tournament={evidence['tournament_n']}, "
          f"declared={evidence['declared_n']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
