#!/usr/bin/env python3
"""How many DISTINCT models hide behind one admission fingerprint? (GOAL-4 / GOAL-6)

GOAL-4's blocker has been stated as "the WF gate cannot distinguish the artifacts". That
is a claim about the gate's *identity function*, and until now it was supported by four
artifacts sharing a recipe fingerprint. This measures it properly, on the bytes:

    recipe fingerprint   — what ADMISSION is keyed on: kind, feature_cols,
                           feature_norm_kind, contract keys, label_col, lookahead_days
                           and the semantic learner params. NO LEARNED PARAMETER.
    booster digest       — sha256 over `booster_raw_json`: the learned model itself.

The ratio between the two is the gate's **collapse factor** — how many genuinely
different trained models the admission key treats as one thing.

WHY THIS MATTERS FOR AN ENSEMBLE. An ensemble needs members that (a) differ and (b) can
be told apart by whatever admits them. This tool measures (a) directly. If (a) fails, the
programme is vacuous; if (a) holds and admission still collapses them, the blocker is
**attribution**, not diversity — a much more tractable statement.

IT ALSO READS THE PROMOTION SERIES. Staging candidates and rollback snapshots carry dates
in their filenames. Comparing each candidate's booster digest with the SERVED one answers
"was anything actually promoted?" on bytes rather than on logs.

WHAT A DIGEST MISMATCH IS AND IS NOT. Two artifacts with different booster digests hold
different learned models. It does NOT follow that their predictions differ materially,
and this tool does not score anything — scoring is the separate, gated study. Equally, a
staged candidate whose digest never appears in prod was not promoted **by byte identity**;
this tool does not read the reason, and a reason is not inferred here.

Read-only. Opens artifacts, writes nothing, never invokes git.

Exit codes: ``0`` clean, ``1`` at least one collapse group holds more than one distinct
booster, ``2`` usage/IO error — so a broken invocation cannot be mistaken for a clean
census.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys

STAGING = re.compile(r"weekly_(\d{4})(\d{2})(\d{2})T\d+Z\.staging\.json$")
ROLLBACK = re.compile(r"weekly_rollback_(\d{4}-\d{2}-\d{2})\.json$")


def booster_digest(payload: dict) -> str | None:
    """sha256 over the learned model, or None when the artifact carries none.

    `None` is returned rather than a digest of the empty string: an artifact with no
    booster and an artifact whose booster is empty must not collide into one identity,
    which is precisely the failure this tool exists to measure.
    """
    raw = payload.get("booster_raw_json")
    if raw is None:
        return None
    blob = raw.encode("utf-8") if isinstance(raw, str) else json.dumps(
        raw, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


#: A provenance container that exists but is not a JSON object. `(x or {}).get(...)` is
#: NOT a guard: a non-empty string is truthy, so the `or {}` never fires. This is the
#: third tool in one session to need this constant; it is named, not inlined.
MALFORMED = "MALFORMED_PROVENANCE"

#: An artifact whose admission identity could not be read at all. NEVER a shared key —
#: see `_identity_key`.
UNKNOWN = "UNKNOWN_ADMISSION_IDENTITY"


def recipe_fingerprint(payload: dict) -> str | None:
    """The admission key, read from the gate stamp — canonical first, legacy fallback.

    Returns `MALFORMED` when a provenance container is present but is not an object,
    `None` when the identity is simply absent, and otherwise `<fp>|<source>` so the
    caller can tell canonical from legacy from a bare `config_fingerprint`.

    Malformed and absent are different facts `[codex on orch#692]`, and neither is an
    identity. The earlier `(payload.get("metadata") or {}).get(...)` crashed with
    AttributeError on an artifact whose `metadata` is a string — measured, not
    hypothetical.
    """
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        return MALFORMED
    # Bound to a plain name before the lookup, deliberately. `(meta or {}).get(KEY)` is
    # behaviourally identical, but the repo-wide R8 invariant scan
    # (tests/test_twin_r8_canonical_gate_key.py) decides "did this reader consult the
    # canonical key" from the RECEIVER node, and a `BoolOp` receiver scores as
    # legacy-only. Writing it this way keeps a compliant reader legible to the check
    # that exists on main today, instead of depending on a detector fix that has not
    # landed yet.
    meta = meta or {}
    for node, source in ((meta.get("wf_gate_metadata"), "canonical"),
                         (payload.get("wf_gate_metadata"), "legacy")):
        if node is None:
            continue
        if not isinstance(node, dict):
            return MALFORMED
        usage = node.get("artifact_usage")
        if usage is not None and not isinstance(usage, dict):
            return MALFORMED
        fp = (usage or {}).get("candidate_recipe_fingerprint")
        if fp is not None and not isinstance(fp, str):
            return MALFORMED
        if fp:
            return f"{fp}|{source}"
    fp = payload.get("config_fingerprint")
    if fp is not None and not isinstance(fp, str):
        return MALFORMED
    return f"{fp}|config_fingerprint_no_gate_stamp" if fp else None


def _identity_key(row: dict) -> str:
    """The grouping key. Unknown and malformed identities get a key PER ARTIFACT.

    Reviewed `[codex on orch#692]`: *"multiple artifacts with no usable recipe
    fingerprint are grouped under None as though they shared one admission identity."*

    That is this census committing the exact collapse it exists to measure — two
    artifacts with NO identity were reported as "2 artifacts -> 2 distinct boosters",
    which reads as a 2:1 collapse. Absence of a shared key is not a shared key. So an
    unknown or malformed identity is made unique to its artifact and can never form a
    group larger than one.
    """
    fp = row["recipe_fingerprint"]
    if fp == MALFORMED:
        return f"{MALFORMED}::{row['artifact']}"
    if fp is None:
        return f"{UNKNOWN}::{row['artifact']}"
    return fp


def census(root: str, query: str) -> dict:
    rows, unreadable = [], []
    for path in sorted(glob.glob(os.path.join(root, query))):
        try:
            with open(path, "rb") as fh:
                payload = json.loads(fh.read())
        except (OSError, ValueError) as exc:
            unreadable.append({"artifact": os.path.basename(path),
                               "why": f"{type(exc).__name__}: {exc}"})
            continue
        if not isinstance(payload, dict):
            unreadable.append({"artifact": os.path.basename(path),
                               "why": f"top-level JSON is {type(payload).__name__}"})
            continue
        name = os.path.basename(path)
        rows.append({
            "artifact": name,
            "recipe_fingerprint": recipe_fingerprint(payload),
            "booster_sha256": booster_digest(payload),
            "n_features": len(payload.get("feature_cols") or []),
            "staging_date": (lambda m: f"{m[1]}-{m[2]}-{m[3]}" if m else None)(
                STAGING.search(name)),
            "rollback_date": (lambda m: m.group(1) if m else None)(
                ROLLBACK.search(name)),
        })

    # Grouped by IDENTITY KEY, and counted by it too. Counting members with the raw
    # fingerprint while keying on the identity key gave every unknown group
    # "0 artifact(s)" -- a silently wrong denominator inside the tool whose subject is
    # wrong denominators.
    groups: dict[str, set] = collections.defaultdict(set)
    members: dict[str, int] = collections.Counter()
    for r in rows:
        k = _identity_key(r)
        groups[k].add(r["booster_sha256"])
        members[k] += 1
    collapse = [{"identity_key": k, "n_artifacts": members[k],
                 "n_distinct_boosters": len(bs)}
                for k, bs in sorted(groups.items(), key=lambda kv: str(kv[0]))]

    n_malformed = sum(1 for r in rows if r["recipe_fingerprint"] == MALFORMED)
    n_unknown = sum(1 for r in rows if r["recipe_fingerprint"] is None)
    return {"root": os.path.basename(os.path.normpath(root)), "query": query,
            "n_artifacts": len(rows), "n_unreadable": len(unreadable),
            "n_malformed_identity": n_malformed,
            "n_unknown_identity": n_unknown,
            # A census missing subjects cannot certify one-identity-per-model, so it says
            # so in its own payload rather than leaving the caller to notice.
            "census_complete": not (unreadable or n_malformed or n_unknown),
            "unreadable": unreadable, "artifacts": rows, "collapse_groups": collapse,
            "scope_note": (
                "A booster digest mismatch means DIFFERENT LEARNED MODELS. It does not "
                "follow that their predictions differ materially — nothing is scored "
                "here. A staged candidate absent from prod was not promoted BY BYTE "
                "IDENTITY; no reason is inferred.")}


def promotion_series(rep: dict, served_artifact: str) -> dict:
    """Was any staged candidate actually promoted? Answered on bytes.

    `served_artifact` must be named explicitly. Guessing which file is served — by
    shortest name, or by mtime — is how a census ends up describing the wrong object.
    """
    by_name = {r["artifact"]: r for r in rep["artifacts"]}
    served = by_name.get(served_artifact)
    if served is None:
        return {"error": f"served artifact {served_artifact!r} not in the census — "
                         f"it must be named, never guessed"}
    staged = sorted((r for r in rep["artifacts"] if r["staging_date"]),
                    key=lambda r: r["staging_date"])
    rollbacks = sorted((r for r in rep["artifacts"] if r["rollback_date"]),
                       key=lambda r: r["rollback_date"])
    changes = [rollbacks[i]["rollback_date"] for i in range(1, len(rollbacks))
               if rollbacks[i]["booster_sha256"] != rollbacks[i - 1]["booster_sha256"]]
    return {
        "served_artifact": served_artifact,
        "served_booster_sha256": served["booster_sha256"],
        "n_staged_candidates": len(staged),
        "n_distinct_staged_boosters": len({r["booster_sha256"] for r in staged}),
        "n_staged_matching_served": sum(
            1 for r in staged if r["booster_sha256"] == served["booster_sha256"]),
        "staged": [{"date": r["staging_date"],
                    "booster_sha256": r["booster_sha256"],
                    "equals_served": r["booster_sha256"] == served["booster_sha256"]}
                   for r in staged],
        "rollback_snapshots": len(rollbacks),
        "rollback_booster_changed_on": changes,
        "scope_note": (
            "'No staged candidate equals the served booster' establishes that none was "
            "promoted by byte identity. It does NOT establish why — rejection, a "
            "failed job and a promotion that rewrites bytes are all consistent with it, "
            "and none is asserted here."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--query", default="*.json")
    ap.add_argument("--served-artifact",
                    help="basename of the SERVED artifact; enables the promotion series")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = census(a.root, a.query)
    except OSError as exc:
        print(f"booster census: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rep["n_artifacts"]:
        print(f"booster census: nothing under {a.root} matches {a.query} — the census "
              f"has no subjects, which is not the same as one identity per model",
              file=sys.stderr)
        return 2

    if a.served_artifact:
        rep["promotion"] = promotion_series(rep, a.served_artifact)

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0 if (rep["census_complete"] and not any(
            g["n_distinct_boosters"] > 1 for g in rep["collapse_groups"])) else 1

    print(f"{rep['n_artifacts']} artifact(s) under {rep['root']}/{rep['query']}, "
          f"{rep['n_unreadable']} unreadable, "
          f"{rep['n_malformed_identity']} malformed identity, "
          f"{rep['n_unknown_identity']} unknown identity")
    if not rep["census_complete"]:
        print("  INCOMPLETE CENSUS — subjects are missing or unidentifiable, so this "
              "cannot certify one admission identity per model")
    for g in rep["collapse_groups"]:
        flag = "COLLAPSE" if g["n_distinct_boosters"] > 1 else "one-to-one"
        print(f"  {flag:11s} identity {g['identity_key']}: "
              f"{g['n_artifacts']} artifact(s) -> "
              f"{g['n_distinct_boosters']} distinct booster(s)")
    p = rep.get("promotion")
    if p and "error" not in p:
        print(f"\nserved booster: {p['served_booster_sha256']}")
        print(f"  staged candidates: {p['n_staged_candidates']} "
              f"({p['n_distinct_staged_boosters']} distinct), "
              f"{p['n_staged_matching_served']} equal to the served booster")
        print(f"  rollback snapshots: {p['rollback_snapshots']}, "
              f"booster changed on: {p['rollback_booster_changed_on'] or 'never'}")
        print("  " + p["scope_note"])
    elif p:
        print(f"\npromotion series: {p['error']}", file=sys.stderr)
    print("\n" + rep["scope_note"])
    return 0 if (rep["census_complete"] and not any(
        g["n_distinct_boosters"] > 1 for g in rep["collapse_groups"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
