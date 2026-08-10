#!/usr/bin/env python3
"""G-D (task #23): shadow-fleet information census.

Quantifies, from EXISTING records only (no future accrual, no new runs), how much
independent information the shadow-lane fleet actually carries:

  1. Lane inventory: every shadow score sink actually recording (per-scorer lanes
     inside the shared alpaca_shadow sink, the dedicated per-lane blend sinks,
     and the file ledgers), with first/last record date, rows, days,
     distinct tickers/day.
  2. Cross-lane per-day Spearman rank correlations (median across days), and each
     lane's correlation vs the PRIMARY served scorer's canonical daily panel.
     Redundancy rule (from the task): median |rho| > 0.95 vs the primary or vs
     another lane => the lane carries little marginal information.
  3. Realized-outcome census vs the FROZEN corpus labels (per-day cross-sectional
     z of fwd_5d_excess in alpha158_291_fundamental_dataset.parquet, which ends
     2026-05-07): lane daily top-5 mean label-z, day counts reported honestly.
  4. AUXILIARY (clearly labeled, NOT the frozen corpus): the same top-5 census
     against the recorded `ticker_forward_returns` sink in the primary DB
     (existing records; per-day cross-sectional z of recorded fwd_5d over the
     tickers recorded that day -- a per-day z of raw fwd_5d equals the z of
     same-day benchmark excess because the benchmark leg is a per-day constant).

All DB access is read-only (sqlite URI mode=ro). The script writes ONLY the CSV
outputs under --out-dir.

Canonical run selection: within one sink, monitor-loop runs score only holdings
(~6-7 non-null rank_score rows) while the daily full scoring run scores ~100-120
names. For each (lane, date) the canonical panel is the run with the MOST
non-null rank_score rows for that lane (ties: latest pipeline_runs.created_at,
then run_id). Panels below --min-panel scored names are excluded from
correlation/outcome measurement (they have no cross-section) but still count in
the inventory.

Usage:
  python3 scripts/g_d_shadow_information_census.py \
      --data-dir /Users/renhao/git/github/RenQuant/data \
      --qp-ledger /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/live-shadow/qp-live-shadow.jsonl \
      --out-dir doc/research/data --out-prefix 2026-08-10-shadow-census
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict

import pandas as pd

CORPUS_END = "2026-05-07"  # frozen corpus last label date
MIN_COMMON_TICKERS = 20    # per-day floor for a pairwise Spearman
MIN_Z_UNIVERSE = 30        # per-day floor for the auxiliary z cross-section

# (sink_tag, db_filename) -- every shadow DB sink + the primary served DB.
SHADOW_SINKS = [
    ("shared", "runs.alpaca_shadow.db"),
    ("blend", "runs.alpaca_shadow_blend.db"),
    ("blend_mom", "runs.alpaca_shadow_blend_mom.db"),
    ("blend_mom_fast", "runs.alpaca_shadow_blend_mom_fast.db"),
    ("blend_rb_fast", "runs.alpaca_shadow_blend_rb_fast.db"),
    ("blend_rb_mom", "runs.alpaca_shadow_blend_rb_mom.db"),
]
PRIMARY_DB = "runs.alpaca.db"
PRIMARY_LANE = "primary:served"


def ro_connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def load_sink(path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (all ticker_daily_state rows, pipeline_runs created_at map)."""
    con = ro_connect(path)
    try:
        tds = pd.read_sql_query(
            "SELECT run_id, date, ticker, active_scorer, rank_score, panel_score "
            "FROM ticker_daily_state", con)
        runs = pd.read_sql_query(
            "SELECT run_id, created_at FROM pipeline_runs", con)
    finally:
        con.close()
    return tds, runs


def lane_frames(tds: pd.DataFrame, sink_tag: str, split_by_scorer: bool) -> dict[str, pd.DataFrame]:
    """Split a sink's rows into lanes. Shadow sinks split by active_scorer
    (NULL => 'unattributed'); the primary is ONE lane (the served scorer of the
    day, whatever its stamp)."""
    if split_by_scorer:
        tds = tds.copy()
        tds["lane"] = sink_tag + ":" + tds["active_scorer"].fillna("unattributed")
        return {lane: g for lane, g in tds.groupby("lane")}
    return {PRIMARY_LANE: tds}


