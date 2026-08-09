"""L2 cost pass. FROZEN BEFORE OUTPUT: one-way cost 10bps on traded notional;
a top-3 name swap trades 2/3 notional (sell 1/3 + buy 1/3) -> cost_t =
(names_changed/3) * 2 * 0.0010. Costs enter r_i BEFORE the clip transform
(§2 contract rule 4). Hedge-layer reallocation cost ignored with statement:
|dw| ~ 1e-3/day * 20bps round trip ~ 0.005bp/day, three orders below arm costs."""
import glob, hashlib, json, sys
sys.path.insert(0,"/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close
SP='/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad'
ETA, C, FLOOR, COST1W = 0.21, 0.05, 0.5, 0.0010
sec=json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
rets={}
for t in [x for x,s in sec.items() if s not in ('benchmark','defensive_bonds')]:
    try:
        df=pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div=df['dividend'] if 'dividend' in df.columns else pd.Series(0.0,index=df.index)
        rets[t]=total_return_close(df['close'],div).pct_change()
    except FileNotFoundError: pass
R=pd.DataFrame(rets).loc['2023-06-01':]
panel={}
for f in sorted(glob.glob(f'{SP}/served_matrix_replay/*/wf_replay_panel__*.parquet')):
    d=f.split('/')[-2]; df=pd.read_parquet(f); panel[d]=dict(zip(df['ticker'],df['score']))
mom=json.load(open(f'{SP}/momentum_dense_scores.json'))
slow={r['date']:r['slow'] for r in mom if isinstance(r.get('slow'),dict) and 'error' not in r['slow'] and len(r['slow'])>=30}
fast={r['date']:r['fast'] for r in mom if isinstance(r.get('fast'),dict) and 'error' not in r['fast'] and len(r['fast'])>=30}
ARMS={'panel':panel,'mom_slow':slow,'mom_fast':fast}
def book(scores_by_date):
    sdates=sorted(scores_by_date); out={}; names_out={}
    si=0; cur=None; cur_d=None; prev=set()
    for t in R.index:
        ts=t.date().isoformat()
        while si<len(sdates) and sdates[si]<ts:
            cur=scores_by_date[sdates[si]]; cur_d=sdates[si]; si+=1
        if cur is None or (pd.Timestamp(ts)-pd.Timestamp(cur_d)).days>7: continue
        row=R.loc[t]
        elig={n:v for n,v in cur.items() if n in R.columns and row[n]==row[n]}
        if len(elig)<3: continue
        names=set(n for n,_ in sorted(elig.items(),key=lambda kv:-kv[1])[:3])
        changed=len(names-prev) if prev else 0
        gross=row[list(names)].mean()
        out[t]=gross-(changed/3)*2*COST1W
        names_out[t]=changed
        prev=names
    return pd.Series(out), pd.Series(names_out)
net={}; churn={}
for a,s in ARMS.items():
    net[a],churn[a]=book(s)
arm=pd.DataFrame(net).dropna()
ch=pd.DataFrame(churn).reindex(arm.index)
def run_hedge(rets):
    w=np.array([FLOOR,(1-FLOOR)/2,(1-FLOOR)/2]); ws=[]; port=[]
    for _,r in rets.iterrows():
        rv=r.values; port.append(float(w@rv)); ws.append(w.copy())
        w=w*np.exp(ETA*np.clip(rv,-C,C)); w=w/w.sum()
        if w[0]<FLOOR: w[1:]*= (1-FLOOR)/(1-w[0]); w[0]=FLOOR
    return np.array(ws), pd.Series(port,index=rets.index)
ws,hedge=run_hedge(arm)
def stats(s,name):
    a=(1+s).prod()**(252/len(s))-1; vol=s.std()*np.sqrt(252)
    cum=(1+s).cumprod(); dd=(cum/cum.cummax()-1).min()
    print(f'{name:26s} ann {a*100:+7.1f}%  sharpe {a/vol:5.2f}  maxDD {dd*100:6.1f}%')
print(f'{len(arm)} days; mean names-changed/day: '+', '.join(f'{a}={ch[a].mean():.2f}' for a in arm))
print(f'annualized cost drag (pp): '+', '.join(f'{a}={ch[a].mean()*2/3*COST1W*252*100:.1f}' for a in arm))
print('\n== NET of arm-level costs ==')
for a in arm: stats(arm[a],a)
stats(hedge,'HEDGE net (floor 0.5)')
stats(arm.mean(axis=1),'uniform 1/3 net')
pd.concat([arm.add_suffix('_net'), ch.add_suffix('_churn'),
           hedge.rename('hedge_net'),
           pd.DataFrame(ws,index=arm.index,columns=[f'w_{c}' for c in arm.columns])],axis=1)\
  .to_csv(f'{SP}/l2_cost_pass_daily.csv')
print('CSV saved')
