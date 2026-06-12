#!/usr/bin/env python3
"""Cutoff-based staleness preflight (#106 §2.3 guard hole; #108 III.3).

model_staleness_days checks trained_date — but skill is governed by
effective_train_cutoff_date (a May training with a Nov-2024 cutoff fooled
it). This check answers the right question: how old is the newest data the
model has ever seen? Thresholds from the measured three-point decay curve
(-0.005/-0.058/-0.070 @ 11/18/24 months): WARN > 9 months, FAIL > 12.
Runs against the REAL prod sidecar.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

WARN_MONTHS, FAIL_MONTHS = 9, 12
PROD_SIDECAR = Path("/Users/renhao/git/github/RenQuant/artifacts/patchtst_shadow/"
                    "pt07_strict_trainfit_embargo60_20260522/seed_44/"
                    "hf_patchtst_all_seed44_model.pt.metadata.json")


def check(sidecar: Path, today: dt.date) -> tuple[str, str]:
    meta = json.loads(sidecar.read_text())
    cutoff = meta.get("effective_train_cutoff_date") or meta.get("trained_date")
    cutoff_d = dt.date.fromisoformat(str(cutoff)[:10])
    months = (today - cutoff_d).days / 30.44
    trained = str(meta.get("trained_date", "?"))[:10]
    msg = (f"cutoff={cutoff_d} ({months:.1f} months ago; trained_date={trained} "
           f"— the field the old guard wrongly checked)")
    if months > FAIL_MONTHS:
        return "FAIL", msg + f" > {FAIL_MONTHS}m: block buys, demand retrain"
    if months > WARN_MONTHS:
        return "WARN", msg + f" > {WARN_MONTHS}m: schedule fresh-cutoff retrain"
    return "OK", msg


if __name__ == "__main__":
    verdict, msg = check(PROD_SIDECAR, dt.date.today())
    print(f"[{verdict}] {msg}")
    # proofs: synthetic sidecars at the three measured decay points
    import tempfile
    for months, expect in ((8, "OK"), (10, "WARN"), (19, "FAIL")):
        p = Path(tempfile.mktemp(suffix=".json"))
        p.write_text(json.dumps({
            "effective_train_cutoff_date":
                (dt.date.today() - dt.timedelta(days=int(months * 30.44))).isoformat(),
            "trained_date": dt.date.today().isoformat()}))   # trained TODAY — old guard would pass all three
        v, _ = check(p, dt.date.today())
        assert v == expect, (months, v)
    print("proofs: 8m->OK, 10m->WARN, 19m->FAIL — all with trained_date=TODAY, "
          "which the old guard would have waved through ✓")
    sys.exit(0 if verdict != "FAIL" else 1)