def canonical_panels(df: pd.DataFrame, created: pd.DataFrame) -> tuple[dict[str, pd.Series], pd.DataFrame]:
    """Per date: pick the run with the most non-null rank_score rows.
    Returns ({date: Series ticker->rank_score}, per-day meta DataFrame)."""
    scored = df[df["rank_score"].notna()]
    if scored.empty:
        return {}, pd.DataFrame(columns=["date", "run_id", "n_scored", "scorer"])
    cov = (scored.groupby(["date", "run_id"], as_index=False)
           .agg(n_scored=("rank_score", "size")))
    cov = cov.merge(created, on="run_id", how="left")
    cov["created_at"] = cov["created_at"].fillna("")
    cov = cov.sort_values(["date", "n_scored", "created_at", "run_id"],
                          ascending=[True, False, False, False])
    pick = cov.groupby("date", as_index=False).first()
    panels: dict[str, pd.Series] = {}
    metas = []
    for _, row in pick.iterrows():
        g = scored[(scored["date"] == row["date"]) & (scored["run_id"] == row["run_id"])]
        # one score per ticker (keep max if duplicated within a run)
        s = g.groupby("ticker")["rank_score"].max()
        panels[row["date"]] = s
        stamps = g["active_scorer"].dropna().unique()
        metas.append({
            "date": row["date"], "run_id": row["run_id"],
            "n_scored": int(row["n_scored"]),
            "scorer": stamps[0] if len(stamps) == 1 else
                      ("unattributed" if len(stamps) == 0 else "|".join(sorted(stamps))),
        })
    return panels, pd.DataFrame(metas)


