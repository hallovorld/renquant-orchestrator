"""Daily-full buy-book preview with the calibrated-μ gate ENABLED.

Reproduces the live buy decision on real data (asof 2026-06-10): score -> gate
(signal_gate_prefer_calibrated_mu) -> calibrated μ -> faithful half-Kelly size
(f*=μ/σ², caps min(max_pct, max_concentration, fractional·f*)) -> fill open
slots (max_concurrent_positions − current holdings). No orders; review only.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))

OHLCV_ROOT = "RenQuant/data/ohlcv"
MODEL_PATH = ("RenQuant/artifacts/patchtst_shadow/"
              "pt07_strict_trainfit_embargo60_20260522/seed_44/"
              "hf_patchtst_all_seed44_model.pt")
CAL_PATH = ("RenQuant/backtesting/renquant_104/artifacts/shadow/"
            "panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG_PATH = "renquant-strategy-104/configs/strategy_config.json"
LIVE_STATE = "RenQuant/backtesting/renquant_104/live_state.alpaca.json"
ASOF = pd.Timestamp("2026-06-10")

from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
from renquant_pipeline.kernel.pipeline.signal_direction import long_signal_ok
from renquant_pipeline.kernel.kelly import kelly_target_pct


class _Ctx:
    pass


def _realized_annual_vol(df, window=60, floor=0.05, ceil=1.5):
    rets = df["close"].pct_change().dropna().tail(window)
    if len(rets) < 5:
        return None
    sig = float(rets.std() * np.sqrt(252.0))
    return min(max(sig, floor), ceil)


def main():
    cfg = json.load(open(CFG_PATH))
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"] = "stable"
    cfg["ranking"]["panel_scoring"]["signal_gate_prefer_calibrated_mu"] = True
    ks = cfg["ranking"]["kelly_sizing"]
    fractional = float(ks.get("fractional", 0.5))
    max_conc = float(ks.get("max_concentration", 0.12))
    max_pct = float(cfg.get("position_sizing", {}).get("max_position_pct", 0.15))
    slots = int(cfg.get("max_concurrent_positions", 8))
    cash = float(cfg.get("initial_cash", 100000))

    live = json.load(open(LIVE_STATE))
    held = list((live.get("entry_dates") or {}).keys())
    regime = live.get("regime")
    print(f"asof {ASOF.date()} | regime={regime} | held={held} "
          f"({len(held)}/{slots} slots) | skip_buys={live.get('skip_buys')}")

    scorer = HFPatchTSTPanelScorer.load(MODEL_PATH)
    ohlcv = {}
    for t in cfg["watchlist"]:
        p = f"{OHLCV_ROOT}/{t}/1d.parquet"
        if os.path.exists(p):
            df = pd.read_parquet(p)
            df = df[df.index <= ASOF]
            if len(df):
                ohlcv[t] = df
    ctx = _Ctx(); ctx.ohlcv = ohlcv; ctx.config = cfg; ctx.holdings = {}
    ctx.models = {}; ctx.today = ASOF
    ph = J._build_live_panel_history(ctx, scorer, list(ohlcv.keys()), ASOF)
    scores = scorer.score_with_history(ph, list(ohlcv.keys())).dropna()
    cal = GlobalPanelCalibration.load(CAL_PATH)

    rows = []
    for t, s in scores.items():
        mu = cal.expected_return(float(s))
        ok, _ = long_signal_ok(float(s), cfg, expected_return=mu)
        if not ok:
            continue
        sigma = _realized_annual_vol(ohlcv[t])
        kt = kelly_target_pct(mu, sigma, max_pct=max_pct,
                              max_concentration=max_conc, fractional=fractional,
                              min_edge=float(ks.get("min_edge", 0.0)))
        rows.append((t, float(s), mu, sigma, kt))
    rows.sort(key=lambda r: r[2], reverse=True)  # by μ (≈ rank)

    admitted = [r for r in rows if r[4] > 0]
    print(f"\ngate admits {len(rows)} names; {len(admitted)} get a non-zero Kelly target.")
    open_slots = max(0, slots - len(held))
    new_buys = [r for r in admitted if r[0] not in held][:open_slots]
    print(f"open slots = {slots} − {len(held)} held = {open_slots} → top {len(new_buys)} NEW buys:\n")
    print(f"  {'ticker':7s}{'raw':>9s}{'mu(60d)':>9s}{'vol(ann)':>10s}{'kelly%':>8s}{'$size':>10s}")
    for t, s, mu, sigma, kt in new_buys:
        print(f"  {t:7s}{s:>+9.4f}{mu:>+9.4f}{sigma:>10.2f}{kt*100:>7.1f}%{kt*cash:>10,.0f}")
    tot = sum(r[4] for r in new_buys)
    print(f"\n  total new deployment ≈ {tot*100:.0f}% of book (${tot*cash:,.0f}); "
          f"MU/EQIX already held (may top-up).")
    # Note held names that also rank well (top-up candidates)
    held_ranked = [r for r in admitted if r[0] in held]
    if held_ranked:
        print("  held names still ranked bullish (top-up candidates): "
              + ", ".join(f"{t}(μ{mu:+.3f})" for t, _, mu, _, _ in held_ranked))


if __name__ == "__main__":
    main()
