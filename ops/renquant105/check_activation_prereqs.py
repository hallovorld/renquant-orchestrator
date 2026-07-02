#!/usr/bin/env python3
"""N1b activation guard (Codex #232 review r2): refuse to activate live rq105
collection until BOTH #224 (broker-regulatory/settlement envelope) and #227
(Stage-1 measurement-integrity pins — gate-input census, order type,
quote-feed quality) have landed on the checked-out `main`.

Why: #229 (H2 execution roadmap)'s own dependency DAG marks N1b (live
collector activation) BLOCKED on #224+#227 — activating before they land
risks a retroactively-dirty pilot corpus (the exact failure #229's DAG exists
to prevent). Correct scheduling code is not sufficient if the documented next
command (`launchctl bootstrap ...`) can still run ahead of that gate — so this
script is a MECHANICAL refusal, not just a README warning.

Detection method (heuristic, not cryptographic): grep the canonical RFC
(`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`) for
the distinctive content markers #224 and #227 each add to its REVISION
header ("amendment A2" / "amendment A5"). This proves the RFC *text* has
landed; it is not a proof that the corresponding CODE (if any) has also
landed, nor a substitute for checking merge status directly via `gh pr view`.
An operator relying solely on this script's exit code, rather than also
confirming #224/#227 are actually merged, is trusting a heuristic — the
error message says so.

Exit 0: both prerequisites detected, activation may proceed.
Exit 1: at least one prerequisite missing, activation MUST NOT proceed.
"""
from __future__ import annotations

import sys
from pathlib import Path

_RFC_RELATIVE_PATH = (
    "doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md"
)

# Distinctive, unique-enough substrings each PR's RFC integration adds to the
# REVISION header. Not just "r13"/"r14" alone (a bare revision number is too
# easy to coincidentally collide with future unrelated revisions) — paired
# with the amendment name each PR's integration fork used verbatim.
_PREREQ_MARKERS: dict[str, tuple[str, str]] = {
    "#224 (broker-regulatory/settlement envelope)": ("r13", "amendment A2"),
    "#227 (Stage-1 measurement-integrity pins)": ("r14", "amendment A5"),
}


def find_rfc_path(repo_root: Path) -> Path:
    return repo_root / _RFC_RELATIVE_PATH


def check_prereqs(repo_root: Path) -> tuple[bool, list[str]]:
    """Return (all_present, missing_descriptions)."""
    rfc_path = find_rfc_path(repo_root)
    if not rfc_path.exists():
        return False, [f"RFC file not found at {rfc_path} — cannot verify prerequisites"]
    text = rfc_path.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for name, (rev_marker, amendment_marker) in _PREREQ_MARKERS.items():
        if rev_marker not in text or amendment_marker not in text:
            missing.append(name)
    return (len(missing) == 0), missing


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    # Resolve the repo root the SAME way the wrappers/liveness check do: this
    # script lives at ops/renquant105/, repo root is two levels up.
    repo_root = Path(__file__).resolve().parents[2]

    ok, missing = check_prereqs(repo_root)
    if ok:
        print(
            "[check_activation_prereqs] OK — #224 and #227 markers both found in "
            f"{_RFC_RELATIVE_PATH}. This is a heuristic text-content check, NOT a "
            "cryptographic proof of merge status — confirm both PRs are actually "
            "merged (e.g. `gh pr view 224 227 --repo hallovorld/renquant-orchestrator "
            "--json state`) before proceeding, especially if this checkout is not a "
            "fresh `git pull --ff-only` of `main`."
        )
        return 0

    print(
        "[check_activation_prereqs] REFUSED — N1b live activation is BLOCKED.\n"
        "Missing prerequisite(s):\n  - " + "\n  - ".join(missing) + "\n\n"
        "Per #229's dependency DAG, live rq105 collection must not start until "
        "BOTH #224 (broker-regulatory/settlement envelope) and #227 (Stage-1 "
        "measurement-integrity pins) have merged to main — activating early risks "
        "a retroactively-dirty pilot corpus. Do NOT run `launchctl bootstrap` for "
        "any rq105 job. Re-run this check after pulling a fresh main checkout once "
        "both PRs have merged.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
