"""SELF-AUDIT of regime_portfolio_v2.py — hunt for leakage / bias.

Checks:
  1. Look-ahead in regime classification (pd.qcut over full history)
  2. Label leakage (no embargo between train window and rebalance date)
  3. Survivorship bias (are the 292 panel tickers the CURRENT watchlist?)
  4. Price adjustment (are closes split/div adjusted?)
  5. Is POOLED APY 45.5% plausible?
"""
import pandas as pd, numpy as np, os, json
import warnings; warnings.filterwarnings('ignore')

OUT = {}
print("="*78)
print("SELF-AUDIT: regime_portfolio_v2.py")
print("="*78)

# ── CHECK 1: look-ahead in regime classification ─────────────────────
print("\n[1] LOOK-AHEAD IN REGIME CLASSIFICATION")
ohlcv = "/Users/renhao/git/github/RenQuant/data/ohlcv"
spy = pd.read_parquet(os.path.join(ohlcv, "SPY", "1d.parquet"))
spy.index = pd.to_datetime(spy.index if 'date' not in spy.columns else spy['date'])
c = spy['close'] if 'close' in spy.columns else spy['Close']
r = c.pct_change(); vol20 = r.rolling(20).std()
trend = c / c.rolling(60).mean() - 1
reg = pd.DataFrame({'vol': vol20, 'trend': trend}).dropna()

# What I DID: qcut over the whole sample
full_q = reg['vol'].quantile([1/3, 2/3]).values
print(f"  Full-sample vol terciles (what I used): {full_q[0]:.5f} / {full_q[1]:.5f}")

# What I SHOULD have done: expanding-window quantile as of each date
exp_lo = reg['vol'].expanding(252).quantile(1/3)
exp_hi = reg['vol'].expanding(252).quantile(2/3)
# Compare labels
lab_full = pd.cut(reg['vol'], [-np.inf, full_q[0], full_q[1], np.inf], labels=['LO','MD','HI'])
lab_exp = pd.Series(np.where(reg['vol'] < exp_lo, 'LO',
                    np.where(reg['vol'] < exp_hi, 'MD', 'HI')), index=reg.index)
valid = exp_lo.notna()
agree = (lab_full[valid].astype(str) == lab_exp[valid]).mean()
print(f"  Label agreement (full-sample vs expanding/causal): {agree:.1%}")
print(f"  → {(1-agree):.1%} of days got a regime label that used FUTURE volatility")
OUT['check1_regime_lookahead'] = {'agreement': float(agree), 'leaky_pct': float(1-agree)}
print(f"  VERDICT: {'LEAK CONFIRMED' if agree < 0.95 else 'minor'}")

# ── CHECK 2: label leakage / no embargo ──────────────────────────────
print("\n[2] LABEL LEAKAGE — EMBARGO")
print("  My code: train_d = dates[di-250 : di]; rebalance at dates[di]")
print("  Label = fwd_20d_excess → the label at date di-1 resolves at di+19")
print("  So training rows from di-20..di-1 carry labels that OVERLAP the")
print("  20-day holding period I'm about to trade.")
print("  Production kernel/walk_forward_splits.py uses embargo_days=60.")
print("  My experiment used embargo_days=0.")
print("  VERDICT: LEAK CONFIRMED — 20 of 250 train days (8%) leak forward")
OUT['check2_embargo'] = {'embargo_used': 0, 'embargo_required': 20,
                         'leaky_train_days': 20, 'train_window': 250}

# ── CHECK 3: survivorship bias ───────────────────────────────────────
print("\n[3] SURVIVORSHIP BIAS")
pan = pd.read_parquet("/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset_rawlabel.parquet")
pan['date'] = pd.to_datetime(pan['date'])
tick = sorted(pan['ticker'].unique())
print(f"  Panel tickers: {len(tick)}")
# When does each ticker first/last appear?
span = pan.groupby('ticker')['date'].agg(['min','max'])
last_date = pan['date'].max()
still_alive = (span['max'] >= last_date - pd.Timedelta(days=10)).mean()
print(f"  Panel last date: {last_date.date()}")
print(f"  Tickers still present at the END of the sample: {still_alive:.1%}")
started_at_open = (span['min'] <= pan['date'].min() + pd.Timedelta(days=10)).mean()
print(f"  Tickers present from the START of the sample:   {started_at_open:.1%}")
OUT['check3_survivorship'] = {'n_tickers': len(tick),
                              'alive_at_end_pct': float(still_alive),
                              'present_at_start_pct': float(started_at_open)}
print(f"  → The panel is a FIXED list of {len(tick)} names known TODAY.")
print(f"  → Backtesting 2017-2026 on today's survivors = survivorship bias.")
print(f"  VERDICT: {'BIAS CONFIRMED' if still_alive > 0.95 else 'check further'}")

