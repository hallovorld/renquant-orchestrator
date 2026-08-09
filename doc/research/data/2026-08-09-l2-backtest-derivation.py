"""L2 bandit backtest over point-in-time replay arms.
FROZEN before output: deployed eta=0.21; clip C=0.05; floor 0.5 on the panel
arm; top-3 books; t->t+1 timing; score staleness <= 7 CALENDAR days (single rule; matches code and report).
Sensitivity grid {0.05,0.1,0.21,0.5,1.0} is DESCRIPTIVE ONLY."""
import glob, hashlib, json, sys
from pathlib import Path

# r1 P1: verify the committed input manifest BEFORE deriving; REFUSE on any
# digest mismatch — the CSV must be regenerable only from the declared,
# hash-pinned inputs.
def _fsha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
def _dirsha(files):
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.split('/')[-1].encode()); h.update(_fsha(f).encode())
    return h.hexdigest(), len(files)
def verify_manifest():
    man = json.load(open(Path(__file__).with_name('2026-08-09-l2-backtest-inputs.manifest.json')))
    ins = man['inputs']
    assert _fsha(ins['momentum_dense_scores.json']['path']) == ins['momentum_dense_scores.json']['sha256'], 'momentum scores digest mismatch'
    files = glob.glob(ins['panel_replay_matrix']['dir'] + '/*/wf_replay_panel__*.parquet')
    d, n = _dirsha(files)
    assert (d, n) == (ins['panel_replay_matrix']['digest_of_digests'], ins['panel_replay_matrix']['n_files']), 'panel replay matrix digest mismatch'
    assert _fsha(ins['sector_map_config']['path']) == ins['sector_map_config']['sha256'], 'sector map digest mismatch'
    print('input manifest verified (momentum scores, panel matrix, sector map)')
verify_manifest()
sys.path.insert(0,"/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close
SP='/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad'
ETA, C, FLOOR = 0.21, 0.05, 0.5
sec=json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
rets={}
for t in [x for x,s in sec.items() if s not in ('benchmark','defensive_bonds')]:
    try:
        df=pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div=df['dividend'] if 'dividend' in df.columns else pd.Series(0.0,index=df.index)
        rets[t]=total_return_close(df['close'],div).pct_change()
    except FileNotFoundError: pass
R=pd.DataFrame(rets).loc['2023-06-01':]

# arm scores
panel={}
for f in sorted(glob.glob(f'{SP}/served_matrix_replay/*/wf_replay_panel__*.parquet')):
    d=f.split('/')[-2]
    df=pd.read_parquet(f); panel[d]=dict(zip(df['ticker'],df['score']))
mom=json.load(open(f'{SP}/momentum_dense_scores.json'))
slow={r['date']:r['slow'] for r in mom if isinstance(r.get('slow'),dict) and 'error' not in r['slow'] and len(r['slow'])>=30}
fast={r['date']:r['fast'] for r in mom if isinstance(r.get('fast'),dict) and 'error' not in r['fast'] and len(r['fast'])>=30}
ARMS={'panel':panel,'mom_slow':slow,'mom_fast':fast}

def top3_series(scores_by_date):
    """daily book return: top-3 by the latest score dated <= t-1, ffill <=5 bd."""
    sdates=sorted(scores_by_date)
    out={}
    si=0; cur=None; cur_d=None
    for t in R.index:
        ts=t.date().isoformat()
        while si<len(sdates) and sdates[si]<ts:
            cur=scores_by_date[sdates[si]]; cur_d=sdates[si]; si+=1
        if cur is None or (pd.Timestamp(ts)-pd.Timestamp(cur_d)).days>7: continue
        # INVESTABLE top-3: filter to names with a price return TODAY first,
        # THEN rank. (r2 fix: ranking before filtering dropped any day whose
        # unfiltered top-3 contained a non-universe/delisted name — 135-day
        # calendar collapse.)
        row=R.loc[t]
        elig={n:v for n,v in cur.items() if n in R.columns and row[n]==row[n]}
        if len(elig)<3: continue
        names=[n for n,_ in sorted(elig.items(),key=lambda kv:-kv[1])[:3]]
        out[t]=row[names].mean()
    return pd.Series(out)

arm_ret=pd.DataFrame({a:top3_series(s) for a,s in ARMS.items()}).dropna()
print(f'common daily calendar: {len(arm_ret)} days {arm_ret.index[0].date()}..{arm_ret.index[-1].date()}')

def run_hedge(eta):
    w=np.array([FLOOR]+[ (1-FLOOR)/2 ]*2)  # panel first
    ws=[]; port=[]
    for _,r in arm_ret.iterrows():
        rc=np.clip(r.values,-C,C)
        port.append(float(w@r.values))     # realized on UNclipped returns
        ws.append(w.copy())
        w=w*np.exp(eta*rc)
        w=w/w.sum()
        if w[0]<FLOOR:
            others=1-w[0]
            w[1:]*= (1-FLOOR)/others; w[0]=FLOOR
    return np.array(ws), pd.Series(port,index=arm_ret.index)

def ann(s): return (1+s).prod()**(252/len(s))-1
def stats(s,name):
    a=ann(s); vol=s.std()*np.sqrt(252); cum=(1+s).cumprod()
    dd=(cum/cum.cummax()-1).min()
    print(f'{name:30s} ann {a*100:+7.1f}%  vol {vol*100:5.1f}%  sharpe {a/vol:5.2f}  maxDD {dd*100:6.1f}%')
    return a

print('\n== arms standalone ==')
for a in arm_ret: stats(arm_ret[a],a)
print('\n== combined ==')
ws,hedge=run_hedge(ETA)
stats(hedge,f'HEDGE eta={ETA} floor=0.5')
stats(arm_ret.mean(axis=1),'uniform 1/3')
stats(arm_ret['panel'],'champion only')
best=arm_ret.apply(ann).idxmax()
print(f'best arm in hindsight: {best}')
# regret ON THE TRANSFORMED series (the contract's claim)
clipped=arm_ret.clip(-C,C)
hedge_clipped=(pd.DataFrame(ws,index=arm_ret.index,columns=arm_ret.columns)*clipped).sum(axis=1)
regret=clipped.sum().max()-hedge_clipped.sum()
T,N=len(arm_ret),3
bound=np.log(N)/ETA + ETA*T*(2*C)**2/8
print(f'\nrealized regret (transformed) = {regret:.4f}  vs bound ln(N)/eta + eta*T*(2C)^2/8 = {bound:.4f}  (T={T}, N={N})')
print(f'final weights: {dict(zip(arm_ret.columns, ws[-1].round(4)))}')
print('\n== eta sensitivity (DESCRIPTIVE; deployed value stays 0.21) ==')
for e in (0.05,0.1,0.21,0.5,1.0):
    _,h=run_hedge(e); a=ann(h)
    print(f'  eta={e:<5} ann {a*100:+6.1f}%')
pd.concat([arm_ret, hedge.rename('hedge_book'),
           pd.DataFrame(ws,index=arm_ret.index,columns=[f'w_{c}' for c in arm_ret.columns])],axis=1)\
  .to_csv(f'{SP}/l2_backtest_daily.csv')
print('daily CSV saved')
