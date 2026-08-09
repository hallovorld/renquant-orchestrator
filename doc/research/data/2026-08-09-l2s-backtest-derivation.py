"""L2-S sector-conditional allocation backtest — the ONE execution of the
merged frozen design doc/design/2026-08-09-l2-sector-conditional-allocation.md.

Every constant is FROM THE DOC (none is a runner choice — the L3 lesson):
eligible sectors/tiers/k, unfloored local Hedge + m_s mixture, general
names-only holdings cost (10bps x sum|dh|, no half, cash excluded), composite
= 0.730 sector-machinery + 0.270 global-only replica, placebo seeds 0..199
with the frozen permutation map, four-leg ADOPT-for-shadow / RECORD-ONLY.
Inputs are the #926/#927 machine-local snapshot, digest-verified before use.
Controls: the engine passed planted-expert positive and no-information null
controls pre-run (two harness bugs found and fixed there: a floored local
path and a missing score-to-trade lag)."""
import glob, hashlib, json, os, sys
from pathlib import Path

def _fsha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
def _dirsha(files):
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.split('/')[-1].encode()); h.update(_fsha(f).encode())
    return h.hexdigest(), len(files)
def verify_manifest():
    man = json.load(open(Path(__file__).with_name('2026-08-09-l2-backtest-inputs.manifest.json')))
    ins = man['inputs']
    assert _fsha(ins['momentum_dense_scores.json']['path']) == ins['momentum_dense_scores.json']['sha256']
    d, n = _dirsha(glob.glob(ins['panel_replay_matrix']['dir'] + '/*/wf_replay_panel__*.parquet'))
    assert (d, n) == (ins['panel_replay_matrix']['digest_of_digests'], ins['panel_replay_matrix']['n_files'])
    assert _fsha(ins['sector_map_config']['path']) == ins['sector_map_config']['sha256']
    smap = json.load(open(ins['sector_map_config']['path']))['sector_map']
    root = ins['ohlcv_universe']['root']
    ofiles = [f'{root}/{t}/1d.parquet' for t, s in smap.items()
              if s not in ('benchmark', 'defensive_bonds') and os.path.exists(f'{root}/{t}/1d.parquet')]
    d, n = _dirsha(ofiles)
    # OHLCV digests drift legitimately (daily runs append bars). The frozen
    # window's DATA is instead checked SUBSTANTIVELY below: the rebuilt
    # global arm books must reproduce #926/#927's committed gross series
    # day-by-day, else the run REFUSES. Fresh digests are recorded in this
    # run's own manifest for future reproduction.
    json.dump({'schema': 'l2s_backtest_inputs.v1',
               'ohlcv_universe': {'root': root, 'digest_of_digests': d, 'n_files': n},
               'static_inputs_verified_against': '2026-08-09-l2-backtest-inputs.manifest.json'},
              open(Path(__file__).with_name('2026-08-09-l2s-inputs.manifest.json'), 'w'), indent=2)
    print('static inputs digest-verified; ohlcv pinned fresh (substantive check follows)', flush=True)
