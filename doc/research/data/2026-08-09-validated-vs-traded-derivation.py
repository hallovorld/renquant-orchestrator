"""Validated-vs-traded forensics — the durable rerun contract (orch#938 r1).

Re-emits the exact table behind doc/research/2026-08-09-validated-vs-traded-
forensics.md from read-only inputs, asserts every published number, and
REFUSES if an input drifted. Run with the umbrella venv:

  /Users/renhao/git/github/RenQuant/.venv/bin/python \
      doc/research/data/2026-08-09-validated-vs-traded-derivation.py

Inputs (all read-only):
  SERVED  runs DB  /Users/renhao/git/github/RenQuant/data/runs.alpaca.db
          (sqlite, uri mode=ro). Rows: candidate_scores JOIN pipeline_runs ON
          run_id WHERE run_type='live' AND role='candidate' AND
          run_date<='2026-08-07' (the forensics as-of date; the DB grows).
          Score = panel_score; per (date, ticker) the FIRST recorded value of
          the day wins (order by pipeline_runs.created_at) — the day's first
          scoring pass, before intraday reruns rescore a thinned set.
  REPLAY  bt#110 served matrix (run wfreplay-2026-08-08, config on orch#905):
          <scratchpad>/served_matrix_replay/<date>/wf_replay_panel__*.parquet
          hash-pinned by 2026-08-09-l2-backtest-inputs.manifest.json
          (digest-of-digests x1685). REFUSES on digest mismatch. If the
          scratchpad is gone, re-emit via renquant-backtesting:
          `python -m renquant_backtesting.wf_gate.wf_sanity_paired \
               --emit-served-matrix --panel <panel.parquet> --out-dir <dir> \
               --run-id <id>` then re-pin.
  CONFIG  renquant-strategy-104 configs/strategy_config.json read FROM GIT at
          the manifest-recorded commit aa775931 (immune to later edits):
          ranking.panel_scoring.kind, the _2026_06_23_xgb_promotion note, the
          panel_ltr._lookahead_days_reason_2026-05-10 note ("trained
          2026-05-09").

Published numbers asserted below: 58 live candidate dates 2026-04-23..
2026-08-07; 5 shared dates; mean widths served 22.0 / replay 147.8; top-3
overlap 0/15; Spearman per-date [0.09, -0.42, 0.67, 0.18, 0.20] mean 0.144.
Output is compared row-for-row against the committed
2026-08-09-validated-vs-traded-rows.csv.
"""
import glob
import hashlib
import io
import json
import sqlite3
import subprocess
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

HERE = Path(__file__).parent
DB = 'file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro'
S104 = '/Users/renhao/git/github/renquant-strategy-104'
ASOF = '2026-08-07'


def _fsha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def load_replay_matrix():
    """Digest-verify the pinned replay matrix, then load dates >= 2026-04-01."""
    man = json.load(open(HERE / '2026-08-09-l2-backtest-inputs.manifest.json'))
    pin = man['inputs']['panel_replay_matrix']
    files = sorted(glob.glob(pin['dir'] + '/*/wf_replay_panel__*.parquet'))
    h = hashlib.sha256()
    for f in files:
        h.update(f.split('/')[-1].encode())
        h.update(_fsha(f).encode())
    assert (h.hexdigest(), len(files)) == (pin['digest_of_digests'], pin['n_files']), (
        'replay matrix digest mismatch — re-emit per module docstring, then re-pin')
    rep = {}
    for f in files:
        d = f.split('/')[-2]
        if d >= '2026-04-01':
            df = pd.read_parquet(f)
            rep[d] = dict(zip(df['ticker'], df['score']))
    return rep, man


def load_served():
    db = sqlite3.connect(DB, uri=True)
    q = """SELECT p.run_date, p.created_at, c.ticker, c.panel_score
           FROM candidate_scores c JOIN pipeline_runs p ON p.run_id = c.run_id
           WHERE p.run_type='live' AND c.role='candidate' AND p.run_date<=?"""
    return pd.read_sql(q, db, params=(ASOF,))


def config_facts(man):
    head = man['sibling_repo_heads']['renquant-strategy-104']
    raw = subprocess.run(
        ['git', '-C', S104, 'show', f'{head}:configs/strategy_config.json'],
        capture_output=True, text=True, check=True).stdout
    cfg = json.loads(raw)
    ps = cfg['ranking']['panel_scoring']
    assert ps['kind'] == 'blend', ps['kind']
    assert '_2026_06_23_xgb_promotion' in ps
    assert 'trained 2026-05-09' in cfg['panel_ltr']['_lookahead_days_reason_2026-05-10']
    print(f'config @ {head[:8]}: ranking.panel_scoring.kind=blend; '
          '_2026_06_23_xgb_promotion present; panel-ltr trained 2026-05-09')


def main():
    rep, man = load_replay_matrix()
    served = load_served()
    config_facts(man)

    dates = sorted(served.run_date.unique())
    assert (len(dates), dates[0], dates[-1]) == (58, '2026-04-23', ASOF), (
        len(dates), dates[0], dates[-1])
    shared = sorted(set(dates) & set(rep))
    assert shared == ['2026-04-23', '2026-04-24', '2026-04-27',
                      '2026-05-04', '2026-05-06'], shared

    rows = []
    for d in shared:
        s = (served[served.run_date == d].sort_values('created_at')
             .groupby('ticker').panel_score.first().dropna())
        r = pd.Series(rep[d])
        inter = s.index.intersection(r.index)
        t3s, t3r = list(s.nlargest(3).index), list(r.nlargest(3).index)
        rows.append(dict(
            date=d, served_width=len(s), replay_width=len(r),
            served_top3=' '.join(t3s), replay_top3=' '.join(t3r),
            top3_overlap=len(set(t3s) & set(t3r)), n_intersection=len(inter),
            spearman=round(float(spearmanr(s[inter], r[inter]).statistic), 6)))
    out = pd.DataFrame(rows)
    print(out.to_string(index=False))

    assert out.served_width.mean() == 22.0, out.served_width.mean()
    assert round(out.replay_width.mean(), 1) == 147.8, out.replay_width.mean()
    assert out.top3_overlap.sum() == 0
    assert [round(x, 2) for x in out.spearman] == [0.09, -0.42, 0.67, 0.18, 0.20]
    assert round(out.spearman.mean(), 3) == 0.144, out.spearman.mean()

    committed = HERE / '2026-08-09-validated-vs-traded-rows.csv'
    if committed.exists():
        pd.testing.assert_frame_equal(out, pd.read_csv(committed))
        print(f'matches committed {committed.name}; all published numbers reproduced')
    else:
        buf = io.StringIO()
        out.to_csv(buf, index=False)
        committed.write_text(buf.getvalue())
        print(f'wrote {committed.name}')


if __name__ == '__main__':
    main()
