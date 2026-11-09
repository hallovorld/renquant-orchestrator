#!/usr/bin/env python3
"""Battery guard: page BEFORE the Mac hibernates and takes the whole trading stack with it.

2026-09-11 and 2026-10-27 the operator machine ran out of battery on a weekday (Low Power Sleep ->
hibernate) and every launchd job — daily 104, intraday, the rq105 chain — stayed dark for 20 h and
5 days respectively; the first signal was the NEXT successful run. A powered-off machine cannot
alarm, so the only place to catch it is while it is still on: this runs every 15 minutes and sends
one ntfy page when the machine is DISCHARGING at or below a threshold.

Read-only: parses ``pmset -g batt``, writes only a tiny state file so one discharge episode pages once
per band (not every 15 minutes).  Unparseable pmset output is itself a finding (fail loud, not silent).

Exit: 0 fine / paged-and-recorded, 1 unreadable battery state.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liveness_common import alert  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
STATE = Path(os.environ.get("RQ_BATTERY_STATE", os.path.expanduser("~/.renquant/battery_guard.json")))
#: Page at the first of these bands crossed while discharging; re-page only on a LOWER band.
BANDS = (40, 25, 15)

_PCT = re.compile(r"(\d{1,3})%;\s*([A-Za-z ]+);")


def parse(pmset_out: str):
    """-> (percent, state) with state in {'discharging','charging','charged','ac attached','finishing charge'},
    or None when the output has no battery line."""
    m = _PCT.search(pmset_out)
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip().lower()


def band_for(percent: int):
    """Lowest band the percentage is at or under, else None."""
    hit = [b for b in BANDS if percent <= b]
    return min(hit) if hit else None


def decide(percent: int, state: str, last_band):
    """-> (should_page, new_last_band).  Charging/charged resets the episode."""
    if state != "discharging":
        return False, None
    b = band_for(percent)
    if b is None:
        return False, None
    if last_band is not None and b >= last_band:
        return False, last_band
    return True, b


def _read_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _write_state(d: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d))


def main(pmset_out: str | None = None) -> int:
    if pmset_out is None:
        try:
            pmset_out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            pmset_out = ""
            print(f"battery_guard: pmset failed: {exc}", file=sys.stderr)
    parsed = parse(pmset_out)
    if parsed is None:
        # A desktop with no battery is not this machine; but an unreadable laptop must not look healthy.
        alert("RenQuant battery guard UNREADABLE", f"could not parse `pmset -g batt`: {pmset_out[:200]!r}", rq_root=RQ)
        return 1
    percent, state = parsed
    st = _read_state()
    page, new_band = decide(percent, state, st.get("band"))
    if page:
        alert(
            f"RenQuant LOW BATTERY {percent}% — plug in NOW",
            f"Mac is {state} at {percent}% (band <= {new_band}%). At ~0% it hibernates and daily 104 / intraday / "
            "the rq105 chain stay dark until the charger is back (2026-09-11: 20 h, 2026-10-27: 5 days). "
            "Nothing else will warn you: a powered-off machine cannot alarm.",
            rq_root=RQ,
        )
    if new_band != st.get("band"):
        _write_state({"band": new_band, "percent": percent, "state": state})
    print(f"battery_guard: {percent}% {state} band={new_band} paged={page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
