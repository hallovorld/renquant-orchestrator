"""L1 deployment-controller evaluation. PARAMETERS FROZEN HERE, BEFORE OUTPUT:
   lambda=0.94 (RiskMetrics EWMA) | sigma*=0.15 | kappa_bear=0.5
   kappa_vol=0.25 | E_min=0.3 | E_max=1.0 | cost=10bps per unit |dE|
Underlying = universe EW (the investable proxy; the accidental live book has
only 63 observable days and is compared separately on its own window).
Regime input = the committed 2026-08-08-regime-posteriors.csv beside this file
(production HMM posteriors snapshot); OHLCV stays machine-local (provenance)."""
import json, sys
sys.path.insert(0,"/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close
LAM, SSTAR, KB, KV, EMIN, EMAX, COST = 0.94, 0.15, 0.5, 0.25, 0.3, 1.0, 10/1e4
HERE=__import__('pathlib').Path(__file__).parent
sec=json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
rets={}
for t in [x for x,s in sec.items() if s not in ('benchmark','defensive_bonds')]:
    try:
        df=pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div=df['dividend'] if 'dividend' in df.columns else pd.Series(0.0,index=df.index)
        rets[t]=total_return_close(df['close'],div).pct_change()
    except FileNotFoundError: pass
uni=pd.DataFrame(rets).loc['2017-01-01':].mean(axis=1).dropna()
reg=pd.read_csv(HERE/'2026-08-08-regime-posteriors.csv', index_col=0)
reg.index=pd.to_datetime(reg.index)
pb=reg['regime_p_bear'].reindex(uni.index).ffill().fillna(0)
pv=reg['regime_p_bull_volatile'].reindex(uni.index).ffill().fillna(0)
# EWMA vol, annualized, shifted 1d (no lookahead)
var=uni.pow(2).ewm(alpha=1-LAM).mean()
sig=np.sqrt(var*252).shift(1)
g=(1 - KB*pb - KV*pv).shift(1).clip(lower=0)
expo=((SSTAR/sig)*g).clip(EMIN,EMAX).fillna(EMIN)
cost=expo.diff().abs().fillna(0)*COST
ctrl=expo*uni - cost
def stats(ser,name):
    ser=ser.dropna(); ann=(1+ser).prod()**(252/len(ser))-1
    vol=ser.std()*np.sqrt(252); cum=(1+ser).cumprod()
    dd=(cum/cum.cummax()-1).min()
    print(f'{name:34s} ann {ann*100:+7.1f}%  vol {vol*100:5.1f}%  sharpe {ann/vol:5.2f}  maxDD {dd*100:6.1f}%')
print(f'days={len(uni)} span {uni.index[0].date()}..{uni.index[-1].date()}  mean exposure {expo.mean()*100:.0f}%  turnover {expo.diff().abs().sum()/ (len(uni)/252):.1f}x/yr')
stats(uni,'fully-invested universe EW')
stats(ctrl,'L1 controller (net of costs)')
for span in ('2024-01-01','2022-01-01'):
    stats(uni.loc[span:],f'  full-invest {span[:4]}..')
    stats(ctrl.loc[span:],f'  controller  {span[:4]}..')
# BEAR-day behavior
bearmask=(pb.shift(1)>0.5).reindex(uni.index).fillna(False)  # the SIGNAL the controller acted on — same lag, no future alignment
if bearmask.sum()>10:
    stats(uni[bearmask],'  full-invest on HIGH-bear days')
    stats(ctrl[bearmask],'  controller  on HIGH-bear days')
pd.DataFrame({'ret_uni':uni,'exposure':expo,'ret_ctrl':ctrl}).to_csv(HERE/'2026-08-08-l1-eval-daily.csv')
print('daily series saved')
