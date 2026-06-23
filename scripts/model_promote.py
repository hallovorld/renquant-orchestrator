#!/usr/bin/env python3
"""Verified, atomic, reversible model promote — the deploy half of the #172 check.

Replaces the 2026-06-23 six-step manual pin/restamp dance with one operation that refuses
unless the candidate bundle is self-consistent (the merged bundle-consistency check), then
atomically swaps the umbrella pin with a saved rollback record.

Subcommands:
  stamp    make a candidate {scorer, calibrator, config} self-consistent into an out dir
           (config-fingerprint + watchlist + calibrator<->scorer fingerprint). Refuses if the
           scorer has no real wf_gate_metadata.
  verify   run the #172 self-consistency check; exit 0 iff deploy_ready.
  promote  verify, then (unless --dry-run) atomically swap a subrepo pin; writes a rollback file.
  rollback restore a pin from a rollback file.

Defaults target the pinned 104 strategy config + the umbrella lock. Promote is DRY-RUN by
default; pass --apply to actually swap the pin. Run inside the strategy venv (uses the live
fingerprint authorities) unless you inject test doubles in code.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from renquant_orchestrator import model_bundle as mb  # noqa: E402

REPO = Path("/Users/renhao/git/github/RenQuant")
DEFAULT_CONFIG = REPO / ".subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json"
DEFAULT_STRATEGY_DIR = REPO / "backtesting/renquant_104"
DEFAULT_LOCK = REPO / "subrepos.lock.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("stamp", help="make a candidate bundle self-consistent")
    sp.add_argument("--scorer", required=True)
    sp.add_argument("--calibrator", default=None)
    sp.add_argument("--config", default=str(DEFAULT_CONFIG))
    sp.add_argument("--out-dir", required=True)

    vp = sub.add_parser("verify", help="run the #172 self-consistency check")
    vp.add_argument("--config", default=str(DEFAULT_CONFIG))
    vp.add_argument("--strategy-dir", default=str(DEFAULT_STRATEGY_DIR))

    pp = sub.add_parser("promote", help="verified, atomic, reversible pin swap")
    pp.add_argument("--config", default=str(DEFAULT_CONFIG))
    pp.add_argument("--strategy-dir", default=str(DEFAULT_STRATEGY_DIR))
    pp.add_argument("--lock", default=str(DEFAULT_LOCK))
    pp.add_argument("--subrepo", default="renquant-strategy-104")
    pp.add_argument("--commit", required=True, help="new pinned commit SHA")
    pp.add_argument("--apply", action="store_true", help="actually swap the pin (default dry-run)")

    rp = sub.add_parser("rollback", help="restore a pin from a rollback file")
    rp.add_argument("--rollback-file", required=True)

    a = ap.parse_args()

    if a.cmd == "stamp":
        res = mb.stamp_bundle(Path(a.scorer), Path(a.calibrator) if a.calibrator else None,
                              Path(a.config), out_dir=Path(a.out_dir))
        print(json.dumps({"scorer": str(res.scorer_path), "calibrator": str(res.calibrator_path),
                          "config_fingerprint": res.config_fingerprint,
                          "scorer_fingerprint": res.scorer_fingerprint,
                          "watchlist_size": res.watchlist_size}, indent=2))
        return 0

    if a.cmd == "verify":
        res = mb.verify_bundle(Path(a.config), Path(a.strategy_dir))
        print(f"deploy_ready={res['deploy_ready']}")
        for c in res["checks"]:
            print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['contract']:24} {c['detail']}")
        return 0 if res["deploy_ready"] else 1

    if a.cmd == "promote":
        res = mb.promote(Path(a.config), Path(a.strategy_dir), Path(a.lock),
                         a.subrepo, a.commit, dry_run=not a.apply)
        print(json.dumps({k: v for k, v in res.items() if k != "verify"}, indent=2))
        if not res.get("promoted") and not res.get("dry_run"):
            print("REFUSED — bundle not deploy_ready; run `verify` for the failing contract(s).",
                  file=sys.stderr)
            return 1
        return 0

    if a.cmd == "rollback":
        restored = mb.rollback_pin(Path(a.rollback_file))
        print(f"restored pin -> {restored}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
