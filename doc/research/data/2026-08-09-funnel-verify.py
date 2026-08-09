"""Assert the research note's quoted numbers against committed artifacts."""
import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
S = json.load(open(HERE / "2026-08-09-funnel-summary.json"))
c = pd.read_csv(HERE / "2026-08-09-funnel-candidates.csv")
bad = []
if S["n_selected_buys"] != 3: bad.append("buys")
if S["n_blocked"] != int((c.blocked_by.notna() & (c.blocked_by != "")).sum()): bad.append("blocked-recount")
p = {r["blocked_by"]: r["n"] for r in S["pareto"]}
if p.get("veto:rank_score_below_floor") != 2390: bad.append("rank-floor")
if p.get("regime_admission:failed:BULL_CALM") != 1155: bad.append("bull-calm")
if bad: print("DRIFT:", bad); sys.exit(1)
print(f"VERIFIED — note numbers reproduce from committed rows: "
      f"{S['n_selected_buys']} buys / {S['n_blocked']} blocks / "
      f"rank-floor {p['veto:rank_score_below_floor']} / BULL_CALM {p['regime_admission:failed:BULL_CALM']}")
