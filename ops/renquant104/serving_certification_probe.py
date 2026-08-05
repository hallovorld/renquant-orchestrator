#!/usr/bin/env python3
"""Does each SERVING artifact carry a checkable certification claim?

WHY (GOAL-6, measured 2026-08-05): orch#726 filed three defects against the
serving artifacts on 2026-08-01. Re-measuring today, **two were already fixed**
(the prod manifest and the override rollback no longer point at a vanished
`/tmp` path) and **one was unchanged** (the clf lane carries no
`wf_gate_metadata` at all, in either the canonical or the legacy location).

Nobody noticed either fact for four days, because checking meant reading two
artifacts by hand. A three-claim P0 sitting two-thirds fixed is how a reader
learns to discount P0s.

This probe answers one question per serving artifact, cheaply and repeatably:
**does it make a walk-forward claim that can be checked at all?** It deliberately
does NOT judge the claim — fold counts are counts of manifest rows and say
nothing about leakage or quality. Establishing that a claim EXISTS is a
different, prior question, and conflating them is what let one lane's 43 folds
read as coverage for a lane with zero.

Read-only. Usage:
    python ops/renquant104/serving_certification_probe.py [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                   "/Users/renhao/git/github/RenQuant"))
ARTIFACTS = REPO / "backtesting" / "renquant_104" / "artifacts"

# (label, path relative to ARTIFACTS). The SERVING set — what the live book and
# the shadow lanes actually load, not everything on disk.
SERVING = (
    ("prod panel (XGB recipe)", "prod/panel-ltr.alpha158_fund.json"),
    ("clf top-decile fwd60 (shadow member)", "shadow/panel-clf.top-decile.fwd60.json"),
)

STATE_CLAIM = "HAS_CHECKABLE_CLAIM"
STATE_UNRESOLVABLE = "CLAIM_REFERENCE_NOT_RESOLVABLE"
STATE_NO_STAMP = "NO_GATE_STAMP"
STATE_DANGLING = "CLAIM_POINTS_AT_A_MISSING_PATH"
STATE_NOTHING_TO_CHECK = "CLAIM_REFERENCES_NO_PATH"
STATE_MALFORMED = "STAMP_MALFORMED"
STATE_UNREADABLE = "ARTIFACT_UNREADABLE"
STATE_ABSENT = "ARTIFACT_ABSENT"
ACTIONABLE = (STATE_NO_STAMP, STATE_DANGLING, STATE_NOTHING_TO_CHECK,
              STATE_MALFORMED, STATE_UNREADABLE, STATE_ABSENT,
              STATE_UNRESOLVABLE)

# [codex on orch#820, twice] ENUMERATING keys was the first bug: v1 checked
# `/tmp` strings plus two manifest keys, so the live prod artifact passed while
# `config_parity.candidate_artifact` dangled. Inverting the default fixed that.
#
# The SECOND bug was the wording. v2 said it walked "every path-shaped string",
# but the matcher took only POSIX absolute / dot-relative strings with a fixed
# extension set — missing bare relatives, Windows paths and file:// URLs, while
# accepting globs it cannot resolve. A recogniser that silently drops a
# reference is the same fail-open the inversion was meant to close.
#
# So the contract is now stated exactly, and nothing path-shaped is dropped in
# silence. A string is a REFERENCE iff, stripped and non-empty, it is:
#   * a `file://` URL, or
#   * rooted — `/…`, `./…`, `../…`, `~/…`, a Windows drive (`C:\…`, `C:/…`) or
#     a UNC share (`\\host\share`), or
#   * separator-bearing with an extension on its last segment
#     (`artifacts/prod/panel.json`), or
#   * bare but carrying one of the artifact extensions (`panel.json`).
# and every reference is then classified three ways, never two:
#   RESOLVABLE     — an absolute POSIX path (or file:// URL) this box can stat;
#   UNRESOLVABLE   — path-shaped but not checkable HERE, with the reason named:
#                    relative to an unstated base (resolving it against CWD is
#                    the probe's own guess, not the artifact's claim); a glob;
#                    a Windows path; a remote URL scheme;
#   not a reference — everything else.
# UNRESOLVABLE is ACTIONABLE. An unresolvable reference is a claim this probe
# cannot check, and reporting that as a checkable claim is exactly the failure
# the inversion exists to prevent.
#
# DELIBERATELY NOT a reference: a separator-bearing string with no extension on
# its last segment (`relative/noext`, `n/a`, `1x/2x/3x`). It is indistinguishable
# from an ordinary identifier, and treating identifiers as dangling paths would
# be the false positive that discredits the probe. Named here so the limit is
# read, not discovered.
_ARTIFACT_EXTS = ("json", "parquet", "jsonl", "csv", "txt", "pkl", "pt", "joblib")
_EXT_TAIL = re.compile(r"\.[A-Za-z0-9]{1,8}$")
_ARTIFACT_TAIL = re.compile(r"\.(?:%s)$" % "|".join(_ARTIFACT_EXTS), re.I)
_SCHEME = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)://")
_WINDOWS = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\)")
_GLOB_CHARS = "*?["

RESOLVABLE = "resolvable"


def classify_reference(value: str) -> tuple[str, str] | None:
    """``(kind, detail)`` for one string, or ``None`` when it is not a reference.

    ``kind`` is ``RESOLVABLE`` (detail = the concrete POSIX path to stat) or a
    short reason this box cannot resolve it. See the contract above; every
    branch is covered by a named test.
    """
    s = value.strip()
    if not s:
        return None
    scheme = _SCHEME.match(s)
    if scheme:
        if scheme.group("scheme").lower() != "file":
            return ("remote URL scheme", s)
        s = s[len(scheme.group(0)):]
        if s.startswith("localhost/"):
            s = s[len("localhost"):]
        elif not s.startswith("/"):
            return ("file:// URL with a host component", value)
        s = s if s.startswith("/") else "/" + s
    elif _WINDOWS.match(s):
        return ("Windows path, not resolvable on this box", s)
    sep = "/" in s or "\\" in s
    rooted = s.startswith(("/", "./", "../", "~/"))
    tail = s.rsplit("/", 1)[-1]
    if not (rooted or (sep and _EXT_TAIL.search(tail)) or
            (not sep and _ARTIFACT_TAIL.search(s))):
        return None
    if any(c in s for c in _GLOB_CHARS):
        return ("glob pattern, not a single path", s)
    if not s.startswith("/"):
        return ("relative to an unstated base", s)
    return (RESOLVABLE, s)


class StampMalformed(Exception):
    """A stamp container exists but is not a mapping. NOT the same as absent —
    fail closed, the way wf_corpus_coverage.py and gate_stamp_parity.py do
    [codex on orch#820]."""


def _gate_stamp(payload: dict) -> dict | None:
    """The canonical location, then the legacy one. Both, because an artifact
    that only has the legacy key still makes a claim.

    Raises ``StampMalformed`` when a container is PRESENT but the wrong shape:
    collapsing that to "no stamp" reports a broken artifact as an honestly
    uncertified one.
    """
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        raise StampMalformed(f"`metadata` is {type(meta).__name__}, not an object")
    if isinstance(meta, dict) and "wf_gate_metadata" in meta:
        stamp = meta["wf_gate_metadata"]
        if not isinstance(stamp, dict):
            raise StampMalformed("`metadata.wf_gate_metadata` is "
                                 f"{type(stamp).__name__}, not an object")
        return stamp
    if "wf_gate_metadata" in payload:
        stamp = payload["wf_gate_metadata"]
        if not isinstance(stamp, dict):
            raise StampMalformed("top-level `wf_gate_metadata` is "
                                 f"{type(stamp).__name__}, not an object")
        return stamp
    return None


def references(stamp: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """``(resolvable_paths, unresolvable)`` for every reference in the stamp.

    Both halves are returned because dropping the second one is how a probe
    reports "checkable" over a claim it never checked.
    """
    ok: set[str] = set()
    bad: set[tuple[str, str]] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            hit = classify_reference(node)
            if hit is None:
                return
            kind, detail = hit
            (ok.add(detail) if kind == RESOLVABLE else bad.add((kind, detail)))

    walk(stamp)
    return sorted(ok), sorted(bad, key=lambda kv: (kv[1], kv[0]))


def referenced_paths(stamp: dict) -> list[str]:
    """The resolvable references only. Callers that need the whole picture must
    use :func:`references` — this name exists for the resolve-and-stat step."""
    return references(stamp)[0]


def probe_one(label: str, rel: str, artifacts: pathlib.Path = ARTIFACTS) -> dict:
    path = artifacts / rel
    row = {"artifact": label, "path": str(path)}
    if not path.exists():
        return {**row, "state": STATE_ABSENT,
                "detail": "the serving artifact is not on disk"}
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception as exc:                     # noqa: BLE001
        return {**row, "state": STATE_UNREADABLE,
                "detail": f"could not be read/parsed ({exc}) — an unreadable "
                          f"artifact is not an absent claim"}
    # [codex on orch#820, round 3] `json.loads` succeeding does not make the
    # payload an artifact. `[]`, `null` and scalars are all valid JSON, and
    # `_gate_stamp` went straight to `.get` on them — an AttributeError that
    # crashed the whole probe instead of emitting one actionable state for one
    # artifact. Validate the ROOT before reaching into it.
    if not isinstance(payload, dict):
        kind = "null" if payload is None else type(payload).__name__
        return {**row, "state": STATE_MALFORMED,
                "detail": f"the artifact parses as JSON but its root is {kind}, "
                          f"not an object — it can carry no stamp at all, which "
                          f"is a broken artifact, not an uncertified one"}
    try:
        stamp = _gate_stamp(payload)
    except StampMalformed as exc:
        return {**row, "state": STATE_MALFORMED,
                "detail": f"a gate-stamp container is present but malformed "
                          f"({exc}) — a broken stamp is not an absent one"}
    if stamp is None:
        return {**row, "state": STATE_NO_STAMP,
                "detail": "no wf_gate_metadata in either the canonical "
                          "metadata.wf_gate_metadata or the legacy top-level key "
                          "— this artifact makes NO claim that could be checked"}
    refs, unresolvable = references(stamp)
    if not refs and not unresolvable:
        # A claim naming nothing cannot be checked, whatever else it says.
        return {**row, "state": STATE_NOTHING_TO_CHECK,
                "detail": "the stamp references no path at all — there is "
                          "nothing to resolve, so the claim cannot be checked"}
    total = len(refs) + len(unresolvable)
    dangling = [p for p in refs if not pathlib.Path(p).exists()]
    # Both lists ride on every row. A missing path is the stronger statement so
    # it names the state, but an unresolvable reference is never dropped from
    # the record just because a worse finding outranked it.
    row = {**row, "referenced": refs,
           "unresolvable": [list(u) for u in unresolvable]}
    tail = (f"; a further {len(unresolvable)} reference(s) are path-shaped but "
            f"unresolvable here" if unresolvable else "")
    if dangling:
        return {**row, "state": STATE_DANGLING,
                "detail": f"{len(dangling)} of {total} referenced path(s) do "
                          f"not exist: " + ", ".join(dangling[:3]) + tail,
                "dangling": dangling}
    if unresolvable:
        why = "; ".join(f"{d} ({k})" for k, d in unresolvable[:3])
        return {**row, "state": STATE_UNRESOLVABLE,
                "detail": f"{len(unresolvable)} of {total} reference(s) are "
                          f"path-shaped but cannot be resolved here: {why} — a "
                          f"reference this probe cannot check is not a checked one"}
    return {**row, "state": STATE_CLAIM,
            "detail": f"all {total} referenced path(s) resolve — the claim "
                      f"can be CHECKED (this says nothing about whether it is a "
                      f"good claim)"}


def probe(artifacts: pathlib.Path = ARTIFACTS) -> list[dict]:
    return [probe_one(label, rel, artifacts) for label, rel in SERVING]


def render(rows: list[dict]) -> str:
    out = ["serving-artifact certification probe", ""]
    for r in rows:
        out.append(f"[{r['state']}] {r['artifact']}")
        out.append(f"    {r['detail']}")
    n = sum(1 for r in rows if r["state"] in ACTIONABLE)
    out.append("")
    out.append(f"PROBE: {n} serving artifact(s) with no checkable claim"
               if n else f"PROBE: all {len(rows)} serving artifacts make a "
                         f"checkable claim")
    out.append("NOTE: this establishes that a claim EXISTS and resolves. It does "
               "NOT judge it —\n      fold counts are manifest rows and say "
               "nothing about leakage or quality.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = probe()
    print(json.dumps(rows, indent=2) if args.json else render(rows))
    return 1 if any(r["state"] in ACTIONABLE for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
