#!/usr/bin/env python3
"""The umbrella's sizing twin diverges from the pipeline's — on the money path.

ROOT CAUSE, PROVEN 2026-08-05 (P0 orch#851). `compute_position_size` exists
TWICE:

  RenQuant/backtesting/renquant_104/kernel/sizing.py       <- what live.runner uses
  renquant-pipeline/.../kernel/sizing.py                   <- the reviewed one

Both carry an "oversize fallback": when the sized target buys less than one
whole share, try ``0.25 * portfolio_value`` instead. The **pipeline** copy then
clamps that back under the cap::

    cap_shares = int(target_dollars / price)
    if shares > cap_shares:
        shares = cap_shares          # -> 0 when the target is sub-one-share

The **umbrella** copy has the fallback and **not the clamp** `[VERIFIED]`. The
clamp landed in the pipeline on 2026-07-03 (`6de6219`); the twin never received
it.

So on the live book, any candidate whose target buys <1 share is silently
allocated **25 % of the portfolio** — regime cap, Kelly target, conviction and
sigma all bypassed. The weaker the candidate, the smaller its target, the more
likely it trips the fallback: **weak candidates get the biggest positions.**

REPRODUCED 7/7 against the umbrella copy with the recorded inputs
`[VERIFIED — this session]`:

    2026-07-28 (LIVE)  TSLA 8 (23.4%)   EME 3 (21.1%)   SPG 1 (2.2%)
    2026-08-03 (dry)   AMZN 9 (22.7%)   MRK 20 (24.2%)  PYPL 47 (25.0%)  GOOG 1 (3.3%)

Every one matches the order that was actually placed. The same inputs through
the pipeline copy give 0, 0, 1 / 0, 0, 0, 1.

THIS PROBE compares the two implementations over a grid and fails on ANY
divergence. It does not fix the twin — the fix belongs in the umbrella, which
this repo does not write — it makes the divergence impossible to miss again.

Read-only. Usage:
    python ops/renquant104/sizing_twin_conformance.py [--json]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import sys

RQ = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                 "/Users/renhao/git/github/RenQuant"))
UMBRELLA = RQ / "backtesting" / "renquant_104" / "kernel" / "sizing.py"
PINNED = (RQ / ".subrepo_runtime" / "repos" / "renquant-pipeline" / "src" /
          "renquant_pipeline" / "kernel" / "sizing.py")


class TwinUnreadable(Exception):
    """A copy could not be loaded. NOT the same as "they agree"."""


def _load(path: pathlib.Path, name: str):
    if not path.is_file():
        raise TwinUnreadable(f"no sizing module at {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:            # pragma: no cover
        raise TwinUnreadable(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:                            # noqa: BLE001
        raise TwinUnreadable(f"{path}: {type(exc).__name__}: {exc}") from exc
    if not hasattr(mod, "compute_position_size"):
        raise TwinUnreadable(f"{path} has no compute_position_size")
    return mod


#: The grid. Prices straddle the sub-one-share boundary at every cap, because
#: that boundary is exactly where the two copies part company.
PORTFOLIO_VALUES = (10_565.46, 50_000.0, 100_000.0)
CASHES = (615.0, 4_460.90, 9_162.85, 50_000.0)
MAX_PCTS = (0.0018, 0.0075, 0.0220, 0.0232, 0.0684, 0.12)
PRICES = (57.21, 130.22, 237.52, 306.52, 704.26, 1_777.0)
RESERVES = (0.0, 0.2)


def compare(umbrella=None, pinned=None) -> dict:
    u = umbrella or _load(UMBRELLA, "umbrella_sizing")
    p = pinned or _load(PINNED, "pinned_sizing")
    diffs = []
    n = 0
    for pv in PORTFOLIO_VALUES:
        for cash in CASHES:
            for mp in MAX_PCTS:
                for price in PRICES:
                    for reserve in RESERVES:
                        n += 1
                        a = u.compute_position_size(pv, cash, mp, reserve, price)
                        b = p.compute_position_size(pv, cash, mp, reserve, price)
                        if a[1] != b[1]:
                            diffs.append({
                                "portfolio_value": pv, "cash": cash,
                                "max_pct": mp, "price": price,
                                "reserve_pct": reserve,
                                "umbrella_shares": a[1], "pinned_shares": b[1],
                                "umbrella_pct_of_pv": a[0],
                                "notional_gap_usd": (a[1] - b[1]) * price,
                            })
    worst = max((d["notional_gap_usd"] for d in diffs), default=0.0)
    return {
        "umbrella": str(UMBRELLA), "pinned": str(PINNED),
        "n_cases": n, "n_divergent": len(diffs),
        "worst_notional_gap_usd": worst,
        "max_umbrella_pct_of_pv": max((d["umbrella_pct_of_pv"] for d in diffs),
                                      default=0.0),
        "divergences": diffs,
    }


def render(r: dict) -> str:
    out = ["sizing twin conformance — umbrella vs pinned pipeline", ""]
    out.append(f"  cases compared ......... {r['n_cases']}")
    out.append(f"  DIVERGENT .............. {r['n_divergent']}")
    if r["n_divergent"]:
        out.append(f"  worst notional gap ..... ${r['worst_notional_gap_usd']:,.0f}")
        out.append(f"  largest umbrella size .. {r['max_umbrella_pct_of_pv']:.1%} of PV")
        out.append("")
        out.append(f"  {'PV':>11}{'cash':>10}{'max_pct':>9}{'price':>9}"
                   f"{'umbrella':>10}{'pinned':>8}{'gap $':>10}")
        for d in r["divergences"][:12]:
            out.append(f"  {d['portfolio_value']:>11,.0f}{d['cash']:>10,.0f}"
                       f"{d['max_pct']:>9.4f}{d['price']:>9.2f}"
                       f"{d['umbrella_shares']:>10}{d['pinned_shares']:>8}"
                       f"{d['notional_gap_usd']:>10,.0f}")
        if len(r["divergences"]) > 12:
            out.append(f"  … and {len(r['divergences']) - 12} more")
    out.append("")
    out.append("  The umbrella copy is what live.runner sizes with. Any row above is a\n"
               "  live order the reviewed implementation would not have placed.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = compare()
    except TwinUnreadable as exc:
        print(f"REFUSED: {exc} — an unreadable twin is not an agreeing one",
              file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 1 if r["n_divergent"] else 0


if __name__ == "__main__":
    sys.exit(main())
