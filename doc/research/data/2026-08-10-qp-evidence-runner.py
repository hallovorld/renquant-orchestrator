"""qp evidence runner (PR B, JOIN-ONLY) — the orchestrator half of the
MERGED freeze doc/design/2026-08-10-qp-reenable-evidence-prereg.md
(orch#955). The doc text wins on any mismatch.

Consumes PR A's hash-pinned artifacts (renquant-model model#221 —
schemas below are THE COMMITTED artifacts', read from the real files):
  scores CSV   fold,date,ticker,recipe_score,regime   (test days only)
  stamps JSON  {"fold_<n>": {"boundaries": {...}, "passed": b,
                             "reason": str,
                             "regimes": {<REGIME>: {"eligible": b,
                                                    "passed": b, ...}}}}
  manifest     outputs.scores_csv.sha256 / outputs.stamps_json.sha256 /
               inputs.frozen_corpus.sha256 / expected_schedule (top)
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
      <manifest.json> <frozen_corpus.parquet> <harness.py> <out_prefix> \
      [--fixture-mode]
Identity: the scores CSV and stamps JSON sha256s must equal the
manifest's recorded values, and the corpus sha must equal the manifest's
frozen_corpus_sha256 (in --fixture-mode the manifest carries the
fixture's own shas — the assertion logic is IDENTICAL, only the pinned
values differ, so tests exercise the real code path).
Outputs <out_prefix>_daily.csv, _coverage.csv, _summary.json verbatim.
"""
import ast, hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

K = 5
BAR = 0.0658
BLOCK, B, BOOT_SEED = 10, 2000, 99
POWER_FLOOR_DAYS = 700
LABEL = "fwd_5d_excess"
FROZEN_CORPUS_SHA = "870f68ebad5d2d87e2601f62310f34615d2d8d25df9d9cbf563629b13129bf7e"
FROZEN_HARNESS_SHA = "7ca9e48f3be9680ed176ecf49c5c73ea09580cd38bbac278521654be4c70924d"
TURNOVER_COST_BPS = 10.0
SIGMA_PER_DAY_RAW = 0.0404   # doc §5 median-day z→raw mapping


