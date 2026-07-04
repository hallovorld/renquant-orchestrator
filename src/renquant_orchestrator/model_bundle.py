"""Self-consistent model-bundle stamping + atomic, reversible, verified promote.

The 2026-06-23 XGB deploy was a 6-step manual pin/restamp dance that hit FOUR
consistency contracts one-by-one in production (WF-gate metadata, calibrator/scorer
fingerprint, config fingerprint, watchlist). PR #172 added the offline *check*
(`scripts/check_model_bundle_consistency.py`). This module is the other half:

- ``stamp_bundle`` — make a candidate ``{scorer, calibrator, config}`` mutually consistent
  on the three MECHANICAL contracts (config-fingerprint, watchlist, calibrator↔scorer
  fingerprint) so the #172 check passes by construction. It deliberately does **not**
  fabricate WF-gate metadata (that must be a real walk-forward result): it preserves any
  existing ``wf_gate_metadata`` and refuses to stamp if it is absent/incomplete.
- ``verify_bundle`` — run the #172 check and return ``deploy_ready`` + per-contract results.
- ``atomic_set_pin`` / ``rollback_pin`` — swap a single subrepo pin in the umbrella lock with
  a temp-file + ``os.replace`` (atomic) and a saved rollback record.
- ``promote`` — refuse unless the bundle is ``deploy_ready``, then atomically swap the pin and
  write a rollback record. ``dry_run`` by default.

It performs NO broker mutation and never writes a live production artifact path unless an
explicit ``out_dir`` is given. The fingerprint authorities are injectable so the unit tests
run without the strategy venv (same convention as the #172 check).
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_CHECK_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_model_bundle_consistency.py"


def _load_check():
    spec = importlib.util.spec_from_file_location("bundlecheck", _CHECK_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _finite(v) -> bool:
    try:
        f = float(v)
        return f == f and f not in (float("inf"), float("-inf"))
    except Exception:
        return False


def _active_panel(config: dict) -> dict:
    return (config.get("ranking", {}).get("panel_scoring", {}) or config.get("panel_ltr", {}) or {})


class BundleError(RuntimeError):
    """Raised when a bundle cannot be made self-consistent honestly."""


@dataclass(frozen=True)
class StampResult:
    scorer_path: Path
    calibrator_path: Optional[Path]
    config_fingerprint: str
    scorer_fingerprint: Optional[str]
    watchlist_size: int


def _default_fingerprint_config() -> Callable[[dict], str]:
    from renquant_common.config_consistency import fingerprint_config  # noqa: PLC0415
    return fingerprint_config


def _default_model_content_sha256() -> Callable[[dict], str]:
    from renquant_common.model_fingerprint import model_content_sha256  # noqa: PLC0415
    return model_content_sha256


def stamp_bundle(
    scorer_path: Path,
    calibrator_path: Optional[Path],
    config_path: Path,
    *,
    out_dir: Path,
    fingerprint_config: Optional[Callable[[dict], str]] = None,
    model_content_sha256: Optional[Callable[[dict], str]] = None,
) -> StampResult:
    """Write a self-consistent copy of the bundle into ``out_dir``.

    Fixes the three mechanical contracts so the #172 check passes by construction:
      (config_fingerprint, watchlist) on the scorer artifact, and the
      calibrator's ``scorer_model_content_fingerprint``.

    Refuses (``BundleError``) if the scorer has no complete ``wf_gate_metadata`` — WF results
    are real measurements and must not be fabricated here.
    """
    fingerprint_config = fingerprint_config or _default_fingerprint_config()
    model_content_sha256 = model_content_sha256 or _default_model_content_sha256()

    config = json.loads(Path(config_path).read_text())
    scorer = json.loads(Path(scorer_path).read_text())

    wf = ((scorer.get("metadata") or {}).get("wf_gate_metadata")) or scorer.get("wf_gate_metadata") or {}
    req = ["wf_3cut_sharpe_mean", "spy_sharpe_mean", "strategy_minus_spy_sharpe_mean"]
    if not (wf.get("passed") is True and all(_finite(wf.get(k)) for k in req) and "n_cuts_beat_spy_sharpe" in wf):
        raise BundleError(
            "scorer has no complete wf_gate_metadata (passed + finite numerics + n_cuts_beat_spy_sharpe); "
            "cannot stamp a deploy-ready bundle without a real walk-forward result"
        )

    # (config fingerprint + watchlist) on the scorer
    scorer["config_fingerprint"] = fingerprint_config(config)
    scorer.setdefault("config_fingerprint_fields", {})["watchlist"] = list(config.get("watchlist", []))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_scorer = out_dir / Path(scorer_path).name
    out_scorer.write_text(json.dumps(scorer, indent=2))

    out_cal: Optional[Path] = None
    scorer_fp: Optional[str] = None
    panel = _active_panel(config)
    gc = panel.get("global_calibration", {}) or {}
    if calibrator_path is not None and gc.get("enabled"):
        cal = json.loads(Path(calibrator_path).read_text())
        scorer_fp = model_content_sha256(scorer)
        cal.setdefault("metadata", {})["scorer_model_content_fingerprint"] = scorer_fp
        out_cal = out_dir / Path(calibrator_path).name
        out_cal.write_text(json.dumps(cal, indent=2))

    return StampResult(
        scorer_path=out_scorer,
        calibrator_path=out_cal,
        config_fingerprint=scorer["config_fingerprint"],
        scorer_fingerprint=scorer_fp,
        watchlist_size=len(scorer["config_fingerprint_fields"]["watchlist"]),
    )


def verify_bundle(
    config_path: Path,
    strategy_dir: Path,
    *,
    fingerprint_config: Optional[Callable[[dict], str]] = None,
    model_content_sha256: Optional[Callable[[dict], str]] = None,
) -> dict:
    """Run the merged #172 self-consistency check; returns its result dict (with deploy_ready)."""
    check = _load_check()
    return check.check_bundle(
        Path(config_path), Path(strategy_dir),
        fingerprint_config=fingerprint_config,
        model_content_sha256=model_content_sha256,
    )


