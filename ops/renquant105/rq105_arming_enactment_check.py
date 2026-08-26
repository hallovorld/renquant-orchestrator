#!/usr/bin/env python3
"""Gate 1 declares intraday decisioning enabled — gate 2 must actually enact it.

THE HAZARD (orch#1034 -> #1067, measured 2026-08-26). #1067 moved rq105's gate 2
out of an uncommitted working-tree edit and into an operator-owned file outside
git:

    $RQ_ROOT/data/rq105/intraday_decisioning.armed.json

That is the right home — a recovery `git checkout --` cannot extinguish it, which
is how the activation nearly died on 2026-08-24 (#1044). But *because* the file
is outside git, merging #1067 does not create it. At the moment of writing, the
deployed wrapper still carries the pre-#1067 hard export, `-run` is behind main,
and the arming file does not exist. The next `-run` sync therefore flips the
mechanism to one whose input is missing, and the decision loop goes dark — the
exact silent deactivation #1067 exists to prevent, performed by the fix for it.

WHAT THIS COMPARES, AND WHY THAT PAIR. Not two log files: an arming verdict read
from history tells you about yesterday, and the cutover's first casualty is
today. This compares the two surfaces that are supposed to agree:

    gate 1  pinned strategy config `intraday_decisioning.enabled`   the REVIEWED intent
    gate 2  the arming file, as read by the DEPLOYED wrapper        the ENACTMENT

A reviewed config that says `enabled: true` while nothing arms gate 2 is a
system whose committed description of itself is false. That is a finding whether
it arrived by a botched cutover, a deleted file, a malformed edit, or a
deliberate disarm nobody wrote down — and in the deliberate case the correct
response is to flip gate 1 too, or to ack, which is exactly the discipline the
ack ledger exists for.

WHY THE DEPLOYED WRAPPER IS AN INPUT. Gate 2 has had two mechanisms in one
month. Reading the arming file alone would report a finding today, when the
deployed wrapper does not consult that file at all and the loop is armed — a
guard that validates the wrong object. So the wrapper in the RUN checkout
decides which mechanism is in force, and a wrapper that predates #1067 yields
`unusable`, not `ok`: with a hard export there is no reviewed surface stating
gate 2's state, so it cannot be verified — only unverifiable. That reading
self-clears on the sync it is warning about.

    deployed wrapper        arming file        verdict                    exit
    ----------------------  -----------------  -------------------------  ----
    consults rq105_arming   valid              enacted, agrees with g1    0
    consults rq105_arming   absent/invalid     G1 ENABLED, G2 NOT ARMED   1
    pre-#1067 hard export   (not consulted)    not verifiable             2
    neither mechanism       -                  not verifiable             2
    gate 1 disabled         (any)              nothing declared to enact  0

NOT IN SCOPE. Whether the loop SHOULD be armed — that is the operator's, and
gate 1 is where they say so. Whether the job ran at all (`launchd-liveness`),
and the mid-session kill-switch (gate 3), which is a halt and not an arming.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RQ_ROOT = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
RQ105_ORCH_ROOT = Path(os.environ.get(
    "RQ105_ORCH_ROOT", "/Users/renhao/git/github/renquant-orchestrator-run"))

#: Gate 1 lives in the PINNED config, not the sibling dev checkout — the pinned
#: copy is the one the scheduler is made to read (orch#1041), so it is the one
#: whose claim has to be true.
PINNED_CONFIG = (".subrepo_runtime/repos/renquant-strategy-104/configs/"
                 "strategy_config.json")
ARMING_FILE = "data/rq105/intraday_decisioning.armed.json"
WRAPPER = "ops/renquant105/run_session_scheduler.sh"

#: The post-#1067 wrapper validates the arming file by invoking this module; the
#: pre-#1067 one exports the flag unconditionally. Two rules make the reading
#: robust. (1) ORDER: the post-#1067 wrapper contains the hard-export line too,
#: inside the `if`, so matching the export first would misread the new mechanism
#: as the old one. (2) COMMENTS ARE NOT CODE: both wrappers document the other
#: mechanism in prose, and a marker found only in a comment would let a REVERTED
#: wrapper keep passing as the new gate — a finding derived from a stale
#: sentence.
ARMING_GATE_MARKER = "renquant_orchestrator.rq105_arming"
HARD_EXPORT_MARKER = "export RENQUANT_INTRADAY_DECISIONING=1"

EXIT_OK, EXIT_FINDING, EXIT_UNVERIFIABLE = 0, 1, 2


class Unverifiable(RuntimeError):
    """An input could not be read, or gate 2's mechanism could not be identified.

    Deliberately not a finding. "I could not determine whether gate 2 is armed"
    and "gate 2 is not armed" have opposite remedies, and collapsing them the
    wrong way is how a check ends up passing on a system it never inspected.
    """


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Unverifiable(f"cannot read the {label} at {path}: {exc}") from exc


def gate1_enabled(rq_root: Path) -> bool:
    """`intraday_decisioning.enabled` from the pinned config."""
    path = rq_root / PINNED_CONFIG
    raw = _read_text(path, "pinned strategy config")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise Unverifiable(f"pinned strategy config at {path} is not JSON: {exc}") from exc
    section = data.get("intraday_decisioning")
    if not isinstance(section, dict):
        raise Unverifiable(
            f"pinned strategy config at {path} has no 'intraday_decisioning' "
            f"object — refusing to infer gate 1 from its absence")
    enabled = section.get("enabled")
    # A non-bool is not a quieter `false`. `"false"` is truthy and `"true"` is
    # not a boolean; reading either as "gate 1 declares nothing" would silence
    # this check on exactly the malformed config that most deserves a look.
    if not isinstance(enabled, bool):
        raise Unverifiable(
            f"pinned strategy config at {path} has "
            f"intraday_decisioning.enabled={enabled!r} ({type(enabled).__name__}), "
            f"not a boolean — gate 1's declaration is unreadable, which is not "
            f"the same as gate 1 being off")
    return enabled


def gate2_mechanism(orch_root: Path) -> str:
    """Which gate-2 mechanism the DEPLOYED wrapper is running: arming-file or export."""
    raw = _read_text(orch_root / WRAPPER, "deployed session-scheduler wrapper")
    src = "\n".join(l for l in raw.splitlines()
                    if not l.lstrip().startswith("#"))
    if ARMING_GATE_MARKER in src:
        return "arming-file"
    if HARD_EXPORT_MARKER in src:
        return "hard-export"
    raise Unverifiable(
        f"the deployed wrapper at {orch_root / WRAPPER} contains neither the "
        f"arming-file gate ({ARMING_GATE_MARKER!r}) nor a hard export "
        f"({HARD_EXPORT_MARKER!r}) — gate 2's mechanism is unrecognised, which "
        f"is not the same as gate 2 being unarmed")


def gate2_armed(rq_root: Path, orch_root: Path) -> tuple[bool, str]:
    """Delegate to the validator the DEPLOYED wrapper itself runs.

    Two decisions here, both deliberate. It is not re-implemented: a private
    second reading of "is this file valid" drifts from the one in force, and
    then this check certifies its own opinion instead of the wrapper's
    behaviour. And it is loaded from `orch_root`, the same checkout the wrapper
    was read from — importing this checkout's copy while judging that
    checkout's wrapper is how a deploy lag becomes invisible.
    """
    src = orch_root / "src" / "renquant_orchestrator" / "rq105_arming.py"
    if not src.is_file():
        raise Unverifiable(
            f"the deployed wrapper invokes the arming validator, but "
            f"{src} is absent — a wrapper and validator that shipped apart "
            f"cannot be checked as one gate")
    # compile+exec rather than importlib's loader, and NOT because it is
    # simpler. `SourceFileLoader.exec_module` writes `__pycache__` beside the
    # source — a read-only detector would then be creating files in the
    # DEPLOYED checkout it is auditing. `test_the_detector_writes_nothing`
    # caught exactly that; the source-regex membership guard never could.
    # This form also avoids sys.path mutation and sys.modules aliasing with
    # this checkout's own module of the same name.
    namespace: dict = {"__file__": str(src), "__name__": "_rq105_arming_deployed"}
    try:
        exec(compile(_read_text(src, "deployed arming validator"), str(src), "exec"),
             namespace)
        evaluate = namespace["evaluate_arming_file"]
    except Unverifiable:
        raise
    except Exception as exc:  # noqa: BLE001 - any failure to load is unverifiable
        raise Unverifiable(
            f"the arming validator at {src} did not load "
            f"({type(exc).__name__}: {exc})") from exc
    return evaluate(rq_root / ARMING_FILE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rq-root", default=None,
                    help="umbrella root (default: $RQ_ROOT)")
    ap.add_argument("--orch-root", default=None,
                    help="the RUN orchestrator checkout (default: $RQ105_ORCH_ROOT)")
    args = ap.parse_args(argv)
    rq_root = Path(args.rq_root) if args.rq_root else RQ_ROOT
    orch_root = Path(args.orch_root) if args.orch_root else RQ105_ORCH_ROOT

    try:
        if not gate1_enabled(rq_root):
            print("OK: gate 1 (intraday_decisioning.enabled) is not true — the "
                  "reviewed config declares nothing for gate 2 to enact.")
            return EXIT_OK
        mechanism = gate2_mechanism(orch_root)
        if mechanism == "hard-export":
            raise Unverifiable(
                f"the deployed wrapper at {orch_root / WRAPPER} predates the "
                f"arming-file gate (orch#1067) and exports "
                f"RENQUANT_INTRADAY_DECISIONING unconditionally, so gate 2's "
                f"state is not recorded on any reviewed surface and cannot be "
                f"checked. This clears when the run checkout syncs #1067 — and "
                f"at that moment {rq_root / ARMING_FILE} must already exist, or "
                f"the sync itself disarms the loop.")
        armed, detail = gate2_armed(rq_root, orch_root)
    except Unverifiable as exc:
        print(f"UNVERIFIABLE: {exc}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    if armed:
        print(f"OK: gate 1 enabled and gate 2 armed ({detail}).")
        return EXIT_OK
    print(f"FAIL: the pinned config declares intraday_decisioning.enabled=true, "
          f"but gate 2 is NOT armed — {detail}. The deployed wrapper reads "
          f"{rq_root / ARMING_FILE}, so no session will decide anything. Either "
          f"restore the arming file (an operator landing step) or set gate 1 "
          f"false, so the reviewed config stops claiming a loop that is dark.")
    return EXIT_FINDING


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
