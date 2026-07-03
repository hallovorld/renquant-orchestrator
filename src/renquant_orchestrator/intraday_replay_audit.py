"""renquant105 Stage-1 replay/audit harness (RFC #208 §6 no-leak proof, §9).

Replays a recorded shadow session — the manifest + the append-only
``intraday_decisions_shadow.jsonl`` lines written by
:mod:`.intraday_session_scheduler` — against the SAME frozen inputs and
asserts decision reproducibility plus the §6 point-in-time invariants:

1. **class-A constancy**: every tick's ``signal_version`` equals the
   manifest's frozen signal, and the manifest's ``as_of`` strictly predates
   the session (the leak guard holds at rest, not just at record time);
2. **class-B constancy**: every tick carries the SAME
   ``gate_input_fingerprint``, and the manifest's captured gate inputs
   still re-fingerprint to it (mutation-at-rest detection);
3. **class-C/D integrity**: each tick's recorded live state re-hashes to
   the tick's own ``live_state_sha256`` (the only inputs allowed to differ
   across ticks are class C state and class D quotes — and they must be the
   ones the decision actually saw);
4. **decision reproducibility (§9 auditability)**: re-running the tick
   runner on the recorded frozen inputs, live state, counters and in-flight
   set — then re-applying the recorded window phase's entry-cutoff policy —
   reproduces the recorded decision payload byte-for-byte (canonical JSON);
5. **window-policy invariant (§11b)**: no recorded ``exits_only`` tick
   contains an entry intent.

Read-only over every input; the only optional write is the audit report
(``--report-out``). The tick runner is injected exactly like the
scheduler's (tests use deterministic fakes; the real binding requires the
pipeline pin, fail-closed).
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from renquant_artifacts import hash_jsonable

from .intraday_session_inputs import (
    SignalLeakError,
    assert_signal_predates_session,
    live_state_fingerprint,
    verify_session_start,
)
from .intraday_session_scheduler import (
    PHASE_EXITS_ONLY,
    RECORD_KIND_TICK,
    PipelineContractUnavailable,
    TickRunner,
    apply_entry_window_policy,
    bind_pipeline_tick_runner,
    normalize_tick_result,
)

log = logging.getLogger("renquant.intraday_replay_audit")

REPLAY_SCHEMA_VERSION = "rq105-intraday-replay-audit-v1"


@dataclass(frozen=True)
class ReplayMismatch:
    tick_index: int
    kind: str
    detail: str

    def to_record(self) -> dict[str, Any]:
        return {"tick_index": self.tick_index, "kind": self.kind, "detail": self.detail}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def load_session_ticks(
    shadow_log: str | Path, session_date: str
) -> list[dict[str, Any]]:
    """The session's tick records from the (multi-session) shadow JSONL."""
    ticks: list[dict[str, Any]] = []
    path = Path(shadow_log)
    if not path.exists():
        return ticks
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("kind") != RECORD_KIND_TICK:
                continue
            if str(row.get("session_date")) != str(session_date):
                continue
            ticks.append(row)
    ticks.sort(key=lambda r: int(r.get("tick_index", -1)))
    return ticks


