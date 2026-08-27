"""G2v2 backfill: PIT daily valuation panel 2016-2020, production semantics.
Mirrors scripts/fetch_sec_fundamentals.py: value overwrites from filed_date
forward; ratios via _safe_ratio(eps=1.0); market_cap = shares*close.
Research output only (scratchpad)."""
import json, pandas as pd, numpy as np, pathlib
SP=pathlib.Path(__file__).parent
FIELD_MAP={"net_income":"NetIncomeLoss","total_assets":"Assets",
           "stockholders_equity":"StockholdersEquity",
           "shares_outstanding":"CommonStockSharesOutstanding",
           "gross_profit":"GrossProfit"}
rows=[]
for fn in ("g2v2_backfill_companyfacts.jsonl","g2v2_backfill_equity_shares.jsonl"):
    for l in open(SP/fn):
        r=json.loads(l)
        f=r.get("field")
        if f not in FIELD_MAP: continue
        if not r.get("filed_date") or r.get("value") is None: continue
        rows.append((r["ticker"],FIELD_MAP[f],r["filed_date"],r.get("period_end") or "",float(r["value"])))
df=pd.DataFrame(rows,columns=["ticker","concept","filed","end","value"])
df["filed"]=pd.to_datetime(df["filed"])
# trading-day index 2015-06..2020-12 (warmup for asset_growth 252d)
spy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet")
idx=pd.DatetimeIndex(spy.index if spy.index.name=="date" or spy.index.dtype.kind=="M" else pd.to_datetime(spy["date"]))
idx=idx[(idx>="2015-01-02")&(idx<="2020-12-31")]
def _safe_ratio(num,den,eps=1.0):
    return num/den.where(den.abs()>eps)
out=[]
for t,g in df.groupby("ticker"):
    px_p=pathlib.Path(f"/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet")
    if not px_p.exists(): continue
    px=pd.read_parquet(px_p,columns=["close"])["close"]
    px.index=pd.to_datetime(px.index); px=px.reindex(idx)
    daily=pd.DataFrame(index=idx)
    for c,gc in g.groupby("concept"):
        # production rule: iterate in filed order, later filings overwrite;
        # same filed date -> newest period_end wins
        gc=gc.sort_values(["filed","end"])
        s=gc.drop_duplicates("filed",keep="last").set_index("filed")["value"]
        daily[c]=s.reindex(idx,method="ffill")
    ni=daily.get("NetIncomeLoss",pd.Series(np.nan,index=idx))
    eq=daily.get("StockholdersEquity",pd.Series(np.nan,index=idx))
    sh=daily.get("CommonStockSharesOutstanding",pd.Series(np.nan,index=idx))
    gp=daily.get("GrossProfit",pd.Series(np.nan,index=idx))
    ast=daily.get("Assets",pd.Series(np.nan,index=idx))
    mc=sh*px
    r=pd.DataFrame(index=idx)
    r["ticker"]=t
    with np.errstate(invalid="ignore",divide="ignore"):
        r["earnings_yield"]=_safe_ratio(ni,mc)
        r["book_to_price"]=_safe_ratio(eq,mc)
        r["gross_profitability"]=_safe_ratio(gp,ast)
        r["roe"]=_safe_ratio(ni,eq)
        r["asset_growth"]=ast.pct_change(periods=252).clip(-0.99,5.0)
    out.append(r.reset_index().rename(columns={"index":"date"}))
panel=pd.concat(out,ignore_index=True)
panel=panel[panel["date"]>="2016-01-01"]
panel.to_parquet(SP/"g2v2_backfill_panel_2016_2020.parquet")
ok=panel["earnings_yield"].notna()&panel["book_to_price"].notna()
panel["year"]=panel["date"].dt.year
cov=panel[ok].groupby("year")["ticker"].nunique()
print("panel rows:",len(panel)," tickers:",panel['ticker'].nunique())
print("tickers with complete valuation row, by year:"); print(cov.to_string())
