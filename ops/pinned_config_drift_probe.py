#!/usr/bin/env python3
"""Is the config the live run reads the config that was reviewed and merged?

WHY THIS EXISTS
---------------
Measured 2026-08-07 (orch#895): `strategy-104` merged
`feat(risk): per-name cap 12% -> 30% (#94)` under an operator directive, the
runtime checkout was advanced to it, and `subrepos.lock.json` was never updated.
The next pin-restoring run checked the lock's sha back out. `origin/main` said
`BULL_CALM.max_position_pct = 0.3`; the config the book actually sized new
entries against said `0.12`. Nothing alarmed for days.

`ops/subrepo_pin_lag_check.py` DID see it — `strategy-104 pin=c8bba9c9 behind=1`
— and could not report it, because its alarm is `behind > --max-lag` with
`--max-lag=50`. That is the defect this probe exists to cover:

    **lag measured in commit COUNT cannot distinguish "1 commit behind because
    of a typo fix" from "1 commit behind because the operator's P0 risk-cap
    change is stranded".**

Lowering that threshold to 0 is not the fix; it is pure noise, since a pin is
legitimately behind main most of the time. The signal that matters is CONTENT:
does the pinned config differ from main's on a key that changes live behaviour?

THE DEFAULT IS INVERTED ON PURPOSE
----------------------------------
An enumerated allow-list of "keys that matter" would leave every key nobody
thought of on the silent-pass side — the exact fail-open shape that has bitten
this fleet repeatedly. So **every difference is a finding**, and the only
exemption is an explicit, tiny set of keys that provably cannot reach live
behaviour (documentation keys, which this config spells with a leading
underscore). A new knob is therefore reported by default, not ignored by
default.

A STALE MIRROR MUST NOT READ AS CLEAN — AND REPORTING THE DATE IS NOT ENOUGH
---------------------------------------------------------------------------
`origin/main` here is whatever the local sibling clone last fetched. An earlier
revision of this probe reported the compared sha and its commit date and called
that a staleness control. It is not (codex on orch#896): a week-old local
`origin/main` whose config happens to match the pin returns exit 0 even when the
remote main carries a risk-critical change — the exact failure this probe claims
to prevent, reproduced inside the probe.

So the local ref is verified against the REMOTE before any comparison is
believed. `git ls-remote origin refs/heads/main` reads the remote's tip without
mutating the clone; if it disagrees with local `origin/main`, the mirror is stale
and the probe REFUSES (exit 2) rather than reporting agreement it cannot
establish. A transport failure is also a refusal — "I could not reach the remote"
is not "the mirror is current". `--allow-stale-mirror` exists for offline use and
downgrades the probe to an explicitly-labelled local diagnostic; the daily audit
does not pass it.

Read-only: runs `git show` / `git rev-parse` / `git ls-remote` and reads two JSON
blobs. It never writes, checks out, or fetches.

Exit codes:
    0  every behavioural key in the pinned config matches origin/main
    1  at least one behavioural key differs                        (FINDING)
    2  refusal — a side could not be read, the mirror has no origin/main, the
       local ref DISAGREES with the remote (stale mirror), or the remote could
       not be reached at all
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

RQ = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))

EXIT_OK, EXIT_DRIFT, EXIT_UNUSABLE = 0, 1, 2

#: Subrepos whose config is read by the live run, as (name, path-within-repo).
#: Kept explicit because each entry names a file a human has agreed is a live
#: run surface — unlike the KEY set below, adding a *file* here is a deliberate
#: widening, not a fail-open default.
WATCHED = (
    ("renquant-strategy-104", "configs/strategy_config.json"),
)


class Unusable(RuntimeError):
    """Raised when the comparison cannot be made. Never downgraded to 'clean'."""


def _is_documentation_key(leaf: str) -> bool:
    """The ONLY exemption. This config spells comments as `_`-prefixed keys
    (`_bb14_meta_reason`, `_sdl_reason`, `_disable_new_buys_reason`); they carry
    provenance prose and are read by no code path. Everything else is a finding.
    """
    return leaf.startswith("_")


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Dotted-path view of a JSON document, minus documentation keys.

    Lists are compared as whole values rather than per index: a reordered
    watchlist is a real difference, and per-index paths would report it as N
    unrelated findings.
    """
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _is_documentation_key(str(k)):
                continue
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(flatten(v, path))
            else:
                out[path] = v
    else:
        out[prefix] = obj
    return out


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise Unusable(f"git {' '.join(args)} in {repo}: "
                       f"{proc.stderr.strip()[:200]}")
    return proc.stdout


def remote_main_sha(mirror: Path) -> str:
    """The REMOTE's main tip, read without mutating the clone.

    `ls-remote` performs no ref update and writes nothing into the object store,
    so this stays a read-only probe while still observing the authority.
    """
    out = _git(mirror, "ls-remote", "origin", "refs/heads/main")
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.strip() == "refs/heads/main" and sha.strip():
            return sha.strip()
    raise Unusable(f"remote has no refs/heads/main: {mirror}")


