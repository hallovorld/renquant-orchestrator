#!/usr/bin/env python3
"""Three probes on the live panel scorer, reproducible from the artifact alone.

Answers a question the score DB cannot: WHY did the model mark a name down
through a large rally? The per-day feature matrices are not retained, so
attribution has to come out of the artifact's own booster.

    python3 scripts/scorer_attribution_probe.py \\
        --artifact <umbrella>/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json \\
        --ohlcv-dir <umbrella>/data/ohlcv \\
        --strategy-config <pinned strategy_config.json>

Probe A  BLOAT              how many declared features the booster ever splits
                            on, and how concentrated the gain is.
Probe B  MARGINAL EFFECT    average score change from moving one feature
                            z=-1 -> z=+1 over N random z-space baselines.
                            A single probe at the all-mean vector is NOT
                            enough: trees are interactive, and the all-zero
                            point can land in leaves where a feature's splits
                            never fire, which makes a used feature look inert.
                            Averaging over random baselines is what separates
                            "the model ignores this" from "this one point does".
Probe C  SERVE TRUNCATION   whether the upstream realized-vol gate truncates
                            the distribution of the feature the model relies
                            on most. The gate runs BEFORE scoring, so a name
                            it drops has no score row at all -- this cannot be
                            seen from the score DB.

READ-ONLY. Loads the artifact and OHLCV parquet; writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile

import numpy as np
import pandas as pd

# Alpha158 families whose definition divides by the CURRENT close, so a rising
# price mechanically pushes them down. Verified in code, not from memory:
#   RenQuant/scripts/build_alpha158_qlib.py:232  MA{n}   = mean(close,n)/close
#   RenQuant/scripts/build_alpha158_qlib.py:239  QTLU{n} = quantile(close,.8,n)/close
#   renquant-base-data .../alpha158_ops.py:366   MA{n}   = win_c.mean()/c_today
PRICE_RATIO_PREFIXES = ("MA", "QTLU", "QTLD", "MIN", "MAX", "ROC", "RSV")


def load_booster(artifact: dict):
    import xgboost as xgb
    raw = artifact["booster_raw_json"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        fh.write(raw if isinstance(raw, str) else json.dumps(raw))
        tmp = fh.name
    booster = xgb.Booster()
    booster.load_model(tmp)
    os.unlink(tmp)
    # The artifact stores features positionally; name them f0..fN so gain keys
    # map back by index rather than by a name the booster never saw.
    booster.feature_names = [f"f{i}" for i in range(len(artifact["feature_cols"]))]
    return booster


def probe_bloat(booster, feature_cols: list[str]) -> dict:
    gain = booster.get_score(importance_type="gain")
    total = sum(gain.values()) or 1.0
    cum = np.cumsum(sorted(gain.values(), reverse=True)) / total

    def name(key: str) -> str:
        if key.startswith("f") and key[1:].isdigit():
            i = int(key[1:])
            return feature_cols[i] if i < len(feature_cols) else key
        return key

    ranked = sorted(((name(k), v) for k, v in gain.items()), key=lambda kv: -kv[1])
    return {
        "declared": len(feature_cols),
        "ever_split_on": len(gain),
        "never_split_on": len(feature_cols) - len(gain),
        "cum_share": {k: float(cum[k - 1]) for k in (10, 20, 30, 50) if k <= len(cum)},
        "top": [(f, float(v), float(v / total)) for f, v in ranked[:20]],
    }


def probe_marginal(booster, feature_cols: list[str], feats: list[str],
                   n_baselines: int, seed: int) -> list[dict]:
    """Average marginal effect over random baselines -- NOT one point."""
    import xgboost as xgb
    idx = {f: i for i, f in enumerate(feature_cols)}
    rng = np.random.default_rng(seed)
    base = rng.normal(size=(n_baselines, len(feature_cols)))
    names = booster.feature_names
    out = []
    for feat in feats:
        if feat not in idx:
            continue
        i = idx[feat]
        lo, hi = base.copy(), base.copy()
        lo[:, i], hi[:, i] = -1.0, +1.0
        delta = (booster.predict(xgb.DMatrix(hi, feature_names=names))
                 - booster.predict(xgb.DMatrix(lo, feature_names=names)))
        out.append({"feature": feat, "mean": float(delta.mean()),
                    "sd": float(delta.std()),
                    "frac_positive": float(np.mean(delta > 0)),
                    "price_ratio": feat.startswith(PRICE_RATIO_PREFIXES)})
    return sorted(out, key=lambda r: -abs(r["mean"]))


def probe_truncation(ohlcv_dir: str, watchlist: list[str],
                     vol_cap_pct: float) -> dict:
    """Does the realized-vol gate truncate the model's dominant feature?

    STD60 as the model sees it is `std(close,60)/close`, a PRICE-dispersion
    ratio. The gate thresholds ANNUALISED RETURN volatility. Those are
    different quantities, so their rank correlation is REPORTED, not assumed.
    """
    rows = []
    for ticker in watchlist:
        path = os.path.join(ohlcv_dir, ticker, "1d.parquet")
        if not os.path.exists(path):
            continue
        try:
            frame = pd.read_parquet(path)
            frame.index = pd.to_datetime(frame.index)
            close = frame.sort_index()["close"].tail(61)
            if len(close) < 61:
                continue
            rows.append((ticker,
                         float(close.tail(60).std()) / float(close.iloc[-1]),
                         float(close.pct_change().tail(60).std()) * np.sqrt(252) * 100))
        except Exception:  # noqa: BLE001 - a malformed parquet is not the subject
            continue
    frame = pd.DataFrame(rows, columns=["ticker", "STD60", "ann_vol_pct"]).dropna()
    if frame.empty:
        return {"n": 0}
    dropped = frame[frame.ann_vol_pct > vol_cap_pct]
    kept = frame[frame.ann_vol_pct <= vol_cap_pct]
    return {
        "n": len(frame),
        "spearman": float(frame.STD60.corr(frame.ann_vol_pct, method="spearman")),
        "n_dropped": len(dropped), "n_kept": len(kept),
        "median_dropped": float(dropped.STD60.median()) if len(dropped) else None,
        "median_kept": float(kept.STD60.median()) if len(kept) else None,
        "ratio": (float(dropped.STD60.median() / kept.STD60.median())
                  if len(dropped) and len(kept) else None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--ohlcv-dir", default=None)
    parser.add_argument("--strategy-config", default=None)
    parser.add_argument("--n-baselines", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--vol-cap-pct", type=float, default=60.0)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    with open(args.artifact) as fh:
        art = json.load(fh)
    feature_cols = art["feature_cols"]
    print(f"artifact  kind={art.get('kind')}  trained_date={art.get('trained_date')}")
    print(f"          label={art.get('label_col')}  lookahead={art.get('lookahead_days')}")
    print(f"          panel_shape={art.get('panel_shape')}")
    booster = load_booster(art)
    result = {"artifact": os.path.basename(args.artifact),
              "trained_date": art.get("trained_date")}

    print("\n=== PROBE A: feature bloat ===")
    bloat = probe_bloat(booster, feature_cols)
    result["bloat"] = bloat
    print(f"  declared={bloat['declared']}  ever split on={bloat['ever_split_on']}  "
          f"NEVER split on={bloat['never_split_on']} "
          f"({bloat['never_split_on'] / bloat['declared']:.0%})")
    for k, share in bloat["cum_share"].items():
        print(f"  top {k:2} carry {share:.0%} of total gain")
    print("  top 10 by gain: "
          + ", ".join(f"{f}({s:.1%})" for f, _, s in bloat["top"][:10]))

    print(f"\n=== PROBE B: marginal effect, {args.n_baselines} random baselines "
          f"(seed {args.seed}) ===")
    marg = probe_marginal(booster, feature_cols,
                          [f for f, _, _ in bloat["top"]],
                          args.n_baselines, args.seed)
    result["marginal"] = marg
    for row in marg:
        tag = "  [price-ratio]" if row["price_ratio"] else ""
        print(f"  {row['feature']:22} mean={row['mean']:+.4f}  sd={row['sd']:.4f}  "
              f"frac>0={row['frac_positive']:.0%}{tag}")
    # A near-zero MEAN has two very different causes and they must not be
    # conflated. INERT: the feature moves the score nowhere from any baseline
    # (sd ~ 0 too) -- it carries tree gain but no effect. SIGN-UNSTABLE: it
    # moves the score a lot, in a direction that flips with the baseline, so
    # the average cancels. Only the first is dead weight.
    inert = [r["feature"] for r in marg
             if abs(r["mean"]) < 1e-3 and r["sd"] < 1e-2]
    unstable = [(r["feature"], r["sd"]) for r in marg
                if abs(r["mean"]) < 1e-3 and r["sd"] >= 1e-2]
    if inert:
        print(f"  INERT (gain but no effect from any baseline): "
              f"{', '.join(inert)}")
    if unstable:
        print("  SIGN-UNSTABLE (large effect, direction flips with baseline): "
              + ", ".join(f"{f}(sd={sd:.3f})" for f, sd in unstable))

    if args.strategy_config and args.ohlcv_dir:
        with open(args.strategy_config) as fh:
            watchlist = json.load(fh).get("watchlist") or []
        print(f"\n=== PROBE C: does the {args.vol_cap_pct:.0f}% vol gate truncate "
              f"the top feature? ===")
        trunc = probe_truncation(args.ohlcv_dir, watchlist, args.vol_cap_pct)
        result["truncation"] = trunc
        if trunc.get("n"):
            print(f"  n={trunc['n']}  spearman(STD60, annualised vol)="
                  f"{trunc['spearman']:+.3f}")
            print(f"  gate DROPS n={trunc['n_dropped']}  median STD60="
                  f"{trunc['median_dropped']:.4f}")
            print(f"  gate KEEPS n={trunc['n_kept']}  median STD60="
                  f"{trunc['median_kept']:.4f}")
            if trunc["ratio"]:
                print(f"  -> dropped names carry {trunc['ratio']:.2f}x the kept "
                      f"median of the feature the model leans on most")
        else:
            print("  no OHLCV rows found -- check --ohlcv-dir")

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(result, fh, indent=2)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
