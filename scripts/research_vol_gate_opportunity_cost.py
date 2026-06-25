"""RIGOROUS redo: does relaxing the hard 60% realized-vol cap survive theory + honest data?

THEORY frame (why a binary cap is the wrong tool, and where it's justified):
- Kelly/Merton: optimal weight f* = μ/σ². Risk enters sizing CONTINUOUSLY; there is no
  binary admission threshold in optimal theory. A hard cap = forcing f*=0 above a line.
- Moreira & Muir (2017, JF) "Volatility-Managed Portfolios": scaling exposure DOWN when vol
  is high (∝1/σ²) RAISES Sharpe — direct support for "size down high-vol, don't exclude".
- COUNTER (the case FOR a vol penalty): the low-volatility anomaly (Ang 2006; Baker 2011;
  Frazzini-Pedersen BAB 2014) — high idio-vol / high-beta names earn LOWER risk-adjusted
  returns. A raw backtest showing high-vol WINNING contradicts this robust anomaly ⇒ suspect
  SURVIVORSHIP/period bias. (Our panel: 291/291 tickers survive to 2026 → busts are missing.)
So the honest test is not "do high-vol names win" (biased up) but: holding the sizer fixed
(Kelly 1/σ²), does RAISING the cap help on RISK-ADJUSTED, NET-OF-COST, DRAWDOWN, and in
CRISIS sub-periods — and does any edge SURVIVE dropping the survivor mega-winners?

Backtest: monthly rebalance, top-quintile by OOS model score, weight ∝ 1/σ² (clip [.05,1.5],
the live Kelly fallback), vary ONLY the cap C ∈ {0.6,0.8,1.0,1.2,1.5,inf}. Forward 1-month
EXCESS return vs SPY from OHLCV. Turnover cost = Σ|Δw|·(5bps + 20bps·vol). Report ann ret,
ann vol, Sharpe, Sortino, maxDD, CVaR5, by full sample + sub-periods; + robustness (median,
drop-top-1% winners).
"""
import glob
import warnings

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")
R = "/Users/renhao/git/github/RenQuant"
LABEL = "fwd_60d_excess"
REG = {"BULL_CALM": "regime_p_bull_calm", "BEAR": "regime_p_bear", "BULL_VOLATILE": "regime_p_bull_volatile"}
N_CUTS, EMB = 6, 60
CAPS = [0.6, 0.8, 1.0, 1.2, 1.5, np.inf]
VOL_FLOOR, VOL_CEIL = 0.05, 1.5
COST_BASE, COST_K = 0.0005, 0.0020   # per-name one-way: 5bps + 20bps*vol


def load_px(t):
    fs = glob.glob(f"{R}/data/ohlcv/{t}/1d.parquet")
    if not fs:
        return None
    d = pd.read_parquet(fs[0]).sort_index()
    d.index = pd.to_datetime(d.index)
    return d["close"]


# ---- panel + OOS scores (purged WF) ----
df = pd.read_parquet(f"{R}/data/alpha158_291_fund_regime_dataset.parquet").dropna(subset=[LABEL]).copy()
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
df["regime"] = df[[REG[r] for r in REG]].values.argmax(1)
tickers = sorted(str(t).upper() for t in df["ticker"].unique())
meta = {"ticker", "date", "regime", "fwd_5d_excess", "fwd_20d_excess", "fwd_60d_excess",
        "split_label", *REG.values()}
feats = [c for c in df.columns if c not in meta]
dts = np.sort(df["date"].unique())
b = np.linspace(0, len(dts), N_CUTS + 1).astype(int)
preds = []
for k in range(1, N_CUTS):
    i = b[k]
    if i >= len(dts):
        break
    lo = dts[i]
    emb = pd.Timestamp(lo) - pd.Timedelta(days=EMB)
    tr = df[df.date <= min(pd.Timestamp(dts[b[k] - 1]), emb)]
    te = df[(df.date >= lo) & (df.date <= dts[min(b[k + 1], len(dts) - 1)])]
    if len(tr) < 1000 or len(te) < 200:
        continue
    m = XGBRegressor(n_estimators=180, max_depth=5, learning_rate=0.05, subsample=0.8,
                     colsample_bytree=0.8, n_jobs=4, random_state=0, verbosity=0)
    m.fit(tr[feats].values, tr[LABEL].values)
    p = te[["date", "ticker"]].copy()
    p["score"] = m.predict(te[feats].values)
    preds.append(p)
    print(f"  WF cut {k} done", flush=True)
P = pd.concat(preds, ignore_index=True)
print(f"OOS scored rows={len(P)}", flush=True)

# ---- price matrix + realized vol + SPY ----
px = {}
for t in tickers + ["SPY"]:
    s = load_px(t)
    if s is not None:
        px[t] = s
spy = px["SPY"]
PX = pd.DataFrame(px).sort_index()
RET = PX.pct_change()
VOL = RET.rolling(60).std() * np.sqrt(252)          # annualized realized vol, per day

# month-end trading dates within the OOS span
oos_dates = np.sort(P["date"].unique())
alld = PX.index
me = pd.Series(alld).groupby([alld.year, alld.month]).max().values
me = pd.to_datetime([d for d in me if d >= oos_dates.min() and d <= oos_dates.max()])
score_by_date = {d: g.set_index("ticker")["score"] for d, g in P.groupby("date")}


def nearest_score_date(d):
    cand = [x for x in oos_dates if x <= np.datetime64(d)]
    return cand[-1] if cand else None


