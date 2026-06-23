import json, numpy as np, pandas as pd
print('loading panel + artifact feature set...', flush=True)
art=json.load(open('backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json'))
feats=[c for c in art.get('feature_cols',[])]
sectors=json.load(open('.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
LBL='fwd_60d_excess'
need=['date','ticker',LBL,'BETA60']+feats
df=pd.read_parquet('data/alpha158_291_fundamental_dataset.parquet', columns=[c for c in dict.fromkeys(need)])
df['date']=pd.to_datetime(df['date'])
df=df[df['date']>=df['date'].max()-pd.Timedelta(days=1100)].copy()  # recent ~3y for speed
df['sector']=df['ticker'].map(sectors)
df=df.dropna(subset=[LBL]).copy()
print(f'rows={len(df)}  feats={len(feats)}  dates={df.date.nunique()}  sectors={df.sector.nunique()}', flush=True)

# per-date OLS residualize label on [sector dummies + BETA60]
def residualize(g):
    y=g[LBL].values
    X=pd.get_dummies(g['sector'],dummy_na=True).astype(float)
    X['beta']=g['BETA60'].fillna(g['BETA60'].median()).values
    X['const']=1.0
    Xm=X.values
    try:
        beta,_,_,_=np.linalg.lstsq(Xm,y,rcond=None); resid=y-Xm@beta
    except Exception:
        resid=y-y.mean()
    return pd.Series(resid,index=g.index)
print('residualizing label per date...', flush=True)
df['resid_label']=df.groupby('date',group_keys=False).apply(residualize)

import xgboost as xgb
def purged_cv_ic(label_col, n_splits=3, embargo=60):
    dates=np.sort(df['date'].unique())
    folds=np.array_split(dates, n_splits+1)
    ics=[]
    for k in range(1,n_splits+1):
        val_dates=set(folds[k]); 
        train_cut=folds[k][0]-pd.Timedelta(days=embargo)
        tr=df[df['date']<train_cut]; va=df[df['date'].isin(val_dates)]
        if len(tr)<5000 or len(va)<500: continue
        m=xgb.XGBRegressor(n_estimators=300,max_depth=5,learning_rate=0.03,subsample=0.8,
                           colsample_bytree=0.8,n_jobs=4,tree_method='hist')
        m.fit(tr[feats].fillna(0), tr[label_col])
        va=va.copy(); va['pred']=m.predict(va[feats].fillna(0))
        # IC measured vs the RAW forward return either way (real economic target)
        ic=va.groupby('date').apply(lambda x: x['pred'].corr(x[LBL],method='spearman')).mean()
        ics.append(ic)
    return float(np.mean(ics)) if ics else float('nan'), ics

print('training XGB on RAW label...', flush=True)
raw_ic, raw_f = purged_cv_ic(LBL)
print('training XGB on RESIDUAL (sector+beta-neutralized) label...', flush=True)
res_ic, res_f = purged_cv_ic('resid_label')
print('\n=== RESIDUAL AUDIT RESULT (OOS mean IC vs RAW fwd_60d_excess) ===', flush=True)
print(f'  XGB trained on RAW label:      OOS IC = {raw_ic:+.4f}   folds={[round(x,4) for x in raw_f]}')
print(f'  XGB trained on RESIDUAL label: OOS IC = {res_ic:+.4f}   folds={[round(x,4) for x in res_f]}')
print(f'  ratio resid/raw = {res_ic/raw_ic:.2f}' if raw_ic else '')
print('\nDECISION:', 'idiosyncratic alpha SURVIVES neutralization -> neutralization retrain is the cheap win' if (res_ic>=0.8*raw_ic and res_ic>0.01) else
      'residual signal COLLAPSES -> the edge was factor/beta exposure, not stock-selection -> need NEW data', flush=True)
