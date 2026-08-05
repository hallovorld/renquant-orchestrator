#!/usr/bin/env python3
"""Was each position sized within the cap the config declares?

WHY (measured 2026-08-05, live book): TSLA is **23.5 % of equity** against
`regime_params.BULL_CALM.max_position_pct = 0.12`. The obvious story — a small
position that rallied — is **wrong**. It was BOUGHT that way: the 2026-07-28
buy stamped `target_pct = 0.2341` while its own `kelly_target_pct` was
`0.0613`. Nearly **2x the regime cap and 3.8x Kelly**, at entry. `EME` the same
day: `0.2109` vs `0.0613` `[VERIFIED]`.

Every other live buy in the window sized between 0.007 and 0.063 — comfortably
under. So this is an EVENT, not the normal path, and an event is exactly the
thing that goes unnoticed without a check.

And nothing corrected it afterwards: `kelly_trim` exists, and across the whole
trades table **250 rows carry it and 0 have a `trade_date`** — i.e. it has fired
in simulation only and **never once on the live book** `[VERIFIED]`.

WHAT THIS IS. A read-only conformance check over the recorded sizing decisions:
for each live buy, was `target_pct` within the regime's `max_position_pct`, and
how did it compare with the Kelly target the model produced?

WHAT IT IS NOT. Not a claim that the cap is the right number, nor that Kelly is.
It compares what was DONE against what the config SAYS — a config the book is
supposed to be expressing. A position the sizing stack never chose is not the
model's position.

Read-only (immutable sqlite). Usage:
    python ops/renquant104/position_cap_conformance.py [--since YYYY-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sqlite3
import sys

RQ = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                 "/Users/renhao/git/github/RenQuant"))
DB = RQ / "data" / "runs.alpaca.db"
CONFIG = (RQ / ".subrepo_runtime" / "repos" / "renquant-strategy-104" /
          "configs" / "strategy_config.json")

STATE_OK = "WITHIN_CAP"
STATE_OVER = "OVER_REGIME_CAP"
STATE_NO_CAP = "NO_CAP_DECLARED_FOR_REGIME"
STATE_UNKNOWN_REGIME = "REGIME_NOT_RECORDED"
STATE_NO_TARGET = "TARGET_PCT_NOT_RECORDED"
ACTIONABLE = (STATE_OVER, STATE_NO_CAP, STATE_UNKNOWN_REGIME, STATE_NO_TARGET)


class EvidenceUnreadable(Exception):
    """The config or the trade record could not be read. NOT 'no violations'."""


def regime_caps(config_path: pathlib.Path = CONFIG) -> dict[str, float | None]:
    """`{regime: max_position_pct}` — the caps the DEPLOYED config declares.

    A regime with no cap maps to ``None``, never to a default. Inventing a cap
    would turn "the config is silent here" into "this was within limits", which
    is the failure this file exists to catch one level up.
    """
    if not config_path.is_file():
        raise EvidenceUnreadable(f"no strategy config at {config_path}")
    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise EvidenceUnreadable(f"{config_path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise EvidenceUnreadable(f"{config_path}: root is not an object")
    out: dict[str, float | None] = {}
    for regime, params in (cfg.get("regime_params") or {}).items():
        val = (params or {}).get("max_position_pct")
        out[str(regime)] = float(val) if isinstance(val, (int, float)) else None
    return out


def classify(row: dict, caps: dict[str, float | None]) -> dict:
    regime, target, kelly = row["regime"], row["target_pct"], row["kelly_target_pct"]
    out = dict(row)
    if target is None:
        out["state"] = STATE_NO_TARGET
        return out
    if not regime:
        out["state"] = STATE_UNKNOWN_REGIME
        return out
    if regime not in caps or caps[regime] is None:
        out["state"] = STATE_NO_CAP
        return out
    cap = caps[regime]
    out["cap"] = cap
    out["over_cap_by"] = target - cap
    out["kelly_ratio"] = (target / kelly) if kelly else None
    out["state"] = STATE_OVER if target > cap + 1e-9 else STATE_OK
    return out


def scan(since: str, *, db: pathlib.Path = DB,
         config_path: pathlib.Path = CONFIG) -> dict:
    caps = regime_caps(config_path)
    if not db.is_file():
        raise EvidenceUnreadable(f"no runs DB at {db}")
    con = sqlite3.connect(f"file://{db}?immutable=1", uri=True)
    try:
        rows = con.execute(
            "select trade_date, ticker, regime, target_pct, kelly_target_pct "
            "from trades where trade_date is not null and trade_date >= ? "
            "and target_pct is not null "
            "and (exit_reason is null or exit_reason in ('accepted','pending_new')) "
            "order by trade_date desc, ticker", (since,)).fetchall()
    except sqlite3.Error as exc:
        raise EvidenceUnreadable(f"{db}: {exc}") from exc
    finally:
        con.close()
    classified = [classify(
        {"trade_date": d, "ticker": t, "regime": r,
         "target_pct": tp, "kelly_target_pct": kt}, caps) for d, t, r, tp, kt in rows]
    return {
        "since": since,
        "caps": caps,
        "n_buys": len(classified),
        "buys": classified,
        "n_over_cap": sum(1 for c in classified if c["state"] == STATE_OVER),
        "n_actionable": sum(1 for c in classified if c["state"] in ACTIONABLE),
    }


def render(r: dict) -> str:
    out = [f"position-cap conformance — live buys since {r['since']}", ""]
    out.append(f"  {'date':12}{'tkr':7}{'regime':15}{'target':>9}{'cap':>7}"
               f"{'kelly':>9}{'x kelly':>9}  state")
    for b in r["buys"]:
        k = b.get("kelly_ratio")
        out.append(
            f"  {b['trade_date']:12}{b['ticker']:7}{str(b['regime']):15}"
            f"{b['target_pct']:>9.4f}"
            f"{(b.get('cap') if b.get('cap') is not None else float('nan')):>7.2f}"
            f"{(b['kelly_target_pct'] or 0):>9.4f}"
            f"{(f'{k:.1f}x' if k else '—'):>9}  {b['state']}")
    out.append("")
    out.append(f"  {r['n_over_cap']} of {r['n_buys']} live buy(s) sized OVER the "
               f"regime cap the deployed config declares")
    out.append("  NOTE: this compares what was DONE against what the config SAYS. It is not\n"
               "        a claim that the cap or the Kelly target is the right number.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default="2026-07-01")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = scan(args.since, db=DB, config_path=CONFIG)
    except EvidenceUnreadable as exc:
        print(f"REFUSED: {exc} — unreadable evidence is not a clean book",
              file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 1 if r["n_actionable"] else 0


if __name__ == "__main__":
    sys.exit(main())
