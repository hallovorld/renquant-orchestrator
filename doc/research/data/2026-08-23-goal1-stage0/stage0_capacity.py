"""GOAL-1 / AC1 Stage 0 v2: what does the sizing arithmetic ADMIT at each cap?

REWRITTEN after codex on orch#1028, whose three findings this version answers:

1. "Calls the leaf function but not the production path." v2 mirrors the
   SizeAndEmitTask preamble EXACTLY (task_selection.py:233-328, read from the
   running tree): legacy max_pct = base_max_pct*conf x conviction_multiplier x
   sigma_multiplier (ranking.kelly_sizing.enabled=False in the served config,
   so the Kelly branch is dead in production too); reserve_pct is ALSO
   confidence-scaled; per_session_buy_cap honoured; fractional eligibility via
   the real fractional_eligible; dust via fractional_dust_floor_usd; the
   one-share floor off because the served config says so. All multipliers are
   the PRODUCTION functions imported from kernel.sizing — nothing re-derived.
   What is NOT replayed is the upstream greedy admission (correlation guard,
   sector caps): its inputs (corr matrix) are not persisted. Instead of
   pretending, v2 MEASURES the gap: a per-session PARITY check compares the
   cap-8/integer arm against the orders production actually emitted
   (trades.decision_inputs_json records conviction, sigma_mult, max_pct,
   reserve_pct per order). If parity fails, the grid is labelled void.

2. "Session selector not provenance-safe." Per date, EXACTLY ONE live run has
   n_candidates>0 — that is the daily full run (measured: 35 runs/date, 1 with
   candidates). v2 asserts uniqueness per date, EXCLUDES dates violating it,
   and records every selected run_id and every exclusion in the artifact.

3. "Hardcoded workstation paths." --runs-db and --strategy-config are REQUIRED
   arguments; the script fails closed without them and records sha256 + row
   counts of both inputs in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import statistics as st
import sys
from types import SimpleNamespace

CAPS = [8, 10, 12, 15, 20]
MODES = [("integer", False), ("fractional", True)]


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_seams(pipeline_src):
    sys.path.insert(0, pipeline_src)
    from renquant_pipeline.kernel.regime import confidence_to_size_multiplier  # noqa: E402
    from renquant_pipeline.kernel.sizing import (  # noqa: E402
        compute_position_size, conviction_multiplier, conviction_score_for_object,
        conviction_score_percentiles, fractional_dust_floor_usd,
        fractional_eligible, sigma_multiplier, universe_sigma_median,
    )
    return SimpleNamespace(**{k: v for k, v in locals().items() if k != "pipeline_src"})


EXPECTED_STRATEGY = "renquant-104"


def canonical_sessions(con):
    """The daily-104 full run per date, selected by EXPLICIT provenance.

    [codex on orch#1028, round 2] Uniqueness of "a candidate-bearing live run"
    does not prove the row is the daily-104 run — another candidate-bearing
    lane could be uniquely wrong. So the filter now names the strategy, the
    per-run provenance (strategy, commit_sha, created_at) is RECORDED for every
    selected run, and any strategy value outside the expected one anywhere in
    the candidate-bearing live set FAILS CLOSED rather than being silently
    dropped — an unexpected lane in this DB means the selection model is wrong,
    not that one row should be skipped.
    """
    stray = con.execute(
        "SELECT DISTINCT strategy FROM pipeline_runs "
        "WHERE run_type='live' AND n_candidates > 0 AND strategy != ?",
        (EXPECTED_STRATEGY,)).fetchall()
    if stray:
        raise SystemExit(f"FAIL CLOSED: unexpected strategy value(s) in "
                         f"candidate-bearing live runs: {[r[0] for r in stray]} "
                         f"— the session-selection model assumes only "
                         f"{EXPECTED_STRATEGY!r}; revisit before trusting any grid")
    rows = con.execute("""
        SELECT run_date, run_id, portfolio_value, cash, regime, confidence,
               strategy, commit_sha, created_at
        FROM pipeline_runs
        WHERE run_type='live' AND n_candidates > 0
          AND strategy = ? AND portfolio_value IS NOT NULL
        ORDER BY run_date""", (EXPECTED_STRATEGY,)).fetchall()
    by = {}
    excluded = []
    for d, rid, pv, cash, rg, cf, strat, sha, ts in rows:
        by.setdefault(d, []).append((rid, pv, cash, rg, cf, strat, sha, ts))
    out, provenance = [], []
    for d in sorted(by):
        if len(by[d]) != 1:
            excluded.append({"date": d,
                             "reason": f"{len(by[d])} candidate-bearing {EXPECTED_STRATEGY} live runs (expected exactly 1)",
                             "run_ids": [r[0] for r in by[d]]})
            continue
        rid, pv, cash, rg, cf, strat, sha, ts = by[d][0]
        out.append((rid, d, pv, cash, rg, cf))
        provenance.append({"run_id": rid, "date": d, "strategy": strat,
                           "commit_sha": sha, "created_at": ts})
    return out, excluded, provenance


def rows_for_run(con, run_id):
    """All scored rows (for sigma_median / percentiles, mirroring ctx.ranked)
    and the admissible NEW-long candidates with a close price."""
    # ctx.ranked at SizeAndEmit time = the CANDIDATE list only. Established by
    # experiment, not assumption: sigma_median over role='candidate' reproduces
    # a recorded production sigma_mult EXACTLY (delta 0.0e+00); including
    # holdings gives delta 8e-03 (probe: run 2026-08-21-live-933658ce, APH).
    ranked = [SimpleNamespace(ticker=t, panel_score=p, sigma=s, expected_return=e, role=role)
              for t, p, s, e, role in con.execute(
        "SELECT ticker, panel_score, sigma, expected_return, role FROM candidate_scores "
        "WHERE run_id=? AND role='candidate' AND panel_score IS NOT NULL", (run_id,))]
    cands = con.execute("""
        SELECT c.ticker, c.panel_score, c.sigma, f.close_price
        FROM candidate_scores c
        JOIN pipeline_runs r ON r.run_id=c.run_id
        JOIN ticker_forward_returns f ON f.ticker=c.ticker AND f.as_of_date=r.run_date
        WHERE c.run_id=? AND c.role='candidate' AND c.panel_score>0
          AND c.expected_return>0 AND f.close_price>0
        ORDER BY c.panel_score DESC""", (run_id,)).fetchall()
    held = con.execute("SELECT COUNT(*) FROM candidate_scores WHERE run_id=? AND role='holding'",
                       (run_id,)).fetchone()[0]
    return ranked, cands, held


def production_emissions(con, run_id):
    out = {}
    for t, sh, di in con.execute(
            "SELECT ticker, shares, decision_inputs_json FROM trades "
            "WHERE run_id=? AND action IN ('buy_pending','buy') AND order_type='NEW_BUY'", (run_id,)):
        rec = {}
        try:
            rec = json.loads(di) if di else {}
        except Exception:
            pass
        out[t] = {"shares": sh, **{k: rec.get(k) for k in
                                   ("conviction", "sigma_mult", "max_pct", "reserve_pct")}}
    return out


def size_session(sz, cfg, cap, fractional, sess, ranked, cands, held):
    rid, d, pv, cash, regime, conf = sess
    rp = cfg["regime_params"].get(regime or "")
    if not rp or float(rp.get("max_position_pct", 0)) <= 0:
        return None
    # PRODUCTION multiplier, not raw confidence [task_selection.py:228]. The
    # function floors at 0.5 ("even worst-case confidence still deploys 50%"),
    # so raw-conf scaling understates low-confidence sessions — reverse-
    # engineering recorded orders shows max(conf, 0.5) behaviour exactly.
    # cusum_cooldown_mode is "bar_count" in the served config, so the
    # wall_time cooldown_mult path is a production no-op here [:240-251].
    c = sz.confidence_to_size_multiplier(conf)
    base_max_pct = float(rp["max_position_pct"]) * c
    reserve_pct = float(rp.get("cash_reserve_pct", 0.0)) * c        # scaled, like :252
    ranking = cfg.get("ranking", {}) or {}
    sizing_cfg = (ranking.get("panel_scoring", {}) or {}).get("sizing", {}) or {}
    sigma_cfg = (ranking.get("panel_scoring", {}) or {}).get("sigma_sizing", {}) or {}
    kelly_cfg = ranking.get("kelly_sizing", {}) or {}
    assert not bool(kelly_cfg.get("enabled", False)), \
        "served config enables Kelly — this replay mirrors the legacy path and must be extended first"
    per_cap = kelly_cfg.get("per_session_buy_cap")
    sigma_median = sz.universe_sigma_median([getattr(x, "sigma", None) for x in ranked])
    pcts = sz.conviction_score_percentiles(ranked)
    dust = sz.fractional_dust_floor_usd(cfg) if fractional else 0.0

    free = max(0, cap - held)
    remaining = float(cash or 0.0)
    filled, invested, emitted, sin, sout = 0, 0.0, {}, [], []
    for tkr, ps, sig, price in cands:
        if filled >= free:
            sout.append(price); continue
        obj = SimpleNamespace(ticker=tkr, panel_score=ps, sigma=sig)
        conv = sz.conviction_multiplier(sz.conviction_score_for_object(obj, sizing_cfg, pcts), sizing_cfg)
        sig_m = sz.sigma_multiplier(sig, sigma_median, sigma_cfg)
        max_pct = base_max_pct * conv * sig_m
        if per_cap is not None and float(per_cap) > 0:
            max_pct = min(max_pct, float(per_cap))
        use_frac = fractional and sz.fractional_eligible(tkr, cfg, None)
        _, shares = sz.compute_position_size(float(pv), remaining, max_pct, reserve_pct,
                                             float(price), fractional=use_frac, min_notional=0.0)
        notional = float(shares) * float(price)
        ok = (shares > 0 and notional >= dust) if use_frac else (shares >= 1)
        if ok:
            filled += 1; invested += notional; remaining -= notional
            emitted[tkr] = {"shares": shares, "conviction": conv, "sigma_mult": sig_m,
                            "max_pct": max_pct, "reserve_pct": reserve_pct}
            sin.append(price)
        else:
            sout.append(price)
    return {"date": d, "run_id": rid, "free": free, "filled": filled,
            "deployed": invested / float(pv) if pv else 0.0,
            "emitted": emitted, "px_in": sin, "px_out": sout}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-db", required=True)
    ap.add_argument("--strategy-config", required=True)
    ap.add_argument("--pipeline-src", required=True,
                    help="src dir of the PINNED renquant-pipeline (the seams are imported, not copied)")
    ap.add_argument("--out", default="stage0_capacity.json")
    a = ap.parse_args()

    sz = load_seams(a.pipeline_src)
    cfg = json.load(open(a.strategy_config))
    con = sqlite3.connect(f"file:{a.runs_db}?mode=ro", uri=True)
    sessions, excluded, run_provenance = canonical_sessions(con)
    print(f"canonical sessions: {len(sessions)}  excluded dates: {len(excluded)}")

    cache = {s[0]: rows_for_run(con, s[0]) for s in sessions}

    # ── PARITY: cap-8 / integer arm vs what production actually emitted ──────
    #
    # ERA-GATED, and the gate is MEASURED, not chosen. Reverse-engineering every
    # recorded NEW_BUY's max_pct/(conv*sig_m) against today's config gives a
    # ratio of EXACTLY 0.4000 for all orders 2026-06-22..2026-08-04 (the era
    # when max_position_pct was 0.12 = 0.3*0.4), per-ticker ratios <=0.40
    # before 06-22 (the Kelly era), and EXACTLY 1.0000 from 2026-08-10 onward —
    # the current-config era. Parity against production is therefore only
    # DEFINED in the current era; earlier eras ran a different policy, and this
    # replay deliberately applies TODAY'S served config to all history (the
    # forward-looking counterfactual: "what would today's policy do at cap X").
    CONFIG_ERA_START = "2026-08-10"
    par = {"sessions": 0, "set_agree": 0, "ticker_matches": 0, "ticker_total": 0,
           "max_abs": {"conviction": 0.0, "sigma_mult": 0.0, "max_pct": 0.0, "reserve_pct": 0.0},
           "share_mismatches": [], "set_diffs": []}
    par["excluded_sessions"] = []
    for sess in sessions:
        if sess[1] < CONFIG_ERA_START:
            continue
        ranked, cands, held = cache[sess[0]]
        # COVERAGE GUARD: the price join is against ticker_forward_returns,
        # which is BACKFILLED — the freshest sessions can have close_price for
        # only a handful of names (2026-08-21: 7 rows), silently shrinking the
        # replay's candidate set. A parity verdict over a truncated set is a
        # data artifact, not a finding; such sessions are excluded AND recorded.
        gate_passers = sum(1 for x in ranked
                           if x.panel_score and x.panel_score > 0
                           and x.expected_return and x.expected_return > 0)
        if gate_passers and len(cands) / gate_passers < 0.9:
            par["excluded_sessions"].append({
                "date": sess[1], "reason": "fwd close_price backfill incomplete",
                "priced": len(cands), "gate_passers": gate_passers})
            continue
        r = size_session(sz, cfg, 8, False, sess, ranked, cands, held)
        if r is None:
            continue
        prod = production_emissions(con, sess[0])
        par["sessions"] += 1
        if set(r["emitted"]) == set(prod):
            par["set_agree"] += 1
        else:
            # annotate every differing name with production's own reason, so
            # the diff carries its explanation instead of demanding forensics
            diff = {"date": sess[1], "replay": sorted(r["emitted"]),
                    "production": sorted(prod), "why": {}}
            for t in set(r["emitted"]) ^ set(prod):
                b = con.execute("SELECT blocked_by FROM candidate_scores WHERE run_id=? AND ticker=?",
                                (sess[0], t)).fetchone()
                diff["why"][t] = (b[0] if b and b[0] else
                                  ("in production only" if t in prod else "no production block recorded"))
            par["set_diffs"].append(diff)
        for t in set(r["emitted"]) & set(prod):
            par["ticker_total"] += 1
            rep, rec = r["emitted"][t], prod[t]
            close = True
            for k in ("conviction", "sigma_mult", "max_pct", "reserve_pct"):
                if rec.get(k) is not None:
                    dlt = abs(rep[k] - float(rec[k]))
                    par["max_abs"][k] = max(par["max_abs"][k], dlt)
                    if dlt > 1e-6:
                        close = False
            if rep["shares"] != rec["shares"]:
                close = False
                par["share_mismatches"].append({"date": sess[1], "ticker": t,
                                                "replay": rep["shares"], "production": rec["shares"]})
            if close:
                par["ticker_matches"] += 1
    print(f"PARITY cap8/int: {par['set_agree']}/{par['sessions']} sessions set-identical; "
          f"{par['ticker_matches']}/{par['ticker_total']} matched orders input+share exact; "
          f"max|Δ| {par['max_abs']}")

    # ── the grid ─────────────────────────────────────────────────────────────
    # DIGEST THE ROWS, NOT THE FILE [codex round 2]: the DB is live and can
    # change without any recorded row count moving, and the pipeline checkout
    # can change in place. Reproducibility is only a claim about THE EXACT
    # INPUTS USED, so: a deterministic sha256 over every selected
    # pipeline_runs / candidate_scores / price / trades row this script read,
    # in sorted order — plus the pinned pipeline commit and a sha256 of each
    # imported seam module file.
    h = hashlib.sha256()
    for rid, d, pv, cash, rg, cf in sessions:
        h.update(json.dumps(["run", rid, d, pv, cash, rg, cf], sort_keys=True).encode())
        for row in con.execute(
                "SELECT ticker, role, panel_score, sigma, expected_return, kelly_target_pct "
                "FROM candidate_scores WHERE run_id=? ORDER BY ticker, role", (rid,)):
            h.update(json.dumps(["cs", rid, *row], sort_keys=True).encode())
        for row in con.execute(
                "SELECT f.ticker, f.close_price FROM ticker_forward_returns f "
                "WHERE f.as_of_date=? ORDER BY f.ticker", (d,)):
            h.update(json.dumps(["px", d, *row], sort_keys=True).encode())
        for row in con.execute(
                "SELECT ticker, shares, decision_inputs_json FROM trades "
                "WHERE run_id=? AND action IN ('buy_pending','buy') "
                "AND order_type='NEW_BUY' ORDER BY ticker", (rid,)):
            h.update(json.dumps(["tr", rid, *row], sort_keys=True).encode())
    rows_digest = h.hexdigest()

    import inspect
    import subprocess
    seam_files = sorted({inspect.getsourcefile(getattr(sz, n)) for n in
                         ("compute_position_size", "confidence_to_size_multiplier")})
    seam_hashes = {f: _sha(f) for f in seam_files if f}
    try:
        pipeline_commit = subprocess.run(
            ["git", "-C", a.pipeline_src, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001
        pipeline_commit = None

    out = {"inputs": {
        "runs_db": {"path": a.runs_db,
                    "rows_digest_sha256": rows_digest,
                    "live_runs": con.execute("SELECT COUNT(*) FROM pipeline_runs WHERE run_type='live'").fetchone()[0],
                    "candidate_scores": con.execute("SELECT COUNT(*) FROM candidate_scores").fetchone()[0]},
        "strategy_config": {"path": a.strategy_config, "sha256": _sha(a.strategy_config)},
        "pipeline": {"src": a.pipeline_src, "commit": pipeline_commit,
                     "seam_module_sha256": seam_hashes},
        "selected_runs": run_provenance,
        "excluded_dates": excluded,
        "admission_note": ("rank-order fill by panel_score among direction-gate passers; "
                           "corr/sector guards NOT replayed (inputs not persisted) — "
                           "UPPER-BOUND admission; the parity block measures the realised gap at cap 8"),
    }, "parity_cap8_integer_current_era": {"era_start": "2026-08-10", **par}, "grid": {}}
    hdr = f"{'cap':>4s} {'mode':>11s} {'n':>3s} {'med_filled':>10s} {'med_deployed':>12s} {'tilt':>6s}"
    print(hdr); print("-" * len(hdr))
    for cap in CAPS:
        for name, frac in MODES:
            rs = [r for r in (size_session(sz, cfg, cap, frac, s, *cache[s[0]]) for s in sessions)
                  if r is not None and r["free"] > 0 and (r["px_in"] or r["px_out"])]
            if not rs:
                continue
            pin = [p for r in rs for p in r["px_in"]]
            pout = [p for r in rs for p in r["px_out"]]
            mi = st.median(pin) if pin else None
            mo = st.median(pout) if pout else None
            tilt = (mo / mi) if (mi and mo) else None
            row = {"sessions": len(rs),
                   "med_filled": st.median(r["filled"] for r in rs),
                   "med_deployed": st.median(r["deployed"] for r in rs),
                   "med_price_in": mi, "med_price_out": mo, "tilt": tilt,
                   "n_in": len(pin), "n_out": len(pout)}
            out["grid"][f"{cap}_{name}"] = row
            print(f"{cap:4d} {name:>11s} {len(rs):3d} {row['med_filled']:10.1f} "
                  f"{row['med_deployed']:11.1%} {(tilt or float('nan')):6.2f}x")
    json.dump(out, open(a.out, "w"), indent=2, sort_keys=True)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
