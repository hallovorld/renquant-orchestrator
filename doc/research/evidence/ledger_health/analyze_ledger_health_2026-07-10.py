#!/usr/bin/env python3
"""Decision-ledger health check + first gate retro-verification (2026-07-10).

READ-ONLY analysis over three production stores (opened ro/immutable):
  * ~/renquant-data/decision_ledger.db          (S5 gate-verdict ledger, enabled 2026-07-05)
  * $RQ/data/runs.alpaca.db                     (active-path per-name substrate + forward returns)
  * $RQ/data/runs.alpaca_shadow.db              (shadow-path pipeline_runs, for run attribution)

Emits a JSON evidence blob (stdout + file). All gate re-derivations mirror the
pinned pipeline code paths:
  * VetoWeakBuysTask  floor = max(buy_floor_min=0.20, mean + 1.0*stdev) over the
    finite calibrated rank_score of the PRE-VETO candidate snapshot
    (configs/strategy_config.json: buy_floor="adaptive_mean_std", std_mult=1, min=0.20).
  * ConvictionGateTask: admit iff expected_return >= mu_floor(0.03); demean-ON
    counterfactual: admit iff (expected_return - xs_mean_full_snapshot) >= 0.03.

DIRECTIONAL / LOW-POWER by construction — tiny n, short horizons. This script is
a health check + earliest-signal probe, NOT a verdict engine.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import date
from pathlib import Path

RQ = Path("/Users/renhao/git/github/RenQuant")
LEDGER_DB = Path.home() / "renquant-data/decision_ledger.db"
ACTIVE_DB = RQ / "data/runs.alpaca.db"
SHADOW_DB = RQ / "data/runs.alpaca_shadow.db"
ENABLE_DATE = "2026-07-05"
TODAY = "2026-07-10"

MU_FLOOR = 0.03          # configs/strategy_config.json ranking.panel_scoring.conviction_gate.mu_floor
BUY_FLOOR_MIN = 0.20     # buy_floor_min
STD_MULT = 1.0           # buy_floor_std_mult

# Canonical FULL live runs (>=80 candidate_scores rows), XGB era (post 2026-06-23
# re-promotion; conviction_gate active) — from kpi_2026-07-07.json canonical list.
CANONICAL_XGB_PRE_ENABLE = [
    "2026-06-23-live-844746ad",
    "2026-06-25-live-6c3aa3fa",
    "2026-06-26-live-3d74ce5c",
    "2026-06-30-live-b616357c",
    "2026-07-01-live-01c54b39",
    "2026-07-02-live-85496d1c",
]
# Post-enable active-path full decisioning runs (the ones that wrote the ledger).
POST_ENABLE_ACTIVE = [
    "2026-07-06-live-ebb9c2ca",
    "2026-07-07-live-dc2a3247",
    "2026-07-08-live-369734c3",
    "2026-07-09-live-40e2dbd0",
    "2026-07-10-live-6f9d5284",
]
# Of these, the ones with candidate-role rows (07-08/09 had zero candidates).
POST_ENABLE_WITH_CANDS = [
    "2026-07-06-live-ebb9c2ca",
    "2026-07-07-live-dc2a3247",
    "2026-07-10-live-6f9d5284",
]


def ro(path: Path, immutable: bool = False) -> sqlite3.Connection:
    """Read-only open. WAL DBs (decision_ledger.db, runs.alpaca_shadow.db) reject
    mode=ro when the -shm sidecar is absent, so those fall back to immutable=1 —
    a snapshot read that never takes locks and never writes. Caveat: if a writer
    is active mid-read the snapshot can be slightly stale; row counts are stamped
    at read time in the evidence."""
    uri = f"file:{path}?{'immutable=1' if immutable else 'mode=ro'}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fmean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 6) if xs else None


def fmedian(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 6) if xs else None


def hit_rate(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x > 0) / len(xs), 4) if xs else None


def summarize(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return {"n": len(vals), "mean": fmean(vals), "median": fmedian(vals),
            "hit_rate": hit_rate(vals)}


# ---------------------------------------------------------------------------
# 1. Ledger health
# ---------------------------------------------------------------------------

def ledger_health() -> dict:
    lc = ro(LEDGER_DB, immutable=True)
    out: dict = {}
    out["db_path"] = str(LEDGER_DB)
    out["tables"] = [r[0] for r in lc.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out["decision_outcomes_table_present"] = "decision_outcomes" in out["tables"]
    out["total_rows"] = lc.execute("SELECT count(*) FROM decision_ledger").fetchone()[0]
    out["rows_pre_enable"] = lc.execute(
        "SELECT count(*) FROM decision_ledger WHERE as_of < ?", (ENABLE_DATE,)).fetchone()[0]
    out["pre_enable_rows"] = [dict(r) for r in lc.execute(
        "SELECT run_id, as_of, scope, gate, verdict, reason FROM decision_ledger "
        "WHERE as_of < ? ORDER BY as_of", (ENABLE_DATE,))]
    out["sessions"] = {r[0]: {"n_rows": r[1], "n_runs": r[2]} for r in lc.execute(
        "SELECT as_of, count(*), count(DISTINCT run_id) FROM decision_ledger "
        "WHERE as_of >= ? GROUP BY as_of ORDER BY as_of", (ENABLE_DATE,))}
    out["gate_verdict_distribution"] = [dict(r) for r in lc.execute(
        "SELECT gate, verdict, count(*) AS n FROM decision_ledger WHERE as_of >= ? "
        "GROUP BY gate, verdict ORDER BY gate, verdict", (ENABLE_DATE,))]
    out["scopes"] = [r[0] for r in lc.execute(
        "SELECT DISTINCT scope FROM decision_ledger WHERE as_of >= ?", (ENABLE_DATE,))]

    # per-run gate completeness (expect the formatter's 6 gates per run)
    per_run = lc.execute(
        "SELECT run_id, as_of, count(*) AS n FROM decision_ledger WHERE as_of >= ? "
        "GROUP BY run_id ORDER BY as_of, run_id", (ENABLE_DATE,)).fetchall()
    out["runs_with_6_gates"] = sum(1 for r in per_run if r["n"] == 6)
    out["runs_total_post_enable"] = len(per_run)

    # Run attribution: which runs DB owns each ledger run_id
    ac = ro(ACTIVE_DB)
    sc = ro(SHADOW_DB, immutable=True)
    attribution = []
    for r in per_run:
        rid = r["run_id"]
        in_active = ac.execute(
            "SELECT 1 FROM pipeline_runs WHERE run_id=?", (rid,)).fetchone() is not None
        in_shadow = sc.execute(
            "SELECT 1 FROM pipeline_runs WHERE run_id=?", (rid,)).fetchone() is not None
        attribution.append({"run_id": rid, "as_of": r["as_of"],
                            "in_active_db": in_active, "in_shadow_db": in_shadow})
    out["run_attribution"] = attribution
    out["n_active_runs"] = sum(1 for a in attribution if a["in_active_db"])
    out["n_shadow_runs"] = sum(1 for a in attribution if a["in_shadow_db"])
    out["n_orphan_runs"] = sum(
        1 for a in attribution if not a["in_active_db"] and not a["in_shadow_db"])

    # Field-fidelity probes
    conv = [dict(r) for r in lc.execute(
        "SELECT run_id, verdict, reason, inputs_json FROM decision_ledger "
        "WHERE gate='conviction' AND as_of >= ?", (ENABLE_DATE,))]
    mu_floor_stamps = [json.loads(c["inputs_json"]).get("mu_floor") for c in conv]
    out["conviction_mu_floor_stamped_values"] = sorted(set(mu_floor_stamps))
    out["conviction_mu_floor_expected_from_config"] = MU_FLOOR
    out["vol_gate_all_none_blocked"] = lc.execute(
        "SELECT count(*) FROM decision_ledger WHERE gate='vol_gate' AND as_of>=? "
        "AND reason != 'none blocked'", (ENABLE_DATE,)).fetchone()[0] == 0
    out["wash_sale_all_none_blocked"] = lc.execute(
        "SELECT count(*) FROM decision_ledger WHERE gate='wash_sale' AND as_of>=? "
        "AND reason != 'none blocked'", (ENABLE_DATE,)).fetchone()[0] == 0
    out["rotation_halve_with_zero_considered"] = lc.execute(
        "SELECT count(*) FROM decision_ledger WHERE gate='rotation' AND as_of>=? "
        "AND verdict='halve' AND json_extract(inputs_json,'$.n_considered')=0",
        (ENABLE_DATE,)).fetchone()[0]
    out["rotation_rows_post_enable"] = lc.execute(
        "SELECT count(*) FROM decision_ledger WHERE gate='rotation' AND as_of>=?",
        (ENABLE_DATE,)).fetchone()[0]

    # runs.alpaca.db gate_verdicts (the parallel, older table the KPI cross-checks)
    out["runs_db_gate_verdicts_rows"] = ac.execute(
        "SELECT count(*) FROM gate_verdicts").fetchone()[0]
    lc.close(); ac.close(); sc.close()
    return out


# ---------------------------------------------------------------------------
# 2. Per-name substrate + forward-return maturity
# ---------------------------------------------------------------------------

def substrate() -> dict:
    ac = ro(ACTIVE_DB)
    out: dict = {}
    runs = []
    for rid in POST_ENABLE_ACTIVE:
        row = {"run_id": rid}
        row["roles"] = {r[0]: r[1] for r in ac.execute(
            "SELECT role, count(*) FROM candidate_scores WHERE run_id=? GROUP BY role",
            (rid,))}
        stats = ac.execute(
            "SELECT count(*) n, sum(mu IS NOT NULL) mu_nn, sum(raw_score IS NOT NULL) raw_nn, "
            "sum(rank_score IS NOT NULL) rank_nn, sum(sigma IS NOT NULL) sigma_nn, "
            "sum(expected_return IS NOT NULL) er_nn, sum(selected=1) sel "
            "FROM candidate_scores WHERE run_id=?", (rid,)).fetchone()
        row["field_coverage"] = dict(stats)
        row["blocked_by"] = {(r[0] or "<null>"): r[1] for r in ac.execute(
            "SELECT blocked_by, count(*) FROM candidate_scores WHERE run_id=? "
            "GROUP BY blocked_by", (rid,))}
        row["trades"] = [dict(r) for r in ac.execute(
            "SELECT ticker, action, exit_reason FROM trades WHERE run_id=?", (rid,))]
        runs.append(row)
    out["post_enable_active_runs"] = runs

    # All trades (any run incl. monitor passes) in the window, and whether the
    # emitting run wrote ledger verdicts.
    lc = ro(LEDGER_DB, immutable=True)
    ledger_runs = {r[0] for r in lc.execute("SELECT DISTINCT run_id FROM decision_ledger")}
    lc.close()
    trades = [dict(r) for r in ac.execute(
        "SELECT trade_date, run_id, ticker, action, exit_reason FROM trades "
        "WHERE trade_date >= ? ORDER BY trade_date", (ENABLE_DATE,))]
    for t in trades:
        t["run_in_ledger"] = t["run_id"] in ledger_runs
    out["window_trades"] = trades
    out["window_exit_trades_outside_ledger_runs"] = sum(
        1 for t in trades if "sell" in t["action"] and not t["run_in_ledger"])
    out["window_exit_trades_total"] = sum(1 for t in trades if "sell" in t["action"])

    # forward-return population per session
    fwd = []
    for r in ac.execute(
            "SELECT as_of_date, count(*) n, sum(fwd_1d IS NOT NULL) f1, "
            "sum(fwd_5d IS NOT NULL) f5, sum(fwd_20d IS NOT NULL) f20, "
            "sum(fwd_60d IS NOT NULL) f60, max(updated_at) last_update "
            "FROM ticker_forward_returns WHERE as_of_date >= ? "
            "GROUP BY as_of_date ORDER BY as_of_date", (ENABLE_DATE,)):
        d = dict(r)
        # cross-section size that SHOULD eventually be covered (candidate-role names)
        d["candidate_names_that_day"] = ac.execute(
            "SELECT count(DISTINCT cs.ticker) FROM candidate_scores cs "
            "JOIN pipeline_runs pr ON pr.run_id=cs.run_id "
            "WHERE pr.run_date=? AND cs.role='candidate'", (d["as_of_date"],)).fetchone()[0]
        fwd.append(d)
    out["forward_return_population"] = fwd
    ac.close()
    return out


# ---------------------------------------------------------------------------
# 3. Gate retro-verification
# ---------------------------------------------------------------------------

def _load_run_candidates(ac, rid: str) -> list[dict]:
    return [dict(r) for r in ac.execute(
        "SELECT cs.ticker, cs.rank_score, cs.mu, cs.expected_return, cs.raw_score, "
        "cs.blocked_by, pr.run_date, tfr.fwd_1d, tfr.fwd_5d, tfr.fwd_20d, tfr.fwd_60d, "
        "(tfr.fwd_1d - spy.fwd_1d) rel_fwd_1d, (tfr.fwd_5d - spy.fwd_5d) rel_fwd_5d, "
        "(tfr.fwd_20d - spy.fwd_20d) rel_fwd_20d "
        "FROM candidate_scores cs "
        "JOIN pipeline_runs pr ON pr.run_id=cs.run_id "
        "LEFT JOIN ticker_forward_returns tfr ON tfr.ticker=cs.ticker AND tfr.as_of_date=pr.run_date "
        "LEFT JOIN ticker_forward_returns spy ON spy.ticker='SPY' AND spy.as_of_date=pr.run_date "
        "WHERE cs.run_id=? AND cs.role='candidate'", (rid,))]


def retro_veto(run_ids: list[str], label: str) -> dict:
    """VetoWeakBuys marginal-band analysis.

    Bands per run (over finite rank_score of the full pre-veto candidate snapshot):
      admitted_core : rank_score >= floor            (floor = max(0.20, mean+1.0*std))
      marginal      : mean+0.5*std <= rank_score < floor   (vetoed today; would be
                      admitted under a hypothetical 0.5-sigma floor)
      deep_veto     : rank_score < mean+0.5*std
    """
    ac = ro(ACTIVE_DB)
    bands = {"admitted_core": [], "marginal_0p5_to_1p0_sigma": [], "deep_veto": []}
    per_run = []
    agree_num = agree_den = 0
    for rid in run_ids:
        cands = _load_run_candidates(ac, rid)
        scored = [c for c in cands if c["rank_score"] is not None]
        if len(scored) < 2:
            per_run.append({"run_id": rid, "skipped": "n<2 scored candidates"})
            continue
        vals = [c["rank_score"] for c in scored]
        m, s = statistics.fmean(vals), statistics.stdev(vals)
        floor = max(BUY_FLOOR_MIN, m + STD_MULT * s)
        half = m + 0.5 * s
        n_band = {k: 0 for k in bands}
        for c in scored:
            rs = c["rank_score"]
            if rs >= floor:
                b = "admitted_core"
            elif rs >= half:
                b = "marginal_0p5_to_1p0_sigma"
            else:
                b = "deep_veto"
            bands[b].append(c)
            n_band[b] += 1
            # reconstruction-agreement: below-floor names should carry the veto tag
            # (unless floored later by a post-veto stage); above-floor should not.
            tagged = (c["blocked_by"] or "").startswith("veto:rank_score_below_floor")
            agree_den += 1
            if (rs < floor) == tagged:
                agree_num += 1
        per_run.append({"run_id": rid, "run_date": scored[0]["run_date"],
                        "n_scored": len(scored), "mean": round(m, 4),
                        "std": round(s, 4), "floor": round(floor, 4),
                        "floor_is_min_failsafe": floor == BUY_FLOOR_MIN,
                        "band_counts": n_band})
    result = {"label": label, "per_run": per_run,
              "floor_reconstruction_agreement": round(agree_num / agree_den, 4) if agree_den else None,
              "bands": {}}
    for b, rows in bands.items():
        result["bands"][b] = {
            h: summarize(rows, h)
            for h in ("fwd_1d", "rel_fwd_1d", "fwd_5d", "rel_fwd_5d", "fwd_20d", "rel_fwd_20d")
        }
        result["bands"][b]["n_names"] = len(rows)
    ac.close()
    return result


def retro_conviction(run_ids: list[str], label: str) -> dict:
    """ConvictionGate mu-floor + demean-ON counterfactual (#145/#190 metrics,
    computed at whatever horizon has matured)."""
    ac = ro(ACTIVE_DB)
    admitted_off, dropped_by_demean, added_by_demean, blocked_actual = [], [], [], []
    per_run = []
    for rid in run_ids:
        cands = _load_run_candidates(ac, rid)
        ers = [c["expected_return"] for c in cands if c["expected_return"] is not None]
        if not ers:
            per_run.append({"run_id": rid, "skipped": "no expected_return"})
            continue
        xs_mean = statistics.fmean(ers)
        survivors = [c for c in cands
                     if not (c["blocked_by"] or "").startswith("veto:")
                     and c["expected_return"] is not None]
        adm_off = [c for c in survivors if c["expected_return"] >= MU_FLOOR]
        adm_on = [c for c in survivors if (c["expected_return"] - xs_mean) >= MU_FLOOR]
        off_t = {c["ticker"] for c in adm_off}
        on_t = {c["ticker"] for c in adm_on}
        admitted_off += adm_off
        dropped_by_demean += [c for c in adm_off if c["ticker"] not in on_t]
        added_by_demean += [c for c in adm_on if c["ticker"] not in off_t]
        blocked_actual += [c for c in cands
                           if (c["blocked_by"] or "") == "conviction:mu_below_floor"]
        per_run.append({
            "run_id": rid, "run_date": cands[0]["run_date"] if cands else None,
            "n_candidates": len(cands), "xs_mean_mu": round(xs_mean, 4),
            "max_mu": round(max(ers), 4),
            "n_veto_survivors": len(survivors),
            "n_admit_demean_off": len(adm_off), "n_admit_demean_on": len(adm_on),
            "zero_admission_under_demean_on": len(adm_on) == 0,
            "headroom_max_mu_minus_xsmean": round(max(ers) - xs_mean, 4),
        })
    horizons = ("fwd_1d", "rel_fwd_1d", "fwd_5d", "rel_fwd_5d", "fwd_20d", "rel_fwd_20d")
    ac.close()
    return {
        "label": label, "mu_floor": MU_FLOOR, "per_run": per_run,
        "admitted_demean_off": {h: summarize(admitted_off, h) for h in horizons},
        "dropped_by_demean_on": {h: summarize(dropped_by_demean, h) for h in horizons},
        "added_by_demean_on": {h: summarize(added_by_demean, h) for h in horizons},
        "actual_conviction_blocked": {h: summarize(blocked_actual, h) for h in horizons},
        "n_dropped_by_demean_names": len(dropped_by_demean),
        "n_added_by_demean_names": len(added_by_demean),
        "n_actual_conviction_blocked": len(blocked_actual),
    }


def main() -> None:
    evidence = {
        "as_of": TODAY,
        "generated_by": "doc/research/evidence/ledger_health/analyze_ledger_health_2026-07-10.py",
        "inputs": {
            "decision_ledger_db": str(LEDGER_DB),
            "active_runs_db": str(ACTIVE_DB),
            "shadow_runs_db": str(SHADOW_DB) + " (immutable=1 snapshot read)",
        },
        "ledger_health": ledger_health(),
        "per_name_substrate": substrate(),
        "retro_veto_post_enable": retro_veto(
            POST_ENABLE_WITH_CANDS, "post-enable sessions 07-06..07-10 (fwd_1d matured for 07-06/07-07 only)"),
        "retro_veto_xgb_era": retro_veto(
            CANONICAL_XGB_PRE_ENABLE + POST_ENABLE_WITH_CANDS,
            "XGB-era canonical runs 2026-06-23..2026-07-10 (fwd_5d matured through 07-02; fwd_20d pending for all)"),
        "retro_conviction_post_enable": retro_conviction(
            POST_ENABLE_WITH_CANDS, "post-enable sessions (fwd_1d only)"),
        "retro_conviction_xgb_era": retro_conviction(
            CANONICAL_XGB_PRE_ENABLE + POST_ENABLE_WITH_CANDS,
            "XGB-era canonical runs 2026-06-23..2026-07-10"),
    }
    out_path = Path(__file__).parent / "ledger_health_2026-07-10.json"
    out_path.write_text(json.dumps(evidence, indent=2, default=str) + "\n")
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    main()
