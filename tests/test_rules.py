"""Rule-transition boundary tests.

A rule change is only correctly implemented if the day before, the day of, and
the day after all produce the right answer. `all_transition_dates()` exists so
this check can be generated rather than remembered.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from jpmarket.rules import (
    MarginMethod,
    RuleSet,
    Timeline,
    all_transition_dates,
)

VAR_START = date(2023, 11, 6)
T2_START = date(2019, 7, 16)


class TestMarginMethodTransition:
    def test_span_before_var_on_and_after(self):
        assert RuleSet.at(VAR_START - timedelta(days=1)).margin_method is MarginMethod.SPAN
        assert RuleSet.at(VAR_START).margin_method is MarginMethod.VAR
        assert RuleSet.at(VAR_START + timedelta(days=1)).margin_method is MarginMethod.VAR

    def test_var_differentiates_side_and_month(self):
        """Under SPAN both sides and all months charged the same; HS-VaR does not."""
        assert RuleSet.at(VAR_START - timedelta(days=1)).margin_side_sensitive is False
        assert RuleSet.at(VAR_START).margin_side_sensitive is True

    def test_parameter_cadence_moves_from_weekly_to_daily(self):
        assert RuleSet.at(VAR_START - timedelta(days=1)).margin_param_cadence == "weekly"
        assert RuleSet.at(VAR_START).margin_param_cadence == "daily"


class TestSettlementCycleTransition:
    def test_t3_before_t2_on_and_after(self):
        assert RuleSet.at(T2_START - timedelta(days=1)).equity_settlement_days == 3
        assert RuleSet.at(T2_START).equity_settlement_days == 2
        assert RuleSet.at(date(2026, 6, 1)).equity_settlement_days == 2


class TestOffExchangePriceBand:
    def test_band_abolished_in_2005(self):
        assert RuleSet.at(date(2004, 1, 1)).off_exchange_price_band is True
        assert RuleSet.at(date(2026, 1, 1)).off_exchange_price_band is False


@pytest.mark.parametrize("transition", all_transition_dates(), ids=lambda d: d.isoformat())
def test_every_transition_resolves_on_all_three_boundary_days(transition: date):
    """Generated boundary coverage: no transition can be added without being tested."""
    for d in (transition - timedelta(days=1), transition, transition + timedelta(days=1)):
        rs = RuleSet.at(d)
        assert rs.as_of == d
        assert rs.margin_method in MarginMethod
        assert rs.equity_settlement_days in (2, 3)


def test_something_changes_at_every_listed_transition():
    for transition in all_transition_dates():
        before = RuleSet.at(transition - timedelta(days=1))
        on = RuleSet.at(transition)
        assert before != on, (
            f"{transition} is listed as a transition but nothing changes there"
        )


class TestTimelineMechanics:
    def test_rejects_unsorted_entries(self):
        with pytest.raises(ValueError, match="date-ascending"):
            Timeline("t", [(date(2020, 1, 1), "b"), (date(2019, 1, 1), "a")])

    def test_rejects_duplicate_dates(self):
        with pytest.raises(ValueError, match="duplicate"):
            Timeline("t", [(date(2020, 1, 1), "a"), (date(2020, 1, 1), "b")])

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="at least one entry"):
            Timeline("t", [])

    def test_lookup_before_first_entry_is_an_error_not_a_guess(self):
        tl = Timeline("t", [(date(2020, 1, 1), "a")])
        with pytest.raises(ValueError, match="no value in force"):
            tl.at(date(2019, 12, 31))
