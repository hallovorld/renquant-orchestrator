"""Supplemental harvest: StockholdersEquity + shares + GrossProfit for the
G2v2 backfill (the stock harvester's CANONICAL_CONCEPTS lacks them).
Reuses the module's session/CIK/fetch machinery; same record shape; research
output only (scratchpad)."""
import json, sys, time, pathlib
sys.path.insert(0, "/Users/renhao/git/github/renquant-base-data/src")
import renquant_base_data.sec_edgar_companyfacts_harvester as H

EXTRA = {
    "stockholders_equity": ("StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "shares_outstanding":  ("CommonStockSharesOutstanding",
                            "EntityCommonStockSharesOutstanding"),
    "gross_profit":        ("GrossProfit",),
}
UNIT = {"stockholders_equity": "USD", "shares_outstanding": "shares", "gross_profit": "USD"}

def extract(ticker, fj):
    out=[]
    if not isinstance(fj, dict): return out
    for taxo in ("us-gaap", "dei"):
        gaap=fj.get("facts",{}).get(taxo,{})
        for field, tags in EXTRA.items():
            for tag in tags:
                c=gaap.get(tag)
                if not c: continue
                for entry in c.get("units",{}).get(UNIT[field],[]):
                    if entry.get("form","") not in ("10-K","10-Q"): continue
                    out.append({"ticker":ticker,"field":field,"xbrl_tag":tag,
                        "value":entry.get("val"),"period_end":entry.get("end"),
                        "period_start":entry.get("start"),"filed_date":entry.get("filed"),
                        "form":entry.get("form"),"fiscal_year":entry.get("fy"),
                        "fiscal_period":entry.get("fp"),"source":"sec_edgar_companyfacts"})
    return out

tickers=[t.strip() for t in open(sys.argv[1]) if t.strip()]
outp=pathlib.Path(sys.argv[2])
done=set()
if outp.exists():
    for l in open(outp):
        try: done.add(json.loads(l)["ticker"])
        except Exception: pass
sess=H._session()
cik=H.fetch_ticker_cik_map(sess)
n=0
with open(outp,"a") as f:
    for i,t in enumerate(tickers):
        if t in done: continue
        c=cik.get(t.upper())
        if c is None:
            print(f"[{i+1}/{len(tickers)}] {t}: no CIK"); continue
        try:
            fj=H.fetch_company_facts(sess, c)
        except Exception as e:
            print(f"[{i+1}/{len(tickers)}] {t}: FETCH FAIL {e}"); continue
        if not fj:
            print(f"[{i+1}/{len(tickers)}] {t}: EMPTY companyfacts"); continue
        recs=extract(t,fj)
        for r in recs: f.write(json.dumps(r)+"\n")
        n+=len(recs)
        print(f"[{i+1}/{len(tickers)}] {t}: {len(recs)} records", flush=True)
        time.sleep(H.REQUEST_DELAY)
print("Done:", n, "records")
