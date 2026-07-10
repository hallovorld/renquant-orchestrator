"""S0 Phase-1 supplementary estimands (protocol §3.1 deployed fraction + §4 gates).

Read-only analysis over the frozen sim DB copy using the existing pipeline API.
No repo files are written; output JSON goes to the scratchpad only.
"""
import json
import numpy as np
from renquant_pipeline.kernel.portfolio_qp.wf_replay_loader import load_replay_bars_from_sim_db
from renquant_pipeline.kernel.portfolio_qp.run_ab_replay import get_allocator, _load_sector_config

S = '/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/2244bd05-9699-4a07-8836-2b6d9e43ca5f/scratchpad/s0_phase1'
CFG = '/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'
ARMS = ["current_qp", "hard_only_qp_allocator", "hybrid_option_f_allocator",
        "fractional_kelly_top_k", "equal_weight_top_k", "inverse_vol_top_k",
        "stage_a_a2_long_only"]

class _A:  # argparse shim for _load_sector_config
    strategy_config = CFG
sector_map, max_per_sector = _load_sector_config(_A())
bars = load_replay_bars_from_sim_db(
    f'{S}/sim_runs.frozen.db', '2024-01-01', '2026-06-22',
    fwd_horizon_days=1, sector_map=sector_map, max_per_sector=max_per_sector)
print('bars:', len(bars))

out = {'n_bars': len(bars), 'per_arm': {}}
ew_turnover = None
for name in ARMS:
    fn = get_allocator(name)
    deployed, max_name_w, max_sector_w, turnover = [], [], [], []
    for bar in bars:
        try:
            alloc = fn(bar.snap, mu=bar.mu, sigma=bar.sigma)
        except TypeError:
            alloc = fn(bar.snap, mu=bar.mu)
        w = np.asarray(alloc.target_w, dtype=float)
        deployed.append(float(np.sum(w)))
        max_name_w.append(float(np.max(w)) if w.size else 0.0)
        if bar.snap.sector_indicator is not None:
            max_sector_w.append(float(np.max(bar.snap.sector_indicator @ w)))
        turnover.append(float(np.sum(np.abs(alloc.delta_w))))
    dep = np.asarray(deployed)
    out['per_arm'][name] = {
        'deployed_fraction': {
            'mean': float(dep.mean()),
            'p05': float(np.percentile(dep, 5)), 'p25': float(np.percentile(dep, 25)),
            'median': float(np.percentile(dep, 50)),
            'p75': float(np.percentile(dep, 75)), 'p95': float(np.percentile(dep, 95)),
            'min': float(dep.min()), 'max': float(dep.max()),
        },
        'max_single_name_weight_overall': float(np.max(max_name_w)),
        'sessions_breaching_12pct_name': int(np.sum(np.asarray(max_name_w) > 0.12 + 1e-9)),
        'max_sector_weight_overall': float(np.max(max_sector_w)) if max_sector_w else None,
        'sessions_breaching_35pct_sector': int(np.sum(np.asarray(max_sector_w) > 0.35 + 1e-9)) if max_sector_w else None,
        'mean_turnover': float(np.mean(turnover)),
    }
    if name == 'equal_weight_top_k':
        ew_turnover = float(np.mean(turnover))
for name in ARMS:
    out['per_arm'][name]['turnover_ratio_vs_equal_weight'] = (
        out['per_arm'][name]['mean_turnover'] / ew_turnover if ew_turnover else None)
with open(f'{S}/s0_phase1_deployed_fraction_and_gates.json', 'w') as f:
    json.dump(out, f, indent=2, sort_keys=True)
for name in ARMS:
    a = out['per_arm'][name]
    d = a['deployed_fraction']
    print(f"{name:32s} dep_mean={d['mean']:.3f} dep_med={d['median']:.3f} maxw={a['max_single_name_weight_overall']:.3f} "
          f"n>12%={a['sessions_breaching_12pct_name']} maxsec={a['max_sector_weight_overall']:.3f} "
          f"n>35%={a['sessions_breaching_35pct_sector']} turn_ratio={a['turnover_ratio_vs_equal_weight']:.2f}")
