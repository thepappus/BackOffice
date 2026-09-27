"""jpmarket-ref — open reference implementation of publicly documented Japanese
post-trade calculations.

See SPEC_BOUNDARY.md for what this library will and will not implement, and why.

Nothing here performs I/O, constructs a market message, or connects to anything.
Given positions, prices, parameters and a date, it produces numbers.
"""

from . import calendar, money, nearai, positions, products, rules
from .money import Rounding, price, to_yen
from .positions import PositionLedger, Side
from .products import ContractMonth, OptionType, Series
from .rules import RuleSet

__version__ = "0.1.0"

__all__ = [
    "ContractMonth",
    "OptionType",
    "PositionLedger",
    "Rounding",
    "RuleSet",
    "Series",
    "Side",
    "calendar",
    "money",
    "nearai",
    "positions",
    "price",
    "products",
    "rules",
    "to_yen",
]
