#!/usr/bin/env python
"""Regime detector assessment — replication checks + manifest (part 3 of 3).

Read-only derivation script for doc/research/2026-08-17-regime-detector-assessment.md.
Run parts 1 and 2 first (this reads their CSV/JSON outputs). Deterministic:
the only RNG (the Hurst white-noise null) uses the fixed seeds below.

Phase-A-dependent pieces are GUARDED (exploratory E1 only, not part of the
reproducible core): on a checkout without the local corpus
(experiments/phase_a_data), the P6 bear_ic_split is computed from part 2's
committed output when available and skipped otherwise, and the manifest
records the corpus identity PIN (sha256 recorded at the 2026-08-17 full run)
instead of hashing absent files — so the reproducible core runs end-to-end
on a clean checkout. All paths emitted into the JSON outputs are normalized
to stable `<repo>:<relpath>` ids (the outputs are committed; machine-local
absolute paths must not leak into them).

Checks (each is a memo claim keyed by the memo's pathology numbers):
  hurst_null          P1 — kernel compute_hurst on 63-day iid N(0,1) draws;
                      share of draws with H>0.65 (two independent seeds)
  hysteresis          item 4 — symmetric confirm-2 smoothing of the serving
                      series: a switch commits only on the 2nd consecutive day
                      of the same new label (so every regime entry, BEAR
                      included, is +1 td late vs raw)
  prereg_plane        P3 — BEAR days/episodes from argmax over the committed
                      2026-08-08-regime-posteriors.csv (the BEAR-exit prereg's
                      data plane)
  snapshot_agreement  replica-validity — replica per-day GMM dominant label
                      occupancy vs the committed 08-08 posterior snapshot
  wf_replay_counts    replica-validity — replica serving-label counts over the
                      WF sanity window vs the served artifact's per-regime
                      n_dates (exact match expected)
  recovery_days       P5 — serving BEAR-labeled days from the mechanical -15%
                      trough (inclusive) through window exit, summed over the
                      5 real bears (memo's 93); strictly-after count also given
  bear_ic_split       P6 — phase-A BEAR-day IC split by serving-episode
                      validation: days whose BEAR episode intersects a -10%
                      drawdown window vs days inside a false-alarm episode
  gmm_artifact        as-built — prod GMM artifact as_of/cluster set
  vixcls_staleness    item 7 — FRED VIXCLS last ingested row vs memo date

Output:
  2026-08-17-regime-detector-replication.json
  2026-08-17-regime-detector-manifest.json  (sources+sha256, date bounds,
                                             detector params, seeds, commands)
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
PREFIX = "2026-08-17-regime-detector"
END_DATE = pd.Timestamp("2026-08-14")
MEMO_DATE = pd.Timestamp("2026-08-17")

RQ = Path(os.environ.get("RQ_UMBRELLA", str(Path.home() / "git/github/RenQuant")))
COMMON = Path(os.environ.get("RQ_COMMON_SRC",
                             str(Path.home() / "git/github/renquant-common/src")))
R104 = RQ / "backtesting" / "renquant_104"
PA = Path(os.environ.get("PHASE_A_DIR", str(REPO / "experiments" / "phase_a_data")))
sys.path.insert(0, str(R104))


def rel(p: Path) -> str:
    """Stable `<repo>:<relpath>` id for a machine-local path. The JSON outputs
    are committed, so absolute paths must not leak into them."""
    for root, name in ((REPO, "renquant-orchestrator"), (RQ, "RenQuant"),
                       (COMMON.parent, "renquant-common")):
        try:
            return f"{name}:{Path(p).relative_to(root)}"
        except ValueError:
            continue
    return str(p)


# Identity pins for the LOCAL, uncommitted phase-A corpus (exploratory E1 only —
# not part of the reproducible core). Recorded at the 2026-08-17 corpus-present
# full run; when the corpus is present the live hashes are checked against them.
PA_FR_SHA256_PIN = \
    "96094d29481543c748d58aa9709654de0e6bd134bb1f01ddac33cc5d1bd9c972"
PA_XGB_N_FILES_PIN = 230
PA_XGB_AGG_SHA256_PIN = \
    "d37f9633d74b186eaa700deb53394485a0fc427db90c96e8d5599777b0272bbf"
PIN_RECORDED = "2026-08-17 full run (corpus present)"

from kernel.regime import compute_hurst  # noqa: E402

HURST_NULL_RUNS = [
    {"seed": 42, "n_draws": 500},        # primary
    {"seed": 20260817, "n_draws": 300},  # independent re-derivation
]
HURST_WINDOW = 63
HURST_TRENDING_THR = 0.65
HURST_REVERSION_THR = 0.52

lbl = pd.read_csv(OUT / f"{PREFIX}-label-series.csv", index_col=0, parse_dates=[0])
post = pd.read_csv(OUT / f"{PREFIX}-posterior-series.csv", index_col=0, parse_dates=[0])
meas = json.load(open(OUT / f"{PREFIX}-measurements.json"))
pic = json.load(open(OUT / f"{PREFIX}-posteriors-ic.json"))

# ── P1: Hurst white-noise null ───────────────────────────────────────────────
hurst_null = []
for run in HURST_NULL_RUNS:
    rng = np.random.default_rng(run["seed"])
    hs = np.array([compute_hurst(rng.standard_normal(HURST_WINDOW),
                                 window=HURST_WINDOW)
                   for _ in range(run["n_draws"])])
    hurst_null.append({
        "seed": run["seed"], "n_draws": run["n_draws"],
        "window": HURST_WINDOW,
        "share_H_gt_0.65": round(float((hs > HURST_TRENDING_THR).mean()), 3),
        "share_H_lt_0.52": round(float((hs < HURST_REVERSION_THR).mean()), 3),
        "mean_H": round(float(hs.mean()), 3),
    })

# ── item 4: symmetric confirm-2 hysteresis on the serving series ─────────────
def episodes(s):
    eps = []
    cur, n = None, 0
    for r in s:
        if r != cur:
            if cur is not None:
                eps.append((cur, n))
            cur, n = r, 1
        else:
            n += 1
    eps.append((cur, n))
    return eps


def confirm2(raw: pd.Series) -> pd.Series:
    """Committed label switches to X only on the 2nd consecutive raw day of X."""
    out = []
    committed = raw.iloc[0]
    pend, pc = None, 0
    for r in raw:
        if r == committed:
            pend, pc = None, 0
        else:
            pc = pc + 1 if pend == r else 1
            pend = r
            if pc >= 2:
                committed, pend, pc = r, None, 0
        out.append(committed)
    return pd.Series(out, index=raw.index)


raw = lbl["S"]
smooth = confirm2(raw)
eps_raw, eps_sm = episodes(raw), episodes(smooth)
fl_raw = sum(1 for _, n in eps_raw if n <= 2)
fl_sm = sum(1 for _, n in eps_sm if n <= 2)
hysteresis = {
    "rule": "symmetric confirm-2: every switch (BEAR included) commits on the "
            "2nd consecutive day of the new raw label (+1 td entry cost)",
    "episodes_raw": len(eps_raw), "episodes_confirm2": len(eps_sm),
    "flicker_le2d_raw": fl_raw, "flicker_le2d_confirm2": fl_sm,
    "flicker_reduction_pct": round(100 * (1 - fl_sm / fl_raw), 1),
    "bear_days_raw": int((raw == "BEAR").sum()),
    "bear_days_confirm2": int((smooth == "BEAR").sum()),
}

# ── P3: prereg data plane from the committed 08-08 posterior snapshot ────────
SNAP = REPO / "doc" / "research" / "data" / "2026-08-08-regime-posteriors.csv"
csv = pd.read_csv(SNAP, parse_dates=["date"]).set_index("date")
cols = {"regime_p_bull_calm": "BULL_CALM", "regime_p_bear": "BEAR",
        "regime_p_bull_volatile": "BULL_VOLATILE", "regime_p_choppy": "CHOPPY"}
am = csv.rename(columns=cols).idxmax(axis=1)
b = (am == "BEAR")
n_eps = int(((b) & (~b.shift(1, fill_value=False))).sum())
prereg_plane = {
    "source": str(SNAP.relative_to(REPO)),
    "bear_days_argmax": int(b.sum()),
    "bear_episodes_argmax": n_eps,
    "runtime_plane_bear_days": meas["stats_S"]["occupancy"]["BEAR"],
    "runtime_plane_bear_episodes": len(meas["bear_episodes_serving"]),
}
prereg_plane["ratio_days"] = round(
    prereg_plane["runtime_plane_bear_days"] / prereg_plane["bear_days_argmax"], 1)

# ── replica validity 1: 08-08 snapshot occupancy agreement ───────────────────
common = am.index.intersection(post.index)
repl_occ = post.loc[common, "gmm_dom"].value_counts(normalize=True) * 100
snap_occ = am.loc[common].value_counts(normalize=True) * 100
snapshot_agreement = {
    "n_common_days": int(len(common)),
    "replica_gmm_dominant_occ_pct": repl_occ.round(2).to_dict(),
    "snapshot_argmax_occ_pct": snap_occ.round(2).to_dict(),
    "max_abs_diff_pp": round(float((repl_occ - snap_occ).abs().max()), 2),
}

# ── replica validity 2: WF sanity-window replay counts (exact) ───────────────
ART = R104 / "artifacts" / "prod" / "panel-ltr.alpha158_fund.json"
art = json.load(open(ART))
gm = art["metadata"]["wf_gate_metadata"]
regimes = gm["sanity_regime_ic"]["regimes"]
win = lbl.loc[gm["sanity_eval_start"]:gm["sanity_eval_end"], "S"].value_counts()
wf_replay_counts = {
    "artifact": rel(ART),
    "sanity_window": [gm["sanity_eval_start"], gm["sanity_eval_end"]],
    "artifact_n_dates": {k: v["n_dates"] for k, v in regimes.items()},
    "replica_counts": {k: int(v) for k, v in win.items()},
    "exact_match": all(int(win.get(k, 0)) == v["n_dates"] for k, v in regimes.items()),
}
# the per-regime sanity ICs the memo quotes, straight from the served artifact
wf_replay_counts["artifact_sanity_regime_ic"] = {
    k: {"mean_ic": round(v["mean_ic"], 4),
        "genuine_ic": (None if v.get("placebo_gate_genuine_ic") is None
                       else round(v["placebo_gate_genuine_ic"], 4)),
        "passed": v.get("passed")}
    for k, v in regimes.items()}

# ── P5: recovery days (BEAR-labeled days from the -15% trough on) ────────────
rec = []
for ep in meas["bear_lag_S_vs_15pct"]:
    tr, ex = pd.Timestamp(ep["trough"]), pd.Timestamp(ep["exit"])
    seg = lbl.loc[tr:ex, "S"]  # trough day inclusive (memo definition)
    rec.append({"trough": ep["trough"], "exit": ep["exit"],
                "bear_days_from_trough_incl": int((seg == "BEAR").sum()),
                "bear_days_strictly_after_trough": int((seg.iloc[1:] == "BEAR").sum())})
recovery_days = {
    "definition": "serving BEAR-labeled days from the mechanical -15% trough "
                  "(inclusive) through the +15% recovery exit",
    "per_episode": rec,
    "total_from_trough_incl": int(sum(r["bear_days_from_trough_incl"] for r in rec)),
    "total_strictly_after": int(sum(r["bear_days_strictly_after_trough"] for r in rec)),
}

# ── P6: phase-A BEAR-day IC, validated vs false-alarm serving episodes ───────
# Exploratory E1 (memo): phase-A-dependent. Guarded — after a clean-checkout
# re-run of part 2 (phase_a_ic.skipped=true) this check skips instead of
# crashing; against part 2's committed corpus-present output it reproduces E1.
pa_ic = pic.get("phase_a_ic", {})
if "ic_daily" not in pa_ic:
    bear_ic_split = {
        "skipped": True,
        "reason": "phase-A corpus output unavailable (part 2 ran without "
                  "experiments/phase_a_data) — exploratory E1 only, not part "
                  "of the reproducible core",
    }
else:
    ic = pd.DataFrame(pa_ic["ic_daily"])
    ic["date"] = pd.to_datetime(ic["date"])
    bear_ic = ic[ic["S"] == "BEAR"].set_index("date")
    fa_windows = [(pd.Timestamp(x["start"]), pd.Timestamp(x["end"]))
                  for x in meas["false_alarms_S_vs_10pct"]]
    in_fa = bear_ic.index.map(
        lambda d: any(lo <= d <= hi for lo, hi in fa_windows))
    bear_ic_split = {
        "definition": "phase-A BEAR days split by serving-episode validation: a day "
                      "is 'false-alarm' when its BEAR episode lies entirely outside "
                      "every mechanical -10% drawdown window (M:false_alarms_S_vs_10pct)",
        "n_days_validated_episodes": int((~in_fa.values).sum()),
        "n_days_false_alarm_episodes": int(in_fa.values.sum()),
        "mean_ic_validated": round(float(bear_ic.loc[~in_fa.values, "ic"].mean()), 3),
        "mean_ic_false_alarm": (round(float(bear_ic.loc[in_fa.values, "ic"].mean()), 3)
                                if in_fa.values.any() else None),
    }

# ── as-built: GMM artifact + VIXCLS staleness ────────────────────────────────
gmm_art_path = R104 / "artifacts" / "prod" / "spy-gmm-regime.json"
g = json.load(open(gmm_art_path))
gmm_artifact = {"path": rel(gmm_art_path), "as_of_date": g["as_of_date"],
                "trained_date": g["trained_date"],
                "cluster_labels": g["cluster_labels"],
                "has_choppy_cluster": "CHOPPY" in g["cluster_labels"]}

vix_path = RQ / "data" / "fred" / "VIXCLS.parquet"
vix = pd.read_parquet(vix_path)
vix_last = pd.Timestamp(vix.index[-1])
vixcls_staleness = {"path": rel(vix_path), "last_row": str(vix_last.date()),
                    "memo_date": str(MEMO_DATE.date()),
                    "calendar_days_stale": int((MEMO_DATE - vix_last).days)}

out = {
    "hurst_null": hurst_null,
    "hysteresis": hysteresis,
    "prereg_plane": prereg_plane,
    "snapshot_agreement": snapshot_agreement,
    "wf_replay_counts": wf_replay_counts,
    "recovery_days": recovery_days,
    "bear_ic_split": bear_ic_split,
    "gmm_artifact": gmm_artifact,
    "vixcls_staleness": vixcls_staleness,
}
(OUT / f"{PREFIX}-replication.json").write_text(json.dumps(out, indent=1, default=str))

# ── manifest: sources + hashes + versions + seeds + commands ─────────────────
def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unavailable"


spy_path = RQ / "data" / "ohlcv" / "SPY" / "1d.parquet"
spy = pd.read_parquet(spy_path).sort_index()
spy.index = pd.to_datetime(spy.index)
spy_clamped = spy.loc[:END_DATE]
clamped_hash = hashlib.sha256(
    spy_clamped.to_csv(float_format="%.10g").encode()).hexdigest()

# Phase-A corpus identity: hash live when present (and check against the
# recorded pins); on a clean checkout record the pins instead of crashing.
pa_fr = PA / "forward_returns.csv"
if pa_fr.exists():
    fr_sha = sha(pa_fr)
    xgb_files = sorted((PA / "xgb").glob("*.json"))
    xgb_agg = hashlib.sha256()
    for f in xgb_files:
        xgb_agg.update(f.name.encode())
        xgb_agg.update(f.read_bytes())
    phase_a_sources = {
        "phase_a_forward_returns": {
            "path": rel(pa_fr), "sha256": fr_sha,
            "matches_pin": fr_sha == PA_FR_SHA256_PIN,
            "committed": False, "present_at_run": True,
            "note": "local extraction corpus, not in git"},
        "phase_a_xgb_scores": {
            "dir": rel(PA / "xgb"), "n_files": len(xgb_files),
            "sha256_aggregate": xgb_agg.hexdigest(),
            "matches_pin": (len(xgb_files) == PA_XGB_N_FILES_PIN
                            and xgb_agg.hexdigest() == PA_XGB_AGG_SHA256_PIN),
            "committed": False, "present_at_run": True},
    }
else:
    phase_a_sources = {
        "phase_a_forward_returns": {
            "path": rel(pa_fr), "committed": False, "present_at_run": False,
            "sha256_pin": PA_FR_SHA256_PIN, "pin_recorded": PIN_RECORDED,
            "note": "local extraction corpus, not in git; absent at this run "
                    "— identity pin recorded at the corpus-present full run"},
        "phase_a_xgb_scores": {
            "dir": rel(PA / "xgb"), "committed": False, "present_at_run": False,
            "n_files_pin": PA_XGB_N_FILES_PIN,
            "sha256_aggregate_pin": PA_XGB_AGG_SHA256_PIN,
            "pin_recorded": PIN_RECORDED},
    }

config = json.load(open(R104 / "strategy_config.json"))
manifest = {
    "memo": "doc/research/2026-08-17-regime-detector-assessment.md",
    "generated_by": [f"{PREFIX}-measurements.py", f"{PREFIX}-posteriors-ic.py",
                     f"{PREFIX}-replication.py"],
    "commands": [
        f"~/git/github/RenQuant/.venv/bin/python doc/research/data/{PREFIX}-measurements.py",
        f"~/git/github/RenQuant/.venv/bin/python doc/research/data/{PREFIX}-posteriors-ic.py",
        f"~/git/github/RenQuant/.venv/bin/python doc/research/data/{PREFIX}-replication.py",
    ],
    "date_bounds": {
        "input_clamp_end": str(END_DATE.date()),
        "spy_input_span_used": [str(spy_clamped.index[0].date()),
                                str(spy_clamped.index[-1].date())],
        "serving_series_span": meas["span"],
        "wf_comparability_window": ["2019-01-14", "2026-03-02"],
        "wf_sanity_window": wf_replay_counts["sanity_window"],
    },
    "sources": {
        "spy_1d_parquet": {"path": rel(spy_path), "sha256_at_run": sha(spy_path),
                           "rows_at_run": int(len(spy)),
                           "last_row_at_run": str(spy.index[-1].date()),
                           "sha256_clamped_slice_csv": clamped_hash,
                           "rows_clamped": int(len(spy_clamped))},
        "strategy_config": {"path": rel(R104 / "strategy_config.json"),
                            "sha256": sha(R104 / "strategy_config.json")},
        "gmm_artifact": {"path": rel(gmm_art_path), "sha256": sha(gmm_art_path),
                         "as_of_date": g["as_of_date"]},
        "served_panel_artifact": {"path": rel(ART), "sha256": sha(ART)},
        "posterior_snapshot_csv": {"path": str(SNAP.relative_to(REPO)),
                                   "sha256": sha(SNAP), "committed": True},
        **phase_a_sources,
        "vixcls_parquet": {"path": rel(vix_path), "sha256": sha(vix_path),
                           "last_row": str(vix_last.date())},
    },
    "code_versions": {
        "renquant_umbrella_git_head": git_head(RQ),
        "renquant_common_git_head": git_head(Path(COMMON).parent),
        "serving_detector": "kernel/regime.py::detect_regime (umbrella renquant_104)",
        "research_detector_versions": ["legacy", "v2026-05-31"],
        "detector_params_from_config": {
            k: config["regime"].get(k)
            for k in ("hurst_window", "hurst_trending_threshold",
                      "hurst_reversion_threshold", "vol_realized_window")},
    },
    "seeds": {"hurst_null": [r["seed"] for r in HURST_NULL_RUNS]},
    "algorithms": {
        "bear_dating": "Lunde-Timmermann-style causal drawdown dating: enter on "
                       "close <= (1-thr)*running_peak, exit on close >= "
                       "(1+thr)*running_trough or new high; thr in {10%,15%,20%}",
        "hysteresis": hysteresis["rule"],
        "episode": "maximal run of consecutive identical daily labels",
        "prereg_plane": "argmax over the four regime_p_* columns of the "
                        "committed 08-08 posterior snapshot",
    },
}
(OUT / f"{PREFIX}-manifest.json").write_text(json.dumps(manifest, indent=1))
print(json.dumps(out, indent=1, default=str))
print(f"wrote {PREFIX}-replication.json + {PREFIX}-manifest.json")