def _read_lock(lock_path: Path) -> dict:
    return json.loads(Path(lock_path).read_text())


def _atomic_write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{int(time.time()*1000)}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(tmp, path)  # atomic on POSIX


def _find_subrepo(lock: dict, subrepo_name: str) -> dict:
    for entry in lock.get("subrepos") or []:
        if entry.get("name") == subrepo_name:
            return entry
    raise BundleError(f"subrepo {subrepo_name!r} not found in lock")


def atomic_set_pin(
    lock_path: Path,
    subrepo_name: str,
    new_commit: str,
    *,
    rollback_dir: Optional[Path] = None,
) -> Path:
    """Atomically set ``subrepos[name].commit = new_commit`` and write a rollback record.

    Returns the path to the rollback record (feed it to ``rollback_pin``).
    """
    lock_path = Path(lock_path)
    lock = _read_lock(lock_path)
    entry = _find_subrepo(lock, subrepo_name)
    old_commit = entry.get("commit")
    if old_commit == new_commit:
        raise BundleError(f"{subrepo_name} pin already at {new_commit}")
    record = {
        "lock_path": str(lock_path),
        "subrepo": subrepo_name,
        "old_commit": old_commit,
        "new_commit": new_commit,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    rollback_dir = Path(rollback_dir or lock_path.parent)
    rollback_dir.mkdir(parents=True, exist_ok=True)
    rollback_path = rollback_dir / f".pin-rollback.{subrepo_name}.{int(time.time())}.json"
    rollback_path.write_text(json.dumps(record, indent=2) + "\n")

    entry["commit"] = new_commit
    _atomic_write_json(lock_path, lock)
    return rollback_path


def rollback_pin(rollback_path: Path) -> str:
    """Restore the pin recorded in ``rollback_path``; returns the restored commit."""
    record = json.loads(Path(rollback_path).read_text())
    lock_path = Path(record["lock_path"])
    lock = _read_lock(lock_path)
    entry = _find_subrepo(lock, record["subrepo"])
    entry["commit"] = record["old_commit"]
    _atomic_write_json(lock_path, lock)
    return record["old_commit"]


def promote(
    config_path: Path,
    strategy_dir: Path,
    lock_path: Path,
    subrepo_name: str,
    new_commit: str,
    *,
    dry_run: bool = True,
    fingerprint_config: Optional[Callable[[dict], str]] = None,
    model_content_sha256: Optional[Callable[[dict], str]] = None,
) -> dict:
    """Verified, atomic, reversible promote.

    Refuses unless the candidate bundle is ``deploy_ready`` (the #172 check). On a real run
    (``dry_run=False``) it atomically swaps the pin and returns a ``rollback_path``.
    """
    res = verify_bundle(
        config_path, strategy_dir,
        fingerprint_config=fingerprint_config,
        model_content_sha256=model_content_sha256,
    )
    if not res.get("deploy_ready"):
        return {"promoted": False, "reason": "bundle not deploy_ready", "verify": res}
    if dry_run:
        return {"promoted": False, "dry_run": True, "would_set": {subrepo_name: new_commit}, "verify": res}
    rollback_path = atomic_set_pin(lock_path, subrepo_name, new_commit)
    return {"promoted": True, "subrepo": subrepo_name, "new_commit": new_commit,
            "rollback_path": str(rollback_path), "verify": res}
