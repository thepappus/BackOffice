"""Invariant property tests.

These are worth more than example-based tests because each one catches a whole
class of error rather than one case. The first is the important one: it validates
the entire futures mark-to-market chain in a single statement.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jpmarket.calendar import is_business_day, next_business_day
from jpmarket.money import Rounding, to_yen
from jpmarket.nearai import (
    CloseTrade,
    DailySettlement,
    FinalSettlement,
    OpenTrade,
    run_lifecycle,
)
from jpmarket.positions import PositionLedger, Side
from jpmarket.products import Series

# Nikkei 225 prices on a 10-point tick, in a plausible range.
TICKS = st.integers(min_value=3000, max_value=4500).map(lambda n: Decimal(n * 10))
SIDES = st.sampled_from([Side.LONG, Side.SHORT])
QUANTITIES = st.integers(min_value=1, max_value=20)


def _business_days(start: date, n: int) -> list[date]:
    days = [start if is_business_day(start) else next_business_day(start)]
    for _ in range(n - 1):
        days.append(next_business_day(days[-1]))
    return days


@given(
    side=SIDES,
    quantity=QUANTITIES,
    trade_price=TICKS,
    settlements=st.lists(TICKS, min_size=0, max_size=8),
    close_price=TICKS,
    settle_at_sq=st.booleans(),
)
@settings(max_examples=400, deadline=None)
def test_daily_marking_moves_money_without_changing_the_total(
    side, quantity, trade_price, settlements, close_price, settle_at_sq
):
    """THE invariant.

        sum(daily marks) + final settlement
            == (final price - trade price) * quantity * multiplier * side

    Daily mark-to-market changes *when* cash moves, never how much. If this holds
    for arbitrary price paths of arbitrary length, the reference-price selection,
    the 帳入値段 carry, the sign handling and the rounding are all consistent.
    """
    series = Series.futures("NK225", "2026-06")
    days = _business_days(date(2026, 6, 1), len(settlements) + 2)

    events = [OpenTrade(days[0], side, quantity, trade_price)]
    for day, px in zip(days[:-1], settlements):
        events.append(DailySettlement(day, px))

    # Settlement i falls on days[i], so the closing trade goes on the next
    # business day after the last settlement (or the open day, if there were none).
    final_day = next_business_day(days[len(settlements) - 1]) if settlements else days[0]

    if settle_at_sq:
        events.append(FinalSettlement(final_day, close_price))
    else:
        events.append(CloseTrade(final_day, side, quantity, close_price))

    run = run_lifecycle(series, events)

    expected = series.spec.move_to_yen(
        (close_price - trade_price) * side.sign, quantity
    )
    assert run.total_cash_jpy == expected
    assert run.total_realized_jpy == expected
    run.check_invariant()


@given(
    side=SIDES,
    quantity=QUANTITIES,
    trade_price=TICKS,
    settlements=st.lists(TICKS, min_size=1, max_size=6),
)
@settings(max_examples=200, deadline=None)
def test_book_price_equals_latest_settlement(side, quantity, trade_price, settlements):
    """After each mark, every open lot's 帳入値段 is the day's settlement price."""
    series = Series.futures("NK225", "2026-06")
    ledger = PositionLedger()
    days = _business_days(date(2026, 6, 1), len(settlements))

    events = [OpenTrade(days[0], side, quantity, trade_price)]
    events += [DailySettlement(d, px) for d, px in zip(days, settlements)]
    run_lifecycle(series, events, ledger=ledger)

    for lot in ledger.lots(series=series):
        assert lot.book_price == settlements[-1]
        # The original trade price is never overwritten — tax depends on it.
        assert lot.trade_price == trade_price


@given(
    opens=st.lists(
        st.tuples(SIDES, QUANTITIES, TICKS), min_size=1, max_size=6
    )
)
@settings(max_examples=300, deadline=None)
def test_gross_quantity_reconciles_after_any_open_sequence(opens):
    """新規 orders never net. Gross quantity per side is the sum of its opens."""
    series = Series.futures("NK225", "2026-06")
    ledger = PositionLedger()
    day = date(2026, 6, 1)

    for side, qty, px in opens:
        ledger.open(series, side, qty, px, day)

    for side in (Side.LONG, Side.SHORT):
        expected = sum(q for s, q, _ in opens if s is side)
        assert ledger.quantity(series, side) == expected

    # Gross report never nets the two legs away.
    reported = sum(q for _, _, q in ledger.open_interest_report())
    assert reported == sum(q for _, q, _ in opens)


@given(
    quantity=st.integers(min_value=2, max_value=30),
    trade_price=TICKS,
    settlement=TICKS,
    close_price=TICKS,
    first_tranche=st.integers(min_value=1, max_value=29),
)
@settings(max_examples=300, deadline=None)
def test_partial_closes_sum_to_the_whole(
    quantity, trade_price, settlement, close_price, first_tranche
):
    """Closing in two tranches realises the same total as closing at once."""
    assume(first_tranche < quantity)
    series = Series.futures("NK225", "2026-06")
    d1 = date(2026, 6, 1)
    d2 = next_business_day(d1)

    events_split = [
        OpenTrade(d1, Side.LONG, quantity, trade_price),
        DailySettlement(d1, settlement),
        CloseTrade(d2, Side.LONG, first_tranche, close_price),
        CloseTrade(d2, Side.LONG, quantity - first_tranche, close_price),
    ]
    events_whole = [
        OpenTrade(d1, Side.LONG, quantity, trade_price),
        DailySettlement(d1, settlement),
        CloseTrade(d2, Side.LONG, quantity, close_price),
    ]

    split = run_lifecycle(series, events_split)
    whole = run_lifecycle(series, events_whole)

    assert split.total_cash_jpy == whole.total_cash_jpy
    assert split.total_realized_jpy == whole.total_realized_jpy


@given(
    points=st.decimals(
        min_value=Decimal("-10000"),
        max_value=Decimal("10000"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
    quantity=QUANTITIES,
)
@settings(max_examples=200, deadline=None)
def test_sign_symmetry_of_yen_conversion(points, quantity):
    """Negating a price move negates the yen amount exactly.

    Catches rounding modes that are not symmetric about zero, which would make a
    long and a short in the same series fail to offset by one yen.
    """
    series = Series.futures("TOPIX", "2026-06")
    up = series.spec.move_to_yen(points, quantity)
    down = series.spec.move_to_yen(-points, quantity)
    assert up == -down


@given(
    amount=st.decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        places=3,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_truncation_never_moves_away_from_zero(amount):
    """TRUNCATE (切捨て) rounds toward zero, never away from it."""
    truncated = to_yen(amount, Rounding.TRUNCATE)
    assert abs(truncated) <= abs(amount)
