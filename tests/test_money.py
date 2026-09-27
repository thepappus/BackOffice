from __future__ import annotations

from decimal import Decimal

import pytest

from jpmarket.money import ProductSpec, Rounding, price, to_yen
from jpmarket.products import NK225, TOPIX


class TestPriceCoercion:
    def test_accepts_str_and_decimal(self):
        assert price("38000") == Decimal(38000)
        assert price(Decimal("2750.5")) == Decimal("2750.5")
        assert price(38000) == Decimal(38000)

    def test_rejects_float(self):
        """Floats are rejected, not converted.

        Decimal(0.1) is not Decimal('0.1'), and a silently imprecise price is
        the root of most unreconcilable one-yen breaks.
        """
        with pytest.raises(TypeError, match="float prices are rejected"):
            price(2750.5)


class TestRounding:
    def test_half_up(self):
        assert to_yen(Decimal("0.5")) == 1
        assert to_yen(Decimal("1.5")) == 2
        assert to_yen(Decimal("-0.5")) == -1

    def test_truncate_rounds_toward_zero(self):
        assert to_yen(Decimal("0.9"), Rounding.TRUNCATE) == 0
        assert to_yen(Decimal("-0.9"), Rounding.TRUNCATE) == 0
        assert to_yen(Decimal("1.9"), Rounding.TRUNCATE) == 1


class TestProductSpec:
    def test_tick_validation(self):
        assert NK225.validate_price(Decimal("38010")) == Decimal("38010")
        with pytest.raises(ValueError, match="not a multiple of tick"):
            NK225.validate_price(Decimal("38005"))

    def test_decimal_place_validation(self):
        assert TOPIX.validate_price(Decimal("2750.5")) == Decimal("2750.5")
        with pytest.raises(ValueError, match="decimal places"):
            TOPIX.validate_price(Decimal("2750.55"))

    def test_negative_price_rejected(self):
        with pytest.raises(ValueError, match="negative price"):
            NK225.validate_price(Decimal("-1"))

    def test_move_to_yen_is_exact_for_index_products(self):
        # One tick on Nikkei 225 futures is 10 points x 1,000 = 10,000 yen.
        assert NK225.move_to_yen(Decimal("10"), 1) == 10_000
        # One tick on TOPIX futures is 0.5 x 10,000 = 5,000 yen.
        assert TOPIX.move_to_yen(Decimal("0.5"), 1) == 5_000

    def test_move_to_yen_is_signed(self):
        assert NK225.move_to_yen(Decimal("-100"), 2) == -200_000

    def test_notional(self):
        assert NK225.notional(Decimal("38000"), 1) == 38_000_000

    def test_fractional_yen_rounds_under_the_spec_policy(self):
        """A product whose multiplier can produce sub-yen amounts rounds under its
        own declared policy, not a global one."""
        odd = ProductSpec(
            code="ODD",
            name="Fractional test product",
            multiplier=1,
            tick=Decimal("0.01"),
            price_dp=2,
            rounding=Rounding.TRUNCATE,
        )
        assert odd.move_to_yen(Decimal("0.99"), 1) == 0
        half_up = ProductSpec(
            code="ODD2",
            name="Fractional test product",
            multiplier=1,
            tick=Decimal("0.01"),
            price_dp=2,
            rounding=Rounding.HALF_UP,
        )
        assert half_up.move_to_yen(Decimal("0.99"), 1) == 1
