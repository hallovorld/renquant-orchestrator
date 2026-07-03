#!/usr/bin/env python3
"""S-REL V5: adversarial independent verification of the M4 intercept finding.

Verifies (or overturns) the load-bearing numbers of renquant-pipeline PR #162
("BL-1 per-bar raw recentering", branch ``feat/bl1-recenter-raw``) — the
shadow replay whose committed evidence is
``doc/evidence/2026-07-02-bl1-recenter-shadow-replay.json`` — WITHOUT
importing any pipeline code. Everything is recomputed from first principles:

  * the calibrator's expected-return head is re-read from the live JSON
    artifact and re-implemented here as pure-Python piecewise-linear
    interpolation (clamped ends), including the load-time clip semantics;
  * the ER=0 ``neutral_raw`` anchor is re-derived by scanning the knot
    polyline for its first zero crossing;
  * raw panel scores and stored production mu come straight from
    ``score_distribution`` in the runs DB (opened READ-ONLY);
  * the live BL-2 ``calibrator_sign_laundered`` counters are cross-checked
    from ``pipeline_runs.counters_json`` (a prod-written source the replay
    tool did not use).

Checks (per the V5 audit item):
  1. replay fidelity — max |recomputed ER(raw) − stored prod mu| per run;
  2. laundering counts — sign(raw) vs sign(mu) disagreement, both directions;
  3. admission collapse at mu_floor=0.03 before/after recentering, plus
     sensitivity variants (mean center; candidates+holdings center);
  4. intercept decomposition — cross-sectional mean/median mu vs the floor,
     the per-name shift delta (is "intercept" a fair word), and an
     intercept-adjusted-floor counterfactual;
  5. vintage window — per-date raw-center/mu timeline locating the regime
     boundary, vs the calibrator/scorer trained_date + restamp evidence.

STRICTLY READ-ONLY on all production inputs. Output: stdout report + an
evidence JSON stamped with input content hashes and this script's own sha256
(S-REL convention).

Usage:
  python3 scripts/v5_m4_intercept_verification.py \
      [--db /Users/renhao/git/github/RenQuant/data/runs.alpaca.db] \
      [--calibrator .../panel-rank-calibration.json] \
      [--committed-evidence /path/to/their/evidence.json] \
      [--as-of 2026-07-02] [--mu-floor 0.03] \
      [--json-out doc/evidence/2026-07-03-v5-m4-verification.json]
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import hashlib
import json
import math
import os
import sqlite3
import statistics
import sys
from pathlib import Path

DEFAULT_DB = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
DEFAULT_CAL = (
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/"
    "artifacts/prod/panel-rank-calibration.json"
)

# The 6 runs the committed evidence replayed (assertion target).
EXPECTED_RUN_IDS = [
    "2026-07-02-live-85496d1c",
    "2026-07-01-live-01c54b39",
    "2026-06-30-live-b616357c",
    "2026-06-26-live-3d74ce5c",
    "2026-06-25-live-6c3aa3fa",
    "2026-06-24-live-710e3805",
]


# ---------------------------------------------------------------------------
# Independent calibrator implementation (no pipeline imports).
# ---------------------------------------------------------------------------
class ERHead:
    """Piecewise-linear expected-return head, re-implemented from the JSON.

    Semantics replicated from the prod contract (verified against
    renquant-pipeline ``global_calibrator.py`` by READING it, not importing):
    linear interpolation between knots, clamped to the end knot values
    outside the x range, with |y| clipped to 0.20 at load only when the
    stored knots exceed that bound.
    """

    def __init__(self, xs: list[float], ys: list[float]) -> None:
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError("ER head needs >= 2 aligned knots")
        for i in range(len(xs) - 1):
            if xs[i + 1] < xs[i]:
                raise ValueError(f"ER head x not monotone at knot {i}")
        absmax = max(abs(v) for v in ys)
        if absmax > 0.20:  # replicate the loader's clip (warn-and-clip)
            ys = [min(0.20, max(-0.20, v)) for v in ys]
        self.xs = [float(v) for v in xs]
        self.ys = [float(v) for v in ys]
        self.knots_clipped = absmax > 0.20

    def er(self, raw: float) -> float:
        xs, ys = self.xs, self.ys
        if raw <= xs[0]:
            return ys[0]
        if raw >= xs[-1]:
            return ys[-1]
        i = bisect.bisect_right(xs, raw) - 1
        # step over zero-width segments (np.interp uses the right value there
        # only when raw == x exactly, which bisect_right already handles)
        x0, x1 = xs[i], xs[i + 1]
        if x1 == x0:
            return ys[i + 1]
        w = (raw - x0) / (x1 - x0)
        return ys[i] + w * (ys[i + 1] - ys[i])

    def neutral_raw(self) -> float | None:
        """First zero crossing of the knot polyline, scanning from low raw."""
        xs, ys = self.xs, self.ys
        for i in range(len(ys) - 1):
            y0, y1 = ys[i], ys[i + 1]
            if y0 == 0.0:
                return xs[i]
            if y0 * y1 < 0.0:
                return xs[i] + (xs[i + 1] - xs[i]) * (0.0 - y0) / (y1 - y0)
        if ys[-1] == 0.0:
            return xs[-1]
        return None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def open_ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def dist(values: list[float]) -> dict[str, float]:
    vs = sorted(values)
    n = len(vs)

    def pct(p: float) -> float:
        # linear-interpolated percentile (numpy default), recomputed manually
        k = (n - 1) * p / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return vs[int(k)]
        return vs[f] * (c - k) + vs[c] * (k - f)

    mean = sum(vs) / n
    return {
        "n": n,
        "mean": mean,
        "median": statistics.median(vs),
        "std": math.sqrt(sum((v - mean) ** 2 for v in vs) / n),  # population, as numpy
        "p10": pct(10),
        "p90": pct(90),
        "min": vs[0],
        "max": vs[-1],
    }


def fetch_rows(
    conn: sqlite3.Connection, run_id: str, is_holding: int
) -> list[tuple[str, float, float | None]]:
    out: list[tuple[str, float, float | None]] = []
    for t, raw, mu in conn.execute(
        "SELECT ticker, raw_panel, mu FROM score_distribution "
        "WHERE run_id = ? AND is_holding = ? AND raw_panel IS NOT NULL "
        "ORDER BY ticker",
        (run_id, is_holding),
    ):
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        out.append((str(t), v, float(mu) if mu is not None else None))
    return out


def analyze_run(
    conn: sqlite3.Connection,
    head: ERHead,
    anchor: float,
    run_id: str,
    mu_floor: float,
) -> dict:
    cand = fetch_rows(conn, run_id, 0)
    hold = fetch_rows(conn, run_id, 1)
    tickers = [t for t, _, _ in cand]
    raws = [r for _, r, _ in cand]
    stored = [m for _, _, m in cand]

    er_b = [head.er(r) for r in raws]

    # --- check 1: fidelity vs stored prod mu -------------------------------
    diffs = [abs(e - m) for e, m in zip(er_b, stored) if m is not None]
    fidelity_max = max(diffs) if diffs else None

    # --- check 2: laundering ------------------------------------------------
    laund_neg_raw_pos_mu = sum(1 for r, e in zip(raws, er_b) if r < 0.0 and e > 0.0)
    laund_pos_raw_neg_mu = sum(1 for r, e in zip(raws, er_b) if r > 0.0 and e < 0.0)
    laund_total = sum(1 for r, e in zip(raws, er_b) if r * e < 0.0)
    # the same counters against the mu prod actually STORED that day
    stored_pairs = [(r, m) for r, m in zip(raws, stored) if m is not None]
    laund_total_stored_mu = sum(1 for r, m in stored_pairs if r * m < 0.0)

    # --- check 3: admission collapse, baseline + sensitivities -------------
    def recentered(center: float) -> list[float]:
        return [head.er(r - center + anchor) for r in raws]

    centers = {
        "median_candidates": statistics.median(raws),
        "mean_candidates": sum(raws) / len(raws),
    }
    all_raws = raws + [r for _, r, _ in hold]
    if all_raws:
        centers["median_cand_plus_holdings"] = statistics.median(all_raws)
        centers["mean_cand_plus_holdings"] = sum(all_raws) / len(all_raws)

    admitted_before = sum(1 for e in er_b if e >= mu_floor)
    admission_after: dict[str, int] = {}
    laundered_after: dict[str, int] = {}
    for name, c in centers.items():
        er_a = recentered(c)
        admission_after[name] = sum(1 for e in er_a if e >= mu_floor)
        laundered_after[name] = sum(
            1 for r, e in zip(raws, er_a) if (r - c) * e < 0.0
        )

    center_med = centers["median_candidates"]
    er_a_med = recentered(center_med)
    set_before = {t for t, e in zip(tickers, er_b) if e >= mu_floor}
    set_after = {t for t, e in zip(tickers, er_a_med) if e >= mu_floor}

    # --- check 4: intercept decomposition ----------------------------------
    d_b = dist(er_b)
    d_a = dist(er_a_med)
    shift_delta = [b - a for b, a in zip(er_b, er_a_med)]  # per-name mu removed
    d_delta = dist(shift_delta)
    sigma_b = d_b["std"] if d_b["std"] > 0 else float("nan")
    sigma_a = d_a["std"] if d_a["std"] > 0 else float("nan")
    # counterfactual: floor re-expressed relative to the pre-recenter median
    # (floor' = mu_floor - median mu_before + median mu_after). If the floor
    # was "mostly gating the intercept", admission at floor' after recentering
    # should land near the before count.
    adj_floor = mu_floor - d_b["median"] + d_a["median"]
    admitted_after_adj_floor = sum(1 for e in er_a_med if e >= adj_floor)

    # live prod counter (BL-2), written by the run itself
    live_counter = conn.execute(
        "SELECT json_extract(counters_json,'$.calibrator_sign_laundered') "
        "FROM pipeline_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()

    return {
        "run_id": run_id,
        "n_candidates": len(raws),
        "n_holdings_rows": len(hold),
        "check1_fidelity": {
            "max_abs_diff_recomputed_er_vs_stored_mu": fidelity_max,
            "n_rows_with_stored_mu": len(diffs),
        },
        "check2_laundering": {
            "recomputed_total_sign_disagree": laund_total,
            "raw_neg_mu_pos": laund_neg_raw_pos_mu,
            "raw_pos_mu_neg": laund_pos_raw_neg_mu,
            "sign_disagree_vs_stored_prod_mu": laund_total_stored_mu,
            "live_bl2_counter_from_pipeline_runs": (
                live_counter[0] if live_counter else None
            ),
        },
        "check3_admission": {
            "mu_floor": mu_floor,
            "admitted_before": admitted_before,
            "admitted_after_by_center": admission_after,
            "laundered_after_by_center": laundered_after,
            "gained": sorted(set_after - set_before),
            "lost": sorted(set_before - set_after),
            "centers": centers,
        },
        "check4_intercept": {
            "mu_before": d_b,
            "mu_after_median_center": d_a,
            "removed_shift_per_name": d_delta,
            "floor_minus_median_mu_before": mu_floor - d_b["median"],
            "floor_minus_median_mu_before_in_sigma": (mu_floor - d_b["median"]) / sigma_b,
            "floor_minus_median_mu_after_in_sigma": (mu_floor - d_a["median"]) / sigma_a,
            "intercept_adjusted_floor": adj_floor,
            "admitted_after_at_adjusted_floor": admitted_after_adj_floor,
        },
    }


def timeline(conn: sqlite3.Connection, since: str) -> list[dict]:
    """Per-date candidate raw-center and stored-mu regime timeline."""
    rows = conn.execute(
        "SELECT date, run_id, raw_panel, mu FROM score_distribution "
        "WHERE date >= ? AND is_holding = 0 AND raw_panel IS NOT NULL "
        "ORDER BY date, run_id",
        (since,),
    ).fetchall()
    by_date: dict[str, dict[str, list[float]]] = {}
    for d, _rid, raw, mu in rows:
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v):
            continue
        slot = by_date.setdefault(str(d), {"raw": [], "mu": []})
        slot["raw"].append(v)
        if mu is not None:
            slot["mu"].append(float(mu))
    out = []
    for d in sorted(by_date):
        raws = by_date[d]["raw"]
        mus = by_date[d]["mu"]
        out.append(
            {
                "date": d,
                "n_candidate_rows": len(raws),
                "median_raw": statistics.median(raws),
                "mean_stored_mu": (sum(mus) / len(mus)) if mus else None,
                "median_stored_mu": statistics.median(mus) if mus else None,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--calibrator", default=DEFAULT_CAL)
    ap.add_argument("--committed-evidence", default=None,
                    help="their evidence JSON, for field-by-field comparison")
    ap.add_argument("--as-of", default="2026-07-02",
                    help="select the 6 most recent full runs with date <= this")
    ap.add_argument("--mu-floor", type=float, default=0.03)
    ap.add_argument("--min-candidates", type=int, default=60)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    cal_payload = json.loads(Path(args.calibrator).read_text(encoding="utf-8"))
    if cal_payload.get("kind") != "global_panel_calibration":
        raise SystemExit("not a global_panel_calibration artifact")
    head = ERHead(
        cal_payload["expected_return"]["x"], cal_payload["expected_return"]["y"]
    )
    anchor = head.neutral_raw()
    if anchor is None:
        raise SystemExit("ER head never crosses zero — nothing to verify")
    native_days = cal_payload.get("metadata", {}).get("lookahead_days")

    conn = open_ro(args.db)
    try:
        runs = conn.execute(
            "SELECT run_id, date, COUNT(*) AS n FROM score_distribution "
            "WHERE is_holding = 0 AND raw_panel IS NOT NULL AND date <= ? "
            "GROUP BY run_id, date HAVING n >= ? "
            "ORDER BY date DESC, run_id DESC LIMIT 6",
            (args.as_of, args.min_candidates),
        ).fetchall()
        run_ids = [r[0] for r in runs]
        horizons = conn.execute(
            "SELECT DISTINCT expected_return_horizon_days, mu_horizon_days "
            "FROM score_distribution WHERE run_id IN (%s) AND is_holding = 0"
            % ",".join("?" * len(run_ids)),
            run_ids,
        ).fetchall()
        results = [
            analyze_run(conn, head, anchor, rid, args.mu_floor) for rid in run_ids
        ]
        for res, (_rid, d, _n) in zip(results, runs):
            res["date"] = d
        tl = timeline(conn, "2026-05-15")
    finally:
        conn.close()

    evidence: dict = {
        "tool": "scripts/v5_m4_intercept_verification.py",
        "purpose": (
            "S-REL V5 independent verification of the M4 intercept finding "
            "(renquant-pipeline PR #162 shadow replay) — no pipeline imports"
        ),
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "inputs": {
            "db": {
                "path": args.db,
                "sha256": sha256_file(args.db),
                "size_bytes": os.path.getsize(args.db),
                "mtime_utc": _dt.datetime.fromtimestamp(
                    os.path.getmtime(args.db), _dt.timezone.utc
                ).isoformat(timespec="seconds"),
                "note": "mutable prod DB — hash pins the exact bytes verified",
            },
            "calibrator": {
                "path": args.calibrator,
                "sha256": sha256_file(args.calibrator),
                "trained_date": cal_payload.get("trained_date"),
                "native_lookahead_days": native_days,
                "er_knots": len(head.xs),
                "er_knots_clipped_at_load": head.knots_clipped,
            },
        },
        "code_sha256_self": sha256_file(Path(__file__).resolve()),
        "recomputed_neutral_raw": anchor,
        "mu_floor": args.mu_floor,
        "as_of": args.as_of,
        "stored_horizon_days_distinct": [list(h) for h in horizons],
        "selected_run_ids": run_ids,
        "expected_run_ids_from_committed_evidence": EXPECTED_RUN_IDS,
        "run_selection_matches_committed_evidence": run_ids == EXPECTED_RUN_IDS,
        "runs": results,
        "regime_timeline_since_2026-05-15": tl,
    }

    if args.committed_evidence:
        theirs = json.loads(Path(args.committed_evidence).read_text())
        evidence["committed_evidence_sha256"] = sha256_file(args.committed_evidence)
        comp = []
        theirs_by_run = {r["run_id"]: r for r in theirs.get("runs", [])}
        for res in results:
            t = theirs_by_run.get(res["run_id"])
            if t is None:
                comp.append({"run_id": res["run_id"], "in_committed": False})
                continue
            mine_fid = res["check1_fidelity"][
                "max_abs_diff_recomputed_er_vs_stored_mu"
            ]
            comp.append(
                {
                    "run_id": res["run_id"],
                    "in_committed": True,
                    "laundered_before": {
                        "theirs": t["sign_laundered_before"],
                        "mine": res["check2_laundering"][
                            "recomputed_total_sign_disagree"
                        ],
                        "match": t["sign_laundered_before"]
                        == res["check2_laundering"]["recomputed_total_sign_disagree"],
                    },
                    "admitted_before": {
                        "theirs": t["admitted_at_mu_floor_before"],
                        "mine": res["check3_admission"]["admitted_before"],
                        "match": t["admitted_at_mu_floor_before"]
                        == res["check3_admission"]["admitted_before"],
                    },
                    "admitted_after": {
                        "theirs": t["admitted_at_mu_floor_after"],
                        "mine": res["check3_admission"]["admitted_after_by_center"][
                            "median_candidates"
                        ],
                        "match": t["admitted_at_mu_floor_after"]
                        == res["check3_admission"]["admitted_after_by_center"][
                            "median_candidates"
                        ],
                    },
                    "center_median": {
                        "theirs": t["cross_section_center_median"],
                        "mine": res["check3_admission"]["centers"][
                            "median_candidates"
                        ],
                        "abs_diff": abs(
                            t["cross_section_center_median"]
                            - res["check3_admission"]["centers"]["median_candidates"]
                        ),
                    },
                    "fidelity_max_abs_diff": {
                        "theirs": t["fidelity_check"][
                            "max_abs_diff_replayed_vs_stored_mu"
                        ],
                        "mine": mine_fid,
                        "abs_diff": abs(
                            t["fidelity_check"]["max_abs_diff_replayed_vs_stored_mu"]
                            - mine_fid
                        )
                        if mine_fid is not None
                        else None,
                    },
                }
            )
        evidence["comparison_vs_committed_evidence"] = comp

    # ---- stdout report -----------------------------------------------------
    print(f"recomputed neutral_raw = {anchor:.14f}")
    print(f"calibrator trained_date = {cal_payload.get('trained_date')}")
    print(f"stored horizon days (distinct) = {horizons}")
    print(f"run selection matches committed evidence: "
          f"{evidence['run_selection_matches_committed_evidence']}")
    hdr = (
        f"{'date':<11}{'n':>4}{'fid_max':>10}{'laun_b':>7}{'liveBL2':>8}"
        f"{'adm_b':>6}{'adm_a_med':>10}{'adm_a_mean':>11}{'adm_a_medH':>11}"
        f"{'med_mu_b':>9}{'adjfloor_adm':>13}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        fid = r["check1_fidelity"]["max_abs_diff_recomputed_er_vs_stored_mu"]
        adm = r["check3_admission"]["admitted_after_by_center"]
        print(
            f"{r['date']:<11}{r['n_candidates']:>4}"
            f"{fid:>10.6f}"
            f"{r['check2_laundering']['recomputed_total_sign_disagree']:>7}"
            f"{str(r['check2_laundering']['live_bl2_counter_from_pipeline_runs']):>8}"
            f"{r['check3_admission']['admitted_before']:>6}"
            f"{adm['median_candidates']:>10}"
            f"{adm['mean_candidates']:>11}"
            f"{adm.get('median_cand_plus_holdings', float('nan')):>11}"
            f"{r['check4_intercept']['mu_before']['median']:>9.4f}"
            f"{r['check4_intercept']['admitted_after_at_adjusted_floor']:>13}"
        )
    print("\nregime timeline (per date, candidates only):")
    for row in tl:
        mu = row["mean_stored_mu"]
        print(
            f"  {row['date']}  n={row['n_candidate_rows']:>4} "
            f"median_raw={row['median_raw']:>+9.4f} "
            f"mean_mu={mu if mu is None else round(mu, 4)}"
        )

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nevidence JSON -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
