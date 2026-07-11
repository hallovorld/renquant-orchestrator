"""Tests for ``outage_monitor`` — the funnel_integrity/data_availability consumer.

All bundles are synthetic dicts/JSON files; the notifier is always an injected
poster (or ``--quiet``). No test touches ntfy, a broker, or production paths.
"""
from __future__ import annotations

import json

import pytest

from renquant_orchestrator import outage_monitor as mod


# --- synthetic blocks ---------------------------------------------------------

def outage_funnel_block():
    """The 2026-07-08 incident shape: admission collapse -> buy scan on ~0 tickers."""
    return {
        "schema": "funnel_integrity.v1",
        "date": "2026-07-08",
        "run_mode": "full",
        "verdict": "STRUCTURAL_BLOCK",
        "verdict_reason": (
            "zero buys with structural invariant(s) fired: universe_admission_collapse"
        ),
        "structural": True,
        "fired": [
            {
                "invariant": "universe_admission_collapse",
                "severity": "structural",
                "reason": "universe admission collapsed: 4/145 admitted, 133 staleness rejections",
                "evidence": {
                    "n_watchlist": 145,
                    "n_admitted": 4,
                    "n_universe_rejected": 141,
                    "n_staleness_rejections": 133,
                    "top_rejection_reasons": {
                        "stale_76d_limit_60": 133,
                        "no_artifact": 9,
                    },
                },
            }
        ],
        "invariants_evaluated": [
            "universe_admission_collapse", "single_gate_funnel_kill",
            "threshold_scale_mismatch", "fail_close_event",
            "wash_sale_mass_block", "zero_priced_candidates",
        ],
        "gate_kill_counts": {},
        "funnel": {
            "n_watchlist": 145, "n_admitted": 4, "n_universe_rejected": 141,
            "n_buy_scan_blocked": 0, "n_late_candidates": 0,
            "n_candidates_final": 0, "n_ranked": 0, "n_rotations": 0,
            "n_buy_orders": 0, "n_exits": 1, "buy_blocked": False,
            "bear_only": False, "skip_buys": False,
        },
        "error": None,
    }


def degraded_data_block():
    """Admission-coverage axis alarming under degrade_with_alarm (07-08 input side)."""
    return {
        "schema": "data_availability.v1",
        "date": "2026-07-08",
        "run_mode": "full",
        "verdict": "DEGRADED",
        "degraded": True,
        "blocked": False,
        "axes": {
            "admission_model_metadata": {
                "verdict": "violation",
                "policy": "degrade_with_alarm",
                "contract_declared": True,
                "present": True,
                "as_of": None,
                "age_days": 76,
                "coverage": 0.028,
                "n_have": 4,
                "n_expected": 145,
                "violations": ["coverage 0.028 < min_coverage 0.5"],
                "evidence": {},
                "error": None,
                "contract": {"min_coverage": 0.5},
            },
            "ohlcv_bars": {
                "verdict": "ok", "policy": "degrade_with_alarm",
                "contract_declared": True, "present": True, "as_of": "2026-07-08",
                "age_days": 0, "coverage": 1.0, "n_have": 145, "n_expected": 145,
                "violations": [], "evidence": {}, "error": None, "contract": {},
            },
        },
        "fired": [
            {
                "axis": "admission_model_metadata",
                "policy": "degrade_with_alarm",
                "reason": "coverage 0.028 < min_coverage 0.5",
                "evidence": {"n_have": 4, "n_expected": 145},
            }
        ],
        "axes_evaluated": ["admission_model_metadata", "ohlcv_bars"],
        "missing_contracts": [],
        "error": None,
    }


def clean_funnel_block(verdict="ECONOMIC_NO_TRADE", n_buys=0):
    return {
        "schema": "funnel_integrity.v1",
        "date": "2026-07-11",
        "run_mode": "full",
        "verdict": verdict,
        "verdict_reason": (
            f"{n_buys} buy order(s) emitted" if n_buys
            else "no invariant fired; no-buy is accounted for by economic/risk bars"
        ),
        "structural": False,
        "fired": [],
        "invariants_evaluated": ["universe_admission_collapse"],
        "gate_kill_counts": {"conviction": 3},
        "funnel": {
            "n_watchlist": 145, "n_admitted": 125, "n_universe_rejected": 20,
            "n_buy_scan_blocked": 3, "n_late_candidates": 8,
            "n_candidates_final": 5, "n_ranked": 5, "n_rotations": 0,
            "n_buy_orders": n_buys, "n_exits": 0, "buy_blocked": False,
            "bear_only": False, "skip_buys": False,
        },
        "error": None,
    }


