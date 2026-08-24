"""rq105 S3-P2: produce ``feature_snapshot_<date>.json`` from the served matrix.

THE MISSING PRODUCER (orch#1026 as amended by #1030). ``run_shadow_serving.sh``
has skipped every session since 2026-08-12 with ``SKIP not-wired: no producer
exists for feature_snapshot_<date>.json``. The daily features it needs have
been persisted all along by ``PersistServedMatrixTask`` (orch#703) as
``logs/served_matrix/<date>/<lane>__<run_id>.parquet`` + a JSON manifest —
this module is the missing BRIDGE from that artifact to the
:class:`~renquant_orchestrator.realtime_data_plane.FeatureSnapshot` contract.
It computes nothing: the features are the ones the prod scorer was actually
served, re-keyed and re-stamped.

CONTRACT VALIDATION IS THE REAL CLASS, NOT A MIRROR. The consumer lives in
this same repo, so the produced payload is round-tripped through
``FeatureSnapshot.from_mapping`` BEFORE it is written; an unwritable snapshot
therefore fails here, loudly, instead of at serving time. (The withdrawn
pipeline#297 attempt mirrored the contract by hand and got a key wrong —
``builder_version`` for ``feature_builder_version``; validating against the
class makes that mistake impossible.)

HONEST CUTOFF SEMANTICS (design amendment #1030): the served matrix is built
by the 13:55 ET run with that day's PARTIAL final bar. ``feature_cutoff``
therefore records the producing run's date, and ``feature_builder_version``
carries the vintage marker ``partial-bar-1355``, so no consumer can mistake
this for an EOD-frozen panel.

FAIL-CLOSED PROVENANCE, same discipline as orch#1028:
  * the source date must be the immediately preceding session within
    ``--max-gap-days`` (default 4: weekend + one holiday) — an older matrix
    silently standing in for yesterday's is exactly the staleness class the
    batch-score export already refuses;
  * exactly ONE prod-lane (``alpaca__``) pair may exist for that date;
  * ``schema_version`` must be the pinned ``served-matrix-1`` and ``lane``
    must be ``alpaca`` — drift in either means the producer's assumptions are
    stale, not that a row should be coerced.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from .realtime_data_plane import FeatureSnapshot

EXPECTED_SCHEMA = "served-matrix-1"
EXPECTED_LANE = "alpaca"
BUILDER_PREFIX = "served-matrix-bridge-v1+partial-bar-1355"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean(v: Any) -> Any:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f if math.isfinite(f) else None


def locate_source(root: Path, for_date: str, max_gap_days: int = 4) -> tuple[Path, Path]:
    """The prod-lane (parquet, manifest) pair for the session preceding ``for_date``."""
    if not root.is_dir():
        raise ProvenanceRefusal(f"served-matrix root missing: {root}")
    target = dt.date.fromisoformat(for_date)
    dated = sorted(d.name for d in root.iterdir()
                   if d.is_dir() and d.name < for_date)
    if not dated:
        raise ProvenanceRefusal(f"no served-matrix date directory before {for_date}")
    src = dated[-1]
    gap = (target - dt.date.fromisoformat(src)).days
    if gap > max_gap_days:
        raise ProvenanceRefusal(
            f"newest served matrix is {src}, {gap} calendar days "
            f"before {for_date} (max {max_gap_days}) — an older matrix must not "
            f"silently stand in for the prior session")
    pairs = sorted((root / src).glob(f"{EXPECTED_LANE}__*.parquet"))
    if len(pairs) != 1:
        raise ProvenanceRefusal(
            f"expected exactly one {EXPECTED_LANE}__*.parquet under "
            f"{root / src}, found {len(pairs)}: {[p.name for p in pairs]}")
    parquet = pairs[0]
    manifest = parquet.with_suffix(".json")
    if not manifest.is_file():
        raise ProvenanceRefusal(f"manifest missing beside {parquet.name}")
    return parquet, manifest


class ProvenanceRefusal(SystemExit):
    """An EXPECTED refusal: the source is absent, stale, ambiguous or internally
    inconsistent. Distinct from every other failure so the wrapper can map this
    — and only this — to the skippable status. An import error, a parquet
    decoder failure or a write failure reaching S3-P3 as "no input today" is a
    guard that fails closed inside the module and open at its boundary
    (codex review 2026-08-24)."""

    EXIT_CODE = 3

    def __init__(self, msg: str) -> None:
        super().__init__(f"PROVENANCE REFUSAL: {msg}")


def build_payload(matrix: pd.DataFrame, manifest: dict,
                  *, source_date: str | None = None,
                  source_run_id: str | None = None) -> dict:
    """Served matrix + manifest → the FeatureSnapshot payload (validated).

    ``source_date`` / ``source_run_id`` are the identity the CALLER derived from
    the path. They are cross-checked against the manifest rather than trusted
    alongside it: `locate_source` trusts the directory and filename while this
    function trusts the manifest, so without a comparison a copied or mismatched
    manifest could stamp a different cutoff or run into a snapshot sourced from
    another parquet and every individual check would still pass
    (codex review 2026-08-24). Each half was validated; the PAIR was not.
    """
    schema = manifest.get("schema_version")
    if schema != EXPECTED_SCHEMA:
        raise ProvenanceRefusal(f"schema_version {schema!r} != {EXPECTED_SCHEMA!r} "
                         f"— the bridge's assumptions are stale, not the data wrong")
    if manifest.get("lane") != EXPECTED_LANE:
        raise ProvenanceRefusal(f"lane {manifest.get('lane')!r} != {EXPECTED_LANE!r}")
    cols = list(manifest.get("feature_cols") or [])
    if not cols:
        raise ProvenanceRefusal("manifest carries no feature_cols")
    missing = [c for c in cols if c not in matrix.columns]
    if missing:
        raise ProvenanceRefusal(f"manifest feature_cols absent from parquet: "
                         f"{missing[:5]}{'…' if len(missing) > 5 else ''}")
    if "ticker" not in matrix.columns:
        raise ProvenanceRefusal("parquet has no 'ticker' column")

    # PATH IDENTITY vs MANIFEST IDENTITY — compare, do not merely trust both.
    m_date = str(manifest.get("as_of_date") or "").strip()
    if source_date is not None and m_date != source_date:
        raise ProvenanceRefusal(
            f"directory date {source_date!r} != manifest as_of_date {m_date!r} — "
            f"the manifest does not describe the parquet it sits beside")
    m_run = str(manifest.get("run_id") or "").strip()
    if source_run_id is not None and m_run != source_run_id:
        raise ProvenanceRefusal(
            f"filename run identity {source_run_id!r} != manifest run_id "
            f"{m_run!r} — mismatched manifest/parquet pair")

    # A dict comprehension over rows silently DROPS duplicates and admits an
    # empty ticker; both would produce a well-formed snapshot describing fewer
    # names than the matrix carried, with nothing recording the loss.
    tickers = [str(row["ticker"]).strip().upper() for _, row in matrix.iterrows()]
    blank = sum(1 for t in tickers if not t)
    if blank:
        raise ProvenanceRefusal(f"{blank} row(s) carry an empty ticker")
    dupes = sorted({t for t in tickers if tickers.count(t) > 1})
    if dupes:
        raise ProvenanceRefusal(
            f"duplicate tickers in the served matrix: {dupes[:5]}"
            f"{'…' if len(dupes) > 5 else ''} — a dict build would silently keep "
            f"only the last row for each")
    features = {
        str(row["ticker"]).strip().upper(): {c: _clean(row[c]) for c in cols}
        for _, row in matrix.iterrows()
    }
    payload = {
        "feature_cutoff": str(manifest["as_of_date"]),
        "feature_builder_version": f"{BUILDER_PREFIX}+{schema}+run:{manifest.get('run_id')}",
        "features": features,
    }
    FeatureSnapshot.from_mapping(payload)      # the REAL contract, same repo
    return payload


def write_snapshot(payload: dict, out_dir: Path, for_date: str,
                   source: tuple[Path, Path]) -> tuple[Path, Path]:
    parquet, manifest = source
    snap = FeatureSnapshot.from_mapping(payload)
    body = json.dumps(payload, sort_keys=True, allow_nan=False)
    meta = {
        "for_date": for_date,
        "feature_cutoff": snap.cutoff,
        "feature_builder_version": snap.builder_version,
        "feature_snapshot_digest": snap.digest,
        "n_tickers": len(snap.features),
        "source_parquet": {"path": str(parquet), "sha256": _sha(parquet)},
        "source_manifest": {"path": str(manifest), "sha256": _sha(manifest)},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"feature_snapshot_{for_date}.json"
    out_meta = out_dir / f"feature_snapshot_{for_date}.meta.json"
    for path, text in ((out, body), (out_meta, json.dumps(meta, sort_keys=True, indent=1))):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    return out, out_meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--served-matrix-root", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--date", default=None, help="session date (default: today)")
    ap.add_argument("--max-gap-days", type=int, default=4)
    a = ap.parse_args(argv)
    for_date = a.date or dt.date.today().isoformat()
    source = locate_source(Path(a.served_matrix_root), for_date, a.max_gap_days)
    # The identity the PATH asserts, handed to build_payload to be COMPARED
    # against the manifest rather than trusted in parallel with it.
    src_date = source[0].parent.name
    src_run = source[0].stem.split("__", 1)[1] if "__" in source[0].stem else None
    matrix = pd.read_parquet(source[0])
    manifest = json.loads(source[1].read_text(encoding="utf-8"))
    payload = build_payload(matrix, manifest,
                            source_date=src_date, source_run_id=src_run)
    out, out_meta = write_snapshot(payload, Path(a.out_dir), for_date, source)
    print(f"feature snapshot written: {out} "
          f"({len(payload['features'])} tickers, cutoff {payload['feature_cutoff']})")
    print(f"meta: {out_meta}")
    return 0


if __name__ == "__main__":
    # A provenance refusal exits with ITS OWN code so the wrapper can pass the
    # distinction through. Everything else — import errors, decoder failures,
    # write failures, programming errors — propagates unchanged and lands on a
    # different nonzero, so S3-P3 can never read implementation breakage as
    # "no input today" (codex review 2026-08-24).
    try:
        raise SystemExit(main())
    except ProvenanceRefusal as refusal:
        print(refusal, file=sys.stderr)
        raise SystemExit(ProvenanceRefusal.EXIT_CODE) from None
