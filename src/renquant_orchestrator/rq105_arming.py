"""rq105 intraday-decisioning ARMING-FILE validator (fail-closed).

The session-scheduler wrapper's triple gate keeps shadow decisioning
default-OFF. Historically gate 2 (the ``RENQUANT_INTRADAY_DECISIONING`` env
flag) was armed by the operator EDITING the wrapper — which left the
activation living as an uncommitted working-tree edit in the run checkout,
where one recovery ``git checkout --`` (or a sync conflict, as on 2026-08-24
/ #1044) silently extinguishes it.

This module moves the ARMING STATE — not the default — into an
operator-owned runtime file OUTSIDE git, mirroring the existing kill-switch
(``data/rq105/intraday_decisioning.KILL``):

    data/rq105/intraday_decisioning.armed.json
    {"armed": true, "operator": "...", "armed_at": "YYYY-MM-DD...",
     "authority": "<the recorded authorization this arming enacts>"}

Contract:
  * The committed default remains OFF. Absent file = not armed.
  * A present-but-invalid file is NOT armed (fail-closed) and the reason is
    reported loudly — a malformed authorization must never read as consent.
  * Creating, editing, or removing the file is a recorded OPERATOR landing
    step. Agents never write it (LONG-ledger class: rq105 authorization
    files are operator-owned).
  * Disarm = delete the file or set ``"armed": false``; the kill-switch
    remains the mid-session halt, unchanged.

CLI: ``python3 -m renquant_orchestrator.rq105_arming <path>`` — exit 0 and
print one provenance line on stdout when armed; exit 1 with the reason on
stderr otherwise. The wrapper exports the env flag ONLY on exit 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ("operator", "armed_at", "authority")


def evaluate_arming_file(path: str | Path) -> tuple[bool, str]:
    """(armed, detail) for ``path``; every failure mode is (False, reason)."""
    p = Path(path)
    if not p.exists():
        return False, f"absent: {p}"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — any parse failure fails closed
        return False, f"unreadable ({type(exc).__name__}: {exc})"
    if not isinstance(payload, dict):
        return False, "not a JSON object"
    if payload.get("armed") is not True:
        return False, "armed is not literal true"
    missing = [f for f in REQUIRED_FIELDS
               if not str(payload.get(f) or "").strip()]
    if missing:
        return False, f"missing/empty required field(s): {', '.join(missing)}"
    return True, (
        f"operator={payload['operator']} armed_at={payload['armed_at']} "
        f"authority={payload['authority']}"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: rq105_arming <arming-file-path>", file=sys.stderr)
        return 2
    armed, detail = evaluate_arming_file(args[0])
    if armed:
        print(detail)
        return 0
    print(f"not armed — {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
