"""qp evidence runner (PR B, JOIN-ONLY) — the orchestrator half of the
MERGED freeze doc/design/2026-08-10-qp-reenable-evidence-prereg.md
(orch#955). The doc text wins on any mismatch.

Consumes PR A's hash-pinned artifacts (renquant-model qp_evidence_scorer):
  scores CSV   fold,date,ticker,recipe_score,regime   (test days only)
  stamps JSON  {"folds": {<fold>: {"boundaries": {...},
                                    "stamps": {<REGIME>: {"eligible": b,
                                                          "passed": b}},
                                    "momentum_degraded": b}},
                ...}
This side does ONLY: frozen-corpus label join, the designed admission
semantics on the FROZEN stamps (fail-closed: missing/ineligible/failed
regime ⇒ the day is gate-starved), the frozen statistic, the frozen
inference, coverage, the §6 verdict enum, and the report-only cost
companion. No training, no scoring, no regime computation.

Frozen constants (doc §3/§5/§6): K=5; BAR=0.0658 σ/day; stationary
bootstrap BLOCK=10, B=2000, SEED=99; POWER_FLOOR_DAYS=700; verdict ∈
{PASS, FAIL, POWER_INSUFFICIENT}; labels = the frozen corpus's
fwd_5d_excess (per-day cross-sectional z).

Usage:
  python 2026-08-10-qp-evidence-runner.py <scores.csv> <stamps.json> \
      <manifest.json> <frozen_corpus.parquet> <out_prefix> \
      [--fixture-mode]
Identity: the scores CSV and stamps JSON sha256s must equal the
manifest's recorded values, and the corpus sha must equal the manifest's
frozen_corpus_sha256 (in --fixture-mode the manifest carries the
fixture's own shas — the assertion logic is IDENTICAL, only the pinned
values differ, so tests exercise the real code path).
Outputs <out_prefix>_daily.csv, _coverage.csv, _summary.json verbatim.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

K = 5
BAR = 0.0658
BLOCK, B, BOOT_SEED = 10, 2000, 99
POWER_FLOOR_DAYS = 700
LABEL = "fwd_5d_excess"
TURNOVER_COST_BPS = 10.0
SIGMA_PER_DAY_RAW = 0.0404   # doc §5 median-day z→raw mapping


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) < 6:
        sys.exit("usage: runner.py <scores.csv> <stamps.json> <manifest.json> "
                 "<frozen_corpus.parquet> <out_prefix> [--fixture-mode]")
    SCORES, STAMPS, MANIFEST, CORPUS, OUT = argv[1:6]
    OUT = Path(OUT)

    man = json.loads(Path(MANIFEST).read_text())
    for path, key in ((SCORES, "scores_csv_sha256"), (STAMPS, "stamps_json_sha256"),
                      (CORPUS, "frozen_corpus_sha256")):
        got = file_sha256(path)
        want = man.get(key)
        assert want and got == want, f"{key}: {got[:12]} != manifest {str(want)[:12]}"

    scores = pd.read_csv(SCORES, dtype={"date": str, "fold": int})
    assert list(scores.columns) == ["fold", "date", "ticker", "recipe_score", "regime"], scores.columns
    assert not scores.duplicated(["date", "ticker"]).any(), "duplicate score keys"

    stamps = json.loads(Path(STAMPS).read_text())["folds"]

    labels = pd.read_parquet(CORPUS, columns=["date", "ticker", LABEL])
    labels["date"] = labels["date"].astype(str).str[:10]

    rows, cov = [], []
    prev_top: set = set()
    for (f, d), g in scores.groupby(["fold", "date"], sort=True):
        fold_stamps = (stamps.get(str(f)) or stamps.get(int(f) if isinstance(f, str) else f) or {}).get("stamps", {})
        regime = str(g.regime.iloc[0])
        st = fold_stamps.get(regime)
        base_cov = {"date": d, "fold": int(f), "regime": regime}
        # Designed admission on FROZEN stamps, fail-closed (doc §4):
        if not st or not st.get("eligible") or not st.get("passed"):
            reason = ("no_stamps" if not st else
                      "ineligible" if not st.get("eligible") else "failed")
            cov.append({**base_cov, "skip": f"gate_starved:{reason}",
                        "n_scored": len(g)})
            continue
        lab_d = labels[labels.date == d].set_index("ticker")[LABEL].dropna()
        gg = g.set_index("ticker")
        inter = gg.index.intersection(lab_d.index).sort_values()
        cov.append({**base_cov, "skip": "",
                    "n_scored": len(gg), "n_labelled": len(inter),
                    "scored_only": "|".join(sorted(set(gg.index) - set(lab_d.index))),
                    "labelled_only_count": len(set(lab_d.index) - set(gg.index))})
        if len(inter) < K:
            cov[-1]["skip"] = "labelled<k"
            continue
        u_scores = gg.loc[inter, "recipe_score"]
        u_labels = lab_d.loc[inter]
        top = u_scores.nlargest(K).index
        base = float(u_labels.mean())
        stat = float(u_labels.loc[top].mean() - base)
        oracle = float(u_labels.nlargest(K).mean() - base)
        turnover = len(set(top) - prev_top) / K if prev_top else 0.0
        prev_top = set(top)
        rows.append({"date": d, "fold": int(f), "n_universe": len(inter),
                     "stat": stat, "oracle": oracle, "turnover": turnover})

    daily = pd.DataFrame(rows)
    n = len(daily)
    daily.to_csv(OUT.parent / (OUT.name + "_daily.csv"), index=False)
    pd.DataFrame(cov).to_csv(OUT.parent / (OUT.name + "_coverage.csv"), index=False)

    if n == 0:
        mean_stat = med_stat = None
        ci = (None, None)
    else:
        x = daily.stat.values
        rng = np.random.default_rng(BOOT_SEED)
        means = []
        for _ in range(B):
            idx = []
            while len(idx) < n:
                start = rng.integers(n)
                length = rng.geometric(1 / BLOCK)
                idx.extend(((start + np.arange(length)) % n).tolist())
            means.append(float(np.mean(x[np.array(idx[:n])])))
        ci = (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
        mean_stat, med_stat = float(np.mean(x)), float(np.median(x))

    # §6 verdict, exactly:
    if n < POWER_FLOOR_DAYS:
        verdict = "POWER_INSUFFICIENT"
    elif mean_stat >= BAR and ci[0] is not None and ci[0] > 0:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    cost_sigma_day = (None if n == 0 else
                      float(daily.turnover.mean() * K * (TURNOVER_COST_BPS / 1e4)
                            / SIGMA_PER_DAY_RAW / 5))
    summary = {
        "design_doc": "doc/design/2026-08-10-qp-reenable-evidence-prereg.md",
        "scores_csv_sha256": man["scores_csv_sha256"],
        "stamps_json_sha256": man["stamps_json_sha256"],
        "frozen_corpus_sha256": man["frozen_corpus_sha256"],
        "k": K, "bar_sigma_per_day": BAR,
        "bootstrap": {"block": BLOCK, "B": B, "seed": BOOT_SEED},
        "n_days_realized": n,
        "n_days_gate_starved": int(sum(1 for c in cov if str(c.get("skip", "")).startswith("gate_starved"))),
        "power_floor_days": POWER_FLOOR_DAYS,
        "mean_stat_sigma_per_day": mean_stat,
        "median_stat_sigma_per_day": med_stat,
        "bootstrap_ci95": list(ci),
        "oracle_mean_plumbing_control": (float(daily.oracle.mean()) if n else None),
        "cost_companion_sigma_per_day_report_only": cost_sigma_day,
        "verdict": verdict,
    }
    (OUT.parent / (OUT.name + "_summary.json")).write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main(sys.argv)
