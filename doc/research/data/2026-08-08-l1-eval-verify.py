"""Verifier: recompute every reported L1 statistic from the committed daily CSV
alone (no OHLCV, no regime artifact, no DB). Default mode = verify."""
from pathlib import Path
import numpy as np, pandas as pd

df = pd.read_csv(Path(__file__).with_name('2026-08-08-l1-eval-daily.csv'),
                 index_col=0, parse_dates=True)

def stats(ser, name):
    ser = ser.dropna()
    ann = (1 + ser).prod() ** (252 / len(ser)) - 1
    vol = ser.std() * np.sqrt(252)
    cum = (1 + ser).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    print(f'{name:34s} ann {ann*100:+7.1f}%  vol {vol*100:5.1f}%  '
          f'sharpe {ann/vol:5.2f}  maxDD {dd*100:6.1f}%')

print(f'days={len(df)} span {df.index[0].date()}..{df.index[-1].date()}  '
      f'mean exposure {df["exposure"].mean()*100:.0f}%  '
      f'turnover {df["exposure"].diff().abs().sum()/(len(df)/252):.1f}x/yr')
stats(df['ret_uni'],  'fully-invested universe EW')
stats(df['ret_ctrl'], 'L1 controller (net of costs)')
for span in ('2024-01-01', '2022-01-01'):
    stats(df['ret_uni'].loc[span:],  f'  full-invest {span[:4]}..')
    stats(df['ret_ctrl'].loc[span:], f'  controller  {span[:4]}..')
