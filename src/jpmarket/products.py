"""Product specifications and series identity.

Contract specifications are public exchange information. The registry here
covers the index products used in the worked examples; it is meant to be
extended, and a caller can always construct a `ProductSpec` directly rather than
wait for the registry to include a product.

Series identity matters more than it looks. For futures a series is a product
plus a contract month. For options it is additionally a strike and a put/call
flag, because a 38,000 call and a 39,000 call are different positions that
cannot close each other even though they offset economically.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from .money import ProductSpec, Rounding, price


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


# Index products. Multipliers and ticks are public exchange specifications.
NK225 = ProductSpec(
    code="NK225",
    name="Nikkei 225 Futures",
    multiplier=1000,
    tick=Decimal("10"),
    price_dp=0,
)

NK225_MINI = ProductSpec(
    code="NK225M",
    name="Nikkei 225 mini",
    multiplier=100,
    tick=Decimal("5"),
    price_dp=0,
)

NK225_MICRO = ProductSpec(
    code="NK225MC",
    name="Nikkei 225 Micro Futures",
    multiplier=10,
    tick=Decimal("5"),
    price_dp=0,
)

TOPIX = ProductSpec(
    code="TOPIX",
    name="TOPIX Futures",
    multiplier=10_000,
    tick=Decimal("0.5"),
    price_dp=1,
)

TOPIX_MINI = ProductSpec(
    code="TOPIXM",
    name="mini-TOPIX Futures",
    multiplier=1_000,
    tick=Decimal("0.25"),
    price_dp=2,
)

NK225_OPTION = ProductSpec(
    code="NK225OP",
    name="Nikkei 225 Options",
    multiplier=1000,
    tick=Decimal("1"),
    price_dp=0,
    is_option=True,
)

REGISTRY: dict[str, ProductSpec] = {
    spec.code: spec
    for spec in (NK225, NK225_MINI, NK225_MICRO, TOPIX, TOPIX_MINI, NK225_OPTION)
}


def get_product(code: str) -> ProductSpec:
    try:
        return REGISTRY[code]
    except KeyError:
        raise KeyError(
            f"unknown product {code!r}; known: {', '.join(sorted(REGISTRY))}. "
            "Construct a ProductSpec directly for products not in the registry."
        ) from None


@dataclass(frozen=True, slots=True, order=True)
class ContractMonth:
    """A listed contract month, e.g. 2026-12."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"invalid month {self.month}")

    @classmethod
    def parse(cls, s: str) -> "ContractMonth":
        """Parse 'YYYY-MM'."""
        y, m = s.split("-")
        return cls(int(y), int(m))

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


@dataclass(frozen=True, slots=True)
class Series:
    """The identity of a tradable series.

    Two positions are in the same series, and can therefore close each other,
    only if every field matches.
    """

    product: str
    contract_month: ContractMonth
    strike: Optional[Decimal] = None
    option_type: Optional[OptionType] = None

    def __post_init__(self) -> None:
        spec = get_product(self.product)
        if spec.is_option:
            if self.strike is None or self.option_type is None:
                raise ValueError(
                    f"{self.product} is an option product: strike and option_type required"
                )
        else:
            if self.strike is not None or self.option_type is not None:
                raise ValueError(
                    f"{self.product} is not an option product: "
                    "strike and option_type must be None"
                )

    @property
    def spec(self) -> ProductSpec:
        return get_product(self.product)

    @property
    def is_option(self) -> bool:
        return self.spec.is_option

    @classmethod
    def futures(cls, product: str, contract_month: str) -> "Series":
        return cls(product=product, contract_month=ContractMonth.parse(contract_month))

    @classmethod
    def option(
        cls, product: str, contract_month: str, strike: str, option_type: str
    ) -> "Series":
        return cls(
            product=product,
            contract_month=ContractMonth.parse(contract_month),
            strike=price(strike),
            option_type=OptionType(option_type),
        )

    def __str__(self) -> str:
        if self.is_option:
            return (
                f"{self.product} {self.contract_month} "
                f"{self.strike} {self.option_type.value}"
            )
        return f"{self.product} {self.contract_month}"
