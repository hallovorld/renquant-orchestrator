"""BEAR exit-side prereg (orch#917) — episode-list derivation + verifier.

The frozen evaluation plan (doc/design/2026-08-08-bear-exit-prereg.md §3)
requires: "the evaluation re-derives the episode list from the production
regime artifact at run time and the results PR commits it as a derivation
artifact". This file is that derivation, executed AHEAD of the (currently
blocked) confirmatory run so the blocker note
doc/research/2026-08-10-bear-exit-eval-runnability.md can quantify exactly
which episodes the existing simulator machinery can and cannot reach.

It derives NOTHING beyond what §3's own text names: per-day regime argmax
from the regime artifact over SPY history 2017-01-01..2026-08-07, BEAR days
grouped into contiguous-trading-day episodes, and the frozen 10-trading-day
post-episode tail per episode. No estimand is computed here.

Artifact-identity note (material, flagged in the runnability note): the
prereg says "production HMM", but production loads
`strategy_config.json::regime.gmm_artifact = prod/spy-gmm-regime.json`,
which is a legacy GMM (no `model_type`/`transition_matrix`); the only HMM
artifact on the machine is `sim/spy-hmm-regime.json`. Both derivations are
committed so the freeze-interpretation ruling can see whether the choice
matters. Labels are the artifact argmax (`max(probs, key=probs.get)` —
the `dominant_gmm` line of RegimeFinalizeTask), NOT the full resolved
regime stack (Hurst/CUSUM/hard-BEAR override/cooldown), because §3 names
"the production regime artifact" as the source and the artifact alone
carries no Hurst/CUSUM state.

DEFAULT (verify): recompute every summary number from the committed CSVs
alone — `2026-08-10-bear-exit-regime-days.csv` and
`2026-08-10-bear-exit-episodes.csv`, beside this file. No parquet, no
sibling checkouts, no network. Exits non-zero on any mismatch with the
frozen EXPECTED values.

--derive: rebuild both CSVs from the machine-local inputs (read-only):
  SPY OHLCV   RenQuant/data/ohlcv/SPY/1d.parquet
  GMM         RenQuant/backtesting/renquant_104/artifacts/prod/spy-gmm-regime.json
  HMM         RenQuant/backtesting/renquant_104/artifacts/sim/spy-hmm-regime.json
  code        renquant-pipeline sibling checkout (kernel.regime.gmm_predict /
              kernel.regime_hmm.hmm_predict — the PRODUCTION functions,
              imported, not reimplemented; regime.py/regime_hmm.py/
              task_regime.py verified byte-identical between the umbrella
              production pin e13cd3eb and checkout HEAD 69bf7116 on
              2026-08-10)
Refuses with a clear message when any input is absent.

Per-day convention (recorded, not frozen anywhere in the prereg): day d is
labeled from bars <= d inclusive (the sim/WF convention: the regime task
sees OHLCV through `today`). spy_returns = close.pct_change().dropna()
over the full slice — the GMM consumes only its last 20 bars plus a 14-bar
ADX window, so the live hydrator's 100-bar truncation is immaterial.

Coverage flags (existing-simulator reach, quantified for the blocker note):
  within_wf_2024   episode start >= 2024-01-02 AND tail end <= 2026-03-28
                   (walk-forward retrain manifest: 39 cutoffs 2024-01-01..
                   2026-03-09; default sim window ends 2026-03-28)
  within_aux_2022  episode start >= 2022-04-01 AND tail end <= 2026-03-28
                   (earliest aux sim artifact set: sim/aux_2022-04-01)
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
DAYS_CSV = HERE / "2026-08-10-bear-exit-regime-days.csv"
EPISODES_CSV = HERE / "2026-08-10-bear-exit-episodes.csv"

SPY_PARQUET = Path("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet")
GMM_ARTIFACT = Path("/Users/renhao/git/github/RenQuant/backtesting/renquant_104"
                    "/artifacts/prod/spy-gmm-regime.json")
HMM_ARTIFACT = Path("/Users/renhao/git/github/RenQuant/backtesting/renquant_104"
                    "/artifacts/sim/spy-hmm-regime.json")
PIPELINE_SRC = Path("/Users/renhao/git/github/renquant-pipeline/src")

START, END = "2017-01-01", "2026-08-07"   # prereg window; END = data boundary
TAIL_N = 10                               # prereg §3 frozen post-episode tail
VOL_WINDOW = 20                           # pinned config regime.vol_realized_window
WF_2024 = ("2024-01-02", "2026-03-28")
AUX_2022 = ("2022-04-01", "2026-03-28")

# Frozen expected values (2026-08-10 derivation; quoted in the runnability
# note). Keyed by artifact column prefix.
EXPECTED = {
    "prod_gmm": {
        "bear_days": 75,
        "episodes": 5,
        "max_episode_len": 41,
        "median_episode_len": 8,
        "episodes_within_wf_2024": 1,
        "episodes_within_aux_2022": 3,
    },
    "sim_hmm": {
        "bear_days": 211,
        "episodes": 17,
        "max_episode_len": 49,
        "median_episode_len": 9,
        "episodes_within_wf_2024": 3,
        "episodes_within_aux_2022": 9,
    },
    "n_trading_days": 2412,
}

DAY_FIELDS = ["date", "prod_gmm_label", "prod_gmm_p_bear",
              "sim_hmm_label", "sim_hmm_p_bear"]
EP_FIELDS = ["artifact", "episode_id", "start", "end", "n_days",
             "tail_start", "tail_end", "n_tail_days", "tail_clipped",
             "within_wf_2024", "within_aux_2022"]


def group_episodes(day_labels: list[tuple[str, bool]],
                   tail_n: int = TAIL_N) -> list[dict]:
    """Group BEAR-flagged trading days into contiguous episodes + tails.

    `day_labels`: ordered (trading_date, is_bear) pairs — EVERY trading day
    in the window, so contiguity is contiguity in trading days, not
    calendar days. The tail is the next `tail_n` trading days after the
    episode's last BEAR day (clipped at the series end, flagged).
    Pure function — unit-tested with planted/null fixtures.
    """
    episodes: list[dict] = []
    dates = [d for d, _ in day_labels]
    i, n = 0, len(day_labels)
    while i < n:
        if not day_labels[i][1]:
            i += 1
            continue
        j = i
        while j + 1 < n and day_labels[j + 1][1]:
            j += 1
        tail_start_idx = j + 1
        tail_end_idx = min(j + tail_n, n - 1)
        n_tail = max(0, tail_end_idx - j)
        episodes.append({
            "episode_id": len(episodes) + 1,
            "start": dates[i],
            "end": dates[j],
            "n_days": j - i + 1,
            "tail_start": dates[tail_start_idx] if tail_start_idx < n else "",
            "tail_end": dates[tail_end_idx] if n_tail > 0 else "",
            "n_tail_days": n_tail,
            "tail_clipped": int(n_tail < tail_n),
        })
        i = j + 1
    return episodes


def coverage_flags(ep: dict) -> dict:
    """Stamp existing-simulator coverage windows onto an episode row."""
    span_end = ep["tail_end"] or ep["end"]
    ep["within_wf_2024"] = int(ep["start"] >= WF_2024[0] and span_end <= WF_2024[1])
    ep["within_aux_2022"] = int(ep["start"] >= AUX_2022[0] and span_end <= AUX_2022[1])
    return ep


def _summarize_arm(episodes: list[dict], bear_days: int) -> dict:
    lens = [e["n_days"] for e in episodes]
    return {
        "bear_days": bear_days,
        "episodes": len(episodes),
        "max_episode_len": max(lens) if lens else 0,
        "median_episode_len": int(statistics.median(lens)) if lens else 0,
        "episodes_within_wf_2024": sum(e["within_wf_2024"] for e in episodes),
        "episodes_within_aux_2022": sum(e["within_aux_2022"] for e in episodes),
    }


def _summaries_from_rows(day_rows: list[dict], ep_rows: list[dict]) -> dict:
    out: dict = {"n_trading_days": len(day_rows)}
    for arm in ("prod_gmm", "sim_hmm"):
        eps = [{k: (int(v) if k in ("n_days", "within_wf_2024",
                                    "within_aux_2022") else v)
                for k, v in e.items()}
               for e in ep_rows if e["artifact"] == arm]
        bear_days = sum(1 for r in day_rows if r[f"{arm}_label"] == "BEAR")
        out[arm] = _summarize_arm(eps, bear_days)
    return out


def verify() -> int:
    with open(DAYS_CSV, newline="") as fh:
        day_rows = list(csv.DictReader(fh))
    with open(EPISODES_CSV, newline="") as fh:
        ep_rows = list(csv.DictReader(fh))
    got = _summaries_from_rows(day_rows, ep_rows)

    # Structural re-check: regrouping the committed day rows must reproduce
    # the committed episode rows exactly (episode table is derived, not
    # independent).
    ok = True
    for arm in ("prod_gmm", "sim_hmm"):
        flags = [(r["date"], r[f"{arm}_label"] == "BEAR") for r in day_rows]
        regrouped = [coverage_flags(e) for e in group_episodes(flags)]
        committed = [e for e in ep_rows if e["artifact"] == arm]
        if len(regrouped) != len(committed):
            print(f"  {arm}: episode regroup count {len(regrouped)} != "
                  f"committed {len(committed)}  MISMATCH")
            ok = False
            continue
        for want, have in zip(regrouped, committed):
            for k in ("start", "end", "tail_end"):
                if str(want[k]) != have[k]:
                    print(f"  {arm} ep{want['episode_id']}: {k} "
                          f"{want[k]} != {have[k]}  MISMATCH")
                    ok = False

    print(f"== episode-derivation verify from {DAYS_CSV.name} / "
          f"{EPISODES_CSV.name} ==")
    for key, want in EXPECTED.items():
        if isinstance(want, dict):
            for k2, w2 in want.items():
                g2 = got[key][k2]
                match = g2 == w2
                ok &= match
                print(f"  {key}.{k2:26s} got={g2:<8} expected={w2:<8} "
                      f"{'OK' if match else 'MISMATCH'}")
        else:
            match = got[key] == want
            ok &= match
            print(f"  {key:30s} got={got[key]:<8} expected={want:<8} "
                  f"{'OK' if match else 'MISMATCH'}")
    print("VERDICT:", "REPRODUCED" if ok else "MISMATCH")
    return 0 if ok else 1


def derive() -> int:
    for p in (SPY_PARQUET, GMM_ARTIFACT, HMM_ARTIFACT, PIPELINE_SRC):
        if not p.exists():
            print(f"--derive needs {p} (machine-local, deliberately not "
                  "committed). Run on the workstation, or use the default "
                  "verify mode against the committed CSVs.")
            return 2
    import numpy as np
    import pandas as pd
    sys.path.insert(0, str(PIPELINE_SRC))
    from renquant_pipeline.kernel.regime import gmm_predict          # noqa: PLC0415
    from renquant_pipeline.kernel.regime_hmm import hmm_predict      # noqa: PLC0415

    gmm = json.loads(GMM_ARTIFACT.read_text())
    hmm = json.loads(HMM_ARTIFACT.read_text())
    spy = pd.read_parquet(SPY_PARQUET).sort_index()
    rets_full = spy["close"].pct_change().dropna()

    dates = [d for d in spy.index if START <= str(d.date()) <= END]
    day_rows: list[dict] = []
    for d in dates:
        df_slice = spy.loc[:d]
        r = rets_full.loc[:d].to_numpy(dtype=float)
        row: dict = {"date": str(d.date())}
        for prefix, artifact, fn in (("prod_gmm", gmm, gmm_predict),
                                     ("sim_hmm", hmm, hmm_predict)):
            probs = fn(artifact, r, df_slice, vol_window=VOL_WINDOW)
            label = max(probs, key=probs.get) if probs else ""
            row[f"{prefix}_label"] = label
            row[f"{prefix}_p_bear"] = round(float(probs.get("BEAR", float("nan"))), 6)
        day_rows.append(row)

    ep_rows: list[dict] = []
    for arm in ("prod_gmm", "sim_hmm"):
        flags = [(r["date"], r[f"{arm}_label"] == "BEAR") for r in day_rows]
        for ep in group_episodes(flags):
            ep = coverage_flags(ep)
            ep_rows.append({"artifact": arm, **ep})

    with open(DAYS_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DAY_FIELDS)
        w.writeheader()
        w.writerows(day_rows)
    with open(EPISODES_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EP_FIELDS)
        w.writeheader()
        w.writerows(ep_rows)
    print(f"wrote {len(day_rows)} day rows -> {DAYS_CSV.name}")
    print(f"wrote {len(ep_rows)} episode rows -> {EPISODES_CSV.name}")

    got = _summaries_from_rows(
        day_rows,
        [{k: str(v) for k, v in e.items()} for e in ep_rows])
    print(json.dumps(got, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(derive() if "--derive" in sys.argv[1:] else verify())
