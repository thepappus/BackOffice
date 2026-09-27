from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from jpmarket.positions import PositionLedger, Side, total_realized
from jpmarket.products import Series

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
NK = Series.futures("NK225", "2026-06")
OPT_CALL_38000 = Series.option("NK225OP", "2026-06", "38000", "call")
OPT_CALL_39000 = Series.option("NK225OP", "2026-06", "39000", "call")


@pytest.fixture
def ledger() -> PositionLedger:
    return PositionLedger()


class TestShinkiDoesNotNet:
    def test_opening_opposite_side_creates_ryodate(self, ledger):
        """A sell designated 新規 against a long creates a short, not a close."""
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        ledger.open(NK, Side.SHORT, 1, "38100", D1)

        assert ledger.quantity(NK, Side.LONG) == 1
        assert ledger.quantity(NK, Side.SHORT) == 1
        assert ledger.is_ryodate(NK)
        assert ledger.net_quantity(NK) == 0
        # Net zero, but two positions are open and both consume margin.
        assert len(ledger.lots(series=NK)) == 2

    def test_gross_report_shows_both_legs(self, ledger):
        ledger.open(NK, Side.LONG, 2, "38000", D1)
        ledger.open(NK, Side.SHORT, 3, "38100", D1)
        rows = ledger.open_interest_report()
        assert (NK, Side.LONG, 2) in rows
        assert (NK, Side.SHORT, 3) in rows


class TestHensai:
    def test_close_reduces_the_named_side(self, ledger):
        ledger.open(NK, Side.LONG, 3, "38000", D1)
        results = ledger.close(NK, Side.LONG, 1, "38500", D2)

        assert len(results) == 1
        assert results[0].quantity == 1
        assert ledger.quantity(NK, Side.LONG) == 2

    def test_realized_pnl_measured_from_original_trade_price(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        ledger.set_book_price(NK, "37900")  # a day's mark intervened
        (res,) = ledger.close(NK, Side.LONG, 1, "38500", D2)

        # Cash on the closing day is measured from the book price...
        assert res.settlement_jpy == 600_000
        # ...but realised P&L, which drives tax, is from the trade price.
        assert res.realized_pnl_jpy == 500_000

    def test_short_side_signs(self, ledger):
        ledger.open(NK, Side.SHORT, 1, "38000", D1)
        (res,) = ledger.close(NK, Side.SHORT, 1, "37500", D2)
        assert res.realized_pnl_jpy == 500_000  # short gains when price falls

    def test_cannot_close_more_than_is_open(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        with pytest.raises(ValueError, match="only 1 open"):
            ledger.close(NK, Side.LONG, 2, "38500", D2)

    def test_cannot_close_a_side_that_is_not_open(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        with pytest.raises(ValueError, match="only 0 open"):
            ledger.close(NK, Side.SHORT, 1, "38500", D2)

    def test_fifo_and_lifo_pick_different_lots(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        ledger.open(NK, Side.LONG, 1, "38400", D1)

        fifo = PositionLedger()
        fifo.open(NK, Side.LONG, 1, "38000", D1)
        fifo.open(NK, Side.LONG, 1, "38400", D1)
        (f,) = fifo.close(NK, Side.LONG, 1, "38500", D2, method="fifo")
        assert f.open_trade_price == Decimal("38000")

        (l,) = ledger.close(NK, Side.LONG, 1, "38500", D2, method="lifo")
        assert l.open_trade_price == Decimal("38400")

    def test_specific_lot_designation(self, ledger):
        first = ledger.open(NK, Side.LONG, 1, "38000", D1)
        second = ledger.open(NK, Side.LONG, 1, "38400", D1)
        (res,) = ledger.close(NK, Side.LONG, 1, "38500", D2, lot_id=second.lot_id)
        assert res.lot_id == second.lot_id
        assert ledger.lots(series=NK)[0].lot_id == first.lot_id

    def test_close_spanning_two_lots(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        ledger.open(NK, Side.LONG, 2, "38100", D1)
        results = ledger.close(NK, Side.LONG, 3, "38500", D2)

        assert [r.quantity for r in results] == [1, 2]
        assert total_realized(results) == 500_000 + 2 * 400_000
        assert ledger.lots(series=NK) == []


class TestSeriesIdentity:
    def test_different_strikes_are_different_positions(self, ledger):
        ledger.open(OPT_CALL_38000, Side.LONG, 1, "420", D1)
        with pytest.raises(ValueError, match="only 0 open"):
            # Economically offsetting, but not the same series.
            ledger.close(OPT_CALL_39000, Side.LONG, 1, "150", D2)

    def test_option_series_requires_strike_and_type(self):
        with pytest.raises(ValueError, match="strike and option_type required"):
            Series(product="NK225OP", contract_month=NK.contract_month)

    def test_futures_series_rejects_strike(self):
        with pytest.raises(ValueError, match="must be None"):
            Series(
                product="NK225",
                contract_month=NK.contract_month,
                strike=Decimal("38000"),
            )


class TestBookPriceCarry:
    def test_set_book_price_leaves_trade_price_alone(self, ledger):
        ledger.open(NK, Side.LONG, 1, "38000", D1)
        ledger.set_book_price(NK, "38200")
        (lot,) = ledger.lots(series=NK)
        assert lot.book_price == Decimal("38200")
        assert lot.trade_price == Decimal("38000")

    def test_options_reject_book_price_rebasing(self, ledger):
        """Options are not marked to market, so their book price never moves."""
        ledger.open(OPT_CALL_38000, Side.LONG, 1, "420", D1)
        with pytest.raises(ValueError, match="not marked to market"):
            ledger.set_book_price(OPT_CALL_38000, "300")