# ── CHECK 4: price adjustment ────────────────────────────────────────
print("\n[4] PRICE ADJUSTMENT (splits/dividends)")
# Look for a known split: NVDA 10:1 June 2024, AAPL 4:1 Aug 2020
for t, split_date, ratio in [("NVDA","2024-06-10",10), ("AAPL","2020-08-31",4)]:
    fp = os.path.join(ohlcv, t, "1d.parquet")
    if not os.path.exists(fp):
        print(f"  {t}: no file"); continue
    df = pd.read_parquet(fp)
    df.index = pd.to_datetime(df.index if 'date' not in df.columns else df['date'])
    cl = df['close'] if 'close' in df.columns else df['Close']
    sd = pd.Timestamp(split_date)
    before = cl[cl.index < sd]
    after = cl[cl.index >= sd]
    if len(before) == 0 or len(after) == 0:
        print(f"  {t}: split date outside data range"); continue
    jump = after.iloc[0] / before.iloc[-1]
    print(f"  {t} {split_date} ({ratio}:1 split): close ratio across date = {jump:.3f}")
    print(f"     {'RAW (unadjusted) — 1-day return would be ' + f'{jump-1:+.0%}' if jump < 0.5 else 'ADJUSTED (no artificial jump)'}")
    OUT.setdefault('check4_splits', {})[t] = {'jump': float(jump), 'adjusted': bool(jump > 0.5)}

# ── CHECK 5: is 45.5% APY plausible? ─────────────────────────────────
print("\n[5] PLAUSIBILITY OF THE BASELINE")
print("  My POOLED (non-regime) baseline: APY 45.5%, Sharpe 1.48, 9 years.")
print("  That is a naive equal-weight rank composite of top-20 IC features.")
print("  If a rank composite of public alpha158 features returned 45%/yr")
print("  for 9 years, it would be one of the best equity strategies on earth.")
print("  A baseline that good is EVIDENCE OF A BUG, not evidence of alpha.")
OUT['check5_plausibility'] = {'pooled_apy': 0.455, 'spy_apy': 0.131,
                              'verdict': 'implausible — indicates leakage/bias'}

# ── CHECK 6: equal-weight panel buy-and-hold (the REAL benchmark) ────
print("\n[6] WHAT DOES THE PANEL ITSELF RETURN? (survivorship floor)")
prices = {}
for t in tick:
    fp = os.path.join(ohlcv, t, "1d.parquet")
    if not os.path.exists(fp): continue
    try:
        df = pd.read_parquet(fp)
        df.index = pd.to_datetime(df.index if 'date' not in df.columns else df['date'])
        prices[t] = df['close'] if 'close' in df.columns else df['Close']
    except Exception:
        pass
P = pd.DataFrame(prices)
dates = sorted(pan['date'].unique())
TRAIN_WIN, HOLD = 250, 20
rebal = [dates[i] for i in range(TRAIN_WIN, len(dates), HOLD)]
fwd20 = P.shift(-20) / P - 1
ew_rets, spy_rets = [], []
spy_fwd = c.shift(-20)/c - 1
for d in rebal:
    if d in fwd20.index:
        v = fwd20.loc[d].dropna()
        ew_rets.append(float(v.mean()) if len(v) else 0.0)
    else:
        ew_rets.append(0.0)
    spy_rets.append(float(spy_fwd.loc[d]) if d in spy_fwd.index and np.isfinite(spy_fwd.loc[d]) else 0.0)
ew = np.array(ew_rets); sp = np.array(spy_rets)
ppy = 252/HOLD; yrs = len(ew)/ppy
ew_apy = (np.prod(1+ew))**(1/yrs)-1
sp_apy = (np.prod(1+sp))**(1/yrs)-1
print(f"  Equal-weight ALL {P.shape[1]} panel names, 20d rebal: APY = {ew_apy:.1%}")
print(f"  SPY buy-and-hold over the same periods:              APY = {sp_apy:.1%}")
print(f"  → Survivorship premium of the panel itself: {ew_apy - sp_apy:+.1%}/yr")
print(f"  → My strategy's 'excess vs SPY' of +28.7% must be compared against")
print(f"    this {ew_apy - sp_apy:+.1%} floor, NOT against zero.")
OUT['check6_panel_ew'] = {'panel_ew_apy': float(ew_apy), 'spy_apy': float(sp_apy),
                          'survivorship_premium': float(ew_apy - sp_apy)}

print("\n" + "="*78)
json.dump(OUT, open("/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad/audit_result.json","w"), indent=2, default=str)
print("Saved audit_result.json")