def available_data_block():
    return {
        "schema": "data_availability.v1",
        "date": "2026-07-11",
        "run_mode": "full",
        "verdict": "AVAILABLE",
        "degraded": False,
        "blocked": False,
        "axes": {
            "ohlcv_bars": {
                "verdict": "ok", "policy": "degrade_with_alarm",
                "contract_declared": True, "present": True, "as_of": "2026-07-11",
                "age_days": 0, "coverage": 1.0, "n_have": 145, "n_expected": 145,
                "violations": [], "evidence": {}, "error": None, "contract": {},
            },
        },
        "fired": [],
        "axes_evaluated": ["ohlcv_bars"],
        "missing_contracts": [],
        "error": None,
    }


def bundle_with(funnel=None, data=None, **extra):
    bundle = {"run_id": "run-2026-07-08", **extra}
    if funnel is not None:
        bundle["funnel_integrity"] = funnel
    if data is not None:
        bundle["data_availability"] = data
    return bundle


class RecordingPoster:
    def __init__(self):
        self.calls = []

    def __call__(self, title, body, topic, *, priority=3, tags="chart"):
        self.calls.append(
            {"title": title, "body": body, "topic": topic,
             "priority": priority, "tags": tags}
        )


# --- the 07-08 outage shape -----------------------------------------------------

class TestOutageShape:
    def test_structural_block_maps_to_outage_tag(self):
        report = mod.build_outage_report(
            bundle_with(outage_funnel_block(), degraded_data_block())
        )
        assert report.title_tag == mod.TAG_OUTAGE
        assert report.title == "RENQUANT-104 OUTAGE SESSION-INTEGRITY 2026-07-08"
        assert report.as_of == "2026-07-08"
        assert report.run_id == "run-2026-07-08"

    def test_body_leads_with_universe_collapse_per_cause_counts(self):
        report = mod.build_outage_report(
            bundle_with(outage_funnel_block(), degraded_data_block())
        )
        # Truncation-proof: the collapse line with per-cause counts is line 1.
        assert report.body_lines[0] == (
            "universe collapse: 4/145 admitted; "
            "causes: stale_76d_limit_60=133, no_artifact=9"
        )
        assert "funnel: STRUCTURAL_BLOCK" in report.body

    def test_body_carries_data_axis_failure(self):
        report = mod.build_outage_report(
            bundle_with(outage_funnel_block(), degraded_data_block())
        )
        assert "data: DEGRADED" in report.body
        assert (
            "axis admission_model_metadata [degrade_with_alarm]: "
            "coverage 0.028 < min_coverage 0.5 (age=76d, coverage=0.028)"
        ) in report.body

    def test_summaries_expose_causes_and_axes(self):
        report = mod.build_outage_report(
            bundle_with(outage_funnel_block(), degraded_data_block())
        )
        assert report.funnel_summary["collapse_causes"] == {
            "stale_76d_limit_60": 133, "no_artifact": 9,
        }
        assert report.funnel_summary["fired"] == ["universe_admission_collapse"]
        assert report.data_summary["failed_axes"] == ["admission_model_metadata"]

    def test_outage_pages_at_max_priority(self):
        report = mod.build_outage_report(bundle_with(outage_funnel_block()))
        poster = RecordingPoster()
        fired = mod.emit_alert(report, topic="t", poster=poster)
        assert fired is True
        assert poster.calls[0]["priority"] == 5
        assert poster.calls[0]["tags"] == "rotating_light"
        assert poster.calls[0]["title"].startswith("RENQUANT-104 OUTAGE")


# --- clean sessions ---------------------------------------------------------------