def admitted_runs(daily, derived):
    """Contiguous admitted runs per fold (review r7): within each fold,
    split the admitted days wherever the next admitted day is NOT the
    immediately next SCHEDULED day — a gate-starved (or missing-regime)
    gap breaks contiguity, so no bootstrap block may bridge it. Returns
    a list of 1-D stat arrays, one per contiguous run."""
    runs = []
    for f in sorted(daily.fold.unique()):
        sched = derived[str(int(f))]
        pos = {d: i for i, d in enumerate(sched)}
        sub = daily[daily.fold == f].sort_values("date")
        cur = []
        prev_pos = None
        for _, r in sub.iterrows():
            i = pos[r.date]
            if prev_pos is not None and i != prev_pos + 1:
                runs.append(cur); cur = []
            cur.append(float(r.stat)); prev_pos = i
        if cur:
            runs.append(cur)
    return [np.asarray(r) for r in runs]


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) < 7:
        sys.exit("usage: runner.py <scores.csv> <stamps.json> <manifest.json> "
                 "<frozen_corpus.parquet> <harness.py> <out_prefix> [--fixture-mode]")
    SCORES, STAMPS, MANIFEST, CORPUS, HARNESS, OUT = argv[1:7]
    OUT = Path(OUT)
    fixture_mode = "--fixture-mode" in argv[7:]

    man = json.loads(Path(MANIFEST).read_text())
    pins = {
        "outputs.scores_csv.sha256": (SCORES, man.get("outputs", {}).get("scores_csv", {}).get("sha256")),
        "outputs.stamps_json.sha256": (STAMPS, man.get("outputs", {}).get("stamps_json", {}).get("sha256")),
        "inputs.frozen_corpus.sha256": (CORPUS, man.get("inputs", {}).get("frozen_corpus", {}).get("sha256")),
    }
    for key, (path, want) in pins.items():
        got = file_sha256(path)
        assert want and got == want, f"{key}: {got[:12]} != manifest {str(want)[:12]}"
    # The freeze pin is the RUNNER'S OWN constant (review r2): the real
    # corpus must equal 870f68eb... regardless of what the manifest says;
    # --fixture-mode relaxes ONLY this constant check (recorded in the
    # summary) so tests exercise the identical manifest-assertion path.
    if not fixture_mode:
        got = file_sha256(CORPUS)
        assert got == FROZEN_CORPUS_SHA, (
            f"corpus {got[:12]} != the freeze pin {FROZEN_CORPUS_SHA[:12]}")
        # The CUTS source is pinned the same way (review r6): the harness
        # text must be EXACTLY the frozen model#213 file before parsing.
        hgot = file_sha256(HARNESS)
        assert hgot == FROZEN_HARNESS_SHA, (
            f"harness {hgot[:12]} != the frozen harness pin "
            f"{FROZEN_HARNESS_SHA[:12]}")

    scores = pd.read_csv(SCORES, dtype={"date": str, "fold": int})
    assert list(scores.columns) == ["fold", "date", "ticker", "recipe_score", "regime"], scores.columns
    assert not scores.duplicated(["date", "ticker"]).any(), "duplicate score keys"

    # Independent schedule derivation (review r4, P0): the manifest is
    # produced by the same side that produces the scores, so trusting its
    # schedule is circular. The runner DERIVES the expected schedule
    # itself — CUTS ast-read from the frozen harness text (sha recorded)
    # intersected with the pin-asserted corpus's own dates — and asserts
    # the manifest's schedule is IDENTICAL before using it for anything.
    tree = ast.parse(Path(HARNESS).read_text())
    cuts = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "CUTS"):
            cuts = ast.literal_eval(node.value)
    assert cuts, "harness text carries no CUTS"
    corpus_dates = sorted(pd.read_parquet(CORPUS, columns=["date"])["date"]
                          .astype(str).str[:10].unique())
    derived = {str(i + 1): [d for d in corpus_dates if ts <= d <= te]
               for i, (_, _, ts, te) in enumerate(cuts)}
    derived = {f: ds for f, ds in derived.items() if ds}
    schedule = man["expected_schedule"]
    assert {str(k): list(v) for k, v in schedule.items()} == derived, (
        "manifest expected_schedule differs from the runner-derived "
        "CUTS x corpus schedule")
    expected = {(int(f), d) for f, ds in derived.items() for d in ds}
    got_pairs = {(int(f), d) for f, d in scores[["fold", "date"]]
                 .drop_duplicates().itertuples(index=False)}
    extra = got_pairs - expected
    assert not extra, f"scores contain off-schedule (fold,date) pairs: {sorted(extra)[:5]}"
    missing = sorted(expected - got_pairs)

    stamps = json.loads(Path(STAMPS).read_text())

    labels = pd.read_parquet(CORPUS, columns=["date", "ticker", LABEL])
    labels["date"] = labels["date"].astype(str).str[:10]

    rows, cov = [], []
    for f, d in missing:
        cov.append({"date": d, "fold": int(f), "regime": None,
                    "skip": "missing_from_scores", "n_scored": 0})
    # FAIL CLOSED (review r5, P0): a scheduled day absent from the scores
    # is an artifact-integrity failure — the run REFUSES to adjudicate.
    # The coverage rows above are still written first (audit trail),
    # then the runner aborts; no verdict of any kind is produced.
    if missing:
        pd.DataFrame(cov).to_csv(OUT.parent / (OUT.name + "_coverage.csv"),
                                 index=False)
        raise AssertionError(
            f"{len(missing)} scheduled day(s) missing from scores — "
            f"artifact incomplete, refusing to adjudicate: "
            f"{missing[:5]}")
    prev_top: set = set()
    prev_fold = None
    for (f, d), g in scores.groupby(["fold", "date"], sort=True):
        if f != prev_fold:
            prev_top = set()   # review r3 P1: no turnover transition across folds
            prev_fold = f
        fold_stamps = stamps.get(f"fold_{int(f)}", {}).get("regimes", {})
        uregs = g.regime.unique()
        assert len(uregs) == 1, f"{d} fold {f}: mixed regimes {list(uregs)}"
        regime = str(uregs[0])
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
                    "labelled_only": "|".join(sorted(set(lab_d.index) - set(gg.index)))})
        if len(inter) < K:
            cov[-1]["skip"] = "labelled<k"
            continue
        u_scores = gg.loc[inter, "recipe_score"]
        u_labels = lab_d.loc[inter]
        # deterministic ties (review r3 P2): sort by (-score, ticker)
        top = (u_scores.rename("s").reset_index()
               .sort_values(["s", "ticker"], ascending=[False, True])
               .head(K).ticker.tolist())
        top = pd.Index(top)
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
        # Contiguous-admitted-run bootstrap (review r7, superseding the
        # r3 per-fold rule): blocks are drawn WITHIN each contiguous
        # admitted run — a run breaks at fold boundaries AND at any
        # gate-starved/missing-regime gap in the fold's schedule, so no
        # block ever bridges calendar days that were not adjacent among
        # the admitted days.
        segments = admitted_runs(daily, derived)
        rng = np.random.default_rng(BOOT_SEED)
        means = []
        for _ in range(B):
            draw = []
            for seg in segments:
                m = len(seg)
                idx = []
                while len(idx) < m:
                    start = rng.integers(m)
                    length = rng.geometric(1 / BLOCK)
                    idx.extend(((start + np.arange(length)) % m).tolist())
                draw.append(seg[np.array(idx[:m])])
            means.append(float(np.mean(np.concatenate(draw))))
        x = daily.stat.values
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
        "fixture_mode": bool(fixture_mode),
        "freeze_corpus_pin": FROZEN_CORPUS_SHA,
        "scores_csv_sha256": pins["outputs.scores_csv.sha256"][1],
        "stamps_json_sha256": pins["outputs.stamps_json.sha256"][1],
        "frozen_corpus_sha256": pins["inputs.frozen_corpus.sha256"][1],
        "manifest_sha256": file_sha256(MANIFEST),
        "harness_sha256_schedule_source": file_sha256(HARNESS),
        "n_schedule_days_derived": len(expected),
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
