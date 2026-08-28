"""Stage I-0 fetch: Alpaca IEX 10-min bars, DEVELOPMENT WINDOW ONLY
(2020-08-01..2024-06-30, per merged design orch#1072). Resumable; one
parquet per name in scratchpad; read-only market data; $0."""
import os, json, time, pathlib, urllib.request, urllib.parse
import pandas as pd
SP=pathlib.Path(__file__).parent
OUT=SP/"g2v3_bars"; OUT.mkdir(exist_ok=True)
KEY=os.environ["ALPACA_API_KEY"]; SEC=os.environ["ALPACA_SECRET_KEY"]
START="2020-08-01T13:00:00Z"; END="2024-07-01T00:00:00Z"
def fetch(sym):
    rows=[]; token=None
    while True:
        q={"timeframe":"10Min","start":START,"end":END,"limit":"10000","feed":"iex","adjustment":"split"}
        if token: q["page_token"]=token
        url=f"https://data.alpaca.markets/v2/stocks/{sym}/bars?"+urllib.parse.urlencode(q)
        req=urllib.request.Request(url,headers={"APCA-API-KEY-ID":KEY,"APCA-API-SECRET-KEY":SEC})
        for attempt in range(5):
            try:
                d=json.load(urllib.request.urlopen(req,timeout=30)); break
            except urllib.error.HTTPError as e:
                if e.code==429: time.sleep(10+5*attempt); continue
                if e.code in (404,422): return None
                time.sleep(3+3*attempt)
            except Exception:
                time.sleep(3+3*attempt)
        else:
            return "RETRY"
        rows.extend(d.get("bars") or [])
        token=d.get("next_page_token")
        if not token: break
    return rows
tickers=[t.strip() for t in open(SP/"g2v3_seed.txt") if t.strip()]
done=0; empty=0
for i,t in enumerate(tickers):
    f=OUT/f"{t}.parquet"
    if f.exists(): continue
    marker=OUT/f"{t}.empty"
    if marker.exists(): continue
    bars=fetch(t)
    if bars=="RETRY":
        print(f"[{i+1}/{len(tickers)}] {t}: RETRY-LATER",flush=True); continue
    if not bars:
        marker.touch(); empty+=1
        print(f"[{i+1}/{len(tickers)}] {t}: none",flush=True); continue
    df=pd.DataFrame(bars)[["t","o","h","l","c","v"]]
    df.columns=["ts","open","high","low","close","volume"]
    df.to_parquet(f,compression="zstd")
    done+=1
    print(f"[{i+1}/{len(tickers)}] {t}: {len(df)} bars",flush=True)
    time.sleep(0.31)  # ~190 req/min ceiling incl pagination
print("fetch pass complete; wrote",done,"empty",empty)