def fwd_excess(t, d0, d1):
    try:
        p0 = PX[t].asof(d0); p1 = PX[t].asof(d1)
        s0 = spy.asof(d0); s1 = spy.asof(d1)
        if any(pd.isna(x) or x <= 0 for x in (p0, p1, s0, s1)):
            return np.nan
        return (p1 / p0 - 1) - (s1 / s0 - 1)
    except Exception:
        return np.nan


def run(cap, drop_top_pct=0.0):
    """Monthly series of basket excess return (net of turnover cost) for a given vol cap."""
    rets, dates, prev_w = [], [], {}
    for j in range(len(me) - 1):
        d0, d1 = me[j], me[j + 1]
        sd = nearest_score_date(d0)
        if sd is None:
            continue
        sc = score_by_date.get(pd.Timestamp(sd))
        if sc is None:
            continue
        vol = VOL.loc[:d0].iloc[-1] if d0 in VOL.index or len(VOL.loc[:d0]) else None
        if vol is None:
            continue
        # candidates: have score + vol + price
        cand = pd.DataFrame({"score": sc})
        cand["vol"] = vol.reindex(cand.index)
        cand = cand.dropna()
        if len(cand) < 20:
            continue
        # top quintile by score
        thr = cand["score"].quantile(0.80)
        top = cand[cand["score"] >= thr].copy()
        top = top[top["vol"] <= cap]                       # the CAP under test
        if len(top) == 0:
            rets.append(0.0); dates.append(d1); prev_w = {}; continue
        # weight ∝ 1/σ² with the live Kelly clip
        sig = top["vol"].clip(VOL_FLOOR, VOL_CEIL)
        w = (1.0 / (sig ** 2))
        w = (w / w.sum()).to_dict()
        # forward excess returns
        fr = {t: fwd_excess(t, d0, d1) for t in w}
        fr = {t: (0.0 if pd.isna(v) else v) for t, v in fr.items()}
        if drop_top_pct > 0 and fr:                        # robustness: drop survivor mega-winners
            cut = np.quantile(list(fr.values()), 1 - drop_top_pct)
            fr = {t: min(v, cut) for t, v in fr.items()}
        gross = sum(w[t] * fr[t] for t in w)
        # turnover cost
        allt = set(w) | set(prev_w)
        cost = sum(abs(w.get(t, 0) - prev_w.get(t, 0)) *
                   (COST_BASE + COST_K * float(sig.get(t, top["vol"].mean()
                    if t in top.index else 0.5))) for t in allt)
        rets.append(gross - cost); dates.append(d1); prev_w = w
    return pd.Series(rets, index=pd.to_datetime(dates))


def metrics(s):
    if len(s) < 6:
        return dict(n=len(s))
    mu, sd = s.mean() * 12, s.std() * np.sqrt(12)
    dn = s[s < 0].std() * np.sqrt(12)
    cum = (1 + s).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    cvar = s[s <= s.quantile(0.05)].mean()
    return dict(n=len(s), ann_ret=mu, ann_vol=sd, sharpe=(mu / sd if sd else np.nan),
                sortino=(mu / dn if dn else np.nan), maxDD=dd, cvar5=cvar,
                med_m=s.median(), hit=(s > 0).mean())


print("\n=== CAP SWEEP — monthly top-quintile, weight∝1/σ², net of cost, excess vs SPY ===", flush=True)
print(f"{'cap':>5s} {'annRet':>7s} {'annVol':>7s} {'Sharpe':>7s} {'Sortino':>7s} {'maxDD':>7s} {'CVaR5':>7s} {'medM':>7s} {'hit':>5s}", flush=True)
series = {}
for c in CAPS:
    s = run(c); series[c] = s; m = metrics(s)
    cs = "inf" if np.isinf(c) else f"{c:.1f}"
    print(f"{cs:>5s} {m['ann_ret']:+.3f} {m['ann_vol']:7.3f} {m['sharpe']:+.3f} {m['sortino']:+.3f} {m['maxDD']:+.3f} {m['cvar5']:+.3f} {m['med_m']:+.4f} {m['hit']:.2f}", flush=True)

print("\n=== ROBUSTNESS: drop top-1% monthly winners (kills survivor tail) ===", flush=True)
for c in [0.6, 1.2, np.inf]:
    m = metrics(run(c, drop_top_pct=0.01))
    cs = "inf" if np.isinf(c) else f"{c:.1f}"
    print(f"cap={cs:>4s} Sharpe={m['sharpe']:+.3f} annRet={m['ann_ret']:+.3f} maxDD={m['maxDD']:+.3f} medM={m['med_m']:+.4f}", flush=True)

print("\n=== SUB-PERIODS (Sharpe by cap) — does relaxing help/hurt in crises? ===", flush=True)
periods = {"<=2019": ("2015-01-01", "2019-12-31"), "2020": ("2020-01-01", "2020-12-31"),
           "2022": ("2022-01-01", "2022-12-31"), "2023-26": ("2023-01-01", "2026-12-31")}
hdr = "period   " + "".join(f"{('inf' if np.isinf(c) else f'{c:.1f}'):>8s}" for c in CAPS)
print(hdr, flush=True)
for pn, (a, bb) in periods.items():
    row = f"{pn:8s} "
    for c in CAPS:
        s = series[c]
        sub = s[(s.index >= a) & (s.index <= bb)]
        m = metrics(sub)
        row += f"{(m.get('sharpe') if m.get('n',0)>=6 else float('nan')):>8.2f}" if m.get('n',0)>=6 else f"{'~':>8s}"
    print(row, flush=True)
print("\nDONE", flush=True)