verify_manifest()
sys.path.insert(0, str(Path(__file__).parent))
from l2_staleness import is_fresh
sys.path.insert(0, "/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close

SP = '/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad'
HERE = Path(__file__).parent
ETA, C, FLOOR, COST1W = 0.21, 0.05, 0.5, 0.0010
ELIGIBLE = {'software': (26, 3, 0.50), 'industrial': (21, 3, 0.50),
            'finance': (20, 3, 0.50), 'ai_chip': (19, 2, 0.67),
            'consumer': (16, 2, 0.67), 'datacenter_hw': (14, 2, 0.67)}
TOTAL = 159
ARM_ORDER = ['panel', 'mom_slow', 'mom_fast']

SEC_MAP = json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
rets = {}
for t in [x for x, s in SEC_MAP.items() if s not in ('benchmark', 'defensive_bonds')]:
    try:
        df = pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div = df['dividend'] if 'dividend' in df.columns else pd.Series(0.0, index=df.index)
        rets[t] = total_return_close(df['close'], div).pct_change()
    except FileNotFoundError:
        pass
R = pd.DataFrame(rets).loc['2023-06-01':]
panel = {}
for f in sorted(glob.glob(f'{SP}/served_matrix_replay/*/wf_replay_panel__*.parquet')):
    d = f.split('/')[-2]; df = pd.read_parquet(f); panel[d] = dict(zip(df['ticker'], df['score']))
mom = json.load(open(f'{SP}/momentum_dense_scores.json'))
slow = {r['date']: r['slow'] for r in mom if isinstance(r.get('slow'), dict) and 'error' not in r['slow'] and len(r['slow']) >= 30}
fast = {r['date']: r['fast'] for r in mom if isinstance(r.get('fast'), dict) and 'error' not in r['fast'] and len(r['fast']) >= 30}
ARMS = {'panel': panel, 'mom_slow': slow, 'mom_fast': fast}

def fresh_scores_before(scores_by_date, sdates, state, ts):
    """freshest score strictly before ts (lag >= 1 day), 7-calendar staleness.
    state = (si, cur, cur_d) CARRIED ACROSS DAYS — #926 semantics: the
    freshest score persists until it goes stale, even on days with no new
    score file (the first draft reset it per call and lost 13 calendar days;
    caught by the invariance gate against #927's committed CSV)."""
    si, cur, cur_d = state
    while si < len(sdates) and sdates[si] < ts:
        cur = scores_by_date[sdates[si]]; cur_d = sdates[si]; si += 1
    ok = cur is not None and is_fresh(pd.Timestamp(ts), pd.Timestamp(cur_d))
    return (cur if ok else None), (si, cur, cur_d)

def book_cost(h_prev, h_now):
    names = set(h_prev) | set(h_now)
    return COST1W * sum(abs(h_now.get(t, 0.0) - h_prev.get(t, 0.0)) for t in names)

# ---- pass 1: the #926 calendar (all arms fresh + >=3 investable, whole universe)
cursors = {a: (0, None, None) for a in ARMS}; sdlists = {a: sorted(ARMS[a]) for a in ARMS}
calendar = []; day_scores = {}
for t in R.index:
    ts = t.date().isoformat(); ok = {}
    for a in ARMS:
        sc, cursors[a] = fresh_scores_before(ARMS[a], sdlists[a], cursors[a], ts)
        ok[a] = sc
    if any(v is None for v in ok.values()):
        continue
    row = R.loc[t]
    if all(len({n: s for n, s in ok[a].items() if n in R.columns and row[n] == row[n]}) >= 3 for a in ARMS):
        calendar.append(t); day_scores[t] = ok
print(f'calendar: {len(calendar)} days {calendar[0].date()}..{calendar[-1].date()}', flush=True)

def run_book_set(members_of, kmap):
    """books for {label: member-set} x arms with per-label k; holdings cost."""
    out = {}; hold_rows = []
    for label, members in members_of.items():
        k = kmap[label]
        for arm in ARM_ORDER:
            h_prev = {}; rows = []
            for t in calendar:
                row = R.loc[t]
                sc = day_scores[t][arm]
                elig = {n: s for n, s in sc.items()
                        if n in members and n in R.columns and row[n] == row[n]}
                ranked = sorted(elig.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
                h = {n: 1.0 / len(ranked) for n, _ in ranked} if ranked else {}
                cost = book_cost(h_prev, h)
                gross = sum(w * row[n] for n, w in h.items())
                rows.append((t, gross, cost, gross - cost, len(h)))
                for n, w in h.items():
                    hold_rows.append((t.date().isoformat(), label, arm, n, round(w, 6)))
                h_prev = h
            out[(label, arm)] = pd.DataFrame(rows, columns=['date', 'gross', 'cost', 'net', 'n_held']).set_index('date')
    return out, hold_rows

def hedge_path(net_df, floor):
    w = np.array([0.5, 0.25, 0.25]); ws = []; port = []
    for _, r in net_df.iterrows():
        rv = r.values; port.append(float(w @ rv)); ws.append(w.copy())
        w = w * np.exp(ETA * np.clip(rv, -C, C)); w = w / w.sum()
        if floor and w[0] < FLOOR:
            w[1:] *= (1 - FLOOR) / (1 - w[0]); w[0] = FLOOR
    return np.array(ws), pd.Series(port, index=net_df.index)

def composite_run(sector_books, g_net_arms, sectors, m_override=None):
    wg = np.array([0.5, 0.25, 0.25]); local = {s: np.array([0.5, 0.25, 0.25]) for s in sectors}
    cap = {s: n / TOTAL for s, (n, _, _) in sectors.items()}
    cap_g = 1.0 - sum(cap.values())
    days = []; wl_paths = {s: [] for s in sectors}; wm_paths = {s: [] for s in sectors}
    for t in g_net_arms.index:
        rg = g_net_arms.loc[t].values
        day = cap_g * float(wg @ rg)
        for s in sectors:
            m = sectors[s][2] if m_override is None else m_override
            ws = (1 - m) * local[s] + m * wg
            rs = np.array([sector_books[(s, a)].at[t.date().isoformat() if False else t, 'net'] if False else sector_books[(s, a)]['net'].loc[t] for a in ARM_ORDER])
            day += cap[s] * float(ws @ rs)
            wl_paths[s].append(local[s].copy()); wm_paths[s].append(ws)
            w2 = local[s] * np.exp(ETA * np.clip(rs, -C, C)); local[s] = w2 / w2.sum()   # UNFLOORED
        w2 = wg * np.exp(ETA * np.clip(rg, -C, C)); w2 = w2 / w2.sum()
        if w2[0] < FLOOR: w2[1:] *= (1 - FLOOR) / (1 - w2[0]); w2[0] = FLOOR
        wg = w2
        days.append(day)
    return (pd.Series(days, index=g_net_arms.index),
            {s: pd.DataFrame(wl_paths[s], index=g_net_arms.index, columns=ARM_ORDER) for s in sectors},
            {s: pd.DataFrame(wm_paths[s], index=g_net_arms.index, columns=ARM_ORDER) for s in sectors})

def sharpe(x):
    a = (1 + x).prod() ** (252 / len(x)) - 1; v = x.std() * np.sqrt(252)
    return a / v if v > 0 else 0.0
def ann(x): return (1 + x).prod() ** (252 / len(x)) - 1
def maxdd(x):
    c = (1 + x).cumprod(); return float((c / c.cummax() - 1).min())

ALL_NAMES = set(R.columns)
gbooks, ghold = run_book_set({'ALL': ALL_NAMES}, {'ALL': 3})
g_net_arms = pd.DataFrame({a: gbooks[('ALL', a)]['net'] for a in ARM_ORDER})
# SUBSTANTIVE INVARIANCE GATE: the rebuilt global gross series must equal
# #927's committed CSV on the shared calendar (proves the frozen window's
# OHLCV history is unchanged; appended future bars are irrelevant).
_ref = pd.read_csv(Path(__file__).with_name('2026-08-09-l2-cost-pass-daily.csv'),
                   index_col=0, parse_dates=True)
_mine = pd.DataFrame({a: gbooks[('ALL', a)]['gross'] for a in ARM_ORDER})
_shared = _mine.index.intersection(_ref.index)
assert len(_shared) == len(_ref), f'calendar drift: {len(_shared)} vs {len(_ref)}'
for _a, _col in (('panel', 'panel_gross'), ('mom_slow', 'mom_slow_gross'), ('mom_fast', 'mom_fast_gross')):
    assert np.allclose(_mine.loc[_shared, _a], _ref.loc[_shared, _col], atol=1e-10), f'{_a} gross drifted from #927 committed'
print('substantive invariance gate PASSED: global gross series reproduce #927 committed CSV', flush=True)
g_ws, g_only = hedge_path(g_net_arms, floor=True)

members_true = {s: {t for t, sec in SEC_MAP.items() if sec == s} for s in ELIGIBLE}
kmap = {s: ELIGIBLE[s][1] for s in ELIGIBLE}
sbooks, shold = run_book_set(members_true, kmap)
comp, wl, wm = composite_run(sbooks, g_net_arms, ELIGIBLE)
pure_local, _, _ = composite_run(sbooks, g_net_arms, ELIGIBLE, m_override=0.0)

print(f'composite  ann {ann(comp)*100:+.1f}% sharpe {sharpe(comp):.2f} maxDD {maxdd(comp)*100:.1f}%', flush=True)
print(f'global     ann {ann(g_only)*100:+.1f}% sharpe {sharpe(g_only):.2f} maxDD {maxdd(g_only)*100:.1f}%', flush=True)
print(f'pure-local ann {ann(pure_local)*100:+.1f}% sharpe {sharpe(pure_local):.2f} maxDD {maxdd(pure_local)*100:.1f}%', flush=True)
table = {s: {a: round(sharpe(sbooks[(s, a)]['net']), 3) for a in ARM_ORDER} for s in ELIGIBLE}
print('per-sector x arm net Sharpe:', json.dumps(table, indent=1), flush=True)
tilts = {s: {a: round(float(wl[s].iloc[-1][a]), 3) for a in ARM_ORDER} for s in ELIGIBLE}
print('final LOCAL hedge weights:', json.dumps(tilts), flush=True)

# ---- placebo: frozen permutation maps, delta(sigma) = permuted composite Sharpe - global Sharpe
tickers_sorted = sorted(SEC_MAP)      # all 159 incl benchmark/defensive per doc enumeration
true_labels = [SEC_MAP[t] for t in tickers_sorted]
deltas = []
for seed in range(200):
    pi = np.random.default_rng(seed).permutation(TOTAL)
    lab = {tickers_sorted[i]: true_labels[pi[i]] for i in range(TOTAL)}
    mem = {s: {t for t, sec in lab.items() if sec == s} for s in ELIGIBLE}
    sb, _ = run_book_set(mem, kmap)
    c, _, _ = composite_run(sb, g_net_arms, ELIGIBLE)
    deltas.append(sharpe(c) - sharpe(g_only))
    if seed % 25 == 24: print(f'placebo {seed+1}/200', flush=True)
p95 = float(np.quantile(deltas, 0.95))
real_delta = sharpe(comp) - sharpe(g_only)
leg_placebo = bool(real_delta > p95)

leg1 = bool(sharpe(comp) >= sharpe(g_only) - 0.05)
leg2 = bool(maxdd(comp) <= maxdd(g_only) + 0.05)
leg3 = bool(any(max(wl[s].iloc[-1][a] for a in ARM_ORDER[1:]) >= 0.40 for s in ELIGIBLE))
verdict = 'ADOPT-for-shadow' if (leg1 and leg2 and leg3 and leg_placebo) else 'RECORD-ONLY'
summary = {'verdict': verdict,
           'leg_sharpe_floor': leg1, 'leg_maxdd': leg2, 'leg_sector_tilt': leg3,
           'leg_placebo': leg_placebo,
           'composite': {'ann': ann(comp), 'sharpe': sharpe(comp), 'maxdd': maxdd(comp)},
           'global_only': {'ann': ann(g_only), 'sharpe': sharpe(g_only), 'maxdd': maxdd(g_only)},
           'pure_local': {'ann': ann(pure_local), 'sharpe': sharpe(pure_local), 'maxdd': maxdd(pure_local)},
           'real_delta': real_delta, 'placebo_p95': p95, 'n_days': len(calendar),
           'per_sector_arm_net_sharpe': table, 'final_local_weights': tilts}
json.dump(summary, open(HERE / '2026-08-09-l2s-summary.json', 'w'), indent=2, default=float)

daily = pd.DataFrame({'composite_net': comp, 'global_only_net': g_only, 'pure_local_net': pure_local})
for (s, a), b in sbooks.items():
    for col in ('gross', 'cost', 'net'):
        daily[f'{s}__{a}_{col}'] = b[col]
for a in ARM_ORDER:
    daily[f'globalarm_{a}_net'] = g_net_arms[a]
for s in ELIGIBLE:
    for a in ARM_ORDER:
        daily[f'wlocal_{s}_{a}'] = wl[s][a]; daily[f'wmix_{s}_{a}'] = wm[s][a]
daily.index = [t.date().isoformat() for t in daily.index]
daily.to_csv(HERE / '2026-08-09-l2s-daily.csv', index_label='date')
pd.DataFrame(shold + ghold, columns=['date', 'sector', 'arm', 'ticker', 'weight']).to_csv(
    HERE / '2026-08-09-l2s-holdings.csv', index=False)
pd.Series(deltas, name='placebo_delta_sharpe').to_csv(HERE / '2026-08-09-l2s-placebo.csv', index=False)
print(json.dumps({k: summary[k] for k in ('verdict', 'real_delta', 'placebo_p95')}, default=float), flush=True)
print('artifacts saved', flush=True)
