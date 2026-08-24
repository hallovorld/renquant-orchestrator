"""S3-P4a: every guardrail must BIND, and every rejection must carry its name.

The capital-touching property under test is negative space: what the plan can
NEVER contain. Each guardrail gets a test that would fail if the check were
deleted, and the budget arithmetic is asserted to hold BY CONSTRUCTION (the
plan cannot exceed a budget the executor then has to catch).
"""
from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone

import pytest

from renquant_orchestrator.intraday_entry_decision import (
    ET,
    EntryCandidate,
    Guardrails,
    InvalidDecisionInput,
    decide_entries,
)


def et(*args) -> datetime:
    """An AWARE America/New_York timestamp.

    `now_et` used to be ET by name only — a naive value was accepted and an
    aware UTC one was compared by wall clock with no conversion. Every helper
    here builds an explicitly-zoned value so the tests cannot re-encode the bug
    they exist to prevent.
    """
    return datetime(*args, tzinfo=ET)


NOON = et(2026, 8, 25, 12, 0)


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
        now = et(2026, 8, 25, *hhmm)
        assert _decide([_c()], now=now).session_block == "outside_entry_window"

    @pytest.mark.parametrize("hhmm", [(9, 45), (12, 0), (15, 44)])
    def test_the_middle_of_the_session_is_open(self, hhmm):
        assert _decide([_c()], now=et(2026, 8, 25, *hhmm)).session_block is None

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


# ===========================================================================
# THE INPUT CONTRACT (codex on #1038)
#
# Two kinds of bad input arrive here and they get opposite treatment, which is
# the design decision these tests pin:
#   * market data  (NaN score, unusable mid)  -> reject the NAME, keep going
#   * plumbing     (NaN size, bad guardrails) -> RAISE; there is no correct plan
# ===========================================================================

class TestNonFiniteMarketDataRejectsTheName:
    """`x <= 0.0` is False for NaN, so every one of these was ADMITTED."""

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_a_nonfinite_score_never_reaches_an_intent(self, bad):
        plan = _decide([_c("APH", score=bad)])
        assert plan.intents == ()
        assert plan.rejections["APH"] == "intraday_score_not_finite"

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_a_nonfinite_mid_never_becomes_a_limit_price(self, bad):
        plan = _decide([_c("APH", mid=bad)])
        assert plan.intents == ()
        assert plan.rejections["APH"] == "intraday_mid_not_finite"

    def test_a_nonfinite_expected_return_does_not_travel_downstream(self):
        plan = _decide([_c("APH", er=float("nan"))])
        assert plan.intents == ()
        assert plan.rejections["APH"] == "batch_expected_return_not_finite"

    def test_one_bad_tick_does_not_stop_the_good_names(self):
        """Rejecting the NAME rather than raising is the point: a NaN on one
        symbol is an ordinary event on a live tape."""
        plan = _decide([_c("AAA", score=float("nan")), _c("BBB")], per_entry=700.0)
        assert [i["ticker"] for i in plan.intents] == ["BBB"]
        assert plan.rejections["AAA"] == "intraday_score_not_finite"


class TestMalformedPlumbingRaises:
    """A NaN notional does not reject one name — it makes EVERY budget
    comparison False, so the plan looks guarded and is not."""

    @pytest.mark.parametrize("bad", [float("nan"), 0.0, -1.0, float("inf")])
    def test_per_entry_notional_must_be_finite_and_positive(self, bad):
        with pytest.raises(InvalidDecisionInput, match="per_entry_notional"):
            _decide([_c()], per_entry=bad)

    def test_a_nan_per_entry_notional_would_otherwise_defeat_the_budget(self):
        """Named separately because it is the exact exploit: `notional + nan >
        max` is False, so the daily notional guardrail never binds."""
        assert not (0.0 + float("nan") > 1_500.0), "premise of this test"
        with pytest.raises(InvalidDecisionInput):
            _decide([_c("A"), _c("B"), _c("C")], per_entry=float("nan"))

    @pytest.mark.parametrize("bad", [float("nan"), -1.0, float("inf")])
    def test_notional_today_must_be_finite_and_nonnegative(self, bad):
        with pytest.raises(InvalidDecisionInput, match="notional_today"):
            _decide([_c()], notional=bad)

    @pytest.mark.parametrize("field,bad", [("entries", -1), ("held", -1),
                                           ("entries", 1.5), ("held", True)])
    def test_counters_must_be_nonnegative_ints(self, field, bad):
        with pytest.raises(InvalidDecisionInput):
            _decide([_c()], **{field: bad})

    def test_a_negative_entry_count_would_otherwise_buy_extra_entries(self):
        """entries_today=-5 with max 2 means seven entries before the counter
        catches up."""
        with pytest.raises(InvalidDecisionInput, match="entries_today"):
            _decide([_c("A"), _c("B"), _c("C")], entries=-5)


