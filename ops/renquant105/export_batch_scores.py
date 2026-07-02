#!/usr/bin/env python3
"""rq105: export the FROZEN batch score vector for today's session (N1 open
item #1 — the producer for shadow_realtime_serving --batch-scores-json).

Reads the latest daily FULL run strictly BEFORE today's session from
runs.alpaca.db (the 13:55 PT batch of the prior session is the class-A frozen
signal for today, #208 §6) and writes:

  data/rq105/batch_scores_<today>.json        flat {ticker: panel_score}
  data/rq105/batch_scores_<today>.meta.json   {run_id, score_kind, n, exported_at}

Read-only against the DB; writes only the dedicated data/rq105/ path. Fails
loudly (exit 1 + ntfy via wrapper) if no qualifying run exists — the shadow
serving driver then skips the day rather than serving a stale vector silently.
"""
import datetime as dt
import json
import os
import sqlite3
import sys

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
OUT_DIR = os.path.join(RQ, "data", "rq105")
MIN_ROWS = 80  # a daily FULL run scores the whole watchlist


def main() -> int:
    today = dt.date.today().isoformat()
    con = sqlite3.connect(DB)
    run = con.execute(
        "select run_id, count(*) n from candidate_scores "
        "where run_id like '%-live-%' and substr(run_id,1,10) < ? "
        "group by run_id having n >= ? order by run_id desc limit 1",
        (today, MIN_ROWS)).fetchone()
    if not run:
        print(f"no qualifying full run before {today}", file=sys.stderr)
        return 1
    run_id = run[0]
    rows = con.execute(
        "select ticker, panel_score from candidate_scores "
        "where run_id=? and panel_score is not null", (run_id,)).fetchall()
    scores = {t: float(s) for t, s in rows}
    if len(scores) < MIN_ROWS // 2:
        print(f"run {run_id} has only {len(scores)} scored names", file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"batch_scores_{today}.json"), "w") as f:
        json.dump(scores, f, sort_keys=True)
    with open(os.path.join(OUT_DIR, f"batch_scores_{today}.meta.json"), "w") as f:
        json.dump({"run_id": run_id, "score_kind": "panel_score",
                   "n": len(scores), "session_date": today,
                   "exported_at": dt.datetime.utcnow().isoformat() + "Z"}, f, indent=2)
    print(f"exported {len(scores)} frozen scores from {run_id} for session {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
