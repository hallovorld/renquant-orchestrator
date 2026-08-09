"""Capital-funnel Pareto — versioned read-only derivation, r2.

SEMANTICS (review r2 — every term defined here, not in prose):
* Window: live sessions with candidate rows, 2026-05-20..2026-08-07.
* Population: ticker_daily_state rows with in_candidates=1 joined to their
  OWN run (run_id) — rows are (run, ticker) BLOCK-EVENTS. A ticker blocked
  in two runs on one date counts twice in event counts; unique-candidate
  counts are reported separately. No cross-run dedup is applied to events.
* As-of rule: ALL live runs in the window are included (not just the widest
  per date); run_id, run created_at, and the run's artifact fingerprint
  (commit_sha, training_cutoff, model_content_sha256) are carried per row so any slice can be re-cut.
* Buy definition: selected=1 on the row (a BUY order was placed that bar).
* Gate-evaluation order: owned by the kernel
  (panel_pipeline/admission_tasks.py; portfolio_qp/tasks.py) — blocked_by
  records the FIRST gate that dropped the row; this derivation counts, it
  does not re-adjudicate order.
* Cash accounting: close-of-run cash and portfolio_value from
  live_state_snapshots (the audit row) per run_date; cash_frac =
  cash/portfolio_value; window mean reported. Cash DRAG in $/yr =
  mean(cash) x R_OPP where R_OPP=0.08 is an ASSUMED opportunity rate,
  reported as such (the G-E record's convention).
"""
import json, sqlite3, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
DB = sys.argv[1] if len(sys.argv) > 1 else "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
W0, W1 = "2026-05-20", "2026-08-07"
R_OPP = 0.08
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
rows = pd.read_sql_query(f"""
  SELECT t.date, t.ticker, t.blocked_by, t.kelly_target_pct, t.selected,
         t.run_id, p.created_at AS run_created_at,
         p.commit_sha, p.training_cutoff, p.model_content_sha256
  FROM ticker_daily_state t JOIN pipeline_runs p ON p.run_id = t.run_id
  WHERE p.run_type='live' AND t.in_candidates=1 AND t.date>='{W0}' AND t.date<='{W1}'""", con)
cash = pd.read_sql_query(f"""
  SELECT run_date, cash, portfolio_value FROM live_state_snapshots
  WHERE run_date>='{W0}' AND run_date<='{W1}' ORDER BY run_date""", con)
con.close()
rows["blocked"] = rows.blocked_by.notna() & (rows.blocked_by != "")
rows.to_csv(HERE / "2026-08-09-funnel-candidates.csv", index=False)
cash = cash.drop_duplicates("run_date", keep="last")
cash["cash_frac"] = cash.cash / cash.portfolio_value
cash.to_csv(HERE / "2026-08-09-funnel-cash.csv", index=False)
per_sess = rows.groupby("date").agg(
    n_block_events=("blocked", "sum"), n_unique_candidates=("ticker", "nunique"),
    n_selected=("selected", "sum"), n_runs=("run_id", "nunique")).reset_index()
per_sess.to_csv(HERE / "2026-08-09-funnel-sessions.csv", index=False)
pareto = (rows[rows.blocked].groupby("blocked_by")
          .agg(n_events=("ticker", "count"), n_unique_tickers=("ticker", "nunique"),
               kelly_pp=("kelly_target_pct", "sum"))
          .sort_values("n_events", ascending=False).reset_index())
summary = {"window": [W0, W1], "semantics": "see module docstring",
           "n_sessions": int(rows.date.nunique()),
           "n_block_events": int(rows.blocked.sum()),
           "n_unique_candidate_tickers": int(rows.ticker.nunique()),
           "n_selected_buys": int(rows.selected.sum()),
           "mean_cash_frac": round(float(cash.cash_frac.mean()), 4),
           "mean_cash_usd": round(float(cash.cash.mean()), 2),
           "cash_drag_usd_yr_at_8pct_ASSUMED": round(float(cash.cash.mean() * R_OPP), 2),
           "pareto": pareto.head(12).to_dict("records")}
(HERE / "2026-08-09-funnel-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: summary[k] for k in ("n_sessions", "n_block_events", "n_selected_buys", "mean_cash_frac", "cash_drag_usd_yr_at_8pct_ASSUMED")}))
