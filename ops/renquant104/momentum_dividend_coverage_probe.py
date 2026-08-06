#!/usr/bin/env python3
"""Did the served momentum artifact actually get dividends, or a silent zero?

WHY (GOAL-7, 2026-08-05). model#110 landed a dividend-adjusted total-return
series so the momentum formation return would stop being a price return. The
served trainer does use it — `tools/momentum_train_run.py` computes
`total_return_close(raw["close"], raw["dividend"])`. But it reaches the dividend
series like this:

    raw["dividend"] if "dividend" in raw.columns
    else pd.Series(0.0, index=raw.index)

**A missing column is silently indistinguishable from a stock that pays nothing.**
Both produce a zero dividend series, and the artifact records neither. Measured
today, all 31 names without the column are genuine non-payers (ADBE, AMD, AMZN,
TSLA, CRWD, GLD, ...), so the fix is currently correct for 144/144. That is the
good case, and it is also exactly why nobody would notice the bad one: if a
PAYER's column ever goes missing -- a vendor schema change, a partial rebuild,
one interrupted backfill -- that name's momentum silently reverts to a price
return, the artifact looks identical, and the digest still verifies.

This probe is the difference. It re-derives, per name in the SERVED artifact,
whether the dividend column was present, and refuses to call a name "clean" just
because its dividend total is zero.

The load-bearing distinction, and the reason this file exists:

    ZERO_BY_DATA    the column is there and sums to zero -> a real non-payer
    ZERO_BY_ABSENCE the column is missing -> the trainer substituted zero and
                    NOTHING recorded that it did

Read-only. Writes nothing. Usage:
    python ops/renquant104/momentum_dividend_coverage_probe.py [--artifact P] [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

RQ_ROOT = pathlib.Path("/Users/renhao/git/github/RenQuant")
DEFAULT_OHLCV = RQ_ROOT / "data" / "ohlcv"
DEFAULT_ARTIFACT_DIR = (RQ_ROOT / "backtesting" / "renquant_104" / "artifacts"
                        / "momentum")

HAS_DIVIDENDS = "HAS_DIVIDENDS"
ZERO_BY_DATA = "ZERO_BY_DATA"
ZERO_BY_ABSENCE = "ZERO_BY_ABSENCE"
SOURCE_MISSING = "SOURCE_MISSING"

# States in which the dividend input was SUBSTITUTED rather than read.
#
# Deliberately NOT named "not a total return": for a genuine non-payer a price
# return IS the total return, so the substituted zero is numerically right. The
# defect is that the artifact cannot distinguish that case from a payer whose
# column went missing -- indistinguishability, not a wrong number. An earlier
# draft of this file rendered these as "got a PRICE return", which overstated
# a real finding into a false one.
#
# A frozenset rather than an inline test so a new state cannot inherit the
# benign default -- the failure mode this repo keeps meeting is an `else` that
# returns PASS for a case nobody enumerated.
SUBSTITUTED_INPUT = frozenset({ZERO_BY_ABSENCE, SOURCE_MISSING})


class ArtifactUnreadable(RuntimeError):
    """The artifact could not be read. Not an empty coverage report."""


def newest_artifact(root: pathlib.Path = DEFAULT_ARTIFACT_DIR) -> pathlib.Path:
    """The newest dated artifact directory's v0 json.

    Sorted by the DIRECTORY NAME (an ISO date), never by mtime: a re-copied or
    rsync'd file gets a fresh mtime without being newer, and this repo has
    already published one wrong 'newest file' that way."""
    if not root.is_dir():
        raise ArtifactUnreadable(f"{root} is not a directory")
    dated = sorted((d for d in root.iterdir()
                    if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"),
                   key=lambda d: d.name)
    for d in reversed(dated):
        f = d / "momentum_residual_v0.json"
        if f.is_file():
            return f
    raise ArtifactUnreadable(f"no momentum_residual_v0.json under {root}")


def classify(ticker: str, ohlcv_root: pathlib.Path) -> dict:
    import pandas as pd

    f = ohlcv_root / ticker / "1d.parquet"
    if not f.is_file():
        return {"ticker": ticker, "state": SOURCE_MISSING,
                "detail": f"no parquet at {f}"}
    cols = pd.read_parquet(f).columns.tolist()
    if "dividend" not in cols:
        # The trainer substitutes zeros here and records nothing.
        return {"ticker": ticker, "state": ZERO_BY_ABSENCE,
                "detail": "no 'dividend' column — the trainer substituted a "
                          "zero series and the artifact does not say so"}
    s = pd.read_parquet(f, columns=["dividend"])["dividend"]
    total = float(s.fillna(0.0).abs().sum())
    return {"ticker": ticker,
            "state": HAS_DIVIDENDS if total > 0 else ZERO_BY_DATA,
            "abs_dividend_sum": total}


def probe(artifact: pathlib.Path | None = None,
          ohlcv_root: pathlib.Path = DEFAULT_OHLCV) -> dict:
    path = artifact or newest_artifact()
    try:
        art = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactUnreadable(f"{path}: {exc}") from exc
    names = art.get("formation_return")
    if not isinstance(names, dict) or not names:
        raise ArtifactUnreadable(
            f"{path}: 'formation_return' absent or empty — cannot enumerate the "
            "names the artifact actually scored, and reporting 0 names as full "
            "coverage would publish a missing input as a clean result")

    rows = [classify(t, ohlcv_root) for t in sorted(names)]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    degraded = [r["ticker"] for r in rows if r["state"] in SUBSTITUTED_INPUT]
    return {
        "artifact": str(path),
        "artifact_cutoff_date": art.get("cutoff_date"),
        "artifact_content_sha256": art.get("content_sha256"),
        "n_names": len(rows),
        "counts": counts,
        # The number that matters: names whose dividend input was substituted,
        # not read. Correct today for every one of them -- and unverifiable
        # from the artifact alone, which is the point.
        "n_substituted_dividend_input": len(degraded),
        "substituted_dividend_input": degraded,
        # Reported so a clean result can never be read as "dividends verified":
        # a zero here means no name was SILENTLY degraded, not that the dividend
        # figures are correct. This probe checks presence, not values.
        "checks": "column presence and sign only — NOT the dividend values",
        "rows": rows,
    }


def render(p: dict) -> str:
    out = [f"momentum dividend coverage — {p['artifact_cutoff_date']}", ""]
    out.append(f"  artifact : {p['artifact']}")
    out.append(f"  names    : {p['n_names']}")
    for k in (HAS_DIVIDENDS, ZERO_BY_DATA, ZERO_BY_ABSENCE, SOURCE_MISSING):
        if k in p["counts"]:
            out.append(f"    {k:<18} {p['counts'][k]:>4}")
    out.append("")
    if p["n_substituted_dividend_input"]:
        out.append(f"  {p['n_substituted_dividend_input']} name(s) had their dividend "
                   f"input SUBSTITUTED with zero rather than read.")
        out.append("  For a genuine non-payer that is the CORRECT number. The defect is\n"
                   "  that the artifact cannot tell you which case each name is:")
        out.append("    " + " ".join(p["substituted_dividend_input"][:40]))
    else:
        out.append("  every name's dividend input was READ, not substituted.")
        out.append("  NOTE: this checks column PRESENCE, not dividend values —\n"
                   "  a clean result here is not a statement that the dividends "
                   "are right.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", type=pathlib.Path, default=None)
    ap.add_argument("--ohlcv-root", type=pathlib.Path, default=DEFAULT_OHLCV)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        p = probe(args.artifact, args.ohlcv_root)
    except ArtifactUnreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(p, indent=2) if args.json else render(p))
    return 1 if p["n_substituted_dividend_input"] else 0


if __name__ == "__main__":
    sys.exit(main())
