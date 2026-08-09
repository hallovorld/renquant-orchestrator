"""Capital-funnel Pareto — versioned read-only derivation (orch#943 r1).
Reads runs.alpaca.db (mode=ro), writes: per-candidate rows CSV, per-session
summary CSV, and the Pareto JSON the research note quotes. Re-run any time;
the verifier asserts the note's numbers against these artifacts."""
import json, sqlite3, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
DB = sys.argv[1] if len(sys.argv) > 1 else "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
W0, W1 = "2026-05-20", "2026-08-07"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = pd.read_sql_query(f"""
  SELECT t.date, t.ticker, t.blocked_by, t.kelly_target_pct, t.selected, t.in_candidates
  FROM ticker_daily_state t JOIN pipeline_runs p ON p.run_id = t.run_id
  WHERE p.run_type='live' AND t.in_candidates=1 AND t.date>='{W0}' AND t.date<='{W1}'""", con)
con.close()
rows["blocked"] = rows.blocked_by.notna() & (rows.blocked_by != "")
rows.to_csv(HERE / "2026-08-09-funnel-candidates.csv", index=False)
per_sess = rows.groupby("date").agg(n_candidates=("ticker", "count"),
    n_blocked=("blocked", "sum"), n_selected=("selected", "sum")).reset_index()
per_sess.to_csv(HERE / "2026-08-09-funnel-sessions.csv", index=False)
pareto = (rows[rows.blocked].groupby("blocked_by")
          .agg(n=("ticker", "count"), kelly_pp=("kelly_target_pct", "sum"))
          .sort_values("n", ascending=False).reset_index())
summary = {"window": [W0, W1], "n_sessions": int(rows.date.nunique()),
           "n_candidate_rows": int(len(rows)), "n_blocked": int(rows.blocked.sum()),
           "n_selected_buys": int(rows.selected.sum()),
           "pareto": pareto.head(12).to_dict("records")}
(HERE / "2026-08-09-funnel-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ("n_sessions", "n_blocked", "n_selected_buys")}))
