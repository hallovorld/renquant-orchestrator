"""Shared canonical-hash + verification logic for the rq105 frozen batch-score
bundle (score JSON + meta JSON). A single implementation used by BOTH the
producer (export_batch_scores.py, at write time) and the consumer
(run_shadow_serving.sh, via verify_bundle_cli, at read time) so the two sides
can never independently drift out of agreement on what "the hash" means
(Codex #236 round 2 — replay previously trusted session_date/run_id with no
verification that the on-disk bundle was actually today's or unmodified)."""
from __future__ import annotations

import hashlib
import json
import sys


def canonical_hash(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def verify_bundle(score_path: str, meta_path: str, *, today: str) -> tuple[bool, str]:
    """Return (ok, reason). Checks the meta's session_date is today and the
    meta's recorded score_content_sha256 matches a fresh hash of the score
    file currently on disk — catches a stale leftover bundle from a prior day
    that was never cleaned up, or an on-disk score file that was corrupted /
    modified after export without a matching meta update."""
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read/parse meta {meta_path}: {exc}"

    session_date = meta.get("session_date")
    if session_date != today:
        return False, (
            f"stale bundle: meta.session_date={session_date!r} != today={today!r} "
            "(a prior day's export was never cleaned up, or today's export "
            "has not run yet)"
        )

    expected_hash = meta.get("score_content_sha256")
    if not expected_hash:
        return False, "meta has no score_content_sha256 — bundle predates hashing, refuse"

    try:
        with open(score_path) as f:
            scores = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read/parse score file {score_path}: {exc}"

    actual_hash = canonical_hash(scores)
    if actual_hash != expected_hash:
        return False, (
            f"score content hash mismatch: on-disk={actual_hash} "
            f"meta-recorded={expected_hash} (corruption or tampering "
            "between export and replay)"
        )
    return True, "ok"


def _cli(argv: list[str]) -> int:
    """python3 -m batch_scores_bundle verify <scores.json> <meta.json> <today-iso>
    exits 0 if the bundle is valid for `today`, 1 otherwise (message on stderr)."""
    if len(argv) != 4 or argv[0] != "verify":
        print("usage: batch_scores_bundle.py verify <scores.json> <meta.json> <today-iso>",
              file=sys.stderr)
        return 2
    _, score_path, meta_path, today = argv
    ok, reason = verify_bundle(score_path, meta_path, today=today)
    print(reason, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
