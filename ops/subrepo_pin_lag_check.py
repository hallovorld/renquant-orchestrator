#!/usr/bin/env python3
"""How far behind is each PIN? (GOAL-5)

**The gap this fills.** `run_surface_drift_check.py` already checks the runtime
subrepo checkouts — but against **`subrepos.lock.json`'s pinned commit**, i.e. it
answers *"does the runtime match what we pinned"*. The neighbouring check in the
same file compares `orchestrator-run` against its fetched **`origin/main`**, which
answers *"is it current"*. **Two surfaces, two different baselines**, and the
weaker one reads exactly like the stronger one in the log.

So a pin that has not moved in months passes clean forever, and every fix merged
behind it is invisible on the run path.

**Measured 2026-07-30**, after a day in which four separate fixes were merged and
none reached the running code:

    renquant-model         240 commits behind its own origin/main
    renquant-orchestrator  213
    renquant-backtesting    50
    renquant-artifacts      38
    renquant-pipeline       34
    renquant-base-data      20
    renquant-execution      15
    renquant-common          5
    renquant-strategy-104    2

That is the difference between "merged" and "running", as a number, per repo.

**Read-only, and it never touches the live tree.** It reads `subrepos.lock.json`
(a file), then measures the lag inside the DEVELOPMENT checkout of each subrepo —
never inside `RenQuant/`, where running `git` is forbidden on this programme.

**A pin being behind is NOT automatically wrong.** Pins are deliberate: the
artifacts pin is frozen at a canonical snapshot by standing decision. The point is
that the distance should be a number somebody chose, not a number nobody has seen.
`--max-lag` is therefore an ALARM threshold, not a policy.

    python ops/subrepo_pin_lag_check.py --max-lag 50
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

UMBRELLA = Path("/Users/renhao/git/github/RenQuant")
GITHUB = Path("/Users/renhao/git/github")
LOCK = UMBRELLA / "subrepos.lock.json"

EXIT_OK, EXIT_LAG, EXIT_UNUSABLE = 0, 1, 2

STATUS_MEASURED, STATUS_NO_CHECKOUT, STATUS_UNKNOWN_PIN = (
    "measured", "no-dev-checkout", "pin-not-in-repo")
#: The pin is NOT an ancestor of origin/main. `rev-list pin..origin/main` still
#: returns a number there, and that number is not a "behind count" — it silently
#: hides a non-fast-forward state. Codex on #653.
STATUS_DIVERGED = "diverged"
#: A lock entry missing `name` or `commit`. The first version DROPPED these, which
#: shrinks the denominator while still reporting success — a malformed lock could
#: quietly reduce the population being checked. Never dropped now.
STATUS_MALFORMED = "malformed-lock-entry"


def _git(cwd: Path, *args: str, timeout: int = 180):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, timeout=timeout)


def measure(name: str, pin: str, github: Path = GITHUB) -> dict:
    dev = github / name
    if not (dev / ".git").is_dir():
        return {"subrepo": name, "pin": pin, "status": STATUS_NO_CHECKOUT,
                "behind": None,
                "detail": f"no development checkout at {dev} — lag unmeasurable"}
    fetched = _git(dev, "fetch", "-q", "origin")
    if fetched.returncode != 0:
        return {"subrepo": name, "pin": pin, "status": STATUS_UNKNOWN_PIN,
                "behind": None,
                "detail": ("fetch failed; refusing to measure against a possibly "
                           f"stale origin/main: {fetched.stderr.strip()[:120]}")}
    # ANCESTRY FIRST. A behind-count only means "behind" when the pin is on the
    # first-parent history of origin/main. Ask git directly rather than inferring it
    # from a count that is defined for divergent pairs too.
    anc = _git(dev, "merge-base", "--is-ancestor", pin, "origin/main")
    if anc.returncode not in (0, 1):
        return {"subrepo": name, "pin": pin, "status": STATUS_UNKNOWN_PIN,
                "behind": None,
                "detail": f"pin {pin[:12]} not reachable in {name}: "
                          f"{(anc.stderr or '').strip()[:120]}"}
    if anc.returncode == 1:
        lr = _git(dev, "rev-list", "--left-right", "--count",
                  f"{pin}...origin/main")
        pair = lr.stdout.split() if lr.returncode == 0 else ["?", "?"]
        return {"subrepo": name, "pin": pin, "status": STATUS_DIVERGED,
                "behind": None,
                "detail": (f"pin is NOT an ancestor of origin/main "
                           f"(pin-only {pair[0]}, main-only {pair[1]}) — a behind "
                           f"count would hide a non-fast-forward state")}
    r = _git(dev, "rev-list", "--count", f"{pin}..origin/main")
    if r.returncode != 0:
        return {"subrepo": name, "pin": pin, "status": STATUS_UNKNOWN_PIN,
                "behind": None,
                "detail": f"count failed for {name}: {r.stderr.strip()[:120]}"}
    return {"subrepo": name, "pin": pin, "status": STATUS_MEASURED,
            "behind": int(r.stdout.strip() or 0), "detail": ""}


def scan(lock: Path = LOCK, github: Path = GITHUB) -> dict:
    entries = json.loads(lock.read_text()).get("subrepos", [])
    if not entries:
        raise ValueError(f"{lock} lists no subrepos — nothing would be checked")
    rows = []
    for e in entries:
        n, c = e.get("name"), e.get("commit")
        if not n or not c:
            # NEVER dropped: a silently shrunk denominator is the failure mode
            # this whole tool exists to expose, one level up.
            rows.append({"subrepo": n or "<no name>", "pin": c or "<no commit>",
                         "status": STATUS_MALFORMED, "behind": None,
                         "detail": f"lock entry missing "
                                   f"{'name' if not n else 'commit'}"})
            continue
        rows.append(measure(n, c, github))
    return {
        "subrepos": len(rows),
        "lock_entries": len(entries),
        "measured": sum(1 for r in rows if r["status"] == STATUS_MEASURED),
        "diverged": sum(1 for r in rows if r["status"] == STATUS_DIVERGED),
        "malformed": sum(1 for r in rows if r["status"] == STATUS_MALFORMED),
        # UNMEASURABLE is counted separately and never folded into "0 behind" —
        # a lag nobody could compute is not a lag of zero.
        "unmeasurable": sum(1 for r in rows if r["status"] != STATUS_MEASURED),
        "total_behind": sum(r["behind"] or 0 for r in rows),
        "rows": sorted(rows, key=lambda r: -(r["behind"] or 0)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", default=str(LOCK))
    ap.add_argument("--github", default=str(GITHUB))
    ap.add_argument("--max-lag", type=int, default=50,
                    help="alarm above this many commits (a threshold, not a policy)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = scan(Path(a.lock), Path(a.github))
    except Exception as exc:  # noqa: BLE001
        print(f"UNUSABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE
    over = [r for r in res["rows"]
            if r["status"] == STATUS_MEASURED and r["behind"] > a.max_lag]
    unmeasurable = [r for r in res["rows"] if r["status"] != STATUS_MEASURED]
    if a.json:
        print(json.dumps({**res, "max_lag": a.max_lag,
                          "over_threshold": [r["subrepo"] for r in over]}, indent=2))
    else:
        print(f"subrepo pin lag: {res['measured']}/{res['lock_entries']} measured "
              f"(diverged {res['diverged']}, malformed {res['malformed']}, "
              f"other-unmeasurable "
              f"{res['unmeasurable'] - res['diverged'] - res['malformed']}), "
              f"{res['total_behind']} commits behind in total "
              f"(threshold {a.max_lag})")
        for r in res["rows"]:
            if r["status"] == STATUS_MEASURED:
                mark = "OVER" if r["behind"] > a.max_lag else "    "
                print(f"  {mark}  {r['subrepo']:24} pin={r['pin'][:8]} "
                      f"behind={r['behind']}")
            else:
                print(f"  ????  {r['subrepo']:24} {r['status']}: {r['detail'][:80]}")
    return EXIT_LAG if (over or unmeasurable) else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
