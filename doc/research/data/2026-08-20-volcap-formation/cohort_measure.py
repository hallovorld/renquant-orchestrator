"""Does the 60% realized-vol cap help or hurt, risk-adjusted?

THE GATE, restated from the live code path it reproduces
(`RealizedVolGateTask: dropped N/M candidates over 60% annualized vol cap
(window=60d)`): for each candidate, 60-trading-day realized vol of daily
returns, annualized by sqrt(252). Strictly greater than 0.60 -> removed from
the candidate pool BEFORE the panel scores anything.

WHY A COHORT COMPARISON AND NOT "WOULD THEY HAVE BEEN BOUGHT". The dropped
names are never scored, so their would-be panel scores do not exist anywhere
and cannot be recovered. What CAN be measured is the thing the cap is for: it
is a RISK control, so its job is to improve the RISK-ADJUSTED outcome of the
pool it leaves behind. If the dropped cohort turns out to have both higher
return AND higher risk-adjusted return, the cap is removing good names for a
reason that does not pay.

PIT: vol at date t uses returns strictly up to and including t; the forward
return is strictly after t. No forward information enters the split.

DEPENDENCE: weekly sampling with h-day forward returns overlaps, so per-date
observations are not independent. Reported on NON-OVERLAPPING blocks (stride =
h trading days) as the headline, with the overlapping series shown only as a
denser view.

SURVIVORSHIP: the watchlist is the CURRENT one. Names that blew up and were
removed are absent from both cohorts. That biases both, and plausibly biases
the high-vol cohort more (a name is likelier to leave after a bad high-vol
episode), so the dropped cohort's numbers here should be read as an UPPER
bound on how good it looks. Stated, not corrected.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

UMB = Path("/Users/renhao/git/github/RenQuant")
CFG = UMB / ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"
OHLCV = UMB / "data/ohlcv"

VOL_WINDOW = 60          # trading days, from the live log line
VOL_CAP = 0.60           # 60% annualized, from the live log line
ANNUALIZE = math.sqrt(252)

# INPUT PINNING [codex on orch#1017]. These paths point at the operator's LIVE
# tree, which is refreshed daily — so without a fingerprint a rerun silently
# scores whatever parquet/config happens to be on disk that day, and the
# committed .out logs would carry no evidence of what produced them. The
# manifest below is computed and PRINTED on every run, and asserted when
# `input_manifest.json` sits beside this script. A rerun on different inputs
# fails loudly instead of quietly disagreeing with the record.
MANIFEST = Path(__file__).with_name("input_manifest.json")


def _sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def input_manifest(tickers: list[str]) -> dict:
    """Identity of every input this measurement consumes."""
    files = [OHLCV / t / "1d.parquet" for t in tickers]
    present = sorted(p for p in files if p.exists())
    import hashlib
    roll = hashlib.sha256()
    for p in present:
        roll.update(p.name.encode())
        roll.update(_sha(p).encode())
    return {
        "config_sha256_16": _sha(CFG),
        "n_ticker_files": len(present),
        "ohlcv_rollup_sha256_16": roll.hexdigest()[:16],
    }


def assert_inputs(tickers: list[str]) -> dict:
    got = input_manifest(tickers)
    print("INPUT MANIFEST:", json.dumps(got, sort_keys=True))
    if MANIFEST.exists():
        want = json.loads(MANIFEST.read_text())
        if want != got:
            raise SystemExit(
                "INPUT DRIFT — this run's inputs differ from the manifest the "
                f"committed .out logs were produced against.\n  manifest: {want}\n"
                f"  this run: {got}\nRefusing to produce numbers that would be "
                "mistaken for the frozen evidence."
            )
        print("INPUT MANIFEST: matches the committed manifest")
    else:
        MANIFEST.write_text(json.dumps(got, sort_keys=True, indent=2) + "\n")
        print(f"INPUT MANIFEST: written to {MANIFEST.name} (first run)")
    return got


def load_closes(tickers: list[str]) -> pd.DataFrame:
    cols = {}
    for t in tickers:
        p = OHLCV / t / "1d.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p)
        if "close" not in d.columns:
            continue
        idx = pd.to_datetime(d.index)
        cols[t] = pd.Series(d["close"].values, index=idx).sort_index()
    return pd.DataFrame(cols).sort_index()


def main() -> None:
    cfg = json.loads(CFG.read_text())
    watchlist = sorted(set(cfg["watchlist"]))
    assert_inputs(watchlist)
    px = load_closes(watchlist)
    rets = px.pct_change()
    # PIT realized vol: uses returns up to and including each date.
    vol = rets.rolling(VOL_WINDOW).std() * ANNUALIZE

    print(f"watchlist={len(watchlist)}  with price data={px.shape[1]}  "
          f"dates {px.index[0].date()}..{px.index[-1].date()}")

    for h in (20, 60):
        fwd = px.shift(-h) / px - 1.0          # strictly forward
        # Non-overlapping: stride h so no two observations share a return window.
        usable = vol.dropna(how="all").index
        dates = [d for d in usable if d in fwd.index][::h]
        dates = [d for d in dates if fwd.loc[d].notna().any()]

        rows = []
        for d in dates:
            v, f = vol.loc[d], fwd.loc[d]
            ok = v.notna() & f.notna()
            if ok.sum() < 20:
                continue
            dropped = ok & (v > VOL_CAP)
            kept = ok & (v <= VOL_CAP)
            if dropped.sum() < 3 or kept.sum() < 3:
                continue
            rows.append({
                "date": d.date(), "n_drop": int(dropped.sum()), "n_keep": int(kept.sum()),
                "r_drop": float(f[dropped].mean()), "r_keep": float(f[kept].mean()),
            })
        if not rows:
            print(f"\nh={h}: no usable blocks")
            continue
        df = pd.DataFrame(rows)
        df["diff"] = df["r_drop"] - df["r_keep"]

        n = len(df)
        m = df["diff"].mean()
        sd = df["diff"].std(ddof=1)
        t = m / (sd / math.sqrt(n)) if sd > 0 else float("nan")

        # Risk-adjusted: per-block return divided by that cohort's own realized
        # cross-sectional dispersion is not a Sharpe; use mean/sd ACROSS blocks,
        # which is the cohort's own return-per-unit-of-its-own-variability.
        def ra(col: str) -> float:
            s = df[col]
            return s.mean() / s.std(ddof=1) if s.std(ddof=1) > 0 else float("nan")

        print(f"\n=== h={h} trading days | {n} NON-OVERLAPPING blocks "
              f"({df.date.iloc[0]}..{df.date.iloc[-1]}) ===")
        print(f"  cohort sizes/block   dropped {df.n_drop.mean():.1f}   kept {df.n_keep.mean():.1f}")
        print(f"  mean fwd return      dropped {df.r_drop.mean():+.4f}   kept {df.r_keep.mean():+.4f}")
        print(f"  return per unit of own block-to-block sd (higher = better risk-adjusted)")
        print(f"                       dropped {ra('r_drop'):+.3f}   kept {ra('r_keep'):+.3f}")
        print(f"  paired diff (drop-keep) {m:+.4f}  sd {sd:.4f}  t {t:+.2f}  "
              f"blocks positive {int((df['diff']>0).sum())}/{n}")
        verdict = ("the cap REMOVES the better cohort" if m > 0 and abs(t) > 2 else
                   "the cap removes the WORSE cohort" if m < 0 and abs(t) > 2 else
                   "NOT DISTINGUISHABLE at |t|>2")
        print(f"  -> {verdict}")


if __name__ == "__main__":
    main()
