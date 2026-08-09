"""Re-assert the note's quoted numbers from the committed artifacts alone."""
import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
S = json.load(open(HERE / "2026-08-09-funnel-summary.json"))
c = pd.read_csv(HERE / "2026-08-09-funnel-candidates.csv")
k = pd.read_csv(HERE / "2026-08-09-funnel-cash.csv")
bad = []
if S["n_selected_buys"] != int(c.selected.sum()): bad.append("buys")
if S["n_block_events"] != int((c.blocked_by.notna() & (c.blocked_by != "")).sum()): bad.append("blocks")
p = {r["blocked_by"]: r["n_events"] for r in S["pareto"]}
if p.get("veto:rank_score_below_floor") != 2390: bad.append("rank-floor")
if p.get("regime_admission:failed:BULL_CALM") != 1155: bad.append("bull-calm")
if abs(S["mean_cash_frac"] - (k.cash / k.portfolio_value).mean()) > 1e-4: bad.append("cash-frac")
if not c.run_id.notna().all(): bad.append("run-id-missing")
if bad: print("DRIFT:", bad); sys.exit(1)
print(f"VERIFIED — {S['n_selected_buys']} buys / {S['n_block_events']} block-events / "
      f"rank-floor {p['veto:rank_score_below_floor']} / BULL_CALM {p['regime_admission:failed:BULL_CALM']} / "
      f"mean cash {S['mean_cash_frac']:.1%} (drag ${S['cash_drag_usd_yr_at_8pct_ASSUMED']}/yr at 8% ASSUMED)")