class TestInvalidGuardrailsRaise:
    @pytest.mark.parametrize("kw", [
        {"max_entries_per_day": -1},
        {"max_notional_per_day": float("nan")},
        {"max_notional_per_day": -1.0},
        {"max_concurrent_positions": -1},
        {"no_entry_first_minutes": -5},
    ])
    def test_incoherent_limits_are_refused(self, kw):
        with pytest.raises(InvalidDecisionInput):
            _decide([_c()], g=Guardrails(**kw))

    def test_backwards_session_bounds_are_refused(self):
        with pytest.raises(InvalidDecisionInput, match="incoherent"):
            _decide([_c()], g=Guardrails(session_open=time(16, 0),
                                         session_close=time(9, 30)))

    def test_edges_that_consume_the_whole_session_are_refused(self):
        """A guardrail that blocks every tick is indistinguishable from a broken
        one, so it must not be silently accepted."""
        with pytest.raises(InvalidDecisionInput, match="whole"):
            _decide([_c()], g=Guardrails(no_entry_first_minutes=200,
                                         no_entry_last_minutes=200))


class TestIdentity:
    """`rejections` is keyed by ticker and each intent names one, so
    'exactly one outcome per name' is only true if names are unique."""

    def test_duplicate_tickers_cannot_produce_two_intents(self):
        plan = _decide([_c("APH"), _c("APH")], per_entry=700.0)
        assert plan.intents == (), "one position, two intents, double budget"
        assert plan.rejections["APH"] == "duplicate_ticker"

    def test_every_occurrence_is_rejected_not_deduplicated_to_a_winner(self):
        """Picking a winner would invent a rule the design does not state,
        inside a capital-adjacent path."""
        plan = _decide([_c("APH", score=9.0), _c("APH", score=1.0), _c("BBB")])
        assert [i["ticker"] for i in plan.intents] == ["BBB"]
        assert plan.rejections["APH"] == "duplicate_ticker"

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_identities_are_refused(self, blank):
        plan = _decide([_c(blank)])
        assert plan.intents == ()
        assert plan.rejections[blank] == "blank_ticker"

    def test_a_duplicate_does_not_overwrite_another_names_rejection(self):
        plan = _decide([_c("AAA", batch=False), _c("BBB"), _c("BBB")])
        assert plan.rejections["AAA"] == "not_batch_admitted"
        assert plan.rejections["BBB"] == "duplicate_ticker"


class TestTheClockIsRealET:
    """`now_et` was ET by name only."""

    def test_a_naive_timestamp_is_refused(self):
        with pytest.raises(InvalidDecisionInput, match="naive"):
            _decide([_c()], now=datetime(2026, 8, 25, 12, 0))

    def test_an_aware_utc_timestamp_is_CONVERTED_not_read_as_wall_clock(self):
        """14:00 UTC is 10:00 ET — inside the window. Read as wall-clock ET it
        is 14:00, also inside; so the decisive case is one where the two
        answers DIFFER."""
        # 13:00 UTC = 09:00 ET — before the open, so outside the window.
        # Read as wall clock it would be 13:00 ET, comfortably inside.
        plan = _decide([_c()], now=datetime(2026, 8, 25, 13, 0, tzinfo=timezone.utc))
        assert plan.session_block == "outside_entry_window", (
            "a UTC timestamp was compared by wall clock instead of converted")

    def test_the_same_instant_in_two_zones_decides_identically(self):
        instant_utc = datetime(2026, 8, 25, 16, 0, tzinfo=timezone.utc)   # 12:00 ET
        instant_et = instant_utc.astimezone(ET)
        instant_ist = instant_utc.astimezone(timezone(timedelta(hours=5, minutes=30)))
        blocks = {_decide([_c()], now=n).session_block
                  for n in (instant_utc, instant_et, instant_ist)}
        assert blocks == {None}, blocks

    def test_a_session_edge_is_evaluated_in_ET(self):
        # 13:44 UTC = 09:44 ET, one minute before open+15 -> still blocked.
        assert _decide([_c()], now=datetime(2026, 8, 25, 13, 44, tzinfo=timezone.utc)
                       ).session_block == "outside_entry_window"
        # 13:45 UTC = 09:45 ET -> the window opens.
        assert _decide([_c()], now=datetime(2026, 8, 25, 13, 45, tzinfo=timezone.utc)
                       ).session_block is None

    def test_a_non_datetime_is_refused(self):
        with pytest.raises(InvalidDecisionInput, match="must be a datetime"):
            _decide([_c()], now="2026-08-25T12:00:00-04:00")