class TestCleanSessions:
    def test_trade_session(self):
        report = mod.build_outage_report(
            bundle_with(clean_funnel_block("ECONOMIC_TRADE", n_buys=2),
                        available_data_block())
        )
        assert report.title_tag == mod.TAG_TRADE
        assert report.priority == 3
        assert "counts: watchlist=145 admitted=125 candidates=5 buys=2 exits=0" in report.body

    def test_economic_no_trade_session(self):
        report = mod.build_outage_report(
            bundle_with(clean_funnel_block(), available_data_block())
        )
        assert report.title_tag == mod.TAG_NO_TRADE
        # AVAILABLE contributes no body noise.
        assert "data:" not in report.body

    def test_degraded_funnel_maps_to_degraded(self):
        block = clean_funnel_block("DEGRADED", n_buys=1)
        block["fired"] = [{
            "invariant": "wash_sale_mass_block", "severity": "warn",
            "reason": "12 wash-sale blocks > p99", "evidence": {"count": 12},
        }]
        report = mod.build_outage_report(bundle_with(block))
        assert report.title_tag == mod.TAG_DEGRADED
        assert "fired[warn] wash_sale_mass_block: 12 wash-sale blocks > p99" in report.body

    def test_data_blocked_escalates_clean_funnel_to_outage(self):
        data = degraded_data_block()
        data["verdict"] = "BLOCKED"
        data["blocked"] = True
        data["axes"]["admission_model_metadata"]["policy"] = "fail_closed"
        data["fired"][0]["policy"] = "fail_closed"
        report = mod.build_outage_report(
            bundle_with(clean_funnel_block(), data)
        )
        assert report.title_tag == mod.TAG_OUTAGE


# --- tag combination ----------------------------------------------------------------

class TestWorstTag:
    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ((mod.TAG_TRADE, None), mod.TAG_TRADE),
            ((mod.TAG_TRADE, mod.TAG_DEGRADED), mod.TAG_DEGRADED),
            ((mod.TAG_NO_TRADE, mod.TAG_OUTAGE), mod.TAG_OUTAGE),
            ((mod.TAG_DEGRADED, mod.TAG_OUTAGE), mod.TAG_OUTAGE),
            ((None, None), None),
            ((mod.TAG_NO_TRADE, mod.TAG_TRADE), mod.TAG_NO_TRADE),
        ],
    )
    def test_worst_wins(self, tags, expected):
        assert mod.worst_tag(*tags) == expected


# --- missing blocks (bundle predates stamping / separate landing) -------------------

class TestMissingBlocks:
    def test_both_missing_yields_no_verdict_and_no_alert(self):
        report = mod.build_outage_report({"run_id": "r1"})
        assert report.title_tag is None
        assert report.title is None
        assert sorted(report.missing_blocks) == [
            "data_availability", "funnel_integrity",
        ]
        poster = RecordingPoster()
        assert mod.emit_alert(report, topic="t", poster=poster) is False
        assert poster.calls == []

    def test_counter_mirrors_surface_as_hint(self):
        report = mod.build_outage_report({
            "run_id": "r1",
            "counters": {
                "funnel_integrity_fired": 1,
                "funnel_integrity_structural": 1,
                "unrelated": 7,
            },
        })
        assert report.counter_hints == {
            "funnel_integrity_fired": 1, "funnel_integrity_structural": 1,
        }
        assert any("counters hint" in line for line in report.body_lines)

    def test_one_block_missing_is_noted_but_other_still_renders(self):
        report = mod.build_outage_report(bundle_with(outage_funnel_block()))
        assert report.missing_blocks == ["data_availability"]
        assert report.title_tag == mod.TAG_OUTAGE
        assert "block missing from run bundle: data_availability" in report.body

    def test_none_bundle_is_fail_soft(self):
        report = mod.build_outage_report(None)
        assert report.title_tag is None
        assert len(report.missing_blocks) == 2


# --- alert gating --------------------------------------------------------------------

