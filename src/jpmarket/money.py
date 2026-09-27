"""Money and price primitives.

Rules this module enforces:

1. **Yen amounts are integers.** There is no sub-yen settlement. A calculation
   that produces a fractional yen must round explicitly, at a named point, with
   a named policy.
2. **Prices are Decimal, never float.** Index option premiums, TOPIX prices and
   commodity prices all carry decimals; binary floating point will eventually
   produce a one-yen break that nobody can explain.
3. **Rounding is per-calculation, not global.** There is no module-level
   rounding mode to change. Each function that can produce a fraction takes its
   policy from the product spec or from an explicit argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from enum import Enum
from typing import Union

Numeric = Union[int, str, Decimal]


class Rounding(str, Enum):
    """Rounding policies used in Japanese settlement arithmetic.

    HALF_UP is the common default for value calculations. TRUNCATE (round toward
    zero) appears in fee and tax contexts where the rule says 切捨て.
    """

    HALF_UP = "half_up"
    TRUNCATE = "truncate"

    @property
    def decimal_mode(self) -> str:
        return {Rounding.HALF_UP: ROUND_HALF_UP, Rounding.TRUNCATE: ROUND_DOWN}[self]


def price(value: Numeric) -> Decimal:
    """Coerce a price to Decimal, rejecting float input.

    Floats are rejected rather than converted because `Decimal(0.1)` is not
    `Decimal("0.1")`, and a silently imprecise price is the root of most
    unreconcilable one-yen breaks.
    """
    if isinstance(value, float):
        raise TypeError(
            "float prices are rejected; pass a str or Decimal "
            f"(got {value!r}) — use price('{value}') if that literal is exact"
        )
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"not a valid price: {value!r}") from exc


def to_yen(amount: Decimal, rounding: Rounding = Rounding.HALF_UP) -> int:
    """Round a Decimal amount to whole yen under an explicit policy."""
    return int(amount.quantize(Decimal(1), rounding=rounding.decimal_mode))


@dataclass(frozen=True, slots=True)
class ProductSpec:
    """Contract specification for a listed product.

    `multiplier` converts a price move into yen: one point of price movement on
    one contract is worth `multiplier` yen.

    `price_dp` is the number of decimal places a valid price carries.
    `tick` is the minimum price increment.
    """

    code: str
    name: str
    multiplier: int
    tick: Decimal
    price_dp: int
    rounding: Rounding = Rounding.HALF_UP
    is_option: bool = False

    def validate_price(self, p: Decimal) -> Decimal:
        """Check a price is on a valid tick and has valid precision."""
        if p < 0:
            raise ValueError(f"{self.code}: negative price {p}")
        if -p.as_tuple().exponent > self.price_dp:
            raise ValueError(
                f"{self.code}: price {p} has more than {self.price_dp} decimal places"
            )
        if self.tick > 0 and (p % self.tick) != 0:
            raise ValueError(f"{self.code}: price {p} is not a multiple of tick {self.tick}")
        return p

    def notional(self, p: Decimal, quantity: int) -> int:
        """Yen value of `quantity` contracts at price `p`."""
        return to_yen(price(p) * self.multiplier * quantity, self.rounding)

    def move_to_yen(self, points: Decimal, quantity: int) -> int:
        """Yen value of a price move of `points` across `quantity` contracts.

        Signed: a negative move gives a negative amount.
        """
        return to_yen(points * self.multiplier * quantity, self.rounding)
