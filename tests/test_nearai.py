from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from jpmarket.nearai import (
    CloseTrade,
    DailySettlement,
    FinalSettlement,
    MarkKind,
    OpenTrade,
    final_settlement,
    mark_to_market,
    run_lifecycle,
)
from jpmarket.positions import PositionLedger, Side
from jpmarket.products import Series

NK = Series.futures("NK225", "2026-06")
OPT = Series.option("NK225OP", "2026-06", "38000", "call")
D1, D2, D3 = date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)
SQ_DAY = date(2026, 6, 12)  # second Friday


class TestReferencePriceSelection:
    def test_open_day_references_the_trade_price(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        (mark,) = mark_to_market(led, NK, "38200", D1)

        assert mark.kind is MarkKind.OPEN_DAY
        assert mark.reference_price == Decimal("38000")
        assert mark.amount_jpy == 200_000

    def test_carried_references_the_previous_settlement(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        mark_to_market(led, NK, "38200", D1)
        (mark,) = mark_to_market(led, NK, "37900", D2)

        assert mark.kind is MarkKind.CARRIED
        assert mark.reference_price == Decimal("38200")
        assert mark.amount_jpy == -300_000

    def test_a_lot_opened_today_and_one_carried_are_marked_together(self):
        """Both use their own book price, so no special casing is needed."""
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        mark_to_market(led, NK, "38200", D1)
        led.open(NK, Side.LONG, 1, "38300", D2)

        marks = mark_to_market(led, NK, "38400", D2)
        kinds = {m.kind for m in marks}
        assert kinds == {MarkKind.CARRIED, MarkKind.OPEN_DAY}
        # Carried: 38400-38200 = +200,000. Opened today: 38400-38300 = +100,000.
        assert sum(m.amount_jpy for m in marks) == 300_000


class TestSigns:
    def test_short_gains_when_the_price_falls(self):
        led = PositionLedger()
        led.open(NK, Side.SHORT, 1, "38000", D1)
        (mark,) = mark_to_market(led, NK, "37500", D1)
        assert mark.amount_jpy == 500_000

    def test_long_and_short_at_the_same_price_offset_exactly(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        led.open(NK, Side.SHORT, 1, "38000", D1)
        marks = mark_to_market(led, NK, "39990", D1)
        assert sum(m.amount_jpy for m in marks) == 0


class TestFinalSettlement:
    def test_sq_references_the_previous_settlement(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        led.set_book_price(NK, "38250")
        (res,) = final_settlement(led, NK, "38500", SQ_DAY)

        assert res.settlement_jpy == 250_000  # 38500 - 38250
        assert res.realized_pnl_jpy == 500_000  # 38500 - 38000
        assert led.lots(series=NK) == []

    def test_sq_settles_both_legs_of_a_ryodate_position(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        led.open(NK, Side.SHORT, 1, "38100", D1)
        results = final_settlement(led, NK, "38500", SQ_DAY)

        assert len(results) == 2
        assert sum(r.realized_pnl_jpy for r in results) == 500_000 - 400_000
        assert led.lots(series=NK) == []

    def test_options_are_rejected(self):
        led = PositionLedger()
        led.open(OPT, Side.LONG, 1, "420", D1)
        with pytest.raises(ValueError, match="option lifecycle"):
            final_settlement(led, OPT, "38500", SQ_DAY)


class TestGuards:
    def test_options_are_never_marked_to_market(self):
        led = PositionLedger()
        led.open(OPT, Side.LONG, 1, "420", D1)
        with pytest.raises(ValueError, match="not marked to market"):
            mark_to_market(led, OPT, "300", D1)

    def test_non_business_day_is_rejected(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        saturday = date(2026, 6, 6)
        with pytest.raises(ValueError, match="not a business day"):
            mark_to_market(led, NK, "38200", saturday)

    def test_non_business_day_can_be_overridden_for_testing(self):
        led = PositionLedger()
        led.open(NK, Side.LONG, 1, "38000", D1)
        marks = mark_to_market(
            led, NK, "38200", date(2026, 6, 6), require_business_day=False
        )
        assert marks[0].amount_jpy == 200_000

    def test_empty_series_produces_no_marks(self):
        assert mark_to_market(PositionLedger(), NK, "38200", D1) == []


class TestLifecycleRunner:
    def test_the_three_day_example(self):
        run = run_lifecycle(
            NK,
            [
                OpenTrade(D1, Side.LONG, 1, Decimal("38000")),
                DailySettlement(D1, Decimal("38200")),
                DailySettlement(D2, Decimal("37900")),
                CloseTrade(D3, Side.LONG, 1, Decimal("38500")),
            ],
        )

        assert [m.amount_jpy for m in run.marks] == [200_000, -300_000]
        assert run.closes[0].settlement_jpy == 600_000
        assert run.total_cash_jpy == 500_000
        assert run.total_realized_jpy == 500_000
        run.check_invariant()

    def test_held_to_expiry(self):
        run = run_lifecycle(
            NK,
            [
                OpenTrade(D1, Side.LONG, 1, Decimal("38000")),
                DailySettlement(D1, Decimal("38250")),
                FinalSettlement(SQ_DAY, Decimal("38500")),
            ],
        )
        assert run.total_cash_jpy == 500_000
        run.check_invariant()

    def test_invariant_failure_is_reported_clearly(self):
        """An open position legitimately breaks the invariant, and says so."""
        run = run_lifecycle(
            NK,
            [
                OpenTrade(D1, Side.LONG, 1, Decimal("38000")),
                DailySettlement(D1, Decimal("38200")),
            ],
        )
        assert run.total_cash_jpy == 200_000
        assert run.total_realized_jpy == 0
        with pytest.raises(AssertionError, match="invariant violated"):
            run.check_invariant()
