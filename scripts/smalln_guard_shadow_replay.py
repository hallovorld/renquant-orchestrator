#!/usr/bin/env python
"""FROZEN shadow-verdict REPLAY for the VetoWeakBuys small-n guard.

Read-only. Drives the DEPLOYED pinned pipeline code:
  .subrepo_runtime/repos/renquant-pipeline @ d32f7017
    - kernel.smalln_eligibility  (#207/#208 eligibility ledger, CLEAN predicate)
    - kernel.panel_pipeline.job_panel_scoring._smalln_guard_params / _apply_smalln_guard
Config: strategy_config.shadow.json ranking.panel_scoring (buy_floor_min_n=12,
        buy_floor_absolute_smalln=0.5).
DB: runs.alpaca.db opened mode=ro&immutable=1. Outputs to TEMP only.
"""
import sys, os, json, math, sqlite3, hashlib, statistics as st
from collections import Counter

PIN = "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-pipeline/src"
sys.path.insert(0, PIN)
from renquant_pipeline.kernel import smalln_eligibility as _elig          # DEPLOYED
from renquant_pipeline.kernel.panel_pipeline.job_panel_scoring import (    # DEPLOYED
    _smalln_guard_params, _apply_smalln_guard,
)

DB = "file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro&immutable=1"
CFG = "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.shadow.json"
PROD_CFG = "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"
OUT = os.path.dirname(os.path.abspath(__file__))

cfg = json.load(open(CFG))
panel_cfg = cfg.get("ranking", {}).get("panel_scoring", {})
watchlist = [str(t) for t in (cfg.get("watchlist") or [])]
elig_cfg = _elig.eligibility_config(panel_cfg)
guard = _smalln_guard_params(panel_cfg)           # (min_n, abs)  -> (12, 0.5)
MIN_FL = float(panel_cfg.get("buy_floor_min", 0.20))
N0, ABS = guard

con = sqlite3.connect(DB, uri=True)
c = con.cursor()

# ---- corpus: evidence-script PART-3 target set (latest live run WITH candidate
#      rows per date; n<10 OR mean+1sigma all-veto). Reproduced exactly. --------
cand_all = c.execute(
    "SELECT pr.run_date, cs.run_id, cs.ticker, cs.rank_score, cs.mu, cs.blocked_by "
    "FROM candidate_scores cs JOIN pipeline_runs pr ON cs.run_id=pr.run_id "
    "WHERE pr.run_type='live' AND cs.role='candidate' AND cs.rank_score IS NOT NULL"
).fetchall()
by_date = {}
for rd, rid, tk, rs, mu, blk in cand_all:
    by_date.setdefault(rd, {}).setdefault(rid, []).append((tk, float(rs), mu, blk))
# latest run_id per date among runs that HAVE candidate rows
sel_run = {rd: max(runs) for rd, runs in by_date.items()}

def floor_mean_std(scores):
    if len(scores) < 2: return MIN_FL
    return max(MIN_FL, st.fmean(scores) + 1.0 * st.stdev(scores))

def floor_quantile(scores, q=0.80):
    if len(scores) < 2: return MIN_FL
    s = sorted(scores); pos = min(max(q,0.0),1.0)*(len(s)-1)
    lo, hi = math.floor(pos), math.ceil(pos)
    qv = s[lo] if lo==hi else s[lo]*(1-(pos-lo)) + s[hi]*(pos-lo)
    return max(MIN_FL, qv)

def admitted(scores, fl): return [i for i,x in enumerate(scores) if x >= fl]

# corpus = dates where (n<10) OR (mean+1sigma admits 0) using the selected run
corpus = []
for rd, rid in sorted(sel_run.items()):
    rows = by_date[rd][rid]
    scores = [r[1] for r in rows]
    if len(scores) < 10 or len(admitted(scores, floor_mean_std(scores))) == 0:
        corpus.append((rd, rid, rows))

def counters_for(rid):
    cj = c.execute("select counters_json from pipeline_runs where run_id=?", (rid,)).fetchone()[0]
    return json.loads(cj) if cj else {}