def replay_session(
    *,
    manifest: Mapping[str, Any],
    ticks: Sequence[Mapping[str, Any]],
    tick_runner: TickRunner,
) -> dict[str, Any]:
    """Replay every recorded tick; return the audit report (see module doc)."""
    session_date = str(manifest.get("session_date") or "")
    class_a = dict(manifest.get("class_a") or {})
    class_b = dict(manifest.get("class_b") or {})
    mismatches: list[ReplayMismatch] = []

    # -- session-level §6 invariants ------------------------------------------
    try:
        assert_signal_predates_session(class_a, session_date)
    except SignalLeakError as exc:
        mismatches.append(ReplayMismatch(-1, "class_a_leak", str(exc)))
    if class_b:
        try:
            verify_session_start(class_b)
        except SignalLeakError as exc:
            mismatches.append(ReplayMismatch(-1, "class_b_mutated", str(exc)))
    elif ticks:
        mismatches.append(
            ReplayMismatch(-1, "class_b_missing", "manifest has ticks but no class_b")
        )
    scores = dict(class_a.get("scores") or {})
    recorded_score_sha = str(class_a.get("score_content_sha256") or "")
    if recorded_score_sha and hash_jsonable(scores) != recorded_score_sha:
        mismatches.append(
            ReplayMismatch(
                -1,
                "class_a_scores_mutated",
                "manifest scores no longer hash to score_content_sha256",
            )
        )

    signal_version = str(class_a.get("signal_version") or "")
    gate_fp = str(class_b.get("gate_input_fingerprint") or "")

    ticks_checked = 0
    for row in ticks:
        idx = int(row.get("tick_index", -1))
        fps = dict(row.get("fingerprints") or {})
        inputs = dict(row.get("inputs") or {})
        recorded = dict(row.get("decisions") or {})
        phase = str(row.get("window_phase") or "")

        # (1) class-A constancy across ticks.
        if str(fps.get("signal_version")) != signal_version:
            mismatches.append(
                ReplayMismatch(
                    idx,
                    "signal_version_drift",
                    f"tick has {fps.get('signal_version')!r}, manifest froze "
                    f"{signal_version!r}",
                )
            )
        # (2) class-B constancy across ticks.
        if str(fps.get("gate_input_fingerprint")) != gate_fp:
            mismatches.append(
                ReplayMismatch(
                    idx,
                    "gate_input_fingerprint_drift",
                    f"tick has {fps.get('gate_input_fingerprint')!r}, manifest "
                    f"froze {gate_fp!r}",
                )
            )
        # (3) class-C/D integrity: the recorded live state is what was hashed.
        live_state = dict(inputs.get("live_state") or {})
        if live_state_fingerprint(live_state) != str(fps.get("live_state_sha256")):
            mismatches.append(
                ReplayMismatch(
                    idx,
                    "live_state_integrity",
                    "recorded live_state does not re-hash to live_state_sha256",
                )
            )
        # (5) §11b window invariant at rest.
        if phase == PHASE_EXITS_ONLY:
            entry_kinds = [
                i
                for i in recorded.get("intents") or ()
                if str(i.get("kind", "")).lower() != "exit"
            ]
            if entry_kinds:
                mismatches.append(
                    ReplayMismatch(
                        idx,
                        "entry_after_cutoff",
                        f"{len(entry_kinds)} entry intent(s) recorded in an "
                        "exits_only tick",
                    )
                )

        # (4) decision reproducibility.
        counters_before = dict(inputs.get("counters_before") or {})
        try:
            raw = tick_runner(
                signal=class_a,
                session_start=class_b,
                live_state=live_state,
                session_counters=counters_before,
                in_flight_parent_intents=list(
                    inputs.get("in_flight_parent_intents") or ()
                ),
                exit_orders=list(inputs.get("exit_orders") or ()),
            )
            replayed = apply_entry_window_policy(
                normalize_tick_result(raw),
                phase=phase,
                counters_before=counters_before,
            )
        except Exception as exc:  # noqa: BLE001 — a replay crash IS a finding
            mismatches.append(
                ReplayMismatch(idx, "replay_error", f"{type(exc).__name__}: {exc}")
            )
            ticks_checked += 1
            continue
        if _canonical(replayed) != _canonical(recorded):
            mismatches.append(
                ReplayMismatch(
                    idx,
                    "decision_mismatch",
                    "replayed decisions differ from the recorded decisions "
                    "(canonical JSON inequality)",
                )
            )
        ticks_checked += 1

    manifest_tick_count = int(manifest.get("tick_count") or 0)
    if manifest_tick_count != len(ticks):
        mismatches.append(
            ReplayMismatch(
                -1,
                "tick_count_mismatch",
                f"manifest says {manifest_tick_count} tick(s), shadow log has "
                f"{len(ticks)}",
            )
        )

    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "session_date": session_date,
        "calendar_id": manifest.get("calendar_id"),
        "signal_version": signal_version,
        "gate_input_fingerprint": gate_fp,
        "ticks_checked": ticks_checked,
        "mismatches": [m.to_record() for m in mismatches],
        "ok": not mismatches,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(
    argv: Sequence[str] | None = None,
    *,
    tick_runner: TickRunner | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="intraday-replay-audit",
        description=(
            "Replay a recorded renquant105 shadow session against its frozen "
            "inputs and assert decision reproducibility (RFC #208 §6/§9)."
        ),
    )
    parser.add_argument("--manifest", required=True, help="session manifest JSON")
    parser.add_argument("--shadow-log", required=True, help="shadow decisions JSONL")
    parser.add_argument(
        "--data-manifest", default=None, help="data manifest JSON (real pipeline replay)"
    )
    parser.add_argument(
        "--artifact-manifest",
        default=None,
        help="artifact manifest JSON (real pipeline replay)",
    )
    parser.add_argument(
        "--strategy-config", default=None, help="strategy config JSON (real replay)"
    )
    parser.add_argument("--report-out", default=None, help="write the audit report JSON here")
    parser.add_argument("--json", action="store_true", help="print the report")
    args = parser.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    ticks = load_session_ticks(args.shadow_log, str(manifest.get("session_date")))

    if tick_runner is None:
        if not (args.strategy_config and args.data_manifest and args.artifact_manifest):
            print(
                "refusing to replay: --strategy-config, --data-manifest and "
                "--artifact-manifest are required for the real pipeline "
                "binding (fail closed)",
                flush=True,
            )
            return 2
        try:
            tick_runner = bind_pipeline_tick_runner(
                strategy_config=json.loads(
                    Path(args.strategy_config).read_text(encoding="utf-8")
                ),
                data_manifest=json.loads(
                    Path(args.data_manifest).read_text(encoding="utf-8")
                ),
                artifact_manifest=json.loads(
                    Path(args.artifact_manifest).read_text(encoding="utf-8")
                ),
            )
        except PipelineContractUnavailable as exc:
            print(f"refusing to replay: {exc}", flush=True)
            return 2

    report = replay_session(manifest=manifest, ticks=ticks, tick_runner=tick_runner)
    if args.report_out:
        out = Path(args.report_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, sort_keys=True, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(
            f"replay {'OK' if report['ok'] else 'FAILED'}: "
            f"{report['ticks_checked']} tick(s) checked, "
            f"{len(report['mismatches'])} mismatch(es)"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
