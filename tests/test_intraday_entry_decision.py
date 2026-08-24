"""S3-P4a: every guardrail must BIND, and every rejection must carry its name.

The capital-touching property under test is negative space: what the plan can
NEVER contain. Each guardrail gets a test that would fail if the check were
deleted, and the budget arithmetic is asserted to hold BY CONSTRUCTION (the
plan cannot exceed a budget the executor then has to catch).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from renquant_orchestrator.intraday_entry_decision import (
    EntryCandidate,
    Guardrails,
    decide_entries,
)

NOON = datetime(2026, 8, 25, 12, 0)


def _c(t="APH", *, batch=True, score=1.0, quote="fresh", mid=150.0, er=0.05):
    return EntryCandidate(ticker=t, batch_admitted=batch,
                          batch_expected_return=er, intraday_score=score,
                          quote_status=quote, intraday_mid=mid)


def _decide(cands, *, now=NOON, entries=0, notional=0.0, held=6,
            per_entry=700.0, env=None, g=None):
    return decide_entries(cands, now_et=now, entries_today=entries,
                          notional_today=notional, held_plus_pending=held,
                          per_entry_notional=per_entry, env=env or {},
                          guardrails=g)


class TestAdmissionIsBatchIntersectIntraday:
    def test_a_clean_candidate_is_admitted(self):
        plan = _decide([_c()])
        assert [i["ticker"] for i in plan.intents] == ["APH"]
        assert plan.intents[0]["limit_price"] == 150.0

    def test_intraday_can_veto_but_never_create(self):
        plan = _decide([_c("NEW", batch=False, score=9.9)])
        assert plan.intents == ()
        assert plan.rejections["NEW"] == "not_batch_admitted"

    def test_a_nonpositive_intraday_score_vetoes_a_batch_admission(self):
        plan = _decide([_c(score=-0.1)])
        assert plan.rejections["APH"] == "intraday_veto"

    def test_a_censored_quote_is_a_veto_not_a_passthrough(self):
        """Stale tape must fail closed — the realtime plane censors for exactly
        this consumer."""
        plan = _decide([_c(quote="stale")])
        assert plan.rejections["APH"] == "intraday_quote_censored"

    def test_a_missing_mid_cannot_become_a_limit_order(self):
        plan = _decide([_c(mid=None)])
        assert plan.rejections["APH"] == "no_usable_mid"


class TestEveryGuardrailBinds:
    def test_the_halt_switch_rejects_everything(self):
        plan = _decide([_c(), _c("NEM")], env={"RENQUANT_RQ105_HALT": "1"})
        assert plan.session_block == "halted" and plan.intents == ()
        assert set(plan.rejections.values()) == {"halted"}

    @pytest.mark.parametrize("hhmm", [(9, 30), (9, 44), (15, 45), (15, 59)])
    def test_the_session_edges_are_closed(self, hhmm):
        now = datetime(2026, 8, 25, *hhmm)
        assert _decide([_c()], now=now).session_block == "outside_entry_window"

    @pytest.mark.parametrize("hhmm", [(9, 45), (12, 0), (15, 44)])
    def test_the_middle_of_the_session_is_open(self, hhmm):
        assert _decide([_c()], now=datetime(2026, 8, 25, *hhmm)).session_block is None

    def test_the_daily_entry_budget_binds_across_the_plan(self):
        plan = _decide([_c("A"), _c("B", score=0.9), _c("C", score=0.8)])
        assert len(plan.intents) == 2                      # design default
        assert plan.rejections["C"] == "daily_entry_budget_exhausted"

    def test_the_notional_budget_holds_BY_CONSTRUCTION(self):
        plan = _decide([_c("A"), _c("B", score=0.9)], per_entry=900.0)
        assert len(plan.intents) == 1, "2x900 > $1,500 — the plan itself must stop"
        assert plan.rejections["B"] == "daily_notional_budget_exhausted"
        total = sum(i["notional_budget"] for i in plan.intents)
        assert total <= Guardrails().max_notional_per_day

    def test_prior_entries_today_consume_the_budget(self):
        plan = _decide([_c()], entries=2)
        assert plan.session_block == "daily_entry_budget_exhausted"

    def test_the_position_cap_is_SHARED_with_the_daily_book(self):
        """No bypass of max_concurrent_positions — the cap counts held plus
        pending, exactly the design's 'shared, no separate budget'."""
        plan = _decide([_c()], held=8)
        assert plan.session_block == "position_cap_full"

    def test_the_cap_also_binds_incrementally_inside_the_plan(self):
        plan = _decide([_c("A"), _c("B", score=0.9)], held=7)
        assert len(plan.intents) == 1
        assert plan.rejections["B"] == "position_cap_full"


class TestPlanShape:
    def test_priority_is_intraday_score_desc_then_ticker(self):
        # held=0: with the default book at 6, the SHARED position cap (8) had
        # correctly blocked the third intent — every prior fixture revision of
        # this test tripped a different real guardrail, which is the suite
        # working as designed.
        plan = _decide([_c("ZZ", score=2.0), _c("AA", score=2.0), _c("MM", score=3.0)],
                       held=0,
                       g=Guardrails(max_entries_per_day=3, max_notional_per_day=5_000.0))
        assert [i["ticker"] for i in plan.intents] == ["MM", "AA", "ZZ"]

    def test_every_nonentered_name_carries_exactly_one_reason(self):
        plan = _decide([_c("A"), _c("B", batch=False), _c("C", quote="stale"),
                        _c("D", score=0.5), _c("E", score=0.4)])
        entered = {i["ticker"] for i in plan.intents}
        for t in "ABCDE":
            assert (t in entered) != (t in plan.rejections), t

    def test_the_plan_records_which_guardrails_produced_it(self):
        g = Guardrails(max_entries_per_day=1)
        assert _decide([_c()], g=g).guardrails is g