def digest(rows):
    payload = json.dumps([(r[0], round(r[1],6)) for r in sorted(rows)], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

# --------------------------------------------------------------------------
# Per-session replay. status-quo floor computed in BOTH modes:
#   prod  = adaptive_mean_std (the PRODUCTION floor mode + what ran live on
#           07-16/17; this is the floor the guard is intended to govern)
#   shadow= adaptive_quantile (the floor mode the guard keys are staged under)
# CLEAN + relax-only branch use the DEPLOYED functions.
# --------------------------------------------------------------------------
sessions = []
for rd, rid, rows in corpus:
    ctr = counters_for(rid)
    scores = [r[1] for r in rows]
    tickers = [r[0] for r in rows]
    mus = {r[0]: r[2] for r in rows}
    n = len(scores)
    score_missing = int(ctr.get("panel_score_missing", 0) or 0)
    vol_dropped = int(ctr.get("risk_gate_vol_dropped", 0) or 0)

    # pre-floor exclusions reconstructed from candidate-row blocked_by that are
    # NOT the floor veto itself (floor veto = veto:rank_score_below_floor).
    blk = Counter()
    for tk, rs, mu, b in rows:
        if b and b != "veto:rank_score_below_floor" and b not in _elig._SCAN_DROP_REASONS:
            blk[b] += 1
    # add the risk-vol pre-floor drop the counter records (INTEGRITY realized_vol)
    pre_floor = dict(blk)
    if vol_dropped:
        pre_floor["risk_gate_vol"] = pre_floor.get("risk_gate_vol", 0) + vol_dropped

    # survivor set = candidate rows NOT pre-floor-excluded (they reach the floor)
    survivors = [tk for tk, rs, mu, b in rows
                 if not (b and b != "veto:rank_score_below_floor" and b not in _elig._SCAN_DROP_REASONS)]
    entered_scan = len(survivors) + score_missing
    # RECONSTRUCTED expected_universe: the generation-stage counter did not exist
    # at replay time (added by #207/#208). Reconstruct = entered + pre-floor drops.
    # NOTE: this makes mass-balance vacuous in replay (see verdict limitation).
    expected = entered_scan + sum(pre_floor.values())

    # failure markers: only surfaces persisted in counters are observable in replay
    markers = {
        "panel_score_missing": bool(score_missing),
        "rank_score_nan": False,   # all replayed rank_scores are finite by query filter
        # contract-failed / feed-staleness markers are ctx attributes, not persisted
        # counters; absent here (documented replay limitation).
    }

    partition = _elig.build_partition(
        watchlist=watchlist,
        counters={"expected_universe": expected, "panel_score_missing": score_missing},
        universe_tickers=None,               # ticker list not recorded -> counter fallback
        survivor_tickers=survivors,
        finite_n=len(survivors),
        nonfinite=0,
        scored=len(survivors),
        blocked={},                          # per-name pre-floor map unavailable; use counts
        markers=markers,
    )
    # inject reconstructed pre_floor counts (build_partition needs the blocked map;
    # we supply counts directly since per-name pre-floor tickers are not recorded)
    partition["pre_floor_exclusions"] = dict(sorted(pre_floor.items()))
    partition["expected_universe"] = expected
    partition["entered_scan"] = entered_scan

    clean, clean_reason = _elig.evaluate_clean(
        partition, watchlist=watchlist, blocked={}, config=elig_cfg,
    )

    finite_n = len(survivors)
    rec = {"date": rd, "run_id": rid, "n_candidates_role": n, "finite_n": finite_n,
           "scores_digest": digest(rows), "score_missing": score_missing,
           "vol_dropped": vol_dropped, "pre_floor_exclusions": partition["pre_floor_exclusions"],
           "expected_universe_reconstructed": expected, "clean": clean,
           "not_clean_reason": clean_reason,
           "funnel_integrity_structural": int(ctr.get("funnel_integrity_structural", 0) or 0),
           "calibrator_sign_laundered": int(ctr.get("calibrator_sign_laundered", 0) or 0)}

    for mode, floorfn in (("prod_adaptive_mean_std", floor_mean_std),
                          ("shadow_adaptive_quantile", floor_quantile)):
        F = floorfn([r[1] for r in rows if r[0] in survivors] or scores)
        # deployed relax-only branch decision
        if finite_n >= N0:
            action, relaxed, delta = "not_small_n", F, []
        elif clean:
            relaxed, _lbl = _apply_smalln_guard(F, "", n_finite=finite_n, min_fl=MIN_FL, guard=guard)
            action = "acted"
            surv_scores = {tk: rs for tk, rs, mu, b in rows if tk in survivors}
            delta = sorted([tk for tk, rs in surv_scores.items() if relaxed <= rs < F])
        else:
            action, relaxed, delta = f"suppressed:{clean_reason}", F, []
        surv_scores = {tk: rs for tk, rs, mu, b in rows if tk in survivors}
        admit_sq = sorted([tk for tk, rs in surv_scores.items() if rs >= F])
        admit_gd = sorted([tk for tk, rs in surv_scores.items() if rs >= relaxed])
        operative = (finite_n < N0) and (ABS < F)   # abs bound below status-quo floor
        rec[mode] = {"status_quo_floor": round(F,4), "relaxed_floor": round(relaxed,4),
                     "branch_action": action, "operative": operative,
                     "admitted_status_quo": admit_sq, "admitted_guarded": admit_gd,
                     "candidate_delta": delta,
                     "delta_mu": {t: round(mus.get(t,0.0),5) for t in delta}}
    sessions.append(rec)

# ---- synthetic mislabel-hazard tests (AC-B / AC-F / AC-G) via DEPLOYED code ----
def synth_clean(expected, entered, pre_floor, score_missing=0, nonfinite=0, markers=None):
    part = {"schema_version": 1, "watchlist_size": 145, "expected_universe": expected,
            "expected_universe_tickers_recorded": False, "entered_scan": entered,
            "scored": entered, "score_missing": score_missing, "nonfinite": nonfinite,
            "finite_n": entered, "pre_floor_exclusions": pre_floor, "unaccounted": [],
            "scan_surplus": [], "failure_markers": markers or {}}
    return _elig.evaluate_clean(part, watchlist=[f"T{i}" for i in range(145)], blocked={}, config=elig_cfg)

synth = {
  # AC-B: entered_scan accounts for the missing score (5 survivors + 1 missing = 6),
  # mass balance passes, funnel-integrity (cond 2) is what must fire.
  "AC-B score_missing>0 @ n=5": synth_clean(6, 6, {}, score_missing=1),
  "AC-F generation-starve exp=145 entered=5 zero-excl": synth_clean(145, 5, {}),
  "AC-G mass-wash-sale share>bound (wash=2 of 5)": synth_clean(5, 3, {"wash_sale:x": 2}),
  "AC-G wash-sale UNDER bound (wash=1 of 10)": synth_clean(10, 9, {"wash_sale:x": 1}),
  "healthy governed n=5 (realized_vol 1 of 6)": synth_clean(6, 5, {"risk_gate_vol": 1}),
  # failure marker: mass balance passes (entered 6 = expected 6), cond 4 must fire.
  "failure marker present": synth_clean(6, 6, {}, markers={"calibrator_contract_failed": True}),
}
synth_out = {k: {"clean": v[0], "reason": v[1]} for k, v in synth.items()}

result = {
  "corpus_size": len(sessions),
  "corpus_dates": [s["date"] for s in sessions],
  "guard": {"min_n": N0, "abs": ABS, "buy_floor_min": MIN_FL,
            "shadow_floor_mode": panel_cfg.get("buy_floor"),
            "prod_floor_mode": json.load(open(PROD_CFG)).get("ranking",{}).get("panel_scoring",{}).get("buy_floor"),
            "prod_guard_keys_present": "buy_floor_min_n" in json.load(open(PROD_CFG)).get("ranking",{}).get("panel_scoring",{})},
  "sessions": sessions,
  "synthetic_mislabel_tests": synth_out,
}
json.dump(result, open(os.path.join(OUT, "replay_raw.json"), "w"), indent=2)

# ---- console summary ----
print(f"CORPUS: {len(sessions)} sessions (evidence-script PART-3 target set)")
print(f"GUARD: min_n={N0} abs={ABS} | shadow_floor={panel_cfg.get('buy_floor')} "
      f"prod_floor={result['guard']['prod_floor_mode']} prod_keys={result['guard']['prod_guard_keys_present']}")
print()
hdr = f"{'date':>11} {'n':>3} {'CLEAN':>6} {'sqFloor(ms)':>11} {'relax':>6} {'action':>10} {'oper':>5} {'delta(prod mean+1σ)':>26}"
print(hdr); print("-"*len(hdr))
for s in sessions:
    p = s["prod_adaptive_mean_std"]
    print(f"{s['date']:>11} {s['finite_n']:>3} {str(s['clean']):>6} {p['status_quo_floor']:>11} "
          f"{p['relaxed_floor']:>6} {p['branch_action'][:10]:>10} {str(p['operative']):>5} "
          f"{','.join(p['candidate_delta']) or '-':>26}")
print("\nOPERATIVE (prod mean+1σ, abs<floor, n<N0):")
op = [s for s in sessions if s["prod_adaptive_mean_std"]["operative"]]
for s in op:
    p = s["prod_adaptive_mean_std"]
    print(f"  {s['date']}: CLEAN={s['clean']} delta={p['candidate_delta']} mu={p['delta_mu']}")
print(f"  operative count = {len(op)} ; operative & CLEAN = {sum(1 for s in op if s['clean'])}")
print("\nSYNTHETIC MISLABEL TESTS (expect NOT-CLEAN for AC-B/AC-F/AC-G-over/marker):")
for k, v in synth_out.items():
    print(f"  {v['clean']!s:>5}  {k}  -> {v['reason']}")
