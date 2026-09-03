"""A4-T1 candidate exception — the orchestrator-owned governance step.

RFC#210 Amendment A4-T1 (renquant-backtesting ``wf_gate/freshness_fallback``)
lets ONE specific staging artifact — run ``20260831T141820Z``, full-artifact
digest ``760912ec…4af1e`` — be fallback-promoted although it carries five
substance failure classes. Backtesting IDENTIFIES that candidate and
VALIDATES the consumption proof it is handed; this module is the ONLY
producer of such proofs and owns everything backtesting must not:

* the **authorization record** — ``ops/governance/a4t1/<run_id>.authorization.json``,
  committed and reviewed in this repo, cross-checked on every use against the
  constants pinned in backtesting (a record and a pin that disagree = REFUSE);
* the **ledger** — ``<data_root>/logs/weekly_wf_promote/a4t1_ledger/``, next
  to the promote verdicts the umbrella already writes. ``data_root`` is
  :func:`renquant_orchestrator.runtime_paths.default_data_root`
  (``RENQUANT_DATA_ROOT`` or the umbrella runtime root): the same durable
  operator state root every other orchestrator job writes to and that
  ``com.renquant.backup`` backs up. This is a single-host deployment; host
  ownership IS the data root. The v11 ``~/.renquant`` location is gone;
* **atomic single consumption** — an ``O_CREAT|O_EXCL`` marker keyed by the
  exception id, written BEFORE ``stamp()`` and flipped to ``stamped: true``
  only after the artifact was rewritten. A second attempt anywhere on the
  host — another directory, another process, a racing thread — sees the
  marker and is refused. A corrupt marker still counts as consumed.

The one operation this module exposes is :func:`promote_candidate`
(identify → validate against the record → atomic consume → stamp). There is
no free-form ``consume()``, no caller-supplied ledger/authorization/proof
path: every substitution surface the reviews rejected is absent by
construction. Production reaches it through ``renquant_orchestrator
a4t1-promote`` (``cli.py``) and the wrapper
``ops/renquant104/a4t1_promote_staged.sh`` that the umbrella
``weekly_wf_promote.sh --promote-staged`` branch calls.

Fail-closed everywhere: any refusal returns ``{"status": "REFUSED",
"refused_on": <reason>, ...}`` and leaves the artifact untouched; a stamp
that fails AFTER consumption leaves the marker in place (``stamped: false``)
so the exception cannot be retried by accident — that state is the operator's
to inspect.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from .runtime_paths import default_data_root

try:
    from renquant_backtesting.wf_gate import freshness_fallback as FF
except ImportError as exc:  # pragma: no cover — environment defect
    raise ImportError(
        "renquant_backtesting.wf_gate.freshness_fallback is required "
        "(renquant-backtesting#128 / A4-T1 v13)") from exc
if not all(hasattr(FF, n) for n in (
        "A4T1_PROOF_SCHEMA", "A4T1_PROOF_FIELDS", "A4T1_CONSUMER",
        "a4t1_receipt_id", "validate_a4t1_proof", "decide", "stamp")):
    raise ImportError(
        "renquant-backtesting on the path predates A4-T1 v13 "
        "(renquant-backtesting#128): the proof contract is missing — "
        "refusing to run against an older pin")

AUTHORIZATION_SCHEMA = "a4t1_authorization.v1"
#: Committed, reviewed authorization records live here (repo-relative).
AUTHORIZATION_DIR = (
    Path(__file__).resolve().parents[2] / "ops" / "governance" / "a4t1")
#: Ledger location under the operator data root.
LEDGER_SUBDIR = ("logs", "weekly_wf_promote", "a4t1_ledger")

_RUN_ID_FORMAT = re.compile(r"^\d{8}T\d{6}Z$")
_STAGING_RUN_ID_RE = re.compile(r"weekly_(\d{8}T\d{6}Z)\.staging\.json$")
_REQUIRED_RECORD_KEYS = (
    "exception_id", "run_id", "artifact_digest", "authority", "temporal_bounds",
)


class A4T1Refused(Exception):
    """A governed refusal. ``refused_on`` is the machine-readable reason."""

    def __init__(self, refused_on: str, why: str, **extra: Any) -> None:
        super().__init__(f"{refused_on}: {why}")
        self.refused_on = refused_on
        self.why = why
        self.extra = extra


def ledger_dir() -> Path:
    return default_data_root().joinpath(*LEDGER_SUBDIR)


def marker_path(exception_id: str) -> Path:
    return ledger_dir() / f"{exception_id}.consumed.json"


def is_consumed(run_id: str) -> bool:
    """Fail-closed: a marker that exists — readable or not — is consumed."""
    return marker_path(f"a4t1_{run_id}").exists()


def load_authorization(run_id: str) -> dict[str, Any]:
    """Read the committed record for ``run_id`` and cross-check it against
    the constants backtesting pins. Any disagreement is a refusal: the two
    repos must name the same exception, digest and authority."""
    if not _RUN_ID_FORMAT.match(run_id):
        raise A4T1Refused("run_id_format", f"{run_id!r} is not YYYYMMDDTHHMMSSZ")
    path = AUTHORIZATION_DIR / f"{run_id}.authorization.json"
    if not path.is_file():
        raise A4T1Refused("authorization_record_missing", str(path))
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise A4T1Refused("authorization_record_unreadable", f"{path}: {exc}")
    if not isinstance(rec, dict) or rec.get("schema") != AUTHORIZATION_SCHEMA:
        raise A4T1Refused(
            "authorization_record_schema",
            f"{path}: schema {getattr(rec, 'get', lambda k: None)('schema')!r}"
            f" != {AUTHORIZATION_SCHEMA!r}")
    missing = [k for k in _REQUIRED_RECORD_KEYS if k not in rec]
    if missing:
        raise A4T1Refused("authorization_record_schema", f"missing keys {missing}")
    if rec["run_id"] != run_id or rec["exception_id"] != f"a4t1_{run_id}":
        raise A4T1Refused(
            "authorization_record_mismatch",
            f"record names run_id {rec['run_id']!r} / exception_id "
            f"{rec['exception_id']!r}; asked for {run_id!r}")
    for key, pinned in (
            ("run_id", FF._A4T1_CANDIDATE_RUN_ID),
            ("artifact_digest", FF._A4T1_CANDIDATE_ARTIFACT_DIGEST),
            ("authority", FF._A4T1_CANDIDATE_AUTHORITY)):
        if rec[key] != pinned:
            raise A4T1Refused(
                "authorization_record_mismatch",
                f"{key}: record {rec[key]!r} != backtesting pin {pinned!r}")
    tb = rec["temporal_bounds"]
    try:
        lo, hi = (dt.date.fromisoformat(x) for x in tb)
    except (TypeError, ValueError):
        raise A4T1Refused("authorization_record_schema",
                          f"temporal_bounds {tb!r} is not [YYYY-MM-DD, YYYY-MM-DD]")
    if lo > hi:
        raise A4T1Refused("authorization_record_schema",
                          f"temporal_bounds {tb!r} is reversed")
    return rec


def _read_marker(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _atomic_write(path: Path, obj: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _promote(prod_path: Path, staging_path: Path, as_of: dt.date) -> dict[str, Any]:
    prod_path, staging_path = Path(prod_path), Path(staging_path)
    auth = load_authorization(FF._A4T1_CANDIDATE_RUN_ID)
    lo, hi = (dt.date.fromisoformat(x) for x in auth["temporal_bounds"])
    if not lo <= as_of <= hi:
        raise A4T1Refused("temporal_bounds", f"as_of {as_of} outside [{lo}, {hi}]")
    m = _STAGING_RUN_ID_RE.search(staging_path.name)
    if not m or m.group(1) != auth["run_id"]:
        raise A4T1Refused(
            "run_id_mismatch",
            f"staging file {staging_path.name!r} does not carry run_id {auth['run_id']}")
    try:
        staging_obj = json.loads(staging_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise A4T1Refused("staging_unreadable", f"{staging_path}: {exc}")
    digest = FF._artifact_digest(staging_obj)
    if digest != auth["artifact_digest"]:
        raise A4T1Refused(
            "artifact_digest_mismatch",
            f"staging digest {digest} != authorized {auth['artifact_digest']}")

    verdict = FF.decide(prod_path, staging_path, as_of)
    if verdict.get("decision") != "FALLBACK_PROMOTE":
        raise A4T1Refused(
            "verdict_refused",
            f"backtesting verdict {verdict.get('decision')!r} "
            f"(refused_on={verdict.get('refused_on')!r})", verdict=verdict)
    if (verdict.get("a4t1_candidate_run_id") != auth["run_id"]
            or verdict.get("a4t1_candidate_artifact_digest") != auth["artifact_digest"]
            or verdict.get("a4t1_candidate_authority") != auth["authority"]):
        raise A4T1Refused(
            "verdict_not_candidate_exception",
            "the verdict is a FALLBACK_PROMOTE but not the authorized "
            "candidate exception — this operation promotes nothing else",
            verdict=verdict)

    exception_id = auth["exception_id"]
    ldir = ledger_dir()
    ldir.mkdir(parents=True, exist_ok=True)
    marker = ldir / f"{exception_id}.consumed.json"
    proof: dict[str, Any] = {
        "schema": FF.A4T1_PROOF_SCHEMA,
        "exception_id": exception_id,
        "run_id": auth["run_id"],
        "artifact_digest": auth["artifact_digest"],
        "authority": auth["authority"],
        "consumed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "consumed_by": FF.A4T1_CONSUMER,
        "ledger_path": str(marker),
    }
    proof["receipt_id"] = FF.a4t1_receipt_id(proof)
    # A defect in the proof we build must surface HERE, before the exception
    # is burned — not as a stamp failure after consumption.
    FF.validate_a4t1_proof(proof, verdict)

    record = {
        "proof": proof, "stamped": False,
        "staging_path": str(staging_path), "prod_path": str(prod_path),
        "as_of": as_of.isoformat(), "verdict": verdict,
    }
    try:
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        prior = _read_marker(marker)
        prior_receipt = None
        if prior and isinstance(prior.get("proof"), dict):
            prior_receipt = prior["proof"].get("receipt_id")
        raise A4T1Refused(
            "already_consumed", f"ledger marker exists: {marker}",
            marker_path=str(marker), prior_receipt_id=prior_receipt,
            prior_stamped=(prior or {}).get("stamped"))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.flush()
        os.fsync(fh.fileno())

    try:
        FF.stamp(staging_path, verdict, a4t1_consumption_proof=proof)
    except Exception as exc:  # noqa: BLE001 — consumed but not stamped: operator state
        return {
            "status": "REFUSED", "refused_on": "stamp_failed",
            "why": f"{type(exc).__name__}: {exc}",
            "marker_path": str(marker), "proof": proof,
        }
    record["stamped"] = True
    record["stamped_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _atomic_write(marker, record)
    return {"status": "PROMOTED", "verdict": verdict, "proof": proof,
            "marker_path": str(marker)}


def promote_candidate(prod_path: Path, staging_path: Path,
                      as_of: dt.date) -> dict[str, Any]:
    """The narrow operation: identify → validate against the committed
    record → atomic consume → stamp. Never raises for a governed refusal;
    returns ``{"status": "PROMOTED" | "REFUSED", ...}``."""
    try:
        return _promote(prod_path, staging_path, as_of)
    except A4T1Refused as exc:
        return {"status": "REFUSED", "refused_on": exc.refused_on,
                "why": exc.why, **exc.extra}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="A4-T1 candidate exception: identify -> atomic consume -> "
                    "stamp. Exit 0 iff PROMOTED.")
    ap.add_argument("--prod", required=True, type=Path)
    ap.add_argument("--staging", required=True, type=Path)
    ap.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
    args = ap.parse_args(argv)
    as_of = (dt.date.fromisoformat(args.as_of) if args.as_of
             else dt.date.today())
    result = promote_candidate(args.prod, args.staging, as_of)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("status") == "PROMOTED" else 1


if __name__ == "__main__":
    sys.exit(main())
