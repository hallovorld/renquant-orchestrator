"""Tests for the best-of-10d fallback SHADOW-LOGGER (#210). Promotes nothing."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from renquant_orchestrator.fallback_shadow_logger import (
    ProdModelState,
    ShadowDecision,
    append_shadow_decision,
    clears_oos_floor,
    run_shadow,
    shadow_decision,
)
from renquant_orchestrator.model_staging_registry import (
    INTEGRITY_FLOOR_KEYS,
    ModelStagingRegistry,
)

AS_OF = date(2026, 6, 30)  # injected clock
OLD_CUTOFF = date(2026, 5, 20)   # 41 days → breaches the 28d ceiling
FRESH_CUTOFF = date(2026, 6, 26)  # 4 days → within ceiling

REQUIRED_KEYS = {
    "as_of", "would_promote", "candidate", "reason",
    "failure_class", "selection_score", "would_NOT_because",
}


def _payload(
    artifact_id: str,
    *,
    trained: str,
    cutoff: str = "2026-06-24",
    created: str | None = None,
    verdict: str = "fail",
    failure_class: str | None = "timeout",
    oos_sharpe: float = 0.5,
    spy_sharpe: float = 0.3,
    net_return: float = 0.01,
    integrity_ok: bool = True,
) -> dict:
    if created is None:
        created = f"{trained}T12:00:00Z"
    integ = (
        {k: True for k in INTEGRITY_FLOOR_KEYS}
        if integrity_ok
        else {"loads": True}
    )
    return {
        "artifact_id": artifact_id,
        "model_family": "panel",
        "artifact_path": f"artifacts/{artifact_id}/model.pt",
        "artifact_created_at": created,
        "data_cutoff": cutoff,
        "trained_date": trained,
        "gate": {"verdict": verdict, "failure_class": failure_class, "observed_at": created},
        "quality": {
            "oos_sharpe": oos_sharpe,
            "spy_sharpe": spy_sharpe,
            "genuine_ic": 0.03,
            "net_return": net_return,
        },
        "integrity": integ,
    }


def _write(staging: Path, artifact_id: str, **kw) -> Path:
    staging.mkdir(parents=True, exist_ok=True)
    path = staging / f"{artifact_id}.staging.json"
    path.write_text(json.dumps(_payload(artifact_id, **kw)), encoding="utf-8")
    return path


def _breached(**kw) -> ProdModelState:
    return ProdModelState(data_cutoff=OLD_CUTOFF, as_of=AS_OF, **kw)


# ── would-promote (the happy path) ──────────────────────────────────────────
def test_would_promote_selects_best_score_among_infra_candidates(tmp_path):
    staging = tmp_path / "staging"
    # newest failed for infra (timeout); an older infra candidate scores higher.
    _write(staging, "newest", trained="2026-06-29", failure_class="timeout", oos_sharpe=0.5)
    _write(staging, "best", trained="2026-06-27", failure_class="config_path", oos_sharpe=0.7)
    _write(staging, "worse", trained="2026-06-26", failure_class="artifact_not_found", oos_sharpe=0.4)
    reg = ModelStagingRegistry.scan(staging)

    d = shadow_decision(reg, _breached())
    assert d.would_promote is True
    assert d.candidate == "best"           # best-of-recent picks the top score, not the newest
    assert d.selection_score == 0.7
    assert d.failure_class == "infra"
    assert d.would_NOT_because is None
    assert d.meta["pool"] == ["best", "newest", "worse"] or set(d.meta["pool"]) == {"best", "newest", "worse"}


def test_would_promote_tie_break_freshest_cutoff(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "n", trained="2026-06-29", failure_class="timeout", oos_sharpe=0.5)
    _write(staging, "tieold", trained="2026-06-28", cutoff="2026-06-20",
           failure_class="timeout", oos_sharpe=0.6)
    _write(staging, "tienew", trained="2026-06-28", cutoff="2026-06-24",
           failure_class="timeout", oos_sharpe=0.6)
    reg = ModelStagingRegistry.scan(staging)

    d = shadow_decision(reg, _breached())
    assert d.would_promote is True
    assert d.candidate == "tienew"  # equal score → freshest data cutoff wins


# ── fail-closed paths ───────────────────────────────────────────────────────
def test_prod_within_ceiling_no_fallback(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "c", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)

    d = shadow_decision(reg, ProdModelState(data_cutoff=FRESH_CUTOFF, as_of=AS_OF))
    assert d.would_promote is False
    assert d.would_NOT_because == "prod_model_within_ceiling"


def test_unknown_prod_cutoff_is_breached(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "c", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)

    prod = ProdModelState(data_cutoff=None, as_of=AS_OF)
    assert prod.breached is True
    d = shadow_decision(reg, prod)
    assert d.would_promote is True  # unknown cutoff proceeds; clean infra candidate exists


def test_slow_axis_off_sla_breaches_even_if_fast_fresh(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "c", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)
    prod = ProdModelState(data_cutoff=FRESH_CUTOFF, as_of=AS_OF, slow_axis_off_sla=True)
    assert prod.breached is True
    d = shadow_decision(reg, prod)
    assert d.would_promote is True


def test_newest_substantive_fails_closed(tmp_path):
    staging = tmp_path / "staging"
    # newest failed on substance → fail closed even though an older infra exists.
    _write(staging, "newest", trained="2026-06-29", verdict="fail", failure_class="sub_spy")
    _write(staging, "older_infra", trained="2026-06-27", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)

    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.failure_class == "substantive"
    assert d.would_NOT_because == "newest_retrain_failed_substantive_fail_closed"


def test_newest_placebo_fails_closed(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "newest", trained="2026-06-29", failure_class="placebo_contamination")
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.would_NOT_because == "newest_retrain_failed_placebo_fail_closed"


def test_newest_leakage_fails_closed(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "newest", trained="2026-06-29", failure_class="leakage_detected")
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.would_NOT_because == "newest_retrain_failed_leakage_fail_closed"


def test_newest_passed_gate_uses_normal_promote(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "passing", trained="2026-06-29", verdict="pass", failure_class=None)
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.would_NOT_because == "newest_retrain_passed_gate_use_normal_promote"


def test_no_candidate_within_window(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "stale", trained="2026-06-15", failure_class="timeout")  # age 15 > 10
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached(), window_days=10)
    assert d.would_promote is False
    assert d.would_NOT_because == "no_candidate_within_10d"


def test_integrity_floor_blocks_only_candidate(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "dirty", trained="2026-06-29", failure_class="timeout", integrity_ok=False)
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.would_NOT_because == "no_eligible_candidate_cleared_floors"
    assert d.meta["rejected"]["dirty"] == "integrity_floor_failed"


def test_oos_floor_not_cleared(tmp_path):
    staging = tmp_path / "staging"
    # infra + integrity ok, but OOS Sharpe below SPY → fails economic floor.
    _write(staging, "weak", trained="2026-06-29", failure_class="timeout",
           oos_sharpe=0.2, spy_sharpe=0.3)
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is False
    assert d.would_NOT_because == "no_eligible_candidate_cleared_floors"
    assert d.meta["rejected"]["weak"] == "oos_floor_not_cleared"


def test_integrity_dirty_excluded_but_clean_wins(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "dirty", trained="2026-06-29", failure_class="timeout", integrity_ok=False)
    _write(staging, "clean", trained="2026-06-28", failure_class="timeout", oos_sharpe=0.6)
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert d.would_promote is True
    assert d.candidate == "clean"
    assert d.meta["rejected"]["dirty"] == "integrity_floor_failed"


def test_clears_oos_floor_helper():
    assert clears_oos_floor({"oos_sharpe": 0.4, "spy_sharpe": 0.3}) is True
    assert clears_oos_floor({"oos_sharpe": 0.2, "spy_sharpe": 0.3}) is False
    assert clears_oos_floor({"oos_sharpe": 0.4, "net_return": -0.01}) is False
    assert clears_oos_floor({"oos_sharpe": 0.4}) is True  # no comparator → passes
    assert clears_oos_floor({}) is False


# ── JSONL logging: idempotent append + record schema ────────────────────────
def test_record_has_required_schema_keys(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "best", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)
    rec = shadow_decision(reg, _breached()).to_record()
    assert REQUIRED_KEYS <= set(rec)


def test_append_is_idempotent(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "best", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    log = tmp_path / "shadow" / "log.jsonl"

    assert append_shadow_decision(log, d) is True
    assert append_shadow_decision(log, d) is False  # same decision → no-op
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["as_of"] == "2026-06-30"
    assert rec["would_promote"] is True
    assert rec["candidate"] == "best"


def test_append_distinct_days_accumulate(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "best", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)
    log = tmp_path / "log.jsonl"

    d1 = shadow_decision(reg, ProdModelState(data_cutoff=OLD_CUTOFF, as_of=date(2026, 6, 30)))
    d2 = shadow_decision(reg, ProdModelState(data_cutoff=OLD_CUTOFF, as_of=date(2026, 7, 1)))
    assert append_shadow_decision(log, d1) is True
    assert append_shadow_decision(log, d2) is True
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2


# ── no-mutation invariant (observe-only) ────────────────────────────────────
def test_run_shadow_mutates_nothing_but_the_log(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "newest", trained="2026-06-29", failure_class="timeout", oos_sharpe=0.5)
    _write(staging, "best", trained="2026-06-27", failure_class="config_path", oos_sharpe=0.7)
    before = {p: p.read_bytes() for p in staging.rglob("*")}
    log = tmp_path / "out" / "shadow.jsonl"

    d = run_shadow(staging, _breached(), log_path=log)
    assert d.would_promote is True

    # staging dir byte-identical, no files added/removed there
    after = {p: p.read_bytes() for p in staging.rglob("*")}
    assert before == after
    # the ONLY thing written is the log file
    assert log.exists()
    written = list((tmp_path / "out").rglob("*"))
    assert written == [log]


def test_shadow_decision_is_a_frozen_value(tmp_path):
    staging = tmp_path / "staging"
    _write(staging, "best", trained="2026-06-29", failure_class="timeout")
    reg = ModelStagingRegistry.scan(staging)
    d = shadow_decision(reg, _breached())
    assert isinstance(d, ShadowDecision)
    import dataclasses

    with_pytest_raises = False
    try:
        d.would_promote = False  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        with_pytest_raises = True
    assert with_pytest_raises
