"""Serving-fidelity probe v1 — identity + distribution + coverage (orch#958).

The G-F thesis: the probe fleet answers "did it arrive", never "was it
correct". v1 closes the cheap two-thirds of that gap in seconds, read-only,
with no feature rebuild:

  LAYER 1 — IDENTITY (the #908 silent-swap class): the RECORDED artifact
    identity of the day's canonical run (pipeline_runs.model_content_sha256,
    training_cutoff) must be consistent across the day's runs, and the
    golden config's blend component pins must match the artifacts on disk
    (panel byte-sha prefix; momentum ledger tail row's content sha).
  LAYER 2 — DISTRIBUTION (the frozen-score class, job_panel_scoring's
    documented SPOT incident): the day's cross-sectional panel_score must
    not be byte-frozen (distinct values >= min_distinct) and its
    cross-sectional std must sit within [lo, hi] x the trailing-20-day
    median std.
  LAYER 3 — COVERAGE: scored names >= min_scored; no NULL-regime rows.

v2 (full offline re-score against rebuilt features — the orch#949/#950
machinery on a daily cadence) is DELIBERATELY out of v1: it needs the
corpus-recipe feature rebuild, which is not a seconds-scale read-only
operation. v1's three layers alert on every failure class tonight's
forensics actually found (silent swap, frozen scores, starved coverage);
v2 is tracked in orch#958.

Usage:
  python serving_fidelity_probe.py <runs.db> <golden_config.json> \
      <artifacts_root> <date YYYY-MM-DD> [--ledger <out.jsonl>]
Exit 0 = all layers PASS; exit 1 = any layer FAIL (alert-ready). The
optional ledger appends one JSON row per invocation (probe history).
Read-only on every input; the ledger is the only write and must not be
a production path.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

MIN_DISTINCT = 10        # layer 2: fewer distinct scores => frozen-score alarm
STD_BAND = (0.25, 4.0)   # layer 2: today's std vs trailing median std
TRAIL_DAYS = 20
MIN_SCORED = 30          # layer 3


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(d):
    return str(d or "").removeprefix("sha256:").lower()


def probe(db, golden, artifacts_root, date):
    findings = []
    ok = lambda: not findings

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    runs = con.execute(
        "SELECT run_id, model_content_sha256, training_cutoff FROM pipeline_runs "
        "WHERE run_type='live' AND run_date=?", (date,)).fetchall()
    if not runs:
        findings.append(f"no live runs recorded for {date}")
        con.close()
        return findings, {}

    # LAYER 1a: one artifact identity across the day's live runs
    idents = {(r[1], r[2]) for r in runs}
    if len(idents) != 1:
        findings.append(f"mixed artifact identities within {date}: {sorted(idents)}")

    # LAYER 1b: golden blend pins vs artifacts on disk
    g = json.loads(Path(golden).read_text())
    comps = g["ranking"]["panel_scoring"].get("components") or []
    for comp in comps:
        apath = Path(artifacts_root) / comp["artifact_path"]
        if comp.get("kind") == "momentum_residual":
            if not apath.exists():
                findings.append(f"momentum ledger missing: {apath}")
                continue
            tail = json.loads(apath.read_text().strip().splitlines()[-1])
            dated = apath.parent / str(tail.get("cutoff_date", "")) / "momentum_residual_v0.json"
            if not dated.exists():
                findings.append(f"momentum tail artifact missing: {dated}")
            else:
                art = json.loads(dated.read_text())
                if _norm(art.get("content_sha256")) != _norm(tail.get("artifact_content_sha256")):
                    findings.append("momentum tail artifact sha != ledger row sha")
        else:
            pin = _norm(comp.get("expected_content_sha256"))
            if not apath.exists():
                findings.append(f"panel artifact missing: {apath}")
            elif pin and not file_sha256(apath).startswith(pin[:16] if len(pin) >= 16 else pin):
                findings.append(f"panel artifact sha does not match golden pin {pin[:12]}")

    # LAYER 2: distribution
    rows = con.execute(
        """WITH canonical AS (
             SELECT run_id FROM (
               SELECT run_id, ROW_NUMBER() OVER (ORDER BY created_at DESC, run_id DESC) rn
               FROM pipeline_runs WHERE run_type='live' AND run_date=?) WHERE rn=1)
           SELECT t.panel_score, t.regime, t.active_scorer FROM ticker_daily_state t
           JOIN canonical c ON c.run_id=t.run_id WHERE t.panel_score IS NOT NULL""",
        (date,)).fetchall()
    scores = [r[0] for r in rows]
    n = len(scores)
    stats = {"date": date, "n_scored": n}
    if n:
        distinct = len(set(scores))
        mean = sum(scores) / n
        std = (sum((x - mean) ** 2 for x in scores) / n) ** 0.5
        # v1.1: the day's active scorer conditions the trailing baseline —
        # comparing a blend composite's scale to a rank-calibrated
        # predecessor's would alarm on every SANCTIONED scorer switch (the
        # live smoke found exactly this on the 08-04 blend cutover).
        day_scorer = rows[0][2] if rows else None
        if any(r[2] != day_scorer for r in rows):
            findings.append("mixed active_scorer within the canonical run")
        stats.update({"n_distinct": distinct, "cs_std": round(std, 6),
                      "active_scorer": day_scorer})
        if distinct < MIN_DISTINCT:
            findings.append(f"frozen-score alarm: only {distinct} distinct scores")
        trail = con.execute(
            """SELECT run_date, panel_score FROM (
                 SELECT p.run_date, t.panel_score, t.active_scorer,
                        ROW_NUMBER() OVER (PARTITION BY p.run_date ORDER BY p.created_at DESC, p.run_id DESC) rn
                 FROM ticker_daily_state t JOIN pipeline_runs p ON p.run_id=t.run_id
                 WHERE p.run_type='live' AND p.run_date < ? AND t.panel_score IS NOT NULL
                   AND t.active_scorer IS ?)
               WHERE rn>=1""", (date, day_scorer)).fetchall()
        by_day = {}
        for d, s in trail:
            by_day.setdefault(d, []).append(s)
        stds = []
        for d in sorted(by_day)[-TRAIL_DAYS:]:
            v = by_day[d]
            m = sum(v) / len(v)
            stds.append((sum((x - m) ** 2 for x in v) / len(v)) ** 0.5)
        if stds:
            med = sorted(stds)[len(stds) // 2]
            stats["trail_median_std"] = round(med, 6)
            stats["trail_days_same_scorer"] = len(stds)
            if med > 0 and not (STD_BAND[0] * med <= std <= STD_BAND[1] * med):
                findings.append(
                    f"distribution alarm: cs_std {std:.4f} outside "
                    f"[{STD_BAND[0]}, {STD_BAND[1]}] x trailing median {med:.4f} "
                    f"({len(stds)} same-scorer trailing days)")
        else:
            stats["trail_days_same_scorer"] = 0
            stats["note"] = "no same-scorer trailing days -- distribution layer skipped (first day after a scorer switch)"

    # LAYER 3: coverage
    if n < MIN_SCORED:
        findings.append(f"coverage alarm: {n} scored names < {MIN_SCORED}")
    null_regime = sum(1 for r in rows if r[1] is None or r[1] == "")
    if null_regime:
        findings.append(f"{null_regime} scored rows with NULL regime")
    con.close()
    return findings, stats


def main(argv):
    if len(argv) < 5:
        sys.exit("usage: serving_fidelity_probe.py <runs.db> <golden_config.json> "
                 "<artifacts_root> <YYYY-MM-DD> [--ledger out.jsonl]")
    db, golden, root, date = argv[1:5]
    ledger = None
    if "--ledger" in argv[5:]:
        ledger = argv[argv.index("--ledger") + 1]
    findings, stats = probe(db, golden, root, date)
    record = {"probe": "serving_fidelity_v1", "date": date,
              "status": "PASS" if not findings else "FAIL",
              "findings": findings, "stats": stats}
    out = json.dumps(record)
    print(out)
    if ledger:
        with open(ledger, "a") as f:
            f.write(out + "\n")
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
