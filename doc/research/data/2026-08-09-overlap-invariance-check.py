"""Overlap-invariance check: extension build vs the FROZEN xgb_mom_60d corpus.

Claim under test (orch#939): the extension build (NaN-label tail kept,
features through the last OHLCV date) reproduces the frozen corpus on every
shared (date, ticker) row for all 70 frozen momentum features. If it does,
the extension window's feature rows are the same measurement process as the
corpus the v2 verdict ran on, and the 43-shared-day replay-vs-served
comparison (task #26) may use them. If it does not, the diff is quantified
per column — no silent pass.

Authorities:
* FEATS + corpus pin: ast-read from the committed harness
  renquant-model/doc/design/frozen/2026-08-09-xgbmom-v2-harness.py
  (the frozen text, nothing re-derived).
* Frozen corpus: RenQuant/data/alpha158_291_fundamental_dataset.parquet,
  sha256 asserted against the harness pin before any comparison.
Read-only on both inputs; the only write is the committed report
2026-08-09-overlap-invariance-report.json next to this script.
"""
import ast, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd

import sys
if len(sys.argv) != 4:
    sys.exit("usage: overlap_invariance_check.py <harness.py> <frozen.parquet> <extension.parquet>\n"
             "rewrites the committed 2026-08-09-overlap-invariance-report.json next to this script")
HARNESS, FROZEN, EXT = (Path(p) for p in sys.argv[1:4])
REPORT = Path(__file__).resolve().with_name("2026-08-09-overlap-invariance-report.json")


def harness_constants():
    tree = ast.parse(HARNESS.read_text())
    out = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in ("FEATS", "CORPUS_SHA256")):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    # CORPUS_SHA256 is assigned inside main() in the harness — ast.walk
    # reaches it regardless of nesting, but assert we actually got both.
    assert set(out) == {"FEATS", "CORPUS_SHA256"}, f"harness constants missing: {set(out)}"
    return out["FEATS"], out["CORPUS_SHA256"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    feats, pin = harness_constants()
    assert len(feats) == 70, f"expected 70 frozen features, harness has {len(feats)}"
    frozen_sha = sha256(FROZEN)
    assert frozen_sha == pin, f"frozen corpus sha {frozen_sha[:12]} != harness pin {pin[:12]}"

    cols = ["date", "ticker"] + feats + ["fwd_60d_excess"]
    fz = pd.read_parquet(FROZEN, columns=cols)
    ex = pd.read_parquet(EXT, columns=cols)
    for df in (fz, ex):
        df["date"] = pd.to_datetime(df["date"])

    m = fz.merge(ex, on=["date", "ticker"], how="inner", suffixes=("_f", "_e"))
    only_fz = len(fz) - len(m)
    only_ex_mask = ~ex.set_index(["date", "ticker"]).index.isin(
        fz.set_index(["date", "ticker"]).index)
    ext_new = ex[only_ex_mask]

    per_col, worst = {}, 0.0
    for c in feats + ["fwd_60d_excess"]:
        a = m[f"{c}_f"].to_numpy(dtype=float)
        b = m[f"{c}_e"].to_numpy(dtype=float)
        both_nan = np.isnan(a) & np.isnan(b)
        one_nan = np.isnan(a) ^ np.isnan(b)
        d = np.abs(a - b)
        d[both_nan] = 0.0
        maxd = float(np.nanmax(d)) if len(d) else 0.0
        per_col[c] = {"max_abs_diff": maxd, "n_nan_mismatch": int(one_nan.sum())}
        if c != "fwd_60d_excess":
            worst = max(worst, maxd if not np.isnan(maxd) else np.inf)

    nan_mismatch_feats = sum(v["n_nan_mismatch"] for k, v in per_col.items()
                             if k != "fwd_60d_excess")
    invariant = bool(worst <= 1e-9 and nan_mismatch_feats == 0)
    report = {
        "artifact_kind": "diagnostic",
        "frozen_sha256": frozen_sha,
        "frozen_rows": int(len(fz)), "ext_rows": int(len(ex)),
        "shared_rows": int(len(m)),
        "frozen_only_rows": int(only_fz),
        "ext_new_rows": int(len(ext_new)),
        "ext_new_dates": [str(ext_new.date.min())[:10] if len(ext_new) else None,
                          str(ext_new.date.max())[:10] if len(ext_new) else None],
        "ext_new_labelled": int(ext_new.fwd_60d_excess.notna().sum()),
        "worst_feature_abs_diff": worst,
        "n_feature_nan_mismatch": nan_mismatch_feats,
        "invariant_on_shared_rows": invariant,
        "worst_columns": sorted(
            ((k, v["max_abs_diff"]) for k, v in per_col.items() if k != "fwd_60d_excess"),
            key=lambda t: -(t[1] if t[1] == t[1] else float("inf")))[:8],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in (
        "shared_rows", "frozen_only_rows", "ext_new_rows", "ext_new_dates",
        "worst_feature_abs_diff", "n_feature_nan_mismatch",
        "invariant_on_shared_rows")}, indent=2))


if __name__ == "__main__":
    main()