def spearman(a: pd.Series, b: pd.Series) -> float:
    return a.rank().corr(b.rank())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", default="/Users/renhao/git/github/RenQuant/data")
    ap.add_argument("--corpus", default=None,
                    help="frozen corpus parquet; default <data-dir>/alpha158_291_fundamental_dataset.parquet")
    ap.add_argument("--qp-ledger", default="/Users/renhao/git/github/RenQuant/backtesting/"
                    "renquant_104/artifacts/live-shadow/qp-live-shadow.jsonl")
    ap.add_argument("--shadow-predictions", default=None,
                    help="one-shot snapshot json; default <data-dir>/shadow_predictions.json")
    ap.add_argument("--out-dir", default="doc/research/data")
    ap.add_argument("--out-prefix", default="shadow-census")
    ap.add_argument("--min-panel", type=int, default=MIN_COMMON_TICKERS,
                    help="min scored names for a lane-day panel to enter measurement")
    args = ap.parse_args()

    corpus_path = args.corpus or os.path.join(args.data_dir, "alpha158_291_fundamental_dataset.parquet")
    snap_path = args.shadow_predictions or os.path.join(args.data_dir, "shadow_predictions.json")
    os.makedirs(args.out_dir, exist_ok=True)

    def outp(name: str) -> str:
        return os.path.join(args.out_dir, f"{args.out_prefix}_{name}")

    # ------------------------------------------------------------------ lanes
    inventory_rows = []
    panels: dict[str, dict[str, pd.Series]] = {}      # lane -> date -> ticker scores
    panel_meta: dict[str, pd.DataFrame] = {}

    sink_specs = [(tag, os.path.join(args.data_dir, fn), True) for tag, fn in SHADOW_SINKS]
    sink_specs.append(("primary", os.path.join(args.data_dir, PRIMARY_DB), False))

    for sink_tag, path, split in sink_specs:
        if not os.path.exists(path):
            print(f"[skip] missing sink {path}", file=sys.stderr)
            continue
        tds, created = load_sink(path)
        for lane, g in sorted(lane_frames(tds, sink_tag, split).items()):
            p, meta = canonical_panels(g, created)
            big = {d: s for d, s in p.items() if len(s) >= args.min_panel}
            panels[lane] = big
            panel_meta[lane] = meta
            per_day_tickers = g.groupby("date")["ticker"].nunique()
            big_meta = meta[meta["n_scored"] >= args.min_panel]
            inventory_rows.append({
                "lane": lane,
                "sink": os.path.basename(path),
                "kind": "db:ticker_daily_state",
                "first_date": g["date"].min(),
                "last_date": g["date"].max(),
                "rows": len(g),
                "days": g["date"].nunique(),
                "median_tickers_per_day": float(per_day_tickers.median()),
                "panel_days_ge_min": len(big),
                "median_scored_panel": (float(big_meta["n_scored"].median())
                                        if len(big_meta) else 0.0),
                "days_before_corpus_end": int((per_day_tickers.index <= CORPUS_END).sum()),
                "note": "",
            })

    # file ledgers + configured-but-empty sinks --------------------------------
    if os.path.exists(args.qp_ledger):
        recs = [json.loads(line) for line in open(args.qp_ledger)]
        dates = sorted({r.get("as_of_date") for r in recs})
        nt = sorted({t for r in recs for t in (r.get("candidate", {}).get("target_w") or {})})
        inventory_rows.append({
            "lane": "file:qp_live_shadow", "sink": os.path.basename(args.qp_ledger),
            "kind": "file:jsonl", "first_date": dates[0], "last_date": dates[-1],
            "rows": len(recs), "days": len(dates),
            "median_tickers_per_day": float(len(nt)), "panel_days_ge_min": 0,
            "median_scored_panel": 0.0,
            "days_before_corpus_end": sum(d <= CORPUS_END for d in dates),
            "note": "allocator shadow (incumbent-vs-candidate QP weights on held names only); "
                    "no cross-sectional scores -- not rank-comparable",
        })

    snap = None
    if os.path.exists(snap_path):
        snap = json.load(open(snap_path))
        inventory_rows.append({
            "lane": "file:shadow_predictions_snapshot", "sink": os.path.basename(snap_path),
            "kind": "file:json", "first_date": snap.get("scoring_date"),
            "last_date": snap.get("scoring_date"), "rows": len(snap.get("top30_long", [])),
            "days": 1, "median_tickers_per_day": float(len(snap.get("top30_long", []))),
            "panel_days_ge_min": 0, "median_scored_panel": 0.0,
            "days_before_corpus_end": int(str(snap.get("scoring_date")) <= CORPUS_END),
            "note": f"one-shot top-30 snapshot of artifact {snap.get('artifact')}; "
                    "the only shadow-surface record predating the corpus end",
        })

    sa_dir = os.path.join(args.data_dir, "shadow_analyst")
    if os.path.isdir(sa_dir):
        files = sorted(f for f in os.listdir(sa_dir) if f.endswith(".json"))
        inventory_rows.append({
            "lane": "file:shadow_analyst_artifacts", "sink": "shadow_analyst/",
            "kind": "file:model-artifacts", "first_date": "", "last_date": "",
            "rows": len(files), "days": 0, "median_tickers_per_day": 0.0,
            "panel_days_ge_min": 0, "median_scored_panel": 0.0,
            "days_before_corpus_end": 0,
            "note": "trained model artifacts (boosters + fold-IC metadata), no daily score records",
        })

    # challenger_decisions: configured sink, check emptiness everywhere
    chall_total = 0
    for _tag, path, _s in sink_specs:
        if not os.path.exists(path):
            continue
        con = ro_connect(path)
        try:
            n = con.execute("SELECT COUNT(*) FROM challenger_decisions").fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        finally:
            con.close()
        chall_total += n
    inventory_rows.append({
        "lane": "db:challenger_decisions", "sink": "all runs.*.db",
        "kind": "db:challenger_decisions", "first_date": "", "last_date": "",
        "rows": chall_total, "days": 0, "median_tickers_per_day": 0.0,
        "panel_days_ge_min": 0, "median_scored_panel": 0.0, "days_before_corpus_end": 0,
        "note": "configured challenger sink; ZERO records in every DB" if chall_total == 0
                else "challenger sink rows found",
    })

    inv = pd.DataFrame(inventory_rows)
    inv.to_csv(outp("inventory.csv"), index=False)

    # primary per-day scorer identity (for the note)
    if PRIMARY_LANE in panel_meta:
        panel_meta[PRIMARY_LANE].to_csv(outp("primary_daily_scorer.csv"), index=False)

    # -------------------------------------------------------- pairwise Spearman
    lanes_measurable = sorted(l for l, p in panels.items() if len(p) > 0)
    pair_rows = []
    for i, la in enumerate(lanes_measurable):
        for lb in lanes_measurable[i + 1:]:
            days = sorted(set(panels[la]) & set(panels[lb]))
            rhos, commons = [], []
            for d in days:
                sa, sb = panels[la][d], panels[lb][d]
                common = sa.index.intersection(sb.index)
                if len(common) < MIN_COMMON_TICKERS:
                    continue
                rho = spearman(sa.loc[common], sb.loc[common])
                if pd.notna(rho):
                    rhos.append(rho)
                    commons.append(len(common))
            if rhos:
                rs = pd.Series(rhos)
                pair_rows.append({
                    "lane_a": la, "lane_b": lb, "n_days": len(rs),
                    "median_spearman": float(rs.median()),
                    "min_spearman": float(rs.min()), "max_spearman": float(rs.max()),
                    "median_common_tickers": float(pd.Series(commons).median()),
                })
    pw = pd.DataFrame(pair_rows).sort_values(["lane_a", "lane_b"])
    pw.to_csv(outp("pairwise_spearman.csv"), index=False)

    # square matrix of medians (blank = no overlapping measurable days)
    mat = pd.DataFrame(index=lanes_measurable, columns=lanes_measurable, dtype=float)
    for _, r in pw.iterrows():
        mat.loc[r["lane_a"], r["lane_b"]] = r["median_spearman"]
        mat.loc[r["lane_b"], r["lane_a"]] = r["median_spearman"]
    for l in lanes_measurable:
        mat.loc[l, l] = 1.0
    mat.round(4).to_csv(outp("median_spearman_matrix.csv"))

    # bit-identity census: for near-perfect pairs, is the score VECTOR identical?
    # (a 2-component and a 3-component blend emitting bit-identical composites
    #  means the extra component contributed exactly nothing that day)
    dup_rows = []
    near = pw[pw["median_spearman"].abs() > 0.99]
    for _, r in near.iterrows():
        la, lb = r["lane_a"], r["lane_b"]
        for d in sorted(set(panels[la]) & set(panels[lb])):
            sa, sb = panels[la][d], panels[lb][d]
            common = sa.index.intersection(sb.index)
            if len(common) < MIN_COMMON_TICKERS:
                continue
            mad = float((sa.loc[common] - sb.loc[common]).abs().max())
            dup_rows.append({"lane_a": la, "lane_b": lb, "date": d,
                             "n_common": len(common), "max_abs_diff": mad,
                             "bit_identical": mad == 0.0})
    pd.DataFrame(dup_rows).to_csv(outp("bit_identity.csv"), index=False)

    # redundancy census (task rule: median |rho| > 0.95 vs primary or any lane)
    red_rows = []
    for lane in lanes_measurable:
        if lane == PRIMARY_LANE:
            continue
        sub = pw[((pw["lane_a"] == lane) | (pw["lane_b"] == lane))]
        vs_primary = sub[(sub["lane_a"] == PRIMARY_LANE) | (sub["lane_b"] == PRIMARY_LANE)]
        rho_p = float(vs_primary["median_spearman"].iloc[0]) if len(vs_primary) else float("nan")
        n_p = int(vs_primary["n_days"].iloc[0]) if len(vs_primary) else 0
        others = sub[(sub["lane_a"] != PRIMARY_LANE) & (sub["lane_b"] != PRIMARY_LANE)]
        if len(others):
            k = others["median_spearman"].abs().idxmax()
            partner = others.loc[k, "lane_b"] if others.loc[k, "lane_a"] == lane else others.loc[k, "lane_a"]
            rho_o, n_o = float(others.loc[k, "median_spearman"]), int(others.loc[k, "n_days"])
        else:
            partner, rho_o, n_o = "", float("nan"), 0
        redundant = (pd.notna(rho_p) and abs(rho_p) > 0.95) or (pd.notna(rho_o) and abs(rho_o) > 0.95)
        red_rows.append({
            "lane": lane, "rho_vs_primary": rho_p, "n_days_vs_primary": n_p,
            "max_abs_rho_other_lane": rho_o, "closest_other_lane": partner,
            "n_days_vs_other": n_o, "redundant_gt_0.95": bool(redundant),
        })
    red = pd.DataFrame(red_rows)
    red.to_csv(outp("redundancy.csv"), index=False)

    # ------------------------------------------- outcome census: frozen corpus
    corpus = pd.read_parquet(corpus_path, columns=["ticker", "date", "fwd_5d_excess"])
    corpus["date"] = pd.to_datetime(corpus["date"]).dt.strftime("%Y-%m-%d")
    corpus = corpus[corpus["fwd_5d_excess"].notna()]
    g = corpus.groupby("date")["fwd_5d_excess"]
    corpus["label_z"] = (corpus["fwd_5d_excess"] - g.transform("mean")) / g.transform("std")
    corpus_z = corpus.set_index(["date", "ticker"])["label_z"]

    corpus_rows = []
    for lane in lanes_measurable:
        days = [d for d in panels[lane] if d <= CORPUS_END]
        zs = []
        for d in days:
            top5 = panels[lane][d].sort_values(ascending=False).head(5)
            vals = [corpus_z.get((d, t)) for t in top5.index]
            vals = [v for v in vals if v is not None and pd.notna(v)]
            if vals:
                zs.append(sum(vals) / len(vals))
        corpus_rows.append({
            "lane": lane, "lane_days_in_corpus_window": len(days),
            "days_scored": len(zs),
            "mean_top5_label_z": float(pd.Series(zs).mean()) if zs else float("nan"),
        })
    # the one-shot snapshot is the only surface with a pre-corpus-end record
    if snap and str(snap.get("scoring_date", "9999")) <= CORPUS_END:
        d = str(snap["scoring_date"])
        preds = pd.DataFrame(snap.get("top30_long", []))
        if len(preds):
            preds = preds.sort_values("pred", ascending=False)
            for label, k in (("top5", 5), ("top30", 30)):
                vals = [corpus_z.get((d, t)) for t in preds["ticker"].head(k)]
                vals = [v for v in vals if v is not None and pd.notna(v)]
                corpus_rows.append({
                    "lane": f"file:shadow_predictions_snapshot:{label}",
                    "lane_days_in_corpus_window": 1, "days_scored": 1 if vals else 0,
                    "mean_top5_label_z": float(pd.Series(vals).mean()) if vals else float("nan"),
                })
    pd.DataFrame(corpus_rows).to_csv(outp("corpus_outcome_census.csv"), index=False)

    # -------------------- AUXILIARY outcome census: recorded forward returns
    con = ro_connect(os.path.join(args.data_dir, PRIMARY_DB))
    try:
        tfr = pd.read_sql_query(
            "SELECT as_of_date AS date, ticker, fwd_5d FROM ticker_forward_returns "
            "WHERE fwd_5d IS NOT NULL", con)
    finally:
        con.close()
    day_n = tfr.groupby("date")["ticker"].transform("size")
    tfr = tfr[day_n >= MIN_Z_UNIVERSE].copy()
    gg = tfr.groupby("date")["fwd_5d"]
    tfr["z"] = (tfr["fwd_5d"] - gg.transform("mean")) / gg.transform("std")
    tfr_z = tfr.set_index(["date", "ticker"])["z"]
    tfr_days = set(tfr["date"].unique())

    aux_rows = []
    for lane in lanes_measurable:
        per_day = []
        for d, s in panels[lane].items():
            if d not in tfr_days:
                continue
            top5 = s.sort_values(ascending=False).head(5)
            vals = [tfr_z.get((d, t)) for t in top5.index]
            vals = [v for v in vals if v is not None and pd.notna(v)]
            if vals:
                per_day.append({"date": d, "mean_top5_z": sum(vals) / len(vals),
                                "coverage": len(vals)})
        if per_day:
            dd = pd.DataFrame(per_day)
            aux_rows.append({
                "lane": lane, "n_days": len(dd),
                "mean_daily_top5_z": float(dd["mean_top5_z"].mean()),
                "median_daily_top5_z": float(dd["mean_top5_z"].median()),
                "share_days_positive": float((dd["mean_top5_z"] > 0).mean()),
                "mean_top5_coverage_of_5": float(dd["coverage"].mean()),
            })
        else:
            aux_rows.append({"lane": lane, "n_days": 0,
                             "mean_daily_top5_z": float("nan"),
                             "median_daily_top5_z": float("nan"),
                             "share_days_positive": float("nan"),
                             "mean_top5_coverage_of_5": float("nan")})
    pd.DataFrame(aux_rows).to_csv(outp("aux_recorded_fwd5d_top5_census.csv"), index=False)

    # ------------------------------------------------------------- console sum
    print("== inventory ==")
    print(inv.to_string(index=False))
    print("\n== redundancy ==")
    print(red.to_string(index=False))
    print("\n== corpus outcome census (frozen labels, end %s) ==" % CORPUS_END)
    print(pd.DataFrame(corpus_rows).to_string(index=False))
    print("\n== AUX recorded-fwd5d top-5 census (NOT the frozen corpus) ==")
    print(pd.DataFrame(aux_rows).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