class TestAlertGating:
    def test_quiet_never_posts(self):
        report = mod.build_outage_report(bundle_with(outage_funnel_block()))
        poster = RecordingPoster()
        assert mod.emit_alert(report, topic="t", quiet=True, poster=poster) is False
        assert poster.calls == []

    def test_only_alerts_silences_clean_sessions(self):
        clean = mod.build_outage_report(
            bundle_with(clean_funnel_block("ECONOMIC_TRADE", 1), available_data_block())
        )
        poster = RecordingPoster()
        assert mod.emit_alert(clean, topic="t", only_alerts=True, poster=poster) is False
        outage = mod.build_outage_report(bundle_with(outage_funnel_block()))
        assert mod.emit_alert(outage, topic="t", only_alerts=True, poster=poster) is True
        assert len(poster.calls) == 1

    def test_default_posts_all_four_tags(self):
        poster = RecordingPoster()
        for block, tag in [
            (outage_funnel_block(), mod.TAG_OUTAGE),
            (clean_funnel_block("ECONOMIC_NO_TRADE"), mod.TAG_NO_TRADE),
            (clean_funnel_block("ECONOMIC_TRADE", 1), mod.TAG_TRADE),
        ]:
            report = mod.build_outage_report(bundle_with(block))
            assert report.title_tag == tag
            assert mod.emit_alert(report, topic="t", poster=poster) is True
        assert len(poster.calls) == 3


# --- bundle discovery -----------------------------------------------------------------

class TestFindLatestBundle:
    def test_picks_newest_by_mtime(self, tmp_path):
        old = tmp_path / "2026-07-07" / "run_bundle.json"
        new = tmp_path / "2026-07-08" / "run_bundle.json"
        for i, p in enumerate([old, new]):
            p.parent.mkdir(parents=True)
            p.write_text("{}")
            import os
            os.utime(p, (1_000_000 + i, 1_000_000 + i))
        assert mod.find_latest_bundle(tmp_path) == new

    def test_missing_root_or_empty(self, tmp_path):
        assert mod.find_latest_bundle(tmp_path / "nope") is None
        assert mod.find_latest_bundle(tmp_path) is None


# --- CLI ---------------------------------------------------------------------------------

class TestCli:
    def _write_bundle(self, tmp_path, bundle):
        p = tmp_path / "run_bundle.json"
        p.write_text(json.dumps(bundle))
        return p

    def test_outage_bundle_exits_2_and_prints_payload(self, tmp_path, capsys):
        p = self._write_bundle(
            tmp_path, bundle_with(outage_funnel_block(), degraded_data_block())
        )
        rc = mod.main(["--run-bundle", str(p), "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["title_tag"] == "OUTAGE"
        assert payload["owner_repo"] == "renquant-orchestrator"
        assert payload["funnel_integrity"]["collapse_causes"]["stale_76d_limit_60"] == 133

    def test_degraded_exits_1(self, tmp_path):
        data = degraded_data_block()
        p = self._write_bundle(
            tmp_path, bundle_with(clean_funnel_block(), data)
        )
        assert mod.main(["--run-bundle", str(p), "--quiet"]) == 1

    def test_clean_exits_0(self, tmp_path):
        p = self._write_bundle(
            tmp_path, bundle_with(clean_funnel_block("ECONOMIC_TRADE", 1),
                                  available_data_block())
        )
        assert mod.main(["--run-bundle", str(p), "--quiet"]) == 0

    def test_require_blocks_exits_3_when_bundle_has_neither(self, tmp_path):
        p = self._write_bundle(tmp_path, {"run_id": "r1"})
        assert mod.main(["--run-bundle", str(p), "--quiet", "--require-blocks"]) == 3
        # without the flag the same bundle is fail-soft
        assert mod.main(["--run-bundle", str(p), "--quiet"]) == 0

    def test_unreadable_bundle_exits_3(self, tmp_path):
        assert mod.main(["--run-bundle", str(tmp_path / "missing.json"), "--quiet"]) == 3

    def test_bundle_dir_discovers_latest(self, tmp_path):
        import os
        old_dir = tmp_path / "a"; old_dir.mkdir()
        new_dir = tmp_path / "b"; new_dir.mkdir()
        old = old_dir / "run_bundle.json"
        old.write_text(json.dumps(bundle_with(clean_funnel_block("ECONOMIC_TRADE", 1))))
        new = new_dir / "run_bundle.json"
        new.write_text(json.dumps(bundle_with(outage_funnel_block())))
        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))
        assert mod.main(["--bundle-dir", str(tmp_path), "--quiet"]) == 2

    def test_empty_bundle_dir_exits_3(self, tmp_path):
        assert mod.main(["--bundle-dir", str(tmp_path), "--quiet"]) == 3
