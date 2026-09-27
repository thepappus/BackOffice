"""Effective-dated rule resolution.

Every calculation in this library is parameterised by the date it applies to,
because the correct answer changes when the rules change. The margin method for
2022 is not the margin method for 2024. The equity settlement cycle for 2018 is
not the cycle for 2020.

This module is the single place those transitions are recorded. Adding a rule
change means adding a row to a timeline here, not editing calculation code.

Sources for each transition are cited inline. Where a date is a matter of public
record it is given; where a rule is firm-configurable it is a parameter, not a
constant.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Generic, Sequence, TypeVar

T = TypeVar("T")

# A date far enough in the past to act as the opening bound of any timeline.
DAWN = date(1949, 5, 16)  # TSE reopening


class Timeline(Generic[T]):
    """An effective-dated sequence of values.

    Each entry is (effective_from, value). Lookup returns the value in force on
    a given date. Entries must be in ascending date order.
    """

    __slots__ = ("_dates", "_values", "_name")

    def __init__(self, name: str, entries: Sequence[tuple[date, T]]) -> None:
        if not entries:
            raise ValueError(f"timeline {name!r} must have at least one entry")
        dates = [d for d, _ in entries]
        if dates != sorted(dates):
            raise ValueError(f"timeline {name!r} entries must be date-ascending")
        if len(set(dates)) != len(dates):
            raise ValueError(f"timeline {name!r} has duplicate effective dates")
        self._name = name
        self._dates = dates
        self._values = [v for _, v in entries]

    def at(self, on: date) -> T:
        idx = bisect_right(self._dates, on) - 1
        if idx < 0:
            raise ValueError(
                f"timeline {self._name!r} has no value in force on {on.isoformat()}; "
                f"earliest entry is {self._dates[0].isoformat()}"
            )
        return self._values[idx]

    def transitions(self) -> list[tuple[date, T]]:
        return list(zip(self._dates, self._values))


class MarginMethod(str, Enum):
    """Listed derivatives margin calculation method."""

    SPAN = "SPAN"
    VAR = "VaR"


class VarModel(str, Enum):
    """VaR sub-method. Index products use historical simulation; commodity
    products use an alternative simulation model."""

    HS = "HS-VaR"
    AS = "AS-VaR"


# JSCC moved listed futures and options margin from SPAN to VaR on 2023-11-06.
# https://www.jpx.co.jp/jscc/seisan/sakimono/shokokin_seido/VaR.html
MARGIN_METHOD = Timeline[MarginMethod](
    "margin_method",
    [
        (DAWN, MarginMethod.SPAN),
        (date(2023, 11, 6), MarginMethod.VAR),
    ],
)

# TSE cash equity settlement cycle. T+3 -> T+2 on 2019-07-16.
EQUITY_SETTLEMENT_DAYS = Timeline[int](
    "equity_settlement_days",
    [
        (DAWN, 3),
        (date(2019, 7, 16), 2),
    ],
)

# Frequency with which JSCC publishes margin parameters. Under SPAN they were
# weekly; under VaR they are published each business day and apply same-day.
MARGIN_PARAM_CADENCE = Timeline[str](
    "margin_param_cadence",
    [
        (DAWN, "weekly"),
        (date(2023, 11, 6), "daily"),
    ],
)

# Whether margin differs by side (sell vs buy) and by contract month.
# Under SPAN both sides and all months charged the same; HS-VaR differentiates.
MARGIN_SIDE_SENSITIVE = Timeline[bool](
    "margin_side_sensitive",
    [
        (DAWN, False),
        (date(2023, 11, 6), True),
    ],
)

# JSDA abolished the price band on off-exchange trading of listed shares.
# https://www.jsda.or.jp/about/public/bosyu/files/05020902.pdf
OFF_EXCHANGE_PRICE_BAND = Timeline[bool](
    "off_exchange_price_band",
    [
        (DAWN, True),
        (date(2005, 4, 1), False),
    ],
)


@dataclass(frozen=True, slots=True)
class RuleSet:
    """The rules in force on a given date.

    Resolve once at the top of a calculation and pass it down, rather than
    querying timelines from inside arithmetic.
    """

    as_of: date
    margin_method: MarginMethod
    margin_param_cadence: str
    margin_side_sensitive: bool
    equity_settlement_days: int
    off_exchange_price_band: bool

    @classmethod
    def at(cls, on: date) -> "RuleSet":
        return cls(
            as_of=on,
            margin_method=MARGIN_METHOD.at(on),
            margin_param_cadence=MARGIN_PARAM_CADENCE.at(on),
            margin_side_sensitive=MARGIN_SIDE_SENSITIVE.at(on),
            equity_settlement_days=EQUITY_SETTLEMENT_DAYS.at(on),
            off_exchange_price_band=OFF_EXCHANGE_PRICE_BAND.at(on),
        )


def all_transition_dates() -> list[date]:
    """Every date on which any rule in this module changes.

    Useful for generating boundary test cases: a correct implementation should
    be tested on the day before, the day of, and the day after each of these.
    """
    seen: set[date] = set()
    for tl in (
        MARGIN_METHOD,
        EQUITY_SETTLEMENT_DAYS,
        MARGIN_PARAM_CADENCE,
        MARGIN_SIDE_SENSITIVE,
        OFF_EXCHANGE_PRICE_BAND,
    ):
        for d, _ in tl.transitions():
            if d != DAWN:
                seen.add(d)
    return sorted(seen)
