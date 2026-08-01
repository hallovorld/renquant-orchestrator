#!/usr/bin/env python3
"""Where the two copies of the WF-gate stamp DISAGREE. (GOAL-3, twin registry R8)

R8 records that `wf_gate_metadata` exists in two places inside one artifact —
`metadata.wf_gate_metadata` (canonical) and a legacy top-level copy — and that they do
not always agree. The registry's own retirement condition for that row asks for
"a parity check that reports the artifacts where the two copies disagree instead of
silently preferring one". This is that check; nothing else in the repo performs it.

WHY IT MATTERS RATHER THAN BEING TIDINESS. Reading the wrong copy produced three defects
in one evening, two of them published claims that had to be retracted (backtesting#89's
"fifteen rows were invented", orch#680's "ten of eleven cannot be re-derived"). Every
reader now consults the canonical key first — but a reader is only as good as the data,
and where the copies disagree the artifact ITSELF carries two answers. Preferring one
silently is what makes that invisible.

WHAT IS AND IS NOT A PROBLEM:
  * both copies present and DISAGREEING anywhere -> PROBLEM. The comparison is the
    UNION of every key in both blocks, walked recursively (round 2, codex on #687:
    an eight-field enumeration is a fail-open default). Two answers in one file is a
    defect of the artifact, regardless of which one a reader takes.
  * a copy PRESENT but not a JSON object -> PROBLEM, fail closed. Unreadable is not
    absent, and treating it as absent passes the artifact most likely to be wrong.
  * only the canonical copy -> fine, and the majority case.
  * only the legacy copy -> INFO. Not a disagreement, but worth counting: it is the one
    shape where a canonical-first reader falls through.
  * neither -> INFO. Not this check's subject.

Read-only. Never writes, never mutates an artifact.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

CANONICAL = "metadata.wf_gate_metadata"
LEGACY = "wf_gate_metadata (legacy top-level)"

#: Fields a consumer is KNOWN to act on. These are NOT the comparison surface — see
#: `compare`, which walks the complete blocks. They are retained only to rank the
#: reported differences so the verdict-bearing ones are read first.
SALIENT_FIELDS = (
    "passed",
    "sanity_eval_scope",
    "wf_eval_scope",
    "gate_verdict_before_override",
    "operator_authorized_override",
    "override_reason",
    "diagnostic_only",
    "gate_version",
)

#: A copy that exists but is not a JSON object. Distinct from absent: absent means the
#: artifact carries one stamp, malformed means it carries two and one is unreadable.
MALFORMED = object()

_ABSENT = object()


def _one(node: object) -> object | None:
    """Classify ONE copy: the dict, `MALFORMED`, or `None` for genuinely absent.

    The earlier version returned `None` for anything that was not a dict, which turned
    a malformed dual stamp into "single stamp, nothing to compare" — the check passed
    on the artifact most likely to be wrong. `None` (the JSON literal) is still absent;
    a string, a list or a number where a block belongs is `MALFORMED`.
    """
    if node is None:
        return None
    return node if isinstance(node, dict) else MALFORMED


def _blocks(payload: dict) -> tuple[object | None, object | None]:
    meta = payload.get("metadata")
    # `metadata` itself may be malformed; then the canonical copy is unreadable, not
    # absent — an artifact whose `metadata` is a string has not simply skipped the stamp.
    if meta is None:
        canon = None
    elif isinstance(meta, dict):
        canon = _one(meta.get("wf_gate_metadata"))
    else:
        canon = MALFORMED
    return canon, _one(payload.get("wf_gate_metadata"))


#: Rendered length cap for ONE side of a reported difference. Presentation only: the
#: comparison walks the complete blocks regardless. Without it a single absent nested
#: key prints its entire subtree -- one live artifact rendered `artifact_usage` as a
#: 6KB line, which is a difference nobody reads.
_MAX_VALUE_CHARS = 160


def _fmt(v: object) -> str:
    """The marker is UNQUOTED so a missing field cannot be confused with a field whose
    value is literally the string "<absent>" -- `repr` made those identical."""
    if v is _ABSENT:
        return "<absent>"
    r = repr(v)
    if len(r) <= _MAX_VALUE_CHARS:
        return r
    return f"{r[:_MAX_VALUE_CHARS]}...<+{len(r) - _MAX_VALUE_CHARS} chars>"


def _walk(a: object, b: object, path: str, out: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            _walk(a.get(k, _ABSENT), b.get(k, _ABSENT), f"{path}.{k}" if path else k,
                  out)
        return
    if a is _ABSENT or b is _ABSENT or a != b:
        out.append(f"{path}: canonical={_fmt(a)} legacy={_fmt(b)}")


def compare(canon: dict, legacy: dict) -> list[str]:
    """EVERY path on which the two copies give different answers.

    Reviewed `[codex on orch#687]`: *"the scanner compares only eight selected fields,
    so a disagreement in any later or currently unlisted gate field passes cleanly."*
    That is this programme's recurring **enumerated allow-list** shape — the enumeration
    is the fail-open default, because a field added to the gate tomorrow is outside it
    and diverges silently.

    So the comparison surface is now the **union of every key in both blocks**, walked
    recursively, with each divergence reported at its dotted path. A key present in one
    copy and absent from the other is a disagreement: that is exactly the shape measured
    on the live tree — a legacy block with no `sanity_eval_scope` beside a canonical
    block that records one. **Absent is not equal.**

    Ordering is by `SALIENT_FIELDS` first so a reader meets `passed` before
    `timings.fit_seconds`; ordering is presentation, and changes nothing about what is
    compared.
    """
    out: list[str] = []
    _walk(canon, legacy, "", out)
    rank = {f: i for i, f in enumerate(SALIENT_FIELDS)}
    return sorted(out, key=lambda s: (rank.get(s.split(":", 1)[0].split(".")[0],
                                               len(rank)), s))


def scan(root: str, query: str) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    both = canon_only = legacy_only = neither = unreadable = malformed = 0

    paths = sorted(glob.glob(os.path.join(root, query)))
    if not paths:
        return ([f"gate-stamp parity: no artifact under {root} matches {query} — "
                 f"the scan has no subjects, which is not the same as parity"], [])

    for path in paths:
        try:
            with open(path, "rb") as fh:
                payload = json.loads(fh.read())
        except Exception as exc:  # noqa: BLE001
            unreadable += 1
            problems.append(f"gate-stamp parity: {os.path.basename(path)} unreadable: "
                            f"{type(exc).__name__}: {exc}")
            continue
        if not isinstance(payload, dict):
            # FAIL CLOSED. Reviewed `[codex on orch#687]`: this branch counted the file
            # and continued SILENTLY, so a scan containing only a JSON array exited zero
            # while its own summary admitted an unreadable artifact -- the summary said
            # one thing and the exit code said another, and the exit code is what a
            # scheduled job reads. A parse that yields a non-object is exactly as
            # uninspectable as a parse that raises, and is reported the same way.
            unreadable += 1
            problems.append(
                f"gate-stamp parity: {os.path.basename(path)} unreadable: its top-level "
                f"JSON value is {type(payload).__name__}, not an object — no gate stamp "
                f"can be located in it, so this artifact was NOT compared")
            continue
        canon, legacy = _blocks(payload)

        # FAIL CLOSED on a malformed copy. A stamp that exists but is not an object
        # cannot be compared, and treating it as absent would let the artifact most
        # likely to be wrong report clean.
        if canon is MALFORMED or legacy is MALFORMED:
            malformed += 1
            which = " and ".join(
                n for n, v in ((CANONICAL, canon), (LEGACY, legacy)) if v is MALFORMED)
            problems.append(
                f"gate-stamp parity: {os.path.basename(path)} carries a MALFORMED gate "
                f"stamp at {which} — present but not a JSON object, so the two copies "
                f"cannot be compared. Unreadable is not absent.")
            continue

        # Presence, NOT truthiness. An EMPTY canonical block `{}` is falsy, and the
        # earlier `if canon and legacy` fell through to `elif legacy` — counting a
        # dual-stamped artifact as legacy-only and skipping the comparison entirely.
        # Identical to the defect codex found in orch#683; keyed on `is not None` here.
        if canon is not None and legacy is not None:
            both += 1
            diffs = compare(canon, legacy)
            if diffs:
                shown = "; ".join(diffs[:12])
                more = f" (+{len(diffs) - 12} more)" if len(diffs) > 12 else ""
                problems.append(
                    f"gate-stamp parity: {os.path.basename(path)} carries TWO gate "
                    f"stamps that disagree on {len(diffs)} path(s) — {shown}{more}. A "
                    f"reader taking the legacy copy gets a different answer from one "
                    f"taking the canonical copy; the artifact itself holds both.")
        elif canon is not None:
            canon_only += 1
        elif legacy is not None:
            legacy_only += 1
        else:
            neither += 1

    infos = [
        f"gate-stamp parity: {len(paths)} artifact(s) scanned — {both} carry BOTH "
        f"copies, {canon_only} canonical-only, {legacy_only} legacy-only, "
        f"{neither} no stamp, {malformed} malformed, {unreadable} unreadable",
    ]
    # The denominator is stated so a shrinking scan cannot read as a clean one.
    accounted = both + canon_only + legacy_only + neither + malformed + unreadable
    if accounted != len(paths):
        problems.append(
            f"gate-stamp parity: {len(paths)} artifact(s) matched but only {accounted} "
            f"were classified — {len(paths) - accounted} fell through every branch, so "
            f"this scan does not cover what it claims to")
    if legacy_only:
        infos.append(
            f"gate-stamp parity: {legacy_only} artifact(s) carry ONLY the legacy "
            f"top-level copy — the one shape where a canonical-first reader falls "
            f"through to it")
    return problems, infos


def _default_artifacts_root() -> str:
    """The 104 prod artifact directory, resolved WITHOUT requiring the package on the path.

    A member of `ops/ops_audit.py` may not take a machine-specific path as an argument:
    baking an absolute path into the reviewed MEMBERS tuple is how a check ends up
    measuring one operator's disk.

    The first attempt used `runtime_paths.default_data_root()`, which is the repo's
    canonical answer — and it returned nothing, because `ops/` scripts are invoked as
    plain files and `renquant_orchestrator` is not importable without PYTHONPATH. So the
    chain below tries the package first and then falls back to the same two roots
    `default_data_root` itself honours, resolved from this file's own location:

      1. `RENQUANT_DATA_ROOT`
      2. `renquant_orchestrator.runtime_paths.default_data_root()`, when importable
      3. `<github root>/RenQuant`, derived from this file's path

    An unresolvable root returns "" — and that is deliberate: the caller's own
    "no subjects" guard then exits NON-ZERO. An empty scan must never read as a clean
    one, which is exactly what the first version's silent "" already did correctly.
    """
    import os
    env = os.environ.get("RENQUANT_DATA_ROOT")
    if env:
        return os.path.join(env, "backtesting", "renquant_104", "artifacts", "prod")
    try:
        from renquant_orchestrator.runtime_paths import default_data_root
        return str(default_data_root() / "backtesting" / "renquant_104" /
                   "artifacts" / "prod")
    except Exception:  # noqa: BLE001
        pass
    here = os.path.abspath(__file__)
    # ops/[renquant104/]<file>.py -> repo root -> its parent is the github root
    repo = here
    for _ in range(4):
        repo = os.path.dirname(repo)
        cand = os.path.join(os.path.dirname(repo), "RenQuant", "backtesting",
                            "renquant_104", "artifacts", "prod")
        if os.path.isdir(cand):
            return cand
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=_default_artifacts_root(),
                    help="artifact directory; defaults to the 104 prod "
                         "root resolved via runtime_paths")
    ap.add_argument("--query", default="panel-ltr.alpha158_fund*.json")
    a = ap.parse_args(argv)
    problems, infos = scan(a.root, a.query)
    for line in infos:
        print(line)
    for line in problems:
        print(line, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
