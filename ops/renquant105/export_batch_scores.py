#!/usr/bin/env python3
"""rq105: export the FROZEN batch score vector for today's session (N1 open
item #1 — the producer for shadow_realtime_serving --batch-scores-json).

Reads the latest daily FULL run strictly BEFORE today's session from
runs.alpaca.db (the 13:55 PT batch of the prior session is the class-A frozen
signal for today, #208 §6) and writes:

  data/rq105/batch_scores_<today>.json        flat {ticker: panel_score}
  data/rq105/batch_scores_<today>.meta.json   {run_id, score_kind, n, exported_at, ...}

Read-only against the DB; writes only the dedicated data/rq105/ path. Fails
loudly (exit 1 + ntfy via wrapper) if no qualifying run exists — the shadow
serving driver then skips the day rather than serving a stale vector silently.

Codex #236 review (round 2) — this module previously selected the
lexicographically-largest run_id with >=80 candidate_scores rows straight off
`candidate_scores`, with no check that a `pipeline_runs` row for it existed,
that it completed successfully, that it carried a strategy/artifact/config
fingerprint, or that it was actually the canonical latest run for that date
(run_id's random uuid suffix does not sort chronologically). It also wrote the
score/meta JSON as two separate direct-to-final-path writes (a crash between
them exposes a mismatched pair) and accepted as few as 40/80 non-null scores
with no visibility into which tickers were missing. Fixed: selection now joins
`pipeline_runs` and requires a real completed live run with a bound
fingerprint (config_hash + non-empty artifact_hashes), ordered by the run's
own `created_at` timestamp (not the run_id string); the score and meta files
are each written atomically (temp+fsync+rename — see
batch_scores_bundle.py's module docstring for why the PAIR is not a single
atomic transaction, and how verify_bundle compensates); coverage is measured
against the run's own persisted candidate roster (role='candidate', per the
2026-05-04 "full pre-veto candidate list" mandate — the concrete, run-bound
expected universe, not an external/driftable definition) with the missing
tickers recorded by name.

Codex #236 review (round 3) — round 2's selection accepted the latest
qualifying run from ANY date strictly before today, then stamped
session_date=today regardless of how old the source run actually was; a
multi-day pipeline outage could silently republish a stale vector as today's
"fresh" bundle, undetected because replay verification only checked the
stamp against itself. Fixed: the source run's date must now equal exactly
the immediately preceding NYSE session (via
batch_scores_bundle.expected_previous_session, the same
pandas_market_calendars primitive used elsewhere this session) — no
fallback to an older run if that exact session has no qualifying run. The
run's actual `run_date` is persisted as `source_run_date` in the meta, and
verified again on the replay side (batch_scores_bundle.verify_bundle).

2026-08-05 (operator directive — "105 应该用 104 prod 的模型"): the wrapper's
default is back to ``prod`` — rq105's frozen vector comes from the run that
placed the day's real orders. The blend lane keeps running; rq105 just stops
sourcing from it. Two things changed with it, and both are consequences of prod
becoming the LOAD-BEARING path rather than the unused branch:

  * ``REQUIRED_BROKER_MODE`` mapped ``prod -> None``, i.e. NO lane check: a
    mispointed DB would have exported a shadow lane's vector stamped
    ``score_source="prod"`` with nothing to say so. It is now ``LANE_EVIDENCE``
    and every source names a required ``broker_mode``. Safe and MEASURED, not
    assumed: ``broker_mode`` is ``'alpaca'`` on 40 of the last 40 live prod
    runs `[VERIFIED — 2026-08-05]`.
  * "prod" no longer means "the single-artifact model". Since the z-blend
    fullbook went live, PROD itself scores with a two-component composite
    `[VERIFIED — 17 of those 40 runs carry two resolved component pins]`. The
    word names the LANE whose vector rq105 replays.

2026-07-28 (superseded operator directive — "105 直接换成 blend 模型"): the exporter can
now source the frozen vector from the BLEND composite lane instead of prod.
``RQ105_SCORE_SOURCE`` selects the source (``prod`` default / ``blend``);
``blend`` reads ``runs.alpaca_shadow_blend.db`` — the isolated read-only lane
daily_104.sh Step 5 (umbrella#535) populates by running the FULL funnel with
the pinned ``strategy_config.shadow_blend.json`` profile (pipeline#218
``kind="blend"``: z(prod panel-ltr) + z(clf top-decile), both component pins
fail-closed inside the pipeline). Sourcing from the lane DB — rather than
re-scoring here — keeps the identity pins single-sourced in the pinned
strategy profile and this repo free of scorer internals. Blend mode adds two
fail-closed guards on top of the shared selection/health/fingerprint gates:
the source run's ``broker_mode`` must be ``alpaca_shadow_blend`` (proves the
DB really is the lane, not a mispointed prod DB) and the run's
``artifact_hashes`` must carry BOTH resolved blend component hashes (proves
the composite actually loaded its two pinned components). Every export (both
modes) now stamps a ``scorer_identity`` block into the meta so each
shadow-realtime record is attributable to the exact model that produced its
frozen vector. ONE-LINE REVERT: set ``RQ105_SCORE_SOURCE=prod`` (or flip the
default line in run_batch_scores_export.sh back).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from batch_scores_bundle import canonical_hash, expected_previous_session  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
#: The Step-5 shadow-blend lane DB (daily_104.sh, RENQUANT_READONLY_TAG=
#: alpaca_shadow_blend) — disjoint from BOTH prod (alpaca) and the legacy
#: PatchTST shadow (alpaca_shadow).
BLEND_DB = os.path.join(RQ, "data/runs.alpaca_shadow_blend.db")
OUT_DIR = os.path.join(RQ, "data", "rq105")

#: score_source -> required run_bundle.broker_mode (None = unenforced).
#: prod keeps broker_mode unenforced: pre-existing behavior, and older prod
#: bundles may predate the field — the revert path must stay byte-identical
#: to today's working prod export. blend ENFORCES the lane tag: pointing the
#: exporter at the wrong DB is exactly the new failure class this switch
#: introduces, so it fails closed.
#: Per-source LANE EVIDENCE. Every source names a required ``broker_mode`` —
#: none may be ``None``.
#:
#: `prod` carried ``None`` from 2026-07-28 to 2026-08-05, i.e. NO lane check at
#: all: a mispointed DB would have exported a shadow lane's vector stamped
#: `score_source="prod"` and nothing would have said so. That was tolerable
#: only while prod was the unused branch. The 2026-08-05 directive makes prod
#: the LOAD-BEARING path, so it gets the same evidence the blend path has had.
#: Enforcing it is safe here and MEASURED, not assumed: `broker_mode` is
#: `'alpaca'` on 40 of the last 40 live prod runs
#: `[VERIFIED — 2026-08-05, runs.alpaca.db]`.
#:
#: `min_blend_components` stays 0 for prod DELIBERATELY. Prod does score with a
#: two-component composite today, but that is a fact about the current pinned
#: profile, not about the lane's identity — gating the exporter on it would
#: fail-close rq105 the day prod's profile changes, which is the wrong object
#: to check.
LANE_EVIDENCE: dict[str, dict[str, object]] = {
    "prod": {"broker_mode": "alpaca", "min_blend_components": 0},
    "blend": {"broker_mode": "alpaca_shadow_blend", "min_blend_components": 2},
}


def _default_db_for(score_source: str) -> str:
    """Module-global lookup at CALL time (not import time) so tests can
    monkeypatch DB/BLEND_DB the same way they already monkeypatch MIN_ROWS."""
    return DB if score_source == "prod" else BLEND_DB
# 2026-07-17 (light-signal-day fix; supersedes the round-2 MIN_ROWS=25
# absolute floor). The 2026-07-16 session produced a LEGITIMATE 5-row
# candidate roster (only 6 tickers entered the buy scan on a light-signal
# day; run 2026-07-16-live-a24a8be1: panel_contract.ok=True, full
# fingerprints, 100% covered, real buys placed) and the absolute floor
# rejected it — starving the entire rq105 class-A chain for the day. The
# floor's original job was excluding the anomalous pre-operational
# 2026-04-23..27 cluster (2-10 rows). That cluster is now excluded by
# THREE independent, stronger evidence checks, each verified against the
# real DB (all five cluster runs fail all three; the 07-16 run passes all):
#   1. `_fingerprint_gaps` (config_hash/artifact_hashes/watchlist_hash —
#      the cluster predates run-bundle fingerprinting entirely),
#   2. `_health_gaps` below: run_bundle.panel_contract.ok must be True
#      (the cluster has no panel_contract at all), the run must NOT have
#      been buy_blocked/skip_buys (a sell-only or containment-mode run
#      never ran the buy funnel its scores are meant to represent — this
#      also excludes e.g. the 2026-07-16 20:55 sell-only guard run), and
#   3. training_cutoff + model_content_sha256 must be present in the
#      bundle (the G4 provenance chain, populated for every healthy full
#      run from 2026-07-16 onward).
# MIN_ROWS therefore drops to a bare non-empty sanity check. Residual gap
# (unchanged in kind from the MIN_COVERAGE_FRACTION note below): a
# completed, contract-clean run whose candidate PERSISTENCE was partially
# truncated — remaining rows 100% self-consistent — is admitted; #227's
# census owns the structural fix, and the ops-layer rq104 degradation
# sentinel (GOAL-5 AC1) independently alarms on zero/thin-candidate
# streaks within one session.
MIN_ROWS = 1

# Fraction of the run's OWN persisted candidate roster (role='candidate', see
# module docstring) that must carry a non-null panel_score. NOT sourced from
# an established repo-wide census threshold — #227 (Stage-1 measurement-
# integrity pins / gate-input census) is still an open design doc, not yet
# shipped as code, so no canonical "expected universe" utility exists to defer
# to. 0.9 is a deliberately conservative interim floor chosen to clearly
# reject the kind of ~50% coverage collapse Codex's review flagged; replace
# with #227's real Stage-1 census requirement once it lands in code.
#
# Residual limitation (Codex round 2): this denominator is still the run's
# OWN roster, not an external expected-universe count — a genuine watchlist-
# based check was investigated and rejected here, because this pipeline's
# candidate roster is legitimately only 24-58% of the 145-name watchlist on
# ordinary days (feature-data availability, not a defect), so requiring 90%
# watchlist coverage would reject every real run. MIN_ROWS above is the
# concrete, evidence-based mitigation for the specific gap this leaves (a
# partial run whose truncated roster is nonetheless 100% self-consistent);
# it does not fully close the structural gap #227 is meant to close.
MIN_COVERAGE_FRACTION = 0.9


def _atomic_write_json(path: str, payload) -> None:
    """temp file in the same dir + fsync + rename: a reader sees either the
    old complete file or the new complete file, never a partial write."""
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)


def _select_source_run(con: sqlite3.Connection, expected_run_date: str):
    """Select the canonical completed live run from EXACTLY
    `expected_run_date` (the immediately preceding NYSE session — computed by
    the caller via batch_scores_bundle.expected_previous_session, NOT "any
    date before today": round 2 accepted any qualifying run strictly before
    today, so a multi-day pipeline outage would silently republish however-
    old a vector was last successfully produced. Ordered by the run's own
    created_at (pipeline_runs), not the run_id string — run_id's trailing
    uuid does not sort chronologically, so two live runs on the same date
    could previously resolve to an arbitrary one.

    Requires a `pipeline_runs` row (proves the run actually completed through
    to record_pipeline_run, not just a partial candidate_scores write) with
    run_type='live' (a real column check, not the previous run_id LIKE
    '%-live-%' string match) and a non-empty `strategy`.

    Returns (run_id, run_date, run_bundle: dict) or None.
    """
    row = con.execute(
        "select pr.run_id, pr.run_date, pr.run_bundle_json, count(cs.ticker) as n "
        "from pipeline_runs pr "
        "join candidate_scores cs "
        "  on cs.run_id = pr.run_id and cs.role = 'candidate' "
        "  and cs.panel_score is not null "
        "where pr.run_type = 'live' "
        "  and pr.run_date = ? "
        "  and pr.strategy is not null and pr.strategy != '' "
        "group by pr.run_id "
        "having n >= ? "
        "order by pr.created_at desc "
        "limit 1",
        (expected_run_date, MIN_ROWS),
    ).fetchone()
    if not row:
        return None
    run_id, run_date, run_bundle_raw, _n = row
    try:
        run_bundle = json.loads(run_bundle_raw) if run_bundle_raw else {}
    except (TypeError, ValueError):
        run_bundle = {}
    return run_id, run_date, run_bundle


# panel + global_calibration are the two "primary runtime artifacts"
# resolve_artifact_paths always aliases regardless of which underlying
# config-field variant is set (ranking.panel_scoring.artifact_path vs.
# panel_ltr.artifact_path fallback), so requiring the alias is both
# necessary and sufficient to prove the class-A signal's own inputs (panel
# score + calibration) are hashed. Everything else a config's
# artifact_paths may carry (shadow lanes, auxiliary ngboost/embedding
# heads, quality-floor thresholds, diagnostic scans, meta-label models,
# regime-conditional PATTERN strings that are never real files) is
# provably not an input to the panel score itself — see
# intraday_session_inputs.py's _REQUIRED_ARTIFACT_KEYS for the full
# reasoning (Codex #399 review; this module mirrors that fix).
_REQUIRED_ARTIFACT_KEYS = frozenset({"panel", "global_calibration"})


def _fingerprint_gaps(run_bundle: dict) -> list[str]:
    gaps = []
    if not run_bundle.get("config_hash"):
        gaps.append("config_hash")
    artifact_hashes = run_bundle.get("artifact_hashes") or {}
    if not artifact_hashes:
        gaps.append("artifact_hashes")
    else:
        missing_required = _REQUIRED_ARTIFACT_KEYS - {
            k for k, v in artifact_hashes.items() if v
        }
        if missing_required:
            gaps.append(f"artifact_hashes({','.join(sorted(missing_required))})")
    if not run_bundle.get("watchlist_hash"):
        gaps.append("watchlist_hash")
    return gaps


def _health_gaps(run_bundle: dict) -> list[str]:
    """Independent evidence the source run was a healthy FULL daily.

    Replaces the retired absolute row floor (see MIN_ROWS note): a class-A
    frozen vector must come from a run that (a) loaded a contract-clean
    panel artifact, (b) actually executed the buy funnel (not a sell-only /
    buy-blocked containment run), and (c) carries the modern training
    provenance chain. Each check fails closed on absent evidence.
    """
    gaps = []
    contract = run_bundle.get("panel_contract") or {}
    if contract.get("ok") is not True:
        gaps.append("panel_contract.ok")
    flags = run_bundle.get("pipeline_flags") or {}
    if flags.get("buy_blocked") is not False or flags.get("skip_buys") is not False:
        gaps.append("full_buy_run(pipeline_flags)")
    if not run_bundle.get("training_cutoff"):
        gaps.append("training_cutoff")
    if not run_bundle.get("model_content_sha256"):
        gaps.append("model_content_sha256")
    return gaps


def _lane_gaps(run_bundle: dict, evidence: dict) -> list[str]:
    """Fail-closed lane guards for EITHER source — the evidence that the DB
    really is the lane the caller named.

    (a) the run's ``broker_mode`` is the lane's own tag, and
    (b) for a composite lane, the pipeline resolved + hashed enough component
        pins to prove the composite actually loaded.
    """
    gaps = []
    required_broker_mode = evidence["broker_mode"]
    broker_mode = run_bundle.get("broker_mode")
    if broker_mode != required_broker_mode:
        gaps.append(
            f"broker_mode={broker_mode!r} (require {required_broker_mode!r})"
        )
    min_components = int(evidence["min_blend_components"])
    n_components = len(_blend_component_hashes(run_bundle))
    if n_components < min_components:
        gaps.append(
            f"artifact_hashes({n_components} resolved blend component pin(s), "
            f"require >= {min_components})")
    return gaps


def _blend_component_hashes(run_bundle: dict) -> dict[str, str]:
    """The resolved blend component artifact hashes, e.g.
    ``ranking.panel_scoring.components[0].artifact_path`` — present iff the
    run's config carried a composite panel_scoring block whose components the
    artifact resolver actually resolved.

    This docstring used to end "Empty for prod runs." That is NO LONGER TRUE
    and was load-bearing: since the z-blend fullbook went live, PROD scores
    with a two-component composite too `[VERIFIED 2026-08-05 — 17 of the last
    40 live prod runs carry two component pins]`. A composite panel is not a
    lane identity, which is why :data:`LANE_EVIDENCE` distinguishes them.
    """
    artifact_hashes = run_bundle.get("artifact_hashes") or {}
    return {
        k: v
        for k, v in sorted(artifact_hashes.items())
        if ".components[" in k and v
    }


def _scorer_identity(run_bundle: dict, score_source: str) -> dict:
    """The WHICH-MODEL stamp for the meta bundle (2026-07-28): every
    shadow-realtime record replayed against this vector must be attributable
    to the exact scorer that produced it, not inferred from dates."""
    artifact_hashes = run_bundle.get("artifact_hashes") or {}
    return {
        "score_source": score_source,
        "broker_mode": run_bundle.get("broker_mode"),
        "config_hash": run_bundle.get("config_hash"),
        "panel_artifact_sha256": artifact_hashes.get("panel"),
        "blend_component_sha256s": _blend_component_hashes(run_bundle),
        "model_content_sha256": run_bundle.get("model_content_sha256"),
        "training_cutoff": run_bundle.get("training_cutoff"),
    }


def main(
    *,
    db_path: str | None = None,
    out_dir: str | None = None,
    today: str | None = None,
    score_source: str | None = None,
) -> int:
    score_source = (
        score_source
        if score_source is not None
        else os.environ.get("RQ105_SCORE_SOURCE", "prod")
    ).strip().lower()
    if score_source not in LANE_EVIDENCE:
        print(
            f"unknown RQ105_SCORE_SOURCE={score_source!r} — refusing to guess "
            f"(valid: {', '.join(sorted(LANE_EVIDENCE))})",
            file=sys.stderr,
        )
        return 1
    db_path = db_path or _default_db_for(score_source)
    out_dir = out_dir or OUT_DIR
    today = today or dt.date.today().isoformat()
    try:
        expected_run_date = expected_previous_session(today)
    except ValueError as exc:
        print(f"cannot compute expected prior session for {today}: {exc}", file=sys.stderr)
        return 1
    con = sqlite3.connect(db_path)

    selected = _select_source_run(con, expected_run_date)
    if not selected:
        print(
            f"no qualifying completed live run for the expected prior "
            f"session {expected_run_date} (immediately preceding NYSE "
            f"session before {today}) — refusing to fall back to an older "
            "run (joined pipeline_runs: requires run_type='live', a "
            "recorded strategy, and >= %d role='candidate' rows with "
            "non-null panel_score)" % MIN_ROWS,
            file=sys.stderr,
        )
        return 1
    run_id, run_date, run_bundle = selected

    health = _health_gaps(run_bundle)
    if health:
        print(
            f"run {run_id} fails class-A health evidence: "
            f"{', '.join(health)} — a frozen vector must come from a "
            "contract-clean, full-buy-funnel run with training provenance; "
            "refusing to export",
            file=sys.stderr,
        )
        return 1

    gaps = _fingerprint_gaps(run_bundle)
    if gaps:
        print(
            f"run {run_id} missing required fingerprint field(s) in its "
            f"run_bundle_json: {', '.join(gaps)} — refusing to export an "
            "unfingerprinted vector",
            file=sys.stderr,
        )
        return 1

    lane_gaps = _lane_gaps(run_bundle, LANE_EVIDENCE[score_source])
    if lane_gaps:
        print(
            f"run {run_id} fails {score_source} lane evidence: "
            f"{', '.join(lane_gaps)} — the DB at {db_path} is not the "
            f"{score_source} lane, or the run did not score with the "
            "components that lane requires; refusing to export",
            file=sys.stderr,
        )
        return 1

    roster = con.execute(
        "select ticker, panel_score from candidate_scores "
        "where run_id=? and role='candidate'",
        (run_id,),
    ).fetchall()
    if not roster:
        print(f"run {run_id} has a pipeline_runs row but no role='candidate' "
              "rows — inconsistent DB state, refusing to export", file=sys.stderr)
        return 1

    scores = {t: float(s) for t, s in roster if s is not None}
    missing_tickers = sorted(t for t, s in roster if s is None)
    universe_n = len(roster)
    coverage = len(scores) / universe_n if universe_n else 0.0

    if coverage < MIN_COVERAGE_FRACTION:
        print(
            f"run {run_id} coverage {coverage:.1%} ({len(scores)}/{universe_n} "
            f"role='candidate' rows scored) is below the "
            f"{MIN_COVERAGE_FRACTION:.0%} floor — refusing to export "
            f"(missing: {', '.join(missing_tickers) or 'n/a'})",
            file=sys.stderr,
        )
        return 1

    os.makedirs(out_dir, exist_ok=True)
    score_content_hash = canonical_hash(scores)
    source_run_bundle_hash = canonical_hash(run_bundle)

    score_path = os.path.join(out_dir, f"batch_scores_{today}.json")
    meta_path = os.path.join(out_dir, f"batch_scores_{today}.meta.json")

    # Write the score payload first (temp+fsync+rename), THEN the meta bundle
    # that names its hash — a crash between the two leaves either (a) neither
    # file updated (meta write never started) or (b) a fresh score file with
    # a STALE meta pointing at the OLD score hash, which the replay-side
    # verifier (run_shadow_serving.sh) will detect and refuse, never a
    # meta claiming a hash the score file doesn't actually have.
    _atomic_write_json(score_path, scores)
    _atomic_write_json(meta_path, {
        "run_id": run_id,
        "score_kind": "panel_score",
        "score_source": score_source,
        "source_db": os.path.basename(db_path),
        "scorer_identity": _scorer_identity(run_bundle, score_source),
        "n": len(scores),
        "universe_n": universe_n,
        "coverage": coverage,
        "missing_tickers": missing_tickers,
        "session_date": today,
        "source_run_date": run_date,
        "score_content_sha256": score_content_hash,
        "source_run_bundle_sha256": source_run_bundle_hash,
        "exported_at": dt.datetime.utcnow().isoformat() + "Z",
    })
    print(
        f"exported {len(scores)}/{universe_n} frozen {score_source} scores "
        f"(coverage {coverage:.1%}) from {run_id} for session {today}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