def compare(name: str, rel_path: str, *, rq: Path = RQ,
            mirror_root: Path = Path("/Users/renhao/git/github"),
            allow_stale_mirror: bool = False) -> dict:
    """Compare the pinned copy of one config against the mirror's origin/main."""
    pinned_file = rq / ".subrepo_runtime" / "repos" / name / rel_path
    mirror = mirror_root / name
    if not pinned_file.is_file():
        raise Unusable(f"pinned config absent: {pinned_file}")
    if not (mirror / ".git").exists():
        raise Unusable(f"no local mirror to read origin/main from: {mirror}")

    main_sha = _git(mirror, "rev-parse", "origin/main").strip()

    # The local ref is not evidence about the remote until it is checked against
    # it. Without this, a stale mirror that happens to agree with the pin exits 0.
    mirror_state = "unchecked (--allow-stale-mirror)"
    if not allow_stale_mirror:
        try:
            remote_sha = remote_main_sha(mirror)
        except Unusable as exc:
            raise Unusable(f"could not observe remote main ({exc}) — refusing "
                           f"rather than trusting a possibly stale local ref")
        if remote_sha != main_sha:
            raise Unusable(
                f"local origin/main is STALE: local={main_sha[:12]} "
                f"remote={remote_sha[:12]}. Refusing — a clean result here would "
                f"mean the reviewed main was never observed.")
        mirror_state = "verified against remote"
    main_date = _git(mirror, "log", "-1", "--format=%cI", main_sha).strip()
    pinned_sha = _git(rq / ".subrepo_runtime" / "repos" / name,
                      "rev-parse", "HEAD").strip()

    try:
        pinned_doc = json.loads(pinned_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise Unusable(f"pinned config unreadable: {type(exc).__name__}: {exc}")
    try:
        main_doc = json.loads(_git(mirror, "show", f"{main_sha}:{rel_path}"))
    except Unusable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise Unusable(f"main config unreadable: {type(exc).__name__}: {exc}")

    a, b = flatten(pinned_doc), flatten(main_doc)
    diffs = []
    for key in sorted(set(a) | set(b)):
        av, bv = a.get(key, "<absent>"), b.get(key, "<absent>")
        if av != bv:
            diffs.append({"key": key, "pinned": av, "main": bv})
    return {"subrepo": name, "path": rel_path, "pinned_sha": pinned_sha,
            "main_sha": main_sha, "main_committed_at": main_date,
            "mirror_state": mirror_state,
            "in_sync": pinned_sha == main_sha, "diffs": diffs,
            "n_keys_compared": len(set(a) | set(b))}


def scan(*, rq: Path = RQ,
         mirror_root: Path = Path("/Users/renhao/git/github"),
         allow_stale_mirror: bool = False) -> dict:
    results, refusals = [], []
    for name, rel in WATCHED:
        try:
            results.append(compare(name, rel, rq=rq, mirror_root=mirror_root,
                                   allow_stale_mirror=allow_stale_mirror))
        except Unusable as exc:
            refusals.append({"subrepo": name, "path": rel, "detail": str(exc)})
    return {"results": results, "refusals": refusals,
            "n_drifted": sum(1 for r in results if r["diffs"])}


def render(res: dict) -> str:
    lines = []
    for r in res["results"]:
        head = (f"{r['subrepo']}/{r['path']}: pinned={r['pinned_sha'][:8]} "
                f"main={r['main_sha'][:8]} (committed {r['main_committed_at']}, "
                f"mirror {r['mirror_state']}), "
                f"{r['n_keys_compared']} keys compared")
        if not r["diffs"]:
            lines.append(f"  OK    {head}")
            continue
        lines.append(f"  DRIFT {head}")
        for d in r["diffs"]:
            lines.append(f"          {d['key']}: pinned={d['pinned']!r} "
                         f"main={d['main']!r}")
    for f in res["refusals"]:
        lines.append(f"  ????  {f['subrepo']}/{f['path']}: {f['detail']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rq-root", default=str(RQ))
    ap.add_argument("--mirror-root", default="/Users/renhao/git/github")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--allow-stale-mirror", action="store_true",
                    help="skip the ls-remote check and label the result a LOCAL "
                         "diagnostic; offline use only, never the daily audit")
    a = ap.parse_args(argv)

    res = scan(rq=Path(a.rq_root), mirror_root=Path(a.mirror_root),
               allow_stale_mirror=a.allow_stale_mirror)
    if a.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        n = res["n_drifted"]
        print(f"pinned-config drift: {len(res['results'])} compared, "
              f"{n} drifted, {len(res['refusals'])} unreadable")
        print(render(res))
    if res["refusals"]:
        return EXIT_UNUSABLE
    return EXIT_DRIFT if res["n_drifted"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
