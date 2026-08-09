"""Real-frame sector table — the frozen derivation contract (orch#940 r1).

Re-emits every number behind doc/research/2026-08-09-realframe-sector-table.md
from read-only inputs and REFUSES if the committed row CSVs drift. Run with the
umbrella venv:

  /Users/renhao/git/github/RenQuant/.venv/bin/python \
      doc/research/data/2026-08-09-realframe-sector-derivation.py

Frozen query contract (the measurement surface, stated once, exactly):

  SCORES  runs DB /Users/renhao/git/github/RenQuant/data/runs.alpaca.db
          (sqlite, uri mode=ro). Rows: ticker_daily_state JOIN pipeline_runs
          ON run_id WHERE run_type='live' AND panel_score IS NOT NULL AND
          date BETWEEN '2026-05-20' AND '2026-08-07' (frozen bounds; the DB
          grows). NOT candidate_scores — ticker_daily_state is the live
          system's own per-name daily snapshot; candidate_scores covers fewer
          dates (41 vs 43 on this window) because not every scoring pass
          emits candidates.
  AS-OF   per (date, ticker) the FIRST recorded panel_score of the day wins
          (order by pipeline_runs.created_at) — the day's first scoring pass,
          before intraday reruns rescore a thinned set. The winning row's
          run_id + created_at are recorded per name in the rows CSV.
  SECTOR  the frozen #934 map committed at 2026-08-09-l2s-true-map.csv.
          The DB's own ticker_daily_state.sector column is asserted to agree
          wherever it is non-null (it is null on 144 rows of this window).
  K       the #934 tiers: software 3 / industrial 3 / finance 3 / ai_chip 2 /
          consumer 2 / datacenter_hw 2. DESCRIPTIVE LENS ONLY — the L2-S run
          that produced these tiers recorded RECORD-ONLY, so they are a
          declared slicing convention here, not a validated allocation rule.
  TIES    top-k = sort by (panel_score DESC, ticker ASC), take k.
  RETURN  per-ticker total-return close series c*(t): cumulative product of
          (close_t + dividend_t) / close_{t-1} over the ticker's own daily
          bars in /Users/renhao/git/github/RenQuant/data/ohlcv/<T>/1d.parquet
          (read-only). fwd5(d, t) = c*(s_5) / c*(d) - 1 where s_5 is the 5th
          bar AFTER d on the ticker's own bar index. ENTRY is the close of
          the score date d itself — timing-safe because the winning score row
          is stamped at the morning live pass (created_at, recorded per row),
          hours before that close. Names missing a bar at d or s_5 are
          excluded from that sector-day (n_scored vs n_priced in the CSV).
  DAYS    a sector-day is admitted iff n_priced >= k; days where
          n_priced == k contribute a zero edge by construction (top-k is the
          whole basket) and are kept, visibly, in the CSV.
  POOLED  per-sector edge = mean over that sector's admitted days of
          (topk_mean - ew_mean); pooled edge = the same mean over ALL
          admitted sector-days, each weighted 1 (day-count weighting).

Published numbers are asserted against the committed CSVs:
  2026-08-09-realframe-sector-rows.csv   per (date, ticker): run_id,
      created_at, panel_score, sector, fwd5, in_topk
  2026-08-09-realframe-sector-days.csv   per (date, sector): n_scored,
      n_priced, topk_tickers, topk_fwd5, ew_fwd5, edge_bp
"""
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DB = 'file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro'
OHLCV = '/Users/renhao/git/github/RenQuant/data/ohlcv/{}/1d.parquet'
D0, D1 = '2026-05-20', '2026-08-07'
K = {'software': 3, 'industrial': 3, 'finance': 3,
     'ai_chip': 2, 'consumer': 2, 'datacenter_hw': 2}
HORIZON = 5


