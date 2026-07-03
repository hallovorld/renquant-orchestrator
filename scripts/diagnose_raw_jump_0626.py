#!/usr/bin/env python3
"""Diagnose the 2026-06-26 raw-score cross-section jump (S-REL follow-up to V5).

V5 (doc/research/2026-07-03-v5-m4-verification.md) found the live panel
scorer's raw-score cross-sectional median jumped +0.25 between the 2026-06-25
and 2026-06-26 daily runs and flagged root-cause as out of scope. This tool
attributes the jump from prod-persisted evidence only.

READ-ONLY against production inputs (DB opened mode=ro; artifact/parquet files
only read and hashed). No pipeline imports: the panel feature-transform
contract (renquant-pipeline kernel/panel_pipeline/feature_transform.py,
source_space="panel") is re-implemented here in pure numpy/pandas, and the
XGBoost boosters are loaded directly from the artifacts' booster_raw_json.

Sections:
  1. per-run raw_panel cross-sectional stats + boundary detection
  2. run-bundle attribution timeline (panel/calibrator/config/watchlist hashes)
  3. artifact-family map: booster-content hash across prod/staging/rollback copies
  4. same-model day-over-day controls vs the boundary (per-ticker deltas)
  5. two-model same-rows decomposition: score identical feature rows under the
     model live on 06-25 (trained 2026-06-21) and the model live on 06-26
     (trained 2026-05-18)
  6. booster gain share by feature family (technical vs fundamental/event)
  7. score_drift_audits (PSI) monitoring-state stats

Usage:
  /Users/renhao/git/github/RenQuant/.venv/bin/python \
      scripts/diagnose_raw_jump_0626.py \
      --json-out doc/research/evidence/2026-07-03-raw-jump-0626/diagnosis.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DB_PATH = "/Users/renhao/git/github/RenQuant/data/runs.alpaca.db"
PROD_DIR = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/prod"
# Exact bytes of the model prod ran 2026-06-23..25 (run bundles hash 04d7a381...):
ARTIFACT_A = f"{PROD_DIR}/panel-ltr.alpha158_fund.weekly_rollback_2026-06-23.json"
# The model prod ran 2026-06-26..07-02 (run bundles hash 5ce63326..., current prod file):
ARTIFACT_B = f"{PROD_DIR}/panel-ltr.alpha158_fund.json"
PANEL_PARQUET = "/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset.parquet"

RUN_A_LAST = "2026-06-25-live-6c3aa3fa"   # last run before the jump
RUN_B_FIRST = "2026-06-26-live-3d74ce5c"  # first run after the jump

ARTIFACT_COPIES = [
    "panel-ltr.alpha158_fund.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-15.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-17.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-18.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-20.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-21.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-22.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-23.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-27.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-28.json",
    "panel-ltr.alpha158_fund.weekly_rollback_2026-06-30.json",
    "panel-ltr.alpha158_fund.weekly_20260621T170005Z.staging.json",
]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_meta(path: str) -> dict:
    p = Path(path)
    st = p.stat()
    return {
        "path": str(p),
        "sha256": sha256_file(path),
        "size_bytes": st.st_size,
        "mtime_utc": dt.datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
    }


def connect_ro(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


# ── Section 1: per-run raw stats ──────────────────────────────────────────

def per_run_raw_stats(con: sqlite3.Connection) -> list[dict]:
    runs = [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT run_id FROM score_distribution "
            "WHERE date BETWEEN '2026-06-08' AND '2026-07-02' ORDER BY run_id"
        )
    ]
    out = []
    for rid in runs:
        vals = [
            r[0]
            for r in con.execute(
                "SELECT raw_panel FROM score_distribution "
                "WHERE run_id=? AND is_holding=0 AND raw_panel IS NOT NULL",
                (rid,),
            )
        ]
        if len(vals) < 30:  # thin/aborted runs carry no cross-sectional signal
            continue
        out.append(
            {
                "run_id": rid,
                "n_candidates": len(vals),
                "median_raw": statistics.median(vals),
                "mean_raw": statistics.fmean(vals),
                "std_raw": statistics.stdev(vals),
            }
        )
    for prev, cur in zip(out, out[1:]):
        cur["delta_median_vs_prev_run"] = cur["median_raw"] - prev["median_raw"]
    return out


# ── Section 2: bundle attribution timeline ────────────────────────────────

def bundle_timeline(con: sqlite3.Connection, run_ids: list[str]) -> list[dict]:
    out = []
    for rid in run_ids:
        row = con.execute(
            "SELECT run_bundle_json, commit_sha FROM pipeline_runs WHERE run_id=?",
            (rid,),
        ).fetchone()
        if not row or not row[0]:
            continue
        b = json.loads(row[0])
        ah = b.get("artifact_hashes", {})
        pc = b.get("panel_contract", {}).get("details", {})
        out.append(
            {
                "run_id": rid,
                "panel_sha256": ah.get("panel"),
                "panel_trained_date": pc.get("trained_date"),
                "panel_oos_mean_ic": pc.get("oos_mean_ic"),
                "calibrator_sha256": ah.get("global_calibration"),
                "config_hash": b.get("config_hash"),
                "watchlist_hash": b.get("watchlist_hash"),
                "watchlist_size": b.get("watchlist_size"),
                "commit_sha": row[1],
                "data_max_date": max((b.get("data_max_dates") or {"": None}).values()),
            }
        )
    return out


# ── Section 3: artifact family map ────────────────────────────────────────

def artifact_families() -> list[dict]:
    out = []
    for name in ARTIFACT_COPIES:
        path = Path(PROD_DIR) / name
        if not path.exists():
            continue
        d = json.loads(path.read_text())
        booster12 = hashlib.sha256(
            json.dumps(d["booster_raw_json"], sort_keys=True).encode()
        ).hexdigest()[:12]
        out.append(
            {
                "file": name,
                "file_sha256_8": sha256_file(str(path))[:8],
                "trained_date": d.get("trained_date"),
                "oos_mean_ic": d.get("oos_mean_ic"),
                "booster_sha256_12": booster12,
                "n_features": len(d.get("feature_cols", [])),
                "objective": (d.get("params") or {}).get("objective"),
            }
        )
    return out


# ── Section 4: per-ticker run-pair deltas ─────────────────────────────────

def run_pair_delta(con: sqlite3.Connection, run_a: str, run_b: str) -> dict:
    a = dict(
        con.execute(
            "SELECT ticker, raw_panel FROM score_distribution "
            "WHERE run_id=? AND raw_panel IS NOT NULL",
            (run_a,),
        )
    )
    b = dict(
        con.execute(
            "SELECT ticker, raw_panel FROM score_distribution "
            "WHERE run_id=? AND raw_panel IS NOT NULL",
            (run_b,),
        )
    )
    common = sorted(set(a) & set(b))
    d = np.array([b[t] - a[t] for t in common])
    sa = pd.Series({t: a[t] for t in common})
    sb = pd.Series({t: b[t] for t in common})
    return {
        "run_a": run_a,
        "run_b": run_b,
        "n_common_tickers": len(common),
        "delta_mean": float(d.mean()),
        "delta_median": float(np.median(d)),
        "delta_std": float(d.std(ddof=1)),
        "delta_min": float(d.min()),
        "delta_max": float(d.max()),
        "n_negative_delta": int((d < 0).sum()),
        "spearman_a_vs_b": float(sa.corr(sb, method="spearman")),
    }


# ── Section 5: two-model same-rows decomposition ──────────────────────────

def _transform_panel_space(
    frame: pd.DataFrame, feature_cols: list[str], artifact: dict, clip: float = 5.0
) -> pd.DataFrame:
    """Re-implementation of renquant-pipeline transform_feature_frame with
    source_space="panel": normalize only columns whose feature_norm_kind is
    robust_z / panel_raw_z (prebuilt panel alpha columns are already
    train-normalized); legacy artifacts without kinds get no normalization.
    Then clip to +/-5. Verified against feature_transform.py (read-only)."""
    X = frame.reindex(columns=feature_cols, fill_value=float("nan")).fillna(0.0)
    n = len(feature_cols)
    means = artifact.get("feature_means")
    stds = artifact.get("feature_stds")
    kinds = artifact.get("feature_norm_kind") or artifact.get("feature_norm_kinds")
    values = X.values.astype(float)
    if means is not None and stds is not None and len(means) == n and len(stds) == n:
        kinds = list(kinds) if isinstance(kinds, list) and len(kinds) == n else ["legacy_full_z"] * n
        mask = np.asarray([k in {"robust_z", "panel_raw_z"} for k in kinds], dtype=bool)
        if mask.any():
            mu = np.asarray(means, dtype=float)
            sd = np.asarray(stds, dtype=float)
            sd = np.where(np.isfinite(sd) & (np.abs(sd) > 1e-12), sd, 1.0)
            values[:, mask] = (values[:, mask] - mu[mask]) / sd[mask]
    values = np.clip(values, -clip, clip)
    return pd.DataFrame(values, index=X.index, columns=feature_cols)


def _load_booster(artifact: dict):
    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(bytearray(artifact["booster_raw_json"].encode("utf-8")))
    return booster


def two_model_same_rows(
    art_a: dict, art_b: dict, watchlist: set[str], n_dates: int = 15
) -> dict:
    feature_cols = list(art_a["feature_cols"])
    assert feature_cols == list(art_b["feature_cols"]), "feature contracts differ"
    df = pd.read_parquet(PANEL_PARQUET)
    missing = [c for c in feature_cols if c not in df.columns]
    df = df.sort_values("date")
    dates = sorted(df["date"].unique())[-n_dates:]
    df = df[df["date"].isin(dates)]

    booster_a = _load_booster(art_a)
    booster_b = _load_booster(art_b)
    import xgboost as xgb

    def score(art, booster, rows):
        X = _transform_panel_space(rows, feature_cols, art)
        return booster.predict(xgb.DMatrix(X.values))

    per_date = []
    deltas_all = []
    spearmans = []
    for d in dates:
        rows = df[df["date"] == d]
        sa = score(art_a, booster_a, rows)
        sb = score(art_b, booster_b, rows)
        wmask = rows["ticker"].isin(watchlist).values
        per_date.append(
            {
                "date": str(pd.Timestamp(d).date()),
                "n_rows": int(len(rows)),
                "median_A_0621": float(np.median(sa)),
                "median_B_0518": float(np.median(sb)),
                "median_shift_A_minus_B": float(np.median(sa) - np.median(sb)),
                "n_watchlist_rows": int(wmask.sum()),
                "median_A_watchlist": float(np.median(sa[wmask])) if wmask.any() else None,
                "median_B_watchlist": float(np.median(sb[wmask])) if wmask.any() else None,
                "spearman_A_vs_B": float(pd.Series(sa).corr(pd.Series(sb), method="spearman")),
            }
        )
        deltas_all.extend((sa - sb).tolist())
        spearmans.append(per_date[-1]["spearman_A_vs_B"])
    deltas_all = np.array(deltas_all)
    return {
        "note": (
            "Both boosters scored on IDENTICAL feature rows (prebuilt training "
            "panel, last dates before its fwd-60d label clip). The panel path "
            "differs from the live raw-feature path, so absolute levels are "
            "indicative; the A-minus-B offset on identical rows is the "
            "load-bearing number."
        ),
        "parquet_missing_feature_cols": missing,
        "per_date": per_date,
        "per_row_delta_A_minus_B_mean": float(deltas_all.mean()),
        "per_row_delta_A_minus_B_std": float(deltas_all.std(ddof=1)),
        "mean_spearman_A_vs_B": float(np.mean(spearmans)),
    }


# ── Section 6: booster gain by feature family ─────────────────────────────

def gain_by_family(art: dict) -> dict:
    booster = _load_booster(art)
    feature_cols = list(art["feature_cols"])
    gains = booster.get_score(importance_type="gain")
    weights = booster.get_score(importance_type="weight")
    fam_gain: dict[str, float] = {}
    fam_n: dict[str, int] = {}
    for fname, g in gains.items():
        idx = int(fname[1:])
        col = feature_cols[idx]
        fam = "technical_alpha158" if col.isupper() else "fundamental_event_sentiment"
        total = g * weights.get(fname, 0.0)  # total gain = mean gain x split count
        fam_gain[fam] = fam_gain.get(fam, 0.0) + total
        fam_n[fam] = fam_n.get(fam, 0) + 1
    total = sum(fam_gain.values()) or 1.0
    return {
        "trained_date": art.get("trained_date"),
        "families": {
            fam: {
                "n_features_used": fam_n[fam],
                "total_gain_share": fam_gain[fam] / total,
            }
            for fam in sorted(fam_gain)
        },
    }


# ── Section 7: drift-audit monitoring stats ───────────────────────────────

def drift_audit_stats(con: sqlite3.Connection) -> dict:
    sev = [
        {"severity": r[0], "n": r[1], "first": r[2], "last": r[3]}
        for r in con.execute(
            "SELECT severity, COUNT(*), MIN(run_date), MAX(run_date) "
            "FROM score_drift_audits GROUP BY severity"
        )
    ]
    psi = [
        {"run_date": r[0], "psi_min": r[1], "psi_max": r[2], "n_baseline": r[3]}
        for r in con.execute(
            "SELECT run_date, MIN(psi), MAX(psi), MAX(n_baseline) "
            "FROM score_drift_audits WHERE run_date BETWEEN '2026-06-22' AND '2026-07-02' "
            "GROUP BY run_date ORDER BY run_date"
        )
    ]
    return {"severity_history": sev, "psi_by_date": psi}


# ── main ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json-out", default=None, help="write evidence JSON here")
    ap.add_argument("--n-dates", type=int, default=15)
    args = ap.parse_args()

    con = connect_ro(DB_PATH)
    art_a = json.loads(Path(ARTIFACT_A).read_text())
    art_b = json.loads(Path(ARTIFACT_B).read_text())

    stats = per_run_raw_stats(con)
    boundary = max(
        (r for r in stats if "delta_median_vs_prev_run" in r),
        key=lambda r: abs(r["delta_median_vs_prev_run"]),
    )
    timeline = bundle_timeline(con, [r["run_id"] for r in stats])
    families = artifact_families()
    watchlist = {
        r[0]
        for r in con.execute(
            "SELECT ticker FROM score_distribution WHERE run_id=?", (RUN_B_FIRST,)
        )
    }
    controls = [
        run_pair_delta(con, "2026-06-24-live-710e3805", RUN_A_LAST),   # A->A control
        run_pair_delta(con, RUN_A_LAST, RUN_B_FIRST),                  # the boundary
        # B->B pair isolating the 2026-06-29 fund-feed rebuild (#26 deploy,
        # serving axis 2026-03-31 -> 2026-06-26) + a weekend of price drift:
        run_pair_delta(con, RUN_B_FIRST, "2026-06-29-live-5970796e"),
        run_pair_delta(con, RUN_B_FIRST, "2026-06-30-live-b616357c"),  # B->B, also spans the rebuild
        run_pair_delta(con, "2026-06-30-live-b616357c", "2026-07-01-live-01c54b39"),  # B->B control
    ]
    decomp = two_model_same_rows(art_a, art_b, watchlist, n_dates=args.n_dates)
    gains = {"A_0621": gain_by_family(art_a), "B_0518": gain_by_family(art_b)}
    monitoring = drift_audit_stats(con)

    evidence = {
        "generated_at_utc": dt.datetime.utcnow().isoformat() + "Z",
        "script_sha256": sha256_file(__file__),
        "inputs": {
            "runs_db": file_meta(DB_PATH),
            "artifact_A_trained_0621_live_0622_0625": file_meta(ARTIFACT_A),
            "artifact_B_trained_0518_live_0626_plus": file_meta(ARTIFACT_B),
            "panel_parquet": file_meta(PANEL_PARQUET),
        },
        "per_run_raw_stats": stats,
        "boundary_run": boundary,
        "bundle_timeline": timeline,
        "artifact_family_map": families,
        "run_pair_deltas": controls,
        "two_model_same_rows_decomposition": decomp,
        "booster_gain_by_family": gains,
        "monitoring_drift_audits": monitoring,
    }

    print("== boundary ==")
    print(json.dumps(boundary, indent=2))
    print("== run pair deltas ==")
    for c in controls:
        print(
            f"{c['run_a']} -> {c['run_b']}: mean {c['delta_mean']:+.4f} "
            f"std {c['delta_std']:.4f} spearman {c['spearman_a_vs_b']:.3f}"
        )
    print("== two-model same-rows ==")
    print(
        f"A(0621) - B(0518) on identical rows: mean {decomp['per_row_delta_A_minus_B_mean']:+.4f} "
        f"std {decomp['per_row_delta_A_minus_B_std']:.4f} "
        f"mean spearman {decomp['mean_spearman_A_vs_B']:.3f}"
    )
    for d in decomp["per_date"][-5:]:
        print(
            f"  {d['date']}: median A {d['median_A_0621']:+.4f}  "
            f"B {d['median_B_0518']:+.4f}  shift {d['median_shift_A_minus_B']:+.4f}  "
            f"(watchlist A {d['median_A_watchlist']:+.4f} B {d['median_B_watchlist']:+.4f})"
        )
    print("== gain by family ==")
    print(json.dumps(gains, indent=2))
    print("== monitoring ==")
    print(json.dumps(monitoring["severity_history"], indent=2))

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2) + "\n")
        print(f"evidence written: {out}")


if __name__ == "__main__":
    main()