def load_first_scores():
    raw = pd.read_sql(
        """SELECT t.date, t.ticker, t.panel_score, t.sector AS db_sector,
                  t.run_id, p.created_at
           FROM ticker_daily_state t JOIN pipeline_runs p ON p.run_id=t.run_id
           WHERE p.run_type='live' AND t.panel_score IS NOT NULL
             AND t.date BETWEEN ? AND ?""",
        sqlite3.connect(DB, uri=True), params=(D0, D1))
    first = (raw.sort_values('created_at')
             .groupby(['date', 'ticker'], as_index=False).first())
    smap = (pd.read_csv(HERE / '2026-08-09-l2s-true-map.csv')
            .set_index('ticker').label.to_dict())
    first['sector'] = first.ticker.map(smap)
    clash = first[first.db_sector.notna() & (first.db_sector != first.sector)]
    assert clash.empty, f'DB sector column disagrees with frozen map: {clash}'
    return first.drop(columns='db_sector')


def tr_close(ticker, cache={}):
    if ticker not in cache:
        try:
            df = pd.read_parquet(OHLCV.format(ticker))
        except FileNotFoundError:
            cache[ticker] = None
            return None
        div = df['dividend'] if 'dividend' in df.columns else 0.0
        ret = (df['close'] + div) / df['close'].shift(1) - 1
        cache[ticker] = (1 + ret.fillna(0)).cumprod()
    return cache[ticker]


def fwd5(ticker, date):
    s = tr_close(ticker)
    if s is None:
        return None
    try:
        i = s.index.get_loc(pd.Timestamp(date))
    except KeyError:
        return None
    if i + HORIZON >= len(s):
        return None
    return float(s.iloc[i + HORIZON] / s.iloc[i] - 1)


def main():
    first = load_first_scores()
    dates = sorted(first.date.unique())
    assert (len(dates), dates[0], dates[-1]) == (43, D0, D1), (
        len(dates), dates[0], dates[-1])

    first['fwd5'] = [fwd5(t, d) for t, d in zip(first.ticker, first.date)]
    first['in_topk'] = False
    days = []
    for (d, sec), g in first.groupby(['date', 'sector']):
        if sec not in K:
            continue
        priced = g.dropna(subset=['fwd5'])
        if len(priced) < K[sec]:
            continue
        topk = priced.sort_values(['panel_score', 'ticker'],
                                  ascending=[False, True]).head(K[sec])
        first.loc[topk.index, 'in_topk'] = True
        days.append(dict(
            date=d, sector=sec, n_scored=len(g), n_priced=len(priced),
            topk_tickers=' '.join(topk.ticker),
            topk_fwd5=round(float(topk.fwd5.mean()), 6),
            ew_fwd5=round(float(priced.fwd5.mean()), 6)))
    days = pd.DataFrame(days)
    days['edge_bp'] = ((days.topk_fwd5 - days.ew_fwd5) * 1e4).round(1)

    per = days.groupby('sector').agg(
        days=('date', 'count'), topk=('topk_fwd5', 'mean'),
        ew=('ew_fwd5', 'mean'), edge_bp=('edge_bp', 'mean'))
    per['edge_bp'] = per.edge_bp.round(1)
    pooled_bp = round(float(days.edge_bp.mean()), 1)
    print(per.sort_values('edge_bp', ascending=False)
          .to_string(float_format=lambda x: f'{x:.4f}'))
    print(f'pooled edge {pooled_bp} bp/5d over {len(days)} sector-days, '
          f'{days.date.nunique()} usable dates; '
          f'{int((days.n_priced == days.sector.map(K)).sum())} sector-days '
          'contribute a zero edge by construction (n_priced == k)')

    rows = first[first.sector.isin(K)].copy()
    rows['panel_score'] = rows.panel_score.round(6)
    rows['fwd5'] = rows.fwd5.round(6)
    rows = rows[['date', 'ticker', 'sector', 'run_id', 'created_at',
                 'panel_score', 'fwd5', 'in_topk']]
    for name, frame in [('2026-08-09-realframe-sector-rows.csv', rows),
                        ('2026-08-09-realframe-sector-days.csv', days)]:
        p = HERE / name
        if p.exists():
            pd.testing.assert_frame_equal(
                frame.reset_index(drop=True), pd.read_csv(p),
                check_dtype=False)
            print(f'matches committed {name}')
        else:
            frame.to_csv(p, index=False)
            print(f'wrote {name}')


if __name__ == '__main__':
    main()
